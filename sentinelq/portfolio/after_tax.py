"""세후 수익률 계산기 (T014).

PREREG: PREREG-0009 §2.2
Mandate: 포트폴리오 세후 실질 수익률 계산 — 증권사 앱의 세전 수익률 공백 보완

세후 수익률 계산 방법:
  remaining_deduction = max(0, 250만 - 당해 실현 양도차익)
  unrealized_taxable  = max(0, 미실현 손익 - remaining_deduction)
  estimated_tax       = ROUND_DOWN(unrealized_taxable x 22%)
  after_tax_gain      = 미실현 손익 - estimated_tax
  after_tax_return_%  = after_tax_gain / cost_basis x 100

주의: estimated_tax는 오늘 전량 매도 시 예상 세금. 실제 세액은 매도 시점에 결정됨.
      당해 이미 실현한 손익은 TaxYearSummary에서 반영 (잔여 기본공제 계산).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from sentinelq.adapters.kis_history import HoldingRecord

BASIC_DEDUCTION = Decimal("2_500_000")
TAX_RATE = Decimal("0.22")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class AfterTaxPosition:
    """종목별 세후 손익 정보."""

    ticker: str
    name: str
    market: str
    quantity: int
    cost_basis_krw: Decimal
    current_value_krw: Decimal
    unrealized_gain_krw: Decimal
    unrealized_return_pct: Decimal  # 세전 수익률 (%)
    estimated_tax_krw: Decimal  # 예상 세금 (원화)
    after_tax_gain_krw: Decimal  # 세후 미실현 손익
    after_tax_return_pct: Decimal  # 세후 수익률 (%)


@dataclass(frozen=True)
class AfterTaxPortfolio:
    """포트폴리오 전체 세후 요약."""

    positions: tuple[AfterTaxPosition, ...]
    total_cost_krw: Decimal
    total_current_value_krw: Decimal
    total_unrealized_gain_krw: Decimal
    total_unrealized_return_pct: Decimal
    total_estimated_tax_krw: Decimal
    total_after_tax_gain_krw: Decimal
    total_after_tax_return_pct: Decimal
    realized_gain_ytd_krw: Decimal  # 당해 기 실현 손익 (기본공제 계산에 사용)
    remaining_deduction_krw: Decimal  # 잔여 기본공제


def _pct(gain: Decimal, basis: Decimal) -> Decimal:
    if not basis:
        return Decimal("0")
    return (gain / basis * _HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _estimated_tax(unrealized: Decimal, remaining_deduction: Decimal) -> Decimal:
    """미실현 손익에 대한 예상 세금 (ROUND_DOWN)."""
    taxable = max(Decimal("0"), unrealized - remaining_deduction)
    return (taxable * TAX_RATE).quantize(_ONE, rounding=ROUND_DOWN)


def calculate_after_tax(
    holdings: list[HoldingRecord],
    *,
    realized_gain_ytd_krw: Decimal = Decimal("0"),
) -> AfterTaxPortfolio:
    """보유 잔고 + 당해 실현 손익 → 세후 포트폴리오 요약.

    Parameters
    ----------
    holdings:
        KIS 잔고 조회 결과 (HoldingRecord 리스트).
    realized_gain_ytd_krw:
        당해 연도 이미 실현된 양도차익 합계 (TaxYearSummary.total_realized_gain_krw).
        기본공제 잔여액 계산에 사용.
    """
    remaining_deduction = max(Decimal("0"), BASIC_DEDUCTION - realized_gain_ytd_krw)

    # 잔여 기본공제를 종목별로 어떻게 배분할지:
    # 포트폴리오 전체 미실현 손익에 대해 통산 → 총 예상 세금 계산
    # 개별 종목은 각 미실현 손익 비율로 안분 (단순화)
    total_unrealized = sum((h.unrealized_gain_krw for h in holdings), Decimal("0"))
    total_estimated_tax = _estimated_tax(total_unrealized, remaining_deduction)

    positions: list[AfterTaxPosition] = []
    total_cost = Decimal("0")
    total_value = Decimal("0")

    for h in holdings:
        total_cost += h.cost_basis_krw
        total_value += h.current_value_krw

        # 종목별 세금 안분 (총 예상 세금 x 종목 미실현 비율)
        if total_unrealized > 0 and h.unrealized_gain_krw > 0:
            pos_tax = (total_estimated_tax * h.unrealized_gain_krw / total_unrealized).quantize(
                _ONE, rounding=ROUND_DOWN
            )
        else:
            pos_tax = Decimal("0")

        after_tax = h.unrealized_gain_krw - pos_tax
        positions.append(
            AfterTaxPosition(
                ticker=h.ticker,
                name=h.name,
                market=h.market,
                quantity=h.quantity,
                cost_basis_krw=h.cost_basis_krw,
                current_value_krw=h.current_value_krw,
                unrealized_gain_krw=h.unrealized_gain_krw,
                unrealized_return_pct=_pct(h.unrealized_gain_krw, h.cost_basis_krw),
                estimated_tax_krw=pos_tax,
                after_tax_gain_krw=after_tax,
                after_tax_return_pct=_pct(after_tax, h.cost_basis_krw),
            )
        )

    total_unrealized_gain = total_value - total_cost
    total_after_tax = total_unrealized_gain - total_estimated_tax

    return AfterTaxPortfolio(
        positions=tuple(positions),
        total_cost_krw=total_cost,
        total_current_value_krw=total_value,
        total_unrealized_gain_krw=total_unrealized_gain,
        total_unrealized_return_pct=_pct(total_unrealized_gain, total_cost),
        total_estimated_tax_krw=total_estimated_tax,
        total_after_tax_gain_krw=total_after_tax,
        total_after_tax_return_pct=_pct(total_after_tax, total_cost),
        realized_gain_ytd_krw=realized_gain_ytd_krw,
        remaining_deduction_krw=remaining_deduction,
    )
