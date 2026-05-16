"""세후 수익률 계산기 단위 테스트 (T014).

Coverage target: sentinelq/portfolio/after_tax.py >= 90%
PREREG: PREREG-0009 §2.2
"""

from __future__ import annotations

from decimal import Decimal

from sentinelq.adapters.kis_history import HoldingRecord
from sentinelq.portfolio.after_tax import (
    calculate_after_tax,
)


def _holding(
    ticker: str,
    *,
    market: str = "US",
    qty: int = 100,
    cost_krw: int = 10_000_000,
    value_krw: int = 13_000_000,
) -> HoldingRecord:
    unrealized = Decimal(value_krw - cost_krw)
    return HoldingRecord(
        ticker=ticker,
        name=ticker,
        market=market,  # type: ignore[arg-type]
        quantity=qty,
        avg_price_krw=Decimal(cost_krw) / qty,
        cost_basis_krw=Decimal(cost_krw),
        current_price_krw=Decimal(value_krw) / qty,
        current_value_krw=Decimal(value_krw),
        unrealized_gain_krw=unrealized,
        currency="USD" if market == "US" else "KRW",  # type: ignore[arg-type]
    )


# ── 기본 동작 ──────────────────────────────────────────────────


class TestCalculateAfterTax:
    def test_empty_holdings(self):
        result = calculate_after_tax([])
        assert result.total_cost_krw == Decimal("0")
        assert result.total_after_tax_return_pct == Decimal("0")

    def test_no_realized_gain_full_deduction_available(self):
        # 미실현 = 1,500,000원 < 250만원 기본공제 → 세금 0
        h = _holding("AAPL", cost_krw=10_000_000, value_krw=11_500_000)
        result = calculate_after_tax([h])
        assert result.total_estimated_tax_krw == Decimal("0")
        assert result.total_after_tax_gain_krw == Decimal("1_500_000")
        assert result.remaining_deduction_krw == Decimal("2_500_000")

    def test_unrealized_exceeds_deduction(self):
        # 미실현 5,000,000원 - 공제 2,500,000원 = 과세 2,500,000원 x 22% = 550,000원
        h = _holding("NVDA", cost_krw=10_000_000, value_krw=15_000_000)
        result = calculate_after_tax([h])
        assert result.total_estimated_tax_krw == Decimal("550_000")
        assert result.total_after_tax_gain_krw == Decimal("4_450_000")

    def test_realized_gain_reduces_deduction(self):
        # 기 실현 2,000,000원 → 잔여공제 500,000원
        # 미실현 2,000,000원 - 잔여공제 500,000원 = 과세 1,500,000원 x 22% = 330,000원
        h = _holding("TSLA", cost_krw=10_000_000, value_krw=12_000_000)
        result = calculate_after_tax([h], realized_gain_ytd_krw=Decimal("2_000_000"))
        assert result.remaining_deduction_krw == Decimal("500_000")
        assert result.total_estimated_tax_krw == Decimal("330_000")

    def test_realized_exceeds_deduction(self):
        # 기 실현 3,000,000원 → 잔여공제 0
        # 미실현 1,000,000원 전액 과세 x 22% = 220,000원
        h = _holding("AMZN", cost_krw=10_000_000, value_krw=11_000_000)
        result = calculate_after_tax([h], realized_gain_ytd_krw=Decimal("3_000_000"))
        assert result.remaining_deduction_krw == Decimal("0")
        assert result.total_estimated_tax_krw == Decimal("220_000")

    def test_multiple_holdings_tax_apportioned(self):
        h1 = _holding("AAPL", cost_krw=5_000_000, value_krw=8_000_000)  # gain 3M
        h2 = _holding("NVDA", cost_krw=5_000_000, value_krw=9_000_000)  # gain 4M
        result = calculate_after_tax([h1, h2])
        # total unrealized = 7M, deduction = 2.5M → taxable = 4.5M x 22% = 990,000
        assert result.total_estimated_tax_krw == Decimal("990_000")
        assert len(result.positions) == 2

    def test_loss_position_no_tax(self):
        h = _holding("LOSS", cost_krw=10_000_000, value_krw=8_000_000)
        result = calculate_after_tax([h])
        assert result.total_estimated_tax_krw == Decimal("0")
        assert result.total_unrealized_gain_krw == Decimal("-2_000_000")
        assert result.total_after_tax_gain_krw == Decimal("-2_000_000")

    def test_return_pct_calculation(self):
        h = _holding("X", cost_krw=10_000_000, value_krw=11_000_000)  # +10% 세전
        result = calculate_after_tax([h])
        # 세금: (1M - 2.5M) → 0원. 세후수익률 = 10%
        assert result.total_unrealized_return_pct == Decimal("10.00")
        assert result.total_after_tax_return_pct == Decimal("10.00")

    def test_after_tax_return_lower_than_pretax(self):
        # 충분히 큰 gain → 세금 발생 → 세후 < 세전
        h = _holding("BIG", cost_krw=10_000_000, value_krw=20_000_000)  # gain 10M
        result = calculate_after_tax([h])
        assert result.total_after_tax_return_pct < result.total_unrealized_return_pct

    def test_zero_cost_basis_no_pct_error(self):
        from sentinelq.portfolio.after_tax import calculate_after_tax as calc

        result = calc([], realized_gain_ytd_krw=Decimal("0"))
        assert result.total_after_tax_return_pct == Decimal("0")

    def test_portfolio_totals_match_sum_of_positions(self):
        h1 = _holding("A", cost_krw=5_000_000, value_krw=6_000_000)
        h2 = _holding("B", cost_krw=4_000_000, value_krw=4_500_000)
        result = calculate_after_tax([h1, h2])
        assert result.total_cost_krw == Decimal("9_000_000")
        assert result.total_current_value_krw == Decimal("10_500_000")
        assert result.total_unrealized_gain_krw == Decimal("1_500_000")

    def test_remaining_deduction_stored_in_result(self):
        result = calculate_after_tax([], realized_gain_ytd_krw=Decimal("1_000_000"))
        assert result.realized_gain_ytd_krw == Decimal("1_000_000")
        assert result.remaining_deduction_krw == Decimal("1_500_000")

    def test_domestic_holding_market_kr(self):
        h = _holding("005930", market="KR", cost_krw=5_000_000, value_krw=5_500_000)
        result = calculate_after_tax([h])
        assert result.positions[0].market == "KR"

    def test_position_fields_populated(self):
        h = _holding("MSFT", cost_krw=10_000_000, value_krw=12_000_000)
        result = calculate_after_tax([h])
        pos = result.positions[0]
        assert pos.ticker == "MSFT"
        assert pos.quantity == 100
        assert pos.cost_basis_krw == Decimal("10_000_000")
        assert pos.current_value_krw == Decimal("12_000_000")
