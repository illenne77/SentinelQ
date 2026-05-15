"""Tests for sentinelq.tax.capital_gains (T003).

spec: ``.claude/queue/spec-T003.md`` (E1~E26)
PREREG: PREREG-0008 §2.2

테스트 그룹:
1. 정확성 (NTS 룰)  — AC1~AC6
2. 견고성             — AC7 + 룰 해소
3. 라운딩·정밀도      — AC8
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from sentinelq.portfolio.tax_lots import SaleRealization
from sentinelq.tax import (
    DEFAULT_RULES,
    TAX_YEAR_RULES_2026,
    TaxYearRules,
    UnknownTaxYearError,
    calculate_all,
    calculate_year,
)

# ---- factory ----


def _sale(
    *,
    ticker: str = "AAPL",
    market: str = "US",
    sell_date: date,
    proceeds: int | str | Decimal,
    cost: int | str | Decimal,
    qty: int = 1,
) -> SaleRealization:
    """간이 SaleRealization 빌더 — 합산 필드만 채우고 consumptions 는 비움."""
    proceeds_d = Decimal(proceeds)
    cost_d = Decimal(cost)
    return SaleRealization(
        ticker=ticker,
        market=market,
        sell_date=sell_date,
        total_qty=qty,
        total_acq_cost_krw=cost_d,
        total_proceeds_krw=proceeds_d,
        total_realized_gain_krw=proceeds_d - cost_d,
        consumptions=(),
    )


# ============================================================================
# 1. 정확성 (NTS 룰)
# ============================================================================


def test_single_overseas_sale_above_deduction() -> None:
    """AC1: 해외주식 양도차익 500만 -> tax = (500만-250만)*0.22 = 55만."""
    sales = [
        _sale(
            ticker="AAPL",
            market="US",
            sell_date=date(2025, 6, 1),
            proceeds=10_000_000,
            cost=5_000_000,
        )
    ]
    s = calculate_year(sales, tax_year=2025)
    assert s.total_realized_gain_krw == Decimal("5000000")
    assert s.deduction_applied_krw == Decimal("2500000")
    assert s.taxable_base_krw == Decimal("2500000")
    assert s.capital_gains_tax_krw == Decimal("550000")
    assert s.sale_count == 1


def test_kr_us_combined_net_taxable() -> None:
    """AC2: 국내+해외 혼합 net 1,000만 -> (1,000만-250만)*0.22 = 165만."""
    sales = [
        _sale(
            ticker="005930",
            market="KR",
            sell_date=date(2025, 3, 1),
            proceeds=8_000_000,
            cost=4_000_000,
        ),  # +400만
        _sale(
            ticker="AAPL",
            market="US",
            sell_date=date(2025, 7, 1),
            proceeds=12_000_000,
            cost=6_000_000,
        ),  # +600만
    ]
    s = calculate_year(sales, tax_year=2025)
    assert s.total_realized_gain_krw == Decimal("10000000")
    assert s.taxable_base_krw == Decimal("7500000")
    assert s.capital_gains_tax_krw == Decimal("1650000")
    assert s.sale_count == 2
    # market breakdown 분리 노출
    by_market = {b.market: b for b in s.by_market}
    assert by_market["KR"].realized_gain_krw == Decimal("4000000")
    assert by_market["US"].realized_gain_krw == Decimal("6000000")


def test_net_below_deduction_no_tax() -> None:
    """AC3: net ≤ 250만 → tax=0, deduction_applied=net."""
    sales = [
        _sale(
            sell_date=date(2025, 5, 1),
            proceeds=3_000_000,
            cost=1_500_000,
        )  # +150만
    ]
    s = calculate_year(sales, tax_year=2025)
    assert s.total_realized_gain_krw == Decimal("1500000")
    assert s.deduction_applied_krw == Decimal("1500000")
    assert s.taxable_base_krw == Decimal("0")
    assert s.capital_gains_tax_krw == Decimal("0")


def test_net_negative_no_tax_no_carryforward() -> None:
    """AC4: 양도차손 net 음수 → tax=0, deduction_applied=0, 이월 X."""
    sales = [
        _sale(
            sell_date=date(2025, 8, 1),
            proceeds=2_000_000,
            cost=5_000_000,
        )  # -300만
    ]
    s = calculate_year(sales, tax_year=2025)
    assert s.total_realized_gain_krw == Decimal("-3000000")
    assert s.deduction_applied_krw == Decimal("0")
    assert s.taxable_base_krw == Decimal("0")
    assert s.capital_gains_tax_krw == Decimal("0")


def test_calculate_all_two_years_independent_no_carryforward() -> None:
    """AC5: 다년 (2024 손실, 2025 이익) → 각 연도 독립, 손실 이월 X."""
    sales = [
        _sale(
            sell_date=date(2024, 11, 1),
            proceeds=1_000_000,
            cost=8_000_000,
        ),  # 2024: -700만
        _sale(
            sell_date=date(2025, 6, 1),
            proceeds=10_000_000,
            cost=4_000_000,
        ),  # 2025: +600만
    ]
    summaries = calculate_all(sales)
    assert [s.tax_year for s in summaries] == [2024, 2025]
    s2024, s2025 = summaries
    assert s2024.total_realized_gain_krw == Decimal("-7000000")
    assert s2024.capital_gains_tax_krw == Decimal("0")
    # 2025 는 2024 의 700만 손실 영향 없이 (600만-250만)*0.22 = 77만
    assert s2025.total_realized_gain_krw == Decimal("6000000")
    assert s2025.taxable_base_krw == Decimal("3500000")
    assert s2025.capital_gains_tax_krw == Decimal("770000")


def test_by_market_sum_invariant() -> None:
    """AC6 (property): sum(by_market.realized_gain_krw) == total_realized_gain_krw."""
    sales = [
        _sale(
            ticker="005930",
            market="KR",
            sell_date=date(2025, 1, 5),
            proceeds=p,
            cost=c,
        )
        for p, c in [(5_000_000, 3_000_000), (2_000_000, 4_000_000)]
    ] + [
        _sale(
            ticker="AAPL",
            market="US",
            sell_date=date(2025, 9, 9),
            proceeds=p,
            cost=c,
        )
        for p, c in [(7_000_000, 6_500_000), (1_000_000, 1_200_000)]
    ]
    s = calculate_year(sales, tax_year=2025)
    assert sum((b.realized_gain_krw for b in s.by_market), Decimal("0")) == (
        s.total_realized_gain_krw
    )
    assert sum(b.sale_count for b in s.by_market) == s.sale_count


# ============================================================================
# 2. 견고성
# ============================================================================


def test_empty_input_returns_zero_summary() -> None:
    """AC7: 매도 0건 → 영 summary."""
    s = calculate_year([], tax_year=2025)
    assert s.tax_year == 2025
    assert s.sale_count == 0
    assert s.by_market == ()
    assert s.total_realized_gain_krw == Decimal("0")
    assert s.capital_gains_tax_krw == Decimal("0")


def test_calculate_year_filters_other_years() -> None:
    """다년 입력에서 단일 연도 추출 — 2024 매도가 2025 산출에 영향 X."""
    sales = [
        _sale(
            sell_date=date(2024, 12, 31),
            proceeds=10_000_000,
            cost=1_000_000,
        ),  # 2024 +900만 (필터됨)
        _sale(
            sell_date=date(2025, 1, 2),
            proceeds=4_000_000,
            cost=3_000_000,
        ),  # 2025 +100만
    ]
    s = calculate_year(sales, tax_year=2025)
    assert s.sale_count == 1
    assert s.total_realized_gain_krw == Decimal("1000000")
    assert s.capital_gains_tax_krw == Decimal("0")


def test_default_rules_lookup_unknown_year_raises() -> None:
    """등록 안 된 연도 + rules None → UnknownTaxYearError."""
    sales = [_sale(sell_date=date(2030, 1, 1), proceeds=10_000_000, cost=1_000_000)]
    with pytest.raises(UnknownTaxYearError):
        calculate_year(sales, tax_year=2030)


def test_external_rules_override_unknown_year() -> None:
    """외부 룰 주입 시 DEFAULT_RULES 미등록 연도도 계산 가능."""
    custom = TaxYearRules(
        basic_deduction_krw=Decimal("3000000"),
        tax_rate=Decimal("0.20"),
    )
    sales = [_sale(sell_date=date(2030, 5, 1), proceeds=10_000_000, cost=1_000_000)]
    s = calculate_year(sales, tax_year=2030, rules=custom)
    # net 900만 → 공제 300만 → 과세 600만 → 세금 600만 * 0.20 = 120만
    assert s.deduction_applied_krw == Decimal("3000000")
    assert s.capital_gains_tax_krw == Decimal("1200000")
    assert s.rules is custom


def test_calculate_all_empty_returns_empty_list() -> None:
    assert calculate_all([]) == []


def test_calculate_all_rules_by_year_override() -> None:
    """calculate_all 의 연도별 룰 override."""
    sales = [
        _sale(sell_date=date(2024, 6, 1), proceeds=10_000_000, cost=1_000_000),
        _sale(sell_date=date(2025, 6, 1), proceeds=10_000_000, cost=1_000_000),
    ]
    custom_2024 = TaxYearRules(
        basic_deduction_krw=Decimal("5000000"),
        tax_rate=Decimal("0.30"),
    )
    summaries = calculate_all(sales, rules_by_year={2024: custom_2024})
    s2024, s2025 = summaries
    assert s2024.rules is custom_2024
    assert s2025.rules is DEFAULT_RULES[2025]
    # 2024: net 900만, 공제 500만, base 400만, tax = 120만
    assert s2024.capital_gains_tax_krw == Decimal("1200000")
    # 2025: net 900만, 공제 250만, base 650만, tax = 143만
    assert s2025.capital_gains_tax_krw == Decimal("1430000")


def test_year_grouping_uses_sell_date() -> None:
    """연도 귀속 = sell_date.year (양도일 기준, NTS 표준)."""
    sales = [
        _sale(sell_date=date(2024, 12, 30), proceeds=5_000_000, cost=1_000_000),
        _sale(sell_date=date(2025, 1, 2), proceeds=5_000_000, cost=1_000_000),
    ]
    summaries = calculate_all(sales)
    assert [s.tax_year for s in summaries] == [2024, 2025]
    assert all(s.sale_count == 1 for s in summaries)


def test_breakdown_sale_count_matches() -> None:
    sales = [
        _sale(market="KR", sell_date=date(2025, 1, 1), proceeds=1, cost=0),
        _sale(market="KR", sell_date=date(2025, 2, 1), proceeds=1, cost=0),
        _sale(market="US", sell_date=date(2025, 3, 1), proceeds=1, cost=0),
    ]
    s = calculate_year(sales, tax_year=2025)
    by_market = {b.market: b for b in s.by_market}
    assert by_market["KR"].sale_count == 2
    assert by_market["US"].sale_count == 1


# ============================================================================
# 3. 라운딩·정밀도
# ============================================================================


def test_round_down_applied_to_final_tax() -> None:
    """소수가 남는 raw_tax 는 ROUND_DOWN 절사."""
    # net = 250만 + 1,234,567 -> base 1234567 * 0.22 = 271604.74 -> 271604
    sales = [
        _sale(
            sell_date=date(2025, 6, 1),
            proceeds=Decimal("3734567"),
            cost=Decimal("0"),
        )
    ]
    s = calculate_year(sales, tax_year=2025)
    assert s.taxable_base_krw == Decimal("1234567")
    assert s.capital_gains_tax_krw == Decimal("271604")


def test_decimal_only_no_float_drift() -> None:
    """누적 소수점 입력에도 0 drift (Decimal-only)."""
    sales = [
        _sale(
            sell_date=date(2025, i, 1),
            proceeds=Decimal("1234567.89"),
            cost=Decimal("1000000.01"),
        )
        for i in range(1, 11)  # 10건
    ]
    # 건당 234567.88, 10건 = 2,345,678.8 — 250만 미만 → tax 0
    s = calculate_year(sales, tax_year=2025)
    assert s.total_realized_gain_krw == Decimal("2345678.80")
    assert s.capital_gains_tax_krw == Decimal("0")


def test_tax_year_rules_2026_constants() -> None:
    """spec 명시 상수 박제 검증."""
    assert TAX_YEAR_RULES_2026.basic_deduction_krw == Decimal("2500000")
    assert TAX_YEAR_RULES_2026.tax_rate == Decimal("0.22")
    assert DEFAULT_RULES[2025] is TAX_YEAR_RULES_2026
