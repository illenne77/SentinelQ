"""FIFO Tax Lot Tracker — KR NTS 양도세 lot 매칭 엔진 (Phase 3 T002).

spec: ``.claude/queue/spec-T002.md``
PREREG: ``docs/preregistration/PREREG-0008-tax-tool.md`` §4.1

본 모듈 책임:

* T001 ``Transaction`` 시퀀스를 입력받아 매도 한 건마다 어느 매수 lot이
  어떤 비율로 소비되었는지의 breakdown과 KRW 단위 실현손익을 산출한다.
* FIFO (선입선출) 매칭을 ``(market, ticker)`` 키 단위로 수행한다.
* 매수 수수료·세금은 취득가액에 가산, 매도 수수료·세금은 양도가액에서
  차감한다 (NTS 표준).
* USD 거래는 자기 거래일 ``fx_rate`` 로 KRW 환산한다 (취득·매도 각각).

비스코프 (T003 이후):

* 250만원 기본공제 · 22% 세율 · 국내해외 합산
* 배당소득 · 환차익 분리
* 12월 손실 인식 권장
* NTS 양식 출력

mandate 위반 금지 (ADR-0011·0012·0013): 알파·자동매매·시장 타이밍 코드 없음.
"""

from __future__ import annotations

import itertools
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sentinelq.adapters.kis_history import Transaction

# ---- 예외 ----


class TaxLotError(Exception):
    """tax_lots 모듈 공통 base 예외."""


class InsufficientLotsError(TaxLotError):
    """매도 수량이 누적 보유 lot 합보다 큼 (공매도)."""


class MissingFxRateError(TaxLotError):
    """USD 거래에 ``fx_rate`` 가 ``None``."""


# ---- 데이터 모델 ----


@dataclass(frozen=True)
class Lot:
    """단일 매수 lot. FIFO 큐의 원소."""

    lot_id: int
    market: str  # "KR" | "US"
    ticker: str
    acquired_date: date
    original_qty: int
    remaining_qty: int
    cost_per_share_krw: Decimal

    def with_remaining(self, new_remaining: int) -> Lot:
        """잔여 수량만 갱신한 새 인스턴스 (frozen 이라 교체)."""
        return Lot(
            lot_id=self.lot_id,
            market=self.market,
            ticker=self.ticker,
            acquired_date=self.acquired_date,
            original_qty=self.original_qty,
            remaining_qty=new_remaining,
            cost_per_share_krw=self.cost_per_share_krw,
        )


@dataclass(frozen=True)
class LotConsumption:
    """매도 한 건이 단일 BUY lot 한 개를 소비한 분량 (FIFO breakdown 한 줄)."""

    lot_id: int
    qty: int
    acq_cost_krw: Decimal
    sale_proceeds_krw: Decimal
    realized_gain_krw: Decimal
    acquired_date: date
    sell_date: date
    holding_days: int


@dataclass(frozen=True)
class SaleRealization:
    """매도 한 건의 종합 실현 (소비된 lot들의 합)."""

    ticker: str
    market: str
    sell_date: date
    total_qty: int
    total_acq_cost_krw: Decimal
    total_proceeds_krw: Decimal
    total_realized_gain_krw: Decimal
    consumptions: tuple[LotConsumption, ...]


# ---- 내부 헬퍼 ----


def _to_krw(amount: Decimal, currency: str, fx_rate: Decimal | None) -> Decimal:
    """단일 금액을 KRW로 환산. USD인데 fx_rate가 None이면 raise."""
    if currency == "KRW":
        return amount
    if fx_rate is None:
        raise MissingFxRateError("USD amount requires fx_rate")
    return amount * fx_rate


def _validate(tx: Transaction) -> None:
    """입력 검증 (모든 BUY/SELL 공통)."""
    if tx.quantity <= 0:
        raise ValueError(f"quantity must be > 0, got {tx.quantity}")
    if tx.market == "US" and tx.fx_rate is None:
        raise MissingFxRateError(f"US trade {tx.ticker} on {tx.trade_date} missing fx_rate")
    if tx.market == "KR" and tx.currency != "KRW":
        raise ValueError(f"KR market requires KRW currency, got {tx.currency} for {tx.ticker}")
    if tx.side not in ("BUY", "SELL"):
        raise ValueError(f"side must be 'BUY' or 'SELL', got {tx.side!r}")


# ---- Ledger ----


