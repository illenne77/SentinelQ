"""T004 세제 우대 한도 추적 단위 테스트.

spec: .claude/queue/spec-T004.md
PREREG: PREREG-0008 §2.3
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from sentinelq.tax.deduction import (
    AccountType,
    ContributionRecord,
    DeductionLimits,
    UnknownDeductionYearError,
    calculate_deduction,
)

# ---- 픽스처 헬퍼 ----


def _contrib(account_type: AccountType, amount: int | str, year: int = 2025) -> ContributionRecord:
    return ContributionRecord(
        account_type=account_type,
        amount_krw=Decimal(str(amount)),
        year=year,
    )


PS = AccountType.PENSION_SAVINGS
IRP = AccountType.IRP
ISA_G = AccountType.ISA_GENERAL
ISA_W = AccountType.ISA_WORKERS


# ---- 세액공제 정확성 ----


def test_pension_only_low_income():
    """AC1: 연금저축 600만, 소득 5500만↓ → 16.5% → 990,000원."""
    result = calculate_deduction(
        [_contrib(PS, 6_000_000)],
        tax_year=2025,
        annual_income_krw=Decimal("50000000"),
    )
    pc = result.pension_credit
    assert pc.pension_contributed_krw == Decimal("6000000")
    assert pc.eligible_for_credit_krw == Decimal("6000000")
    assert pc.tax_credit_rate == Decimal("0.165")
    assert pc.tax_credit_krw == Decimal("990000")


def test_pension_only_high_income():
    """연금저축 600만, 소득 5500만 초과 → 13.2% → 792,000원."""
    result = calculate_deduction(
        [_contrib(PS, 6_000_000)],
        tax_year=2025,
        annual_income_krw=Decimal("60000000"),
    )
    pc = result.pension_credit
    assert pc.tax_credit_rate == Decimal("0.132")
    assert pc.tax_credit_krw == Decimal("792000")


def test_pension_irp_combined_low_income():
    """AC2: 연금+IRP 900만, 소득 5500만↓ → 1,485,000원."""
    result = calculate_deduction(
        [_contrib(PS, 6_000_000), _contrib(IRP, 3_000_000)],
        tax_year=2025,
        annual_income_krw=Decimal("40000000"),
    )
    pc = result.pension_credit
    assert pc.combined_contributed_krw == Decimal("9000000")
    assert pc.eligible_for_credit_krw == Decimal("9000000")
    assert pc.tax_credit_krw == Decimal("1485000")


def test_eligible_capped_at_combined_limit():
    """AC4: 연금 600만 + IRP 400만 = 1000만 → eligible = 900만 (상한 적용)."""
    result = calculate_deduction(
        [_contrib(PS, 6_000_000), _contrib(IRP, 4_000_000)],
        tax_year=2025,
    )
    pc = result.pension_credit
    assert pc.combined_contributed_krw == Decimal("10000000")
    assert pc.eligible_for_credit_krw == Decimal("9000000")
    assert pc.combined_remaining_krw == Decimal("0")


def test_pension_exceeds_individual_limit():
    """AC3: 연금 700만 단독 → eligible=700만, pension_remaining=0."""
    result = calculate_deduction(
        [_contrib(PS, 7_000_000)],
        tax_year=2025,
    )
    pc = result.pension_credit
    assert pc.pension_contributed_krw == Decimal("7000000")
    assert pc.eligible_for_credit_krw == Decimal("7000000")
    assert pc.pension_remaining_krw == Decimal("0")


# ---- 소득 분기 ----


def test_income_none_uses_conservative_rate():
    """AC5: annual_income_krw=None → 보수적 13.2%."""
    result = calculate_deduction(
        [_contrib(PS, 6_000_000)],
        tax_year=2025,
        annual_income_krw=None,
    )
    assert result.pension_credit.tax_credit_rate == Decimal("0.132")
    assert result.annual_income_krw is None


def test_income_at_threshold_boundary():
    """소득 정확히 5500만원 → 16.5% (≤ 기준, low rate)."""
    result = calculate_deduction(
        [_contrib(PS, 6_000_000)],
        tax_year=2025,
        annual_income_krw=Decimal("55000000"),
    )
    assert result.pension_credit.tax_credit_rate == Decimal("0.165")


# ---- ISA 한도 ----


def test_isa_general_annual_remaining():
    """AC6: ISA 일반형 연 1500만 납입 → 잔여 500만."""
    result = calculate_deduction(
        [_contrib(ISA_G, 15_000_000)],
        tax_year=2025,
    )
    assert result.isa_status is not None
    isa = result.isa_status
    assert isa.isa_type == ISA_G
    assert isa.annual_contributed_krw == Decimal("15000000")
    assert isa.annual_remaining_krw == Decimal("5000000")
    assert isa.tax_free_limit_krw == Decimal("5000000")


def test_isa_workers_cumulative_remaining():
    """AC7: ISA 서민형 5년 누적 8000만 → 잔여 2000만."""
    past = [_contrib(ISA_W, 20_000_000, year=y) for y in [2021, 2022, 2023]]
    current = [_contrib(ISA_W, 20_000_000, year=2024)]
    all_records = past + current
    result = calculate_deduction(
        current,
        tax_year=2024,
        isa_cumulative_records=all_records,
    )
    assert result.isa_status is not None
    isa = result.isa_status
    assert isa.isa_type == ISA_W
    assert isa.cumulative_5year_krw == Decimal("80000000")
    assert isa.cumulative_5year_remaining_krw == Decimal("20000000")
    assert isa.tax_free_limit_krw == Decimal("10000000")


def test_isa_absent_returns_none():
    """AC10: ISA 납입 없으면 isa_status=None."""
    result = calculate_deduction(
        [_contrib(PS, 3_000_000)],
        tax_year=2025,
    )
    assert result.isa_status is None


# ---- 경계·견고성 ----


def test_zero_contributions():
    """AC8: 납입 0건 → pension_remaining=600만, combined_remaining=900만, tax_credit=0."""
    result = calculate_deduction([], tax_year=2025)
    pc = result.pension_credit
    assert pc.pension_remaining_krw == Decimal("6000000")
    assert pc.combined_remaining_krw == Decimal("9000000")
    assert pc.tax_credit_krw == Decimal("0")
    assert pc.eligible_for_credit_krw == Decimal("0")
    assert result.isa_status is None


def test_tax_credit_round_down():
    """AC9: 세액공제 소수점 → ROUND_DOWN (원 단위 절사)."""
    # 7,777,777 x 0.132 = 1,026,666.564 -> ROUND_DOWN -> 1,026,666
    result = calculate_deduction(
        [_contrib(PS, 7_777_777)],
        tax_year=2025,
        annual_income_krw=Decimal("60000000"),
    )
    pc = result.pension_credit
    expected = (Decimal("7777777") * Decimal("0.132")).to_integral_value(rounding="ROUND_DOWN")
    assert pc.tax_credit_krw == expected


def test_external_limits_override():
    """외부 DeductionLimits 주입이 정상 동작한다."""
    custom = DeductionLimits(
        pension_savings_annual_krw=Decimal("7000000"),
        pension_irp_combined_annual_krw=Decimal("10000000"),
        isa_annual_krw=Decimal("20000000"),
        isa_5year_krw=Decimal("100000000"),
        isa_general_tax_free_krw=Decimal("5000000"),
        isa_workers_tax_free_krw=Decimal("10000000"),
        income_threshold_krw=Decimal("55000000"),
        tax_credit_rate_low=Decimal("0.165"),
        tax_credit_rate_high=Decimal("0.132"),
    )
    result = calculate_deduction(
        [_contrib(PS, 7_000_000)],
        tax_year=2025,
        limits=custom,
    )
    pc = result.pension_credit
    assert pc.pension_annual_limit_krw == Decimal("7000000")
    assert pc.pension_remaining_krw == Decimal("0")
    assert result.limits is custom


def test_over_contributed_remaining_zero():
    """초과납입 시 remaining=0 (음수 방지)."""
    result = calculate_deduction(
        [_contrib(PS, 10_000_000)],  # 600만 한도 초과
        tax_year=2025,
    )
    pc = result.pension_credit
    assert pc.pension_remaining_krw == Decimal("0")
    assert pc.combined_remaining_krw == Decimal("0")


def test_decimal_only_no_float():
    """Decimal-only: 소수점 납입에도 float 없음, 정밀도 유지."""
    result = calculate_deduction(
        [_contrib(PS, "3333333")],
        tax_year=2025,
        annual_income_krw=Decimal("40000000"),
    )
    pc = result.pension_credit
    # 3,333,333 x 0.165 = 549,999.945 -> ROUND_DOWN -> 549,999
    assert pc.tax_credit_krw == Decimal("549999")
    assert isinstance(pc.tax_credit_krw, Decimal)
    assert isinstance(pc.eligible_for_credit_krw, Decimal)


def test_unknown_tax_year_raises():
    """DEFAULT_LIMITS에 없는 연도 + limits=None → UnknownDeductionYearError."""
    with pytest.raises(UnknownDeductionYearError):
        calculate_deduction([], tax_year=2099)


def test_isa_annual_limit_full():
    """ISA 연간 2000만 납입 → annual_remaining=0."""
    result = calculate_deduction(
        [_contrib(ISA_G, 20_000_000)],
        tax_year=2025,
    )
    assert result.isa_status is not None
    assert result.isa_status.annual_remaining_krw == Decimal("0")


def test_mixed_year_contributions_filtered():
    """다른 연도 납입 기록이 섞여 있어도 tax_year만 계산에 사용한다."""
    contributions = [
        _contrib(PS, 6_000_000, year=2024),
        _contrib(PS, 3_000_000, year=2025),
    ]
    result = calculate_deduction(contributions, tax_year=2025)
    pc = result.pension_credit
    assert pc.pension_contributed_krw == Decimal("3000000")
    assert pc.pension_remaining_krw == Decimal("3000000")


def test_tax_year_stored_in_summary():
    """DeductionYearSummary.tax_year가 요청 연도와 일치한다."""
    result = calculate_deduction([], tax_year=2026)
    assert result.tax_year == 2026
