"""T005 12월 손실 인식 권장 단위 테스트.

spec: .claude/queue/spec-T005.md
PREREG: PREREG-0008 §2.4
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sentinelq.tax.capital_gains import (
    TAX_YEAR_RULES_2026,
    TaxYearRules,
    TaxYearSummary,
)
from sentinelq.tax.loss_harvesting import (
    HoldingSnapshot,
    recommend_loss_harvest,
)

# ---- 픽스처 헬퍼 ----


def _summary(
    realized_gain: int | str,
    tax_year: int = 2025,
    rules: TaxYearRules = TAX_YEAR_RULES_2026,
) -> TaxYearSummary:
    """TaxYearSummary를 직접 조립 (T003 calculate_year 없이 단위 테스트 격리)."""
    net = Decimal(str(realized_gain))
    if net <= 0:
        deduction = Decimal("0")
        taxable = Decimal("0")
    else:
        deduction = min(net, rules.basic_deduction_krw)
        taxable = net - deduction
    from decimal import ROUND_DOWN

    raw_tax = taxable * rules.tax_rate
    tax = raw_tax.quantize(Decimal("1"), rounding=ROUND_DOWN)
    return TaxYearSummary(
        tax_year=tax_year,
        rules=rules,
        by_market=(),
        total_realized_gain_krw=net,
        deduction_applied_krw=deduction,
        taxable_base_krw=taxable,
        capital_gains_tax_krw=tax,
        sale_count=0,
    )


def _holding(
    ticker: str,
    quantity: int | str,
    avg_cost: int | str,
    current_price: int | str,
    market: str = "US",
) -> HoldingSnapshot:
    return HoldingSnapshot(
        ticker=ticker,
        market=market,
        quantity=Decimal(str(quantity)),
        avg_cost_krw=Decimal(str(avg_cost)),
        current_price_krw=Decimal(str(current_price)),
    )


DEC_15 = date(2025, 12, 15)
JUN_15 = date(2025, 6, 15)
DEC_31 = date(2025, 12, 31)
DEC_1 = date(2025, 12, 1)
DEC_30 = date(2025, 12, 30)


# ---- 권장 정확성 ----


def test_harvest_recommended_december_above_deduction():
    """AC1: 12월 + gain>250만 + 손실 종목 → is_harvest_recommended=True."""
    summary = _summary(10_000_000)
    holdings = [_holding("AAPL", 100, 50_000, 30_000)]  # 손실 -2,000,000
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.is_december_window is True
    assert result.is_harvest_recommended is True
    assert len(result.loss_candidates) == 1
    assert result.loss_candidates[0].unrealized_loss_krw == Decimal("-2000000")


def test_no_recommend_gain_below_deduction():
    """AC2: gain < 250만 → is_harvest_recommended=False (세금 이미 0)."""
    summary = _summary(2_000_000)
    holdings = [_holding("AAPL", 10, 50_000, 30_000)]
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.is_harvest_recommended is False
    assert result.current_tax_krw == Decimal("0")


def test_no_recommend_no_loss_candidates():
    """AC3: 손실 종목 없음 (전부 이익) → candidates 비어 있음, False."""
    summary = _summary(10_000_000)
    holdings = [_holding("AAPL", 10, 30_000, 50_000)]  # 이익
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.loss_candidates == ()
    assert result.is_harvest_recommended is False


def test_no_recommend_not_december():
    """AC4: 비 12월 날짜 → is_december_window=False, is_harvest_recommended=False."""
    summary = _summary(10_000_000)
    holdings = [_holding("AAPL", 100, 50_000, 30_000)]
    result = recommend_loss_harvest(summary, holdings, check_date=JUN_15)
    assert result.is_december_window is False
    assert result.is_harvest_recommended is False


# ---- 12월 윈도우 ----


def test_december_31_not_in_window():
    """AC5: 12월 31일 → is_december_window=False."""
    result = recommend_loss_harvest(_summary(10_000_000), [], check_date=DEC_31)
    assert result.is_december_window is False


def test_december_1_in_window():
    """12월 1일 → is_december_window=True."""
    result = recommend_loss_harvest(_summary(10_000_000), [], check_date=DEC_1)
    assert result.is_december_window is True


def test_december_30_in_window():
    """12월 30일 → is_december_window=True."""
    result = recommend_loss_harvest(_summary(10_000_000), [], check_date=DEC_30)
    assert result.is_december_window is True


# ---- 절세 계산 ----


def test_g4_scenario_saving_over_1m():
    """AC7/G4: gain=10,000,000, loss=-6,000,000 (12월) → saving ≥ 100만원.

    taxable_base = 10M - 2.5M = 7.5M
    offset = min(6M, 7.5M) = 6M
    saving = 6,000,000 * 0.22 = 1,320,000
    """
    summary = _summary(10_000_000)
    holdings = [_holding("TSLA", 100, 70_000, 10_000)]  # 손실 -6,000,000
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.estimated_max_saving_krw == Decimal("1320000")
    assert result.estimated_max_saving_krw >= Decimal("1000000")
    assert result.is_harvest_recommended is True


def test_max_saving_capped_at_taxable_base():
    """AC10: total_harvestable_loss > taxable_base → offset = taxable_base.

    taxable_base = 10M - 2.5M = 7.5M
    harvestable = 10M
    offset = min(10M, 7.5M) = 7.5M
    saving = 7,500,000 * 0.22 = 1,650,000
    """
    summary = _summary(10_000_000)
    holdings = [_holding("TSLA", 100, 110_000, 10_000)]  # 손실 -10,000,000
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.total_harvestable_loss_krw == Decimal("-10000000")
    assert result.loss_needed_to_zero_tax_krw == Decimal("7500000")
    assert result.estimated_max_saving_krw == Decimal("1650000")


def test_saving_round_down():
    """절세액 ROUND_DOWN: 소수점 발생 시 원 단위 절사.

    loss=-1,000,001, taxable_base=1,000,001
    offset=1,000,001, saving=1,000,001*0.22=220,000.22 -> ROUND_DOWN -> 220,000
    """
    summary = _summary(3_500_001)  # taxable = 3,500,001 - 2,500,000 = 1,000,001
    holdings = [_holding("X", 1, 1_000_001, 0)]  # loss = -1,000,001
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    expected = (Decimal("1000001") * Decimal("0.22")).to_integral_value(rounding="ROUND_DOWN")
    assert result.estimated_max_saving_krw == expected


# ---- 필터링·정렬 ----


def test_profit_holdings_excluded():
    """이익 종목은 candidates에서 완전 제외."""
    summary = _summary(10_000_000)
    holdings = [
        _holding("AAPL", 10, 30_000, 50_000),  # 이익
        _holding("TSLA", 10, 50_000, 30_000),  # 손실
    ]
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert len(result.loss_candidates) == 1
    assert result.loss_candidates[0].ticker == "TSLA"


def test_candidates_sorted_by_loss_descending():
    """AC6: 손실 큰 순 정렬 — unrealized_loss 오름차순 (더 음수가 앞)."""
    summary = _summary(20_000_000)
    holdings = [
        _holding("A", 1, 100_000, 90_000),  # 손실 -10,000
        _holding("B", 1, 100_000, 50_000),  # 손실 -50,000
        _holding("C", 1, 100_000, 70_000),  # 손실 -30,000
    ]
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    losses = [c.unrealized_loss_krw for c in result.loss_candidates]
    assert losses == sorted(losses)  # 오름차순 = 더 큰 손실이 앞
    assert result.loss_candidates[0].ticker == "B"  # 손실 -50,000 최대


# ---- 견고성 ----


def test_empty_holdings_no_crash():
    """AC8: 빈 holdings → candidates=(), crash 없음."""
    summary = _summary(10_000_000)
    result = recommend_loss_harvest(summary, [], check_date=DEC_15)
    assert result.loss_candidates == ()
    assert result.is_harvest_recommended is False
    assert result.total_harvestable_loss_krw == Decimal("0")
    assert result.estimated_max_saving_krw == Decimal("0")


def test_zero_quantity_holding_excluded():
    """AC9: 수량 0인 종목은 candidates 제외."""
    summary = _summary(10_000_000)
    holdings = [_holding("AAPL", 0, 50_000, 30_000)]  # 수량 0 손실
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.loss_candidates == ()


def test_check_date_none_uses_today():
    """check_date=None → date.today() 사용, 예외 없음."""
    summary = _summary(10_000_000)
    # date.today()가 어떤 날이든 result가 반환되어야 함
    result = recommend_loss_harvest(summary, [], check_date=None)
    assert isinstance(result.check_date, date)
    assert result.check_date == date.today()


def test_invariant_total_loss_nonpositive():
    """total_harvestable_loss_krw <= 0 invariant."""
    summary = _summary(10_000_000)
    holdings = [
        _holding("A", 10, 50_000, 30_000),  # 손실
        _holding("B", 10, 50_000, 30_000),  # 손실
    ]
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.total_harvestable_loss_krw <= Decimal("0")


def test_invariant_max_saving_nonnegative():
    """estimated_max_saving_krw >= 0 invariant (gain=음수여도)."""
    summary = _summary(-1_000_000)  # 양도차손
    holdings = [_holding("A", 10, 50_000, 30_000)]
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.estimated_max_saving_krw >= Decimal("0")


def test_breakeven_holding_excluded():
    """current_price == avg_cost (본전) 종목은 candidates 제외."""
    summary = _summary(10_000_000)
    holdings = [_holding("A", 10, 50_000, 50_000)]  # 손익=0
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    assert result.loss_candidates == ()


def test_result_tax_year_matches_summary():
    """LossHarvestingResult.tax_year = TaxYearSummary.tax_year."""
    summary = _summary(10_000_000, tax_year=2024)
    result = recommend_loss_harvest(summary, [], check_date=DEC_15)
    assert result.tax_year == 2024


def test_loss_needed_equals_taxable_base():
    """loss_needed_to_zero_tax_krw = TaxYearSummary.taxable_base_krw."""
    summary = _summary(8_000_000)
    result = recommend_loss_harvest(summary, [], check_date=DEC_15)
    assert result.loss_needed_to_zero_tax_krw == summary.taxable_base_krw


def test_individual_candidate_saving_calculation():
    """개별 HarvestCandidate.estimated_saving_krw = |loss| * 22% ROUND_DOWN."""
    summary = _summary(10_000_000)
    holdings = [_holding("NVDA", 1, 100_000, 55_555)]  # loss = -44,445
    result = recommend_loss_harvest(summary, holdings, check_date=DEC_15)
    cand = result.loss_candidates[0]
    expected = (Decimal("44445") * Decimal("0.22")).to_integral_value(rounding="ROUND_DOWN")
    assert cand.estimated_saving_krw == expected
    assert isinstance(cand.estimated_saving_krw, Decimal)
