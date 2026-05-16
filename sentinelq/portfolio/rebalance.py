"""패시브 리밸런싱 계산기 (T017).

PREREG: PREREG-0010 §2.1-2.4
Mandate: ETF 패시브 전략의 목표 배분 유지 보조 (ADR-0011 권고 실행)

NOT in scope: 시장 타이밍, 종목 선정, 알파 발견, 자동 주문 (ADR-0011·0012 종결)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from sentinelq.portfolio.after_tax import AfterTaxPortfolio

_ONE = Decimal("1")
_HUNDRED = Decimal("100")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class TargetAllocation:
    """시장별 목표 자산배분 (%)."""

    weights: dict[str, Decimal]

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if abs(total - _HUNDRED) > Decimal("0.01"):
            raise ValueError(f"목표 배분 합계가 100%이어야 합니다 (현재 {total}%)")

    @classmethod
    def from_dict(cls, d: dict[str, float | str | int]) -> TargetAllocation:
        """{"KR": 30, "US": 70} 형식으로 생성."""
        return cls(weights={k: Decimal(str(v)) for k, v in d.items()})


@dataclass(frozen=True)
class MarketAllocation:
    """시장별 현재 vs 목표 배분."""

    market: str
    target_pct: Decimal
    current_pct: Decimal
    current_value_krw: Decimal
    target_value_krw: Decimal
    drift_pct: Decimal  # current - target (양수 = 초과, 음수 = 부족)
    trade_amount_krw: Decimal  # 양수 = 매수 필요, 음수 = 매도 필요
    estimated_sell_tax_krw: Decimal  # 매도 필요 시 발생 추정 세금 (매수 시 0)


@dataclass(frozen=True)
class RebalancePlan:
    """리밸런싱 실행 계획."""

    total_portfolio_krw: Decimal
    allocations: tuple[MarketAllocation, ...]
    threshold_pct: Decimal
    is_rebalance_needed: bool
    total_sell_amount_krw: Decimal
    total_buy_amount_krw: Decimal
    total_estimated_sell_tax_krw: Decimal
    net_after_rebalance_sell_tax_krw: Decimal  # 총 자산 - 매도 세금 추정


def calculate_rebalance(
    portfolio: AfterTaxPortfolio,
    targets: TargetAllocation,
    *,
    threshold_pct: Decimal = Decimal("5"),
) -> RebalancePlan:
    """현재 포트폴리오 vs 목표 배분 → 리밸런싱 계획.

    Parameters
    ----------
    portfolio:
        AfterTaxPortfolio (calculate_after_tax 결과)
    targets:
        TargetAllocation (시장별 목표 비중 %)
    threshold_pct:
        리밸런싱 발동 임계값 (기본 5%): |drift| >= threshold_pct이면
        is_rebalance_needed = True
    """
    total = portfolio.total_current_value_krw

    # 시장별 현재 평가금액 + 예상 세금 집계
    by_market: dict[str, Decimal] = {}
    market_tax: dict[str, Decimal] = {}
    for pos in portfolio.positions:
        by_market[pos.market] = by_market.get(pos.market, _ZERO) + pos.current_value_krw
        market_tax[pos.market] = market_tax.get(pos.market, _ZERO) + pos.estimated_tax_krw

    all_markets = sorted(set(by_market) | set(targets.weights))

    allocations: list[MarketAllocation] = []
    is_rebalance_needed = False
    total_sell = _ZERO
    total_buy = _ZERO
    total_sell_tax = _ZERO

    for market in all_markets:
        current_value = by_market.get(market, _ZERO)
        target_pct = targets.weights.get(market, _ZERO)
        target_value = (
            (total * target_pct / _HUNDRED).quantize(_ONE, rounding=ROUND_DOWN) if total else _ZERO
        )

        current_pct = (
            (current_value / total * _HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            if total
            else _ZERO
        )
        drift_pct = current_pct - target_pct
        trade_amount = target_value - current_value  # 양수=매수, 음수=매도

        if total and abs(drift_pct) > threshold_pct:
            is_rebalance_needed = True

        # 매도 세금: 이 시장에서 팔아야 하는 비율만큼 포지션 세금 안분
        sell_tax = _ZERO
        if trade_amount < 0 and current_value:
            mkt_tax = market_tax.get(market, _ZERO)
            sell_ratio = abs(trade_amount) / current_value
            sell_tax = (mkt_tax * sell_ratio).quantize(_ONE, rounding=ROUND_DOWN)
            total_sell += abs(trade_amount)
            total_sell_tax += sell_tax
        elif trade_amount > 0:
            total_buy += trade_amount

        allocations.append(
            MarketAllocation(
                market=market,
                target_pct=target_pct,
                current_pct=current_pct,
                current_value_krw=current_value,
                target_value_krw=target_value,
                drift_pct=drift_pct,
                trade_amount_krw=trade_amount,
                estimated_sell_tax_krw=sell_tax,
            )
        )

    return RebalancePlan(
        total_portfolio_krw=total,
        allocations=tuple(allocations),
        threshold_pct=threshold_pct,
        is_rebalance_needed=is_rebalance_needed,
        total_sell_amount_krw=total_sell,
        total_buy_amount_krw=total_buy,
        total_estimated_sell_tax_krw=total_sell_tax,
        net_after_rebalance_sell_tax_krw=total - total_sell_tax,
    )
