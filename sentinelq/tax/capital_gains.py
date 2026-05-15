"""Capital Gains Calculator — KR 양도세 계산 엔진 (Phase 3 T003).

spec: ``.claude/queue/spec-T003.md``
PREREG: ``docs/preregistration/PREREG-0008-tax-tool.md`` §2.2
predecessor: T002 (``sentinelq.portfolio.tax_lots.SaleRealization``)

본 모듈 책임:

* T002 ``SaleRealization`` 시퀀스를 입력받아 KR NTS 룰
  (250만원 기본공제 + 22% 세율 + 국내·해외 합산)을 적용한
  연도별 ``TaxYearSummary`` 를 산출한다.
* 이월공제 불가 — 다년 입력 시 각 연도 독립 계산.
* 최종 양도세는 NTS 양식 표준 ``ROUND_DOWN`` (원 단위 절사).
* 룰은 ``TaxYearRules`` frozen dataclass 로 외부 주입 가능.

비스코프 (T003 OUT):

* 배당소득 (15.4% 원천징수, 별도 모듈)
* 환차익 분리과세 (NTS 는 KRW 환산값만 본다)
* 12월 손실 인식 권장 (T005 = ``loss_harvesting.py``)
* 세제 우대 한도 추적 (T004 = ``deduction.py``)
* NTS 양식 PDF 출력 (T006 = ``reports/nts_form.py``)
* 국내 상장주식 소액주주 비과세 / 대주주 판정
  (PREREG §2.2 가 합산 단순화 채택, 차이는 amendment 영역)

mandate 위반 금지 (ADR-0011·0012·0013): 알파·자동매매·시장 타이밍 코드 없음.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from sentinelq.portfolio.tax_lots import SaleRealization

# ---- 예외 ----


class UnknownTaxYearError(KeyError):
    """``rules`` None 인데 ``DEFAULT_RULES`` 에 해당 연도 키가 없음."""


# ---- 룰 ----


@dataclass(frozen=True)
class TaxYearRules:
    """단일 과세기간(연도) KR 양도세 룰. 변경 대비 frozen + 외부 주입 가능."""

    basic_deduction_krw: Decimal
    tax_rate: Decimal


TAX_YEAR_RULES_2026: TaxYearRules = TaxYearRules(
    basic_deduction_krw=Decimal("2500000"),
    tax_rate=Decimal("0.22"),
)


DEFAULT_RULES: dict[int, TaxYearRules] = {
    2024: TAX_YEAR_RULES_2026,
    2025: TAX_YEAR_RULES_2026,
    2026: TAX_YEAR_RULES_2026,
}


# ---- 데이터 모델 ----


@dataclass(frozen=True)
class MarketBreakdown:
    """국내·해외 market 별 raw 합산 (정보 노출용, 과세 단위 아님).

    합산 과세는 ``TaxYearSummary.total_realized_gain_krw`` 가 담당하며,
    본 breakdown 은 NTS 양식의 분리 칸 출력(T006) 준비 + 사용자 가시성용.
    """

    market: str
    total_proceeds_krw: Decimal
    total_acq_cost_krw: Decimal
    realized_gain_krw: Decimal
    sale_count: int


@dataclass(frozen=True)
class TaxYearSummary:
    """단일 과세기간(연도) 양도세 요약."""

    tax_year: int
    rules: TaxYearRules
    by_market: tuple[MarketBreakdown, ...]
    total_realized_gain_krw: Decimal
    deduction_applied_krw: Decimal
    taxable_base_krw: Decimal
    capital_gains_tax_krw: Decimal
    sale_count: int


# ---- 내부 헬퍼 ----


def _resolve_rules(tax_year: int, rules: TaxYearRules | None) -> TaxYearRules:
    if rules is not None:
        return rules
    try:
        return DEFAULT_RULES[tax_year]
    except KeyError as exc:
        raise UnknownTaxYearError(
            f"no DEFAULT_RULES entry for tax_year={tax_year}; "
            "pass an explicit `rules=TaxYearRules(...)`"
        ) from exc


def _build_breakdowns(
    realizations: list[SaleRealization],
) -> tuple[MarketBreakdown, ...]:
    grouped: dict[str, list[SaleRealization]] = defaultdict(list)
    for r in realizations:
        grouped[r.market].append(r)
    out: list[MarketBreakdown] = []
    for market in sorted(grouped):
        sales = grouped[market]
        out.append(
            MarketBreakdown(
                market=market,
                total_proceeds_krw=sum((s.total_proceeds_krw for s in sales), Decimal("0")),
                total_acq_cost_krw=sum((s.total_acq_cost_krw for s in sales), Decimal("0")),
                realized_gain_krw=sum((s.total_realized_gain_krw for s in sales), Decimal("0")),
                sale_count=len(sales),
            )
        )
    return tuple(out)


def _empty_summary(tax_year: int, rules: TaxYearRules) -> TaxYearSummary:
    return TaxYearSummary(
        tax_year=tax_year,
        rules=rules,
        by_market=(),
        total_realized_gain_krw=Decimal("0"),
        deduction_applied_krw=Decimal("0"),
        taxable_base_krw=Decimal("0"),
        capital_gains_tax_krw=Decimal("0"),
        sale_count=0,
    )


# ---- public API ----


def calculate_year(
    realizations: Iterable[SaleRealization],
    tax_year: int,
    rules: TaxYearRules | None = None,
) -> TaxYearSummary:
    """단일 과세기간 양도세 계산.

    입력에 다른 연도 매도가 섞여 있으면 ``sell_date.year != tax_year`` 항목은
    조용히 필터링한다 (다년 통합 입력에서 단일 연도 추출 유스케이스).
    매도 0건이어도 영(零) summary 를 반환한다.
    """
    resolved = _resolve_rules(tax_year, rules)
    matched = [r for r in realizations if r.sell_date.year == tax_year]
    if not matched:
        return _empty_summary(tax_year, resolved)

    by_market = _build_breakdowns(matched)
    net = sum((b.realized_gain_krw for b in by_market), Decimal("0"))

    if net <= 0:
        deduction_applied = Decimal("0")
        taxable_base = Decimal("0")
    else:
        deduction_applied = min(net, resolved.basic_deduction_krw)
        taxable_base = net - deduction_applied

    raw_tax = taxable_base * resolved.tax_rate
    tax = raw_tax.quantize(Decimal("1"), rounding=ROUND_DOWN)

    return TaxYearSummary(
        tax_year=tax_year,
        rules=resolved,
        by_market=by_market,
        total_realized_gain_krw=net,
        deduction_applied_krw=deduction_applied,
        taxable_base_krw=taxable_base,
        capital_gains_tax_krw=tax,
        sale_count=len(matched),
    )


def calculate_all(
    realizations: Iterable[SaleRealization],
    rules_by_year: dict[int, TaxYearRules] | None = None,
) -> list[TaxYearSummary]:
    """입력의 ``sell_date.year`` 기준 자동 분할 → 연도별 summary 리스트.

    빈 입력은 빈 리스트를 반환. 이월공제는 적용되지 않는다 (KR 룰).
    각 연도 summary 는 ``calculate_year`` 와 동일한 룰 해소 절차를 거친다.
    """
    materialised = list(realizations)
    if not materialised:
        return []

    years = sorted({r.sell_date.year for r in materialised})
    out: list[TaxYearSummary] = []
    for year in years:
        override = rules_by_year.get(year) if rules_by_year else None
        out.append(calculate_year(materialised, year, rules=override))
    return out