class TaxLotLedger:
    """FIFO lot 매칭 상태 객체.

    Usage
    -----
    >>> ledger = TaxLotLedger()
    >>> ledger.apply_all(transactions)
    >>> for r in ledger.realizations():
    ...     print(r.ticker, r.total_realized_gain_krw)
    """

    def __init__(self) -> None:
        self._lots: dict[tuple[str, str], deque[Lot]] = defaultdict(deque)
        self._realizations: list[SaleRealization] = []
        self._lot_id_counter = itertools.count(1)

    # ---- public API ----

    def apply(self, tx: Transaction) -> SaleRealization | None:
        """단일 거래 적용. BUY → None, SELL → SaleRealization 반환."""
        _validate(tx)
        key = (tx.market, tx.ticker)
        if tx.side == "BUY":
            self._apply_buy(tx, key)
            return None
        realization = self._apply_sell(tx, key)
        self._realizations.append(realization)
        return realization

    def apply_all(self, txs: Iterable[Transaction]) -> list[SaleRealization]:
        """거래 시퀀스를 순서대로 적용. SELL 결과만 모아 반환."""
        out: list[SaleRealization] = []
        for tx in txs:
            r = self.apply(tx)
            if r is not None:
                out.append(r)
        return out

    def realizations(self) -> list[SaleRealization]:
        """지금까지 누적된 모든 매도 실현 내역."""
        return list(self._realizations)

    def open_lots(self, market: str, ticker: str) -> list[Lot]:
        """특정 (market, ticker)의 잔여 lot 큐 사본."""
        return list(self._lots.get((market, ticker), ()))

    def open_lots_all(self) -> dict[tuple[str, str], list[Lot]]:
        """잔여가 있는 모든 (market, ticker)의 lot 큐 사본."""
        return {k: list(v) for k, v in self._lots.items() if v}

    # ---- 내부 구현 ----

    def _apply_buy(self, tx: Transaction, key: tuple[str, str]) -> None:
        fx = tx.fx_rate if tx.currency == "USD" else None
        gross = _to_krw(tx.price * Decimal(tx.quantity), tx.currency, fx)
        fee_krw = _to_krw(tx.fee, tx.currency, fx)
        tax_krw = _to_krw(tx.tax, tx.currency, fx)
        # 매수: 취득가액 += fee + tax (NTS 룰)
        total_cost = gross + fee_krw + tax_krw
        cost_per_share = total_cost / Decimal(tx.quantity)
        lot = Lot(
            lot_id=next(self._lot_id_counter),
            market=tx.market,
            ticker=tx.ticker,
            acquired_date=tx.trade_date,
            original_qty=tx.quantity,
            remaining_qty=tx.quantity,
            cost_per_share_krw=cost_per_share,
        )
        self._lots[key].append(lot)

    def _apply_sell(self, tx: Transaction, key: tuple[str, str]) -> SaleRealization:
        fx = tx.fx_rate if tx.currency == "USD" else None
        gross_proceeds = _to_krw(tx.price * Decimal(tx.quantity), tx.currency, fx)
        fee_krw = _to_krw(tx.fee, tx.currency, fx)
        tax_krw = _to_krw(tx.tax, tx.currency, fx)
        # 매도: 양도가액 -= fee + tax (NTS 룰)
        net_proceeds = gross_proceeds - fee_krw - tax_krw
        proceeds_per_share = net_proceeds / Decimal(tx.quantity)

        queue = self._lots[key]
        total_open = sum(lot.remaining_qty for lot in queue)
        if total_open < tx.quantity:
            raise InsufficientLotsError(
                f"SELL qty {tx.quantity} > open {total_open} for "
                f"{tx.market}/{tx.ticker} on {tx.trade_date}"
            )

        consumptions: list[LotConsumption] = []
        remaining = tx.quantity
        while remaining > 0:
            head = queue[0]
            take = min(head.remaining_qty, remaining)
            acq = head.cost_per_share_krw * Decimal(take)
            proc = proceeds_per_share * Decimal(take)
            gain = proc - acq
            consumptions.append(
                LotConsumption(
                    lot_id=head.lot_id,
                    qty=take,
                    acq_cost_krw=acq,
                    sale_proceeds_krw=proc,
                    realized_gain_krw=gain,
                    acquired_date=head.acquired_date,
                    sell_date=tx.trade_date,
                    holding_days=(tx.trade_date - head.acquired_date).days,
                )
            )
            new_rem = head.remaining_qty - take
            if new_rem == 0:
                queue.popleft()
            else:
                queue[0] = head.with_remaining(new_rem)
            remaining -= take

        total_acq = sum((c.acq_cost_krw for c in consumptions), Decimal(0))
        total_proc = sum((c.sale_proceeds_krw for c in consumptions), Decimal(0))
        return SaleRealization(
            ticker=tx.ticker,
            market=tx.market,
            sell_date=tx.trade_date,
            total_qty=tx.quantity,
            total_acq_cost_krw=total_acq,
            total_proceeds_krw=total_proc,
            total_realized_gain_krw=total_proc - total_acq,
            consumptions=tuple(consumptions),
        )


__all__ = [
    "InsufficientLotsError",
    "Lot",
    "LotConsumption",
    "MissingFxRateError",
    "SaleRealization",
    "TaxLotError",
    "TaxLotLedger",
]
