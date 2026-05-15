"""세제 우대 한도 추적 — KR 연금저축·IRP·ISA 납입 한도·세액공제 계산 (Phase 3 T004).

spec: ``.claude/queue/spec-T004.md``
PREREG: ``docs/preregistration/PREREG-0008-tax-tool.md`` §2.3
predecessor: T003 (``sentinelq.tax.capital_gains`` — 병렬 사용)

본 모듈 책임:

* 연금저축·IRP 납입액 → 잔여 한도 + 세액공제액 산출
* ISA 납입액 → 연간·5년 누적 잔여 한도 표시
* 세액공제율: 총소득 5,500만원 이하 16.5%, 초과 13.2%, None → 보수적 13.2%
* 최종 세액공제액은 NTS 표준 ROUND_DOWN (원 단위 절사)
* 룰 상수는 DeductionLimits frozen dataclass로 외부 주입 가능

비스코프 (T004 OUT):

* ISA 계좌 내 투자 수익 비과세 계산 (투자 수익 데이터 미보유)
* 양도세 계산 (T003 = capital_gains.py)
* 12월 손실 인식 권장 (T005 = loss_harvesting.py)
* NTS 양식 PDF 출력 (T006 = reports/nts_form.py)
* KIS API 납입 데이터 자동 fetch (수동 입력 기반)
* 퇴직금·DB형 퇴직연금·국민연금

mandate 위반 금지 (ADR-0011·0012·0013): 알파·자동매매·시장 타이밍 코드 없음.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

# ---- 예외 ----


class DeductionError(Exception):
    """deduction 모듈 공통 base 예외."""


class UnknownDeductionYearError(KeyError):
    """limits=None 인데 DEFAULT_LIMITS 에 해당 연도 키 없음."""


# ---- 계좌 유형 ----


class AccountType(StrEnum):
    PENSION_SAVINGS = "pension_savings"  # 연금저축
    IRP = "irp"  # 개인형 퇴직연금
    ISA_GENERAL = "isa_general"  # ISA 일반형
    ISA_WORKERS = "isa_workers"  # ISA 서민형/근로자형


# ---- 룰 상수 ----


@dataclass(frozen=True)
class DeductionLimits:
    """연도별 세제 우대 한도 룰. 변경 대비 frozen + 외부 주입 가능."""

    pension_savings_annual_krw: Decimal  # 6_000_000
    pension_irp_combined_annual_krw: Decimal  # 9_000_000
    isa_annual_krw: Decimal  # 20_000_000
    isa_5year_krw: Decimal  # 100_000_000
    isa_general_tax_free_krw: Decimal  # 5_000_000  (비과세 한도 정보용)
    isa_workers_tax_free_krw: Decimal  # 10_000_000 (비과세 한도 정보용)
    income_threshold_krw: Decimal  # 55_000_000 (세액공제율 분기점)
    tax_credit_rate_low: Decimal  # 0.165 (소득 ≤ 5500만)
    tax_credit_rate_high: Decimal  # 0.132 (소득 > 5500만)


DEDUCTION_LIMITS_2026: DeductionLimits = DeductionLimits(
    pension_savings_annual_krw=Decimal("6000000"),
    pension_irp_combined_annual_krw=Decimal("9000000"),
    isa_annual_krw=Decimal("20000000"),
    isa_5year_krw=Decimal("100000000"),
    isa_general_tax_free_krw=Decimal("5000000"),
    isa_workers_tax_free_krw=Decimal("10000000"),
    income_threshold_krw=Decimal("55000000"),
    tax_credit_rate_low=Decimal("0.165"),
    tax_credit_rate_high=Decimal("0.132"),
)

DEFAULT_LIMITS: dict[int, DeductionLimits] = {
    2024: DEDUCTION_LIMITS_2026,
    2025: DEDUCTION_LIMITS_2026,
    2026: DEDUCTION_LIMITS_2026,
}


# ---- 납입 기록 ----


@dataclass(frozen=True)
class ContributionRecord:
    """단일 납입 기록."""

    account_type: AccountType
    amount_krw: Decimal  # 납입액 (양수)
    year: int  # 납입 과세연도


# ---- 결과 데이터 모델 ----


@dataclass(frozen=True)
class PensionCreditResult:
    """연금저축+IRP 세액공제 계산 결과."""

    pension_contributed_krw: Decimal  # 연금저축 납입 합계
    irp_contributed_krw: Decimal  # IRP 납입 합계
    combined_contributed_krw: Decimal  # 합산 납입액
    pension_annual_limit_krw: Decimal  # 6_000_000 (연금저축 단독 상한)
    combined_annual_limit_krw: Decimal  # 9_000_000 (합산 상한)
    eligible_for_credit_krw: Decimal  # min(combined_contributed, 9_000_000)
    tax_credit_rate: Decimal  # 0.132 or 0.165
    tax_credit_krw: Decimal  # eligible x rate, ROUND_DOWN
    pension_remaining_krw: Decimal  # max(0, 6_000_000 - pension_contributed)
    combined_remaining_krw: Decimal  # max(0, 9_000_000 - combined_contributed)


@dataclass(frozen=True)
class ISAStatusResult:
    """ISA 납입 현황 요약 (투자 수익 비과세 계산 제외)."""

    isa_type: AccountType  # ISA_GENERAL or ISA_WORKERS
    annual_contributed_krw: Decimal  # 해당 연도 납입액
    annual_limit_krw: Decimal  # 20_000_000
    annual_remaining_krw: Decimal  # max(0, 20_000_000 - annual_contributed)
    cumulative_5year_krw: Decimal  # 5년 누적 납입액
    cumulative_5year_limit_krw: Decimal  # 100_000_000
    cumulative_5year_remaining_krw: Decimal  # max(0, 100_000_000 - cumulative)
    tax_free_limit_krw: Decimal  # 정보용: 일반 5_000_000 / 서민 10_000_000


@dataclass(frozen=True)
class DeductionYearSummary:
    """단일 과세기간 세제 우대 한도 전체 요약."""

    tax_year: int
    limits: DeductionLimits  # 적용된 룰 (감사 추적)
    annual_income_krw: Decimal | None  # 세액공제율 결정용 소득 (None = conservative)
    pension_credit: PensionCreditResult  # 연금저축+IRP 결과
    isa_status: ISAStatusResult | None  # ISA 보유 시만 존재


# ---- 내부 헬퍼 ----


def _resolve_limits(tax_year: int, limits: DeductionLimits | None) -> DeductionLimits:
    if limits is not None:
        return limits
    try:
        return DEFAULT_LIMITS[tax_year]
    except KeyError as exc:
        raise UnknownDeductionYearError(
            f"no DEFAULT_LIMITS entry for tax_year={tax_year}; "
            "pass an explicit `limits=DeductionLimits(...)`"
        ) from exc


def _resolve_rate(
    annual_income_krw: Decimal | None,
    limits: DeductionLimits,
) -> Decimal:
    """소득 기준 세액공제율 결정. None이면 보수적 high rate."""
    if annual_income_krw is None:
        return limits.tax_credit_rate_high
    if annual_income_krw <= limits.income_threshold_krw:
        return limits.tax_credit_rate_low
    return limits.tax_credit_rate_high


def _build_pension_credit(
    contributions: list[ContributionRecord],
    limits: DeductionLimits,
    annual_income_krw: Decimal | None,
) -> PensionCreditResult:
    pension = sum(
        (r.amount_krw for r in contributions if r.account_type == AccountType.PENSION_SAVINGS),
        Decimal("0"),
    )
    irp = sum(
        (r.amount_krw for r in contributions if r.account_type == AccountType.IRP),
        Decimal("0"),
    )
    combined = pension + irp
    eligible = min(combined, limits.pension_irp_combined_annual_krw)
    rate = _resolve_rate(annual_income_krw, limits)
    raw_credit = eligible * rate
    tax_credit = raw_credit.quantize(Decimal("1"), rounding=ROUND_DOWN)

    pension_remaining = max(Decimal("0"), limits.pension_savings_annual_krw - pension)
    combined_remaining = max(Decimal("0"), limits.pension_irp_combined_annual_krw - combined)

    return PensionCreditResult(
        pension_contributed_krw=pension,
        irp_contributed_krw=irp,
        combined_contributed_krw=combined,
        pension_annual_limit_krw=limits.pension_savings_annual_krw,
        combined_annual_limit_krw=limits.pension_irp_combined_annual_krw,
        eligible_for_credit_krw=eligible,
        tax_credit_rate=rate,
        tax_credit_krw=tax_credit,
        pension_remaining_krw=pension_remaining,
        combined_remaining_krw=combined_remaining,
    )


def _build_isa_status(
    annual_contributions: list[ContributionRecord],
    cumulative_contributions: list[ContributionRecord],
    limits: DeductionLimits,
) -> ISAStatusResult | None:
    """ISA 납입 현황 산출. ISA 납입 기록이 없으면 None 반환.

    ISA_GENERAL과 ISA_WORKERS가 동시에 있으면 ISA_GENERAL 우선.
    실제로는 둘 중 하나만 개설 가능하나, 입력 오류 시 ISA_GENERAL 우선으로 단순화.
    """
    isa_types_present = {
        r.account_type
        for r in annual_contributions
        if r.account_type in (AccountType.ISA_GENERAL, AccountType.ISA_WORKERS)
    }
    if not isa_types_present:
        return None

    # ISA_GENERAL 우선
    isa_type = (
        AccountType.ISA_GENERAL
        if AccountType.ISA_GENERAL in isa_types_present
        else AccountType.ISA_WORKERS
    )

    annual_contributed = sum(
        (r.amount_krw for r in annual_contributions if r.account_type == isa_type),
        Decimal("0"),
    )
    cumulative_5year = sum(
        (r.amount_krw for r in cumulative_contributions if r.account_type == isa_type),
        Decimal("0"),
    )

    annual_remaining = max(Decimal("0"), limits.isa_annual_krw - annual_contributed)
    cumulative_remaining = max(Decimal("0"), limits.isa_5year_krw - cumulative_5year)
    tax_free_limit = (
        limits.isa_general_tax_free_krw
        if isa_type == AccountType.ISA_GENERAL
        else limits.isa_workers_tax_free_krw
    )

    return ISAStatusResult(
        isa_type=isa_type,
        annual_contributed_krw=annual_contributed,
        annual_limit_krw=limits.isa_annual_krw,
        annual_remaining_krw=annual_remaining,
        cumulative_5year_krw=cumulative_5year,
        cumulative_5year_limit_krw=limits.isa_5year_krw,
        cumulative_5year_remaining_krw=cumulative_remaining,
        tax_free_limit_krw=tax_free_limit,
    )


# ---- public API ----


def calculate_deduction(
    contributions: Iterable[ContributionRecord],
    tax_year: int,
    annual_income_krw: Decimal | None = None,
    limits: DeductionLimits | None = None,
    isa_cumulative_records: Iterable[ContributionRecord] | None = None,
) -> DeductionYearSummary:
    """단일 과세기간 세제 우대 한도 계산.

    contributions: 납입 기록 (다른 연도 포함 시 tax_year 필터링)
    annual_income_krw: None이면 보수적 세율 13.2% 적용
    limits: None이면 DEFAULT_LIMITS[tax_year] 사용
    isa_cumulative_records: ISA 5년 누적 계산용 과거 납입 기록.
        None이면 contributions(해당 연도) 기록만으로 누적 계산.
    """
    resolved = _resolve_limits(tax_year, limits)

    all_contributions = list(contributions)
    # 해당 연도 필터
    year_contributions = [r for r in all_contributions if r.year == tax_year]

    # ISA 5년 누적: 별도 기록 제공 시 사용, 없으면 해당 연도만
    if isa_cumulative_records is not None:
        cumulative = list(isa_cumulative_records)
    else:
        cumulative = year_contributions

    pension_credit = _build_pension_credit(year_contributions, resolved, annual_income_krw)
    isa_status = _build_isa_status(year_contributions, cumulative, resolved)

    return DeductionYearSummary(
        tax_year=tax_year,
        limits=resolved,
        annual_income_krw=annual_income_krw,
        pension_credit=pension_credit,
        isa_status=isa_status,
    )
