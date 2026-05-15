"""tests/test_nts_form.py — NTS 양도세 신고서 양식 단위 테스트.

Spec: .claude/queue/spec-T006.md  AC1~AC14 + E1~E28
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sentinelq.portfolio.tax_lots import SaleRealization
from sentinelq.reports.nts_form import (
    build_nts_form,
    export_detail_csv,
    export_summary_csv,
)
from sentinelq.tax.capital_gains import TaxYearRules, TaxYearSummary

# ---- 테스트 헬퍼 -------------------------------------------------------


def _rules(deduction: str = "2500000", rate: str = "0.22") -> TaxYearRules:
    return TaxYearRules(
        basic_deduction_krw=Decimal(deduction),
        tax_rate=Decimal(rate),
    )


def _summary(
    *,
    tax_year: int = 2025,
    total_gain: str = "10000000",
    deduction_applied: str = "2500000",
    taxable_base: str = "7500000",
    capital_gains_tax: str = "1650000",
    rules: TaxYearRules | None = None,
) -> TaxYearSummary:
    r = rules if rules is not None else _rules()
    return TaxYearSummary(
        tax_year=tax_year,
        rules=r,
        by_market=(),
        total_realized_gain_krw=Decimal(total_gain),
        deduction_applied_krw=Decimal(deduction_applied),
        taxable_base_krw=Decimal(taxable_base),
        capital_gains_tax_krw=Decimal(capital_gains_tax),
        sale_count=1,
    )


def _real(
    *,
    ticker: str = "005930",
    market: str = "KR",
    sell_date: date = date(2025, 6, 1),
    qty: int = 10,
    proceeds: str = "10000000",
    acq_cost: str = "9000000",
    realized: str = "1000000",
) -> SaleRealization:
    return SaleRealization(
        ticker=ticker,
        market=market,
        sell_date=sell_date,
        total_qty=qty,
        total_acq_cost_krw=Decimal(acq_cost),
        total_proceeds_krw=Decimal(proceeds),
        total_realized_gain_krw=Decimal(realized),
        consumptions=(),
    )


# ---- AC1: 기본 세금 계산 -----------------------------------------------


def test_basic_form_ac1_national_local_total():
    """AC1: 양도차익 1천만 → 과세표준 750만 → national=1,500,000, local=150,000, total=1,650,000."""
    summary = _summary(capital_gains_tax="1650000")
    # 양도차익 = 12,500,000 - 2,500,000 = 10,000,000 → 과세표준 = 1천만 - 250만 = 750만
    form = build_nts_form(summary, [_real(proceeds="12500000", acq_cost="2500000")])

    assert form.taxable_base_krw == Decimal("7500000")
    assert form.national_tax_krw == Decimal("1500000")
    assert form.local_tax_krw == Decimal("150000")
    assert form.total_tax_krw == Decimal("1650000")


# ---- AC2: gain ≤ 250만 세금 0 -----------------------------------------


def test_gain_below_deduction_zero_tax():
    """AC2: gain ≤ 250만 → taxable_base=0 → 모든 세금 0."""
    summary = _summary(
        total_gain="2000000",
        deduction_applied="2000000",
        taxable_base="0",
        capital_gains_tax="0",
    )
    form = build_nts_form(summary, [_real(proceeds="2000000", acq_cost="0", realized="2000000")])

    assert form.national_tax_krw == Decimal("0")
    assert form.local_tax_krw == Decimal("0")
    assert form.total_tax_krw == Decimal("0")


# ---- AC3: 양도차손 세금 0, 라인 보존 ------------------------------------


def test_negative_gain_zero_tax_preserves_lines():
    """AC3: 양도차손 → 세금 0, sale_lines 는 라인 보존."""
    summary = _summary(
        total_gain="-1000000",
        deduction_applied="0",
        taxable_base="0",
        capital_gains_tax="0",
    )
    real = _real(proceeds="9000000", acq_cost="10000000", realized="-1000000")
    form = build_nts_form(summary, [real])

    assert form.total_tax_krw == Decimal("0")
    assert form.national_tax_krw == Decimal("0")
    assert form.local_tax_krw == Decimal("0")
    assert form.sale_count == 1
    assert form.sale_lines[0].realized_gain_krw == Decimal("-1000000")


# ---- AC4: 신고기간 2025 → (2026-05-01, 2026-05-31) --------------------


def test_filing_period_next_year_may_ac4():
    """AC4: tax_year=2025 → filing_period=(2026-05-01, 2026-05-31)."""
    form = build_nts_form(_summary(tax_year=2025), [])

    assert form.filing_period_start == date(2026, 5, 1)
    assert form.filing_period_end == date(2026, 5, 31)


# ---- 다른 연도 신고기간 ------------------------------------------------


def test_filing_period_correct_for_other_years():
    """2023 과세연도 → (2024-05-01, 2024-05-31)."""
    summary = _summary(tax_year=2023)
    form = build_nts_form(summary, [])

    assert form.filing_period_start == date(2024, 5, 1)
    assert form.filing_period_end == date(2024, 5, 31)


# ---- AC5: 다른 연도 라인 필터 ------------------------------------------


def test_realizations_filtered_by_tax_year_ac5():
    """AC5: realizations 에 2024·2025 섞임, tax_year=2025 → 2024 라인 제외."""
    summary = _summary(tax_year=2025)
    real_2025 = _real(sell_date=date(2025, 3, 1), ticker="A")
    real_2024 = _real(sell_date=date(2024, 12, 31), ticker="B")

    form = build_nts_form(summary, [real_2025, real_2024])

    assert form.sale_count == 1
    assert form.sale_lines[0].ticker == "A"


# ---- AC6: 빈 realizations → 영 폼 -------------------------------------


def test_empty_realizations_returns_zero_form_ac6():
    """AC6: 빈 realizations → sale_count=0, totals=0, by_market=(), 세금 0."""
    summary = _summary(taxable_base="0", capital_gains_tax="0")
    form = build_nts_form(summary, [])

    assert form.sale_count == 0
    assert form.total_proceeds_krw == Decimal("0")
    assert form.total_acquisition_cost_krw == Decimal("0")
    assert form.total_realized_gain_krw == Decimal("0")
    assert form.by_market == ()
    assert form.national_tax_krw == Decimal("0")
    assert form.total_tax_krw == Decimal("0")


# ---- AC7: KR·US 혼합 by_market ------------------------------------------


def test_kr_us_mixed_by_market_aggregation_ac7():
    """AC7: KR·US 매도 혼합 → by_market 2개, 합 == totals."""
    summary = _summary(taxable_base="0", capital_gains_tax="0")
    kr = _real(
        market="KR", ticker="005930", proceeds="5000000", acq_cost="4500000", realized="500000"
    )
    us = _real(
        market="US", ticker="AAPL", proceeds="3000000", acq_cost="2800000", realized="200000"
    )

    form = build_nts_form(summary, [kr, us])

    assert len(form.by_market) == 2
    mkts = {b.market: b for b in form.by_market}
    assert "KR" in mkts
    assert "US" in mkts
    assert mkts["KR"].total_proceeds_krw == Decimal("5000000")
    assert mkts["US"].total_proceeds_krw == Decimal("3000000")

    # by_market 합 == totals
    assert sum(b.total_proceeds_krw for b in form.by_market) == form.total_proceeds_krw
    assert (
        sum(b.total_acquisition_cost_krw for b in form.by_market) == form.total_acquisition_cost_krw
    )
    assert sum(b.total_realized_gain_krw for b in form.by_market) == form.total_realized_gain_krw
    assert sum(b.sale_count for b in form.by_market) == form.sale_count


# ---- AC8: sale_lines 정렬 결정성 ----------------------------------------


def test_sale_lines_sorted_deterministically_ac8():
    """AC8: sell_date asc → market asc → ticker asc 정렬."""
    summary = _summary(taxable_base="0", capital_gains_tax="0")
    reals = [
        _real(sell_date=date(2025, 6, 2), market="US", ticker="TSLA"),
        _real(sell_date=date(2025, 6, 1), market="US", ticker="AAPL"),
        _real(sell_date=date(2025, 6, 1), market="KR", ticker="005935"),
        _real(sell_date=date(2025, 6, 1), market="KR", ticker="005930"),
    ]
    form = build_nts_form(summary, reals)

    keys = [(sl.sell_date, sl.market, sl.ticker) for sl in form.sale_lines]
    assert keys == sorted(keys)


# ---- AC9: summary CSV 형식 -----------------------------------------------


def test_summary_csv_has_header_and_key_fields_ac9():
    """AC9: summary CSV 헤더 (field, value) + 주요 필드 포함."""
    form = build_nts_form(_summary(), [_real()])
    csv_str = export_summary_csv(form)

    lines = csv_str.strip().splitlines()
    assert lines[0] == "field,value"

    fields = {row.split(",")[0] for row in lines[1:]}
    for key in (
        "tax_year",
        "total_proceeds_krw",
        "national_tax_krw",
        "local_tax_krw",
        "total_tax_krw",
    ):
        assert key in fields, f"summary CSV missing field: {key}"


# ---- AC10: detail CSV 컬럼·행 수 ----------------------------------------


def test_detail_csv_per_line_columns_ac10():
    """AC10: detail CSV 헤더 + 라인 N행, 지정 컬럼 포함."""
    summary = _summary(taxable_base="0", capital_gains_tax="0")
    form = build_nts_form(summary, [_real(ticker="AAA"), _real(ticker="BBB")])
    csv_str = export_detail_csv(form)

    lines = csv_str.strip().splitlines()
    header_cols = lines[0].split(",")
    for col in (
        "market",
        "ticker",
        "sell_date",
        "quantity",
        "proceeds_krw",
        "acquisition_cost_krw",
        "realized_gain_krw",
    ):
        assert col in header_cols

    assert len(lines) == 3  # header + 2 data rows


# ---- AC11: CSV float 미사용 -----------------------------------------------


def test_csv_no_float_repr_ac11():
    """AC11: CSV 직렬화에 float repr (.0e, e+, e-) 0건."""
    form = build_nts_form(_summary(), [_real()])
    summary_csv = export_summary_csv(form)
    detail_csv = export_detail_csv(form)

    float_pattern = re.compile(r"(\.\d+e[+-]|\d+e[+\-]\d+|\.0\b)", re.IGNORECASE)
    assert not float_pattern.search(summary_csv), "float repr in summary CSV"
    assert not float_pattern.search(detail_csv), "float repr in detail CSV"


# ---- AC12: T003 22% vs NTS 분리 차이 ≤ 2원 ------------------------------


def test_t003_cross_reference_within_2_won_ac12():
    """AC12: |t003_combined_tax_krw - total_tax_krw| ≤ 2."""
    # 양도차익 1천만 → 과세표준 750만 → NTS 분리 세액 1,650,000 = T003 22% 세액
    summary = _summary(capital_gains_tax="1650000")
    form = build_nts_form(summary, [_real(proceeds="12500000", acq_cost="2500000")])
    diff = abs(form.t003_combined_tax_krw - form.total_tax_krw)
    assert diff <= Decimal("2"), f"차이={diff} 허용범위 초과"


# ---- AC13: by_market 합 == totals invariant --------------------------------


def test_by_market_sum_invariant_holds_ac13():
    """AC13: by_market 집계 합 == form totals (proceeds·cost·gain·sale_count)."""
    summary = _summary(taxable_base="0", capital_gains_tax="0")
    form = build_nts_form(
        summary,
        [
            _real(market="KR", ticker="A"),
            _real(market="US", ticker="B"),
            _real(market="KR", ticker="C"),
        ],
    )
    assert sum(b.total_proceeds_krw for b in form.by_market) == form.total_proceeds_krw
    assert (
        sum(b.total_acquisition_cost_krw for b in form.by_market) == form.total_acquisition_cost_krw
    )
    assert sum(b.total_realized_gain_krw for b in form.by_market) == form.total_realized_gain_krw
    assert sum(b.sale_count for b in form.by_market) == form.sale_count


# ---- Invariant: total_tax == national + local ----------------------------


def test_total_tax_equals_national_plus_local():
    """national_tax + local_tax == total_tax 항상 성립."""
    form = build_nts_form(_summary(), [_real()])
    assert form.total_tax_krw == form.national_tax_krw + form.local_tax_krw


# ---- ROUND_DOWN 독립 적용 ------------------------------------------------


def test_round_down_applied_independently():
    """national과 local 각각 ROUND_DOWN — 소수점 버림 확인."""
    # 양도차익 3,734,567 → 과세표준 1,234,567
    # national=floor(1234567*0.20)=246913, local=floor(246913*0.10)=24691
    form = build_nts_form(_summary(), [_real(proceeds="3734567", acq_cost="0")])

    assert form.taxable_base_krw == Decimal("1234567")
    assert form.national_tax_krw == Decimal("246913")
    assert form.local_tax_krw == Decimal("24691")
    assert form.total_tax_krw == Decimal("271604")


def test_sub_won_amounts_truncated_to_won():
    """원 미만 소수(USD 환산 등)는 양식에서 원 단위 절사."""
    real = _real(proceeds="6191218.2470000000", acq_cost="2500000.9")
    form = build_nts_form(_summary(), [real])

    line = form.sale_lines[0]
    assert line.proceeds_krw == Decimal("6191218")  # 절사
    assert line.acquisition_cost_krw == Decimal("2500000")  # 절사
    assert line.realized_gain_krw == Decimal("3691218")  # 6191218 - 2500000
    assert form.total_realized_gain_krw == Decimal("3691218")
    # 원 미만 소수 없음 (정수)
    assert form.total_realized_gain_krw == form.total_realized_gain_krw.to_integral_value()


# ---- Decimal-only (float 미사용) ------------------------------------------


def test_decimal_only_no_float_in_pipeline():
    """build_nts_form / export_* 결과의 금액 필드가 모두 Decimal."""
    form = build_nts_form(_summary(), [_real()])
    assert isinstance(form.national_tax_krw, Decimal)
    assert isinstance(form.local_tax_krw, Decimal)
    assert isinstance(form.total_tax_krw, Decimal)
    assert isinstance(form.total_proceeds_krw, Decimal)
    assert isinstance(form.total_acquisition_cost_krw, Decimal)
    assert isinstance(form.total_realized_gain_krw, Decimal)
    if form.sale_lines:
        line = form.sale_lines[0]
        assert isinstance(line.proceeds_krw, Decimal)
        assert isinstance(line.acquisition_cost_krw, Decimal)
        assert isinstance(line.realized_gain_krw, Decimal)


# ---- E12: realizations vs gain_summary 불일치 허용 ----------------------


def test_caller_inconsistency_silently_accepted():
    """E12: gain_summary 가 realizations 와 불일치해도 예외 없음.

    양식의 금액·세금은 모두 realizations 기준으로 자체 산출하고, gain_summary
    는 tax_year·기본공제·교차검증값에만 쓴다.
    """
    summary = _summary(total_gain="99999999", taxable_base="88888888", capital_gains_tax="0")
    form = build_nts_form(summary, [_real()])  # proceeds 1천만, cost 9백만 → 양도차익 1백만

    assert form.total_realized_gain_krw == Decimal("1000000")  # realizations 기준
    assert form.taxable_base_krw == Decimal("0")  # 1백만 < 250만 공제 → 0
    assert form.national_tax_krw == Decimal("0")


# ---- by_market market asc 정렬 -------------------------------------------


def test_by_market_sorted_market_asc():
    """by_market 은 market asc (KR < US) 순 정렬."""
    summary = _summary(taxable_base="0", capital_gains_tax="0")
    form = build_nts_form(
        summary,
        [
            _real(market="US"),
            _real(market="KR"),
        ],
    )
    mkt_order = [b.market for b in form.by_market]
    assert mkt_order == sorted(mkt_order)


# ---- taxable_base=0 → 세금 전부 0 ----------------------------------------


def test_taxable_base_zero_all_taxes_zero():
    """taxable_base=0 ⇒ national=local=total=0."""
    summary = _summary(taxable_base="0", capital_gains_tax="0")
    form = build_nts_form(summary, [])

    assert form.national_tax_krw == Decimal("0")
    assert form.local_tax_krw == Decimal("0")
    assert form.total_tax_krw == Decimal("0")


# ---- tax_year 저장 확인 ---------------------------------------------------


def test_form_stores_correct_tax_year():
    """form.tax_year 가 summary.tax_year 를 정확히 저장."""
    for yr in (2023, 2024, 2025):
        form = build_nts_form(_summary(tax_year=yr), [])
        assert form.tax_year == yr
