"""NTS 양도소득세 신고서 양식 조립 및 CSV 직렬화.

Spec: .claude/queue/spec-T006.md
PREREG: PREREG-0008 §2.5 + §4.1
ADR: ADR-0013 Phase 3 KR Investor Tools
KPI Gate: G1 — 양도세 NTS 양식 자동 출력

T003(TaxYearSummary) + T002(SaleRealization) 입력으로 NTS 홈택스 입력용
구조체를 조립한다.  CSV 직렬화 2종 (summary / detail) 포함.
OUT: PDF 렌더링, 자동 제출, 종합소득세, 대주주 판정 (PREREG §3 참조).
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal
from io import StringIO

from sentinelq.portfolio.tax_lots import SaleRealization
from sentinelq.tax.capital_gains import TaxYearSummary

# ---- NTS 세율 상수 ----------------------------------------

NATIONAL_TAX_RATE: Decimal = Decimal("0.20")  # 양도소득세 (국세)
LOCAL_TAX_RATE_OF_NATIONAL: Decimal = Decimal("0.10")  # 지방소득세 = 산출세액 x 10%

_ONE = Decimal("1")


def _truncate_won(amount: Decimal) -> Decimal:
    """원 단위 절사 (ROUND_DOWN) — NTS 신고서는 원 미만을 버린다."""
    return amount.quantize(_ONE, rounding=ROUND_DOWN)


# ---- 데이터 모델 -------------------------------------------


@dataclass(frozen=True)
class NTSSaleLine:
    """홈택스 양식 종목별 매도 행 (1 매도 = 1 행)."""

    market: str  # "KR" | "US"
    ticker: str
    sell_date: date
    quantity: int  # 매도 수량 (양수)
    proceeds_krw: Decimal  # 양도가액
    acquisition_cost_krw: Decimal  # 취득가액
    realized_gain_krw: Decimal  # 양도차익(+) / 차손(-)


@dataclass(frozen=True)
class NTSMarketBreakdown:
    """국내·해외 시장별 집계 행 (양식 상단 요약용)."""

    market: str
    total_proceeds_krw: Decimal
    total_acquisition_cost_krw: Decimal
    total_realized_gain_krw: Decimal
    sale_count: int


@dataclass(frozen=True)
class NTSCapitalGainsForm:
    """단일 과세기간 NTS 양도소득세 신고서 (홈택스 입력용)."""

    tax_year: int
    filing_period_start: date  # date(tax_year+1, 5, 1)
    filing_period_end: date  # date(tax_year+1, 5, 31)
    sale_lines: tuple[NTSSaleLine, ...]  # sell_date · market · ticker 오름차순
    by_market: tuple[NTSMarketBreakdown, ...]  # market asc
    total_proceeds_krw: Decimal
    total_acquisition_cost_krw: Decimal
    total_realized_gain_krw: Decimal
    basic_deduction_krw: Decimal  # 250만원
    deduction_applied_krw: Decimal  # 실제 적용 공제액
    taxable_base_krw: Decimal  # 과세표준
    national_tax_krw: Decimal  # 산출세액 (20%, ROUND_DOWN)
    local_tax_krw: Decimal  # 지방소득세 (산출세액 x 10%, ROUND_DOWN)
    total_tax_krw: Decimal  # national + local (NTS 공식 합계)
    t003_combined_tax_krw: Decimal  # T003 의 22% 단일 계산값 (교차 검증용)
    sale_count: int


# ---- public API -------------------------------------------


def build_nts_form(
    gain_summary: TaxYearSummary,
    realizations: Iterable[SaleRealization],
) -> NTSCapitalGainsForm:
    """T003 + T002 입력으로 NTS 양식 통합 객체 조립.

    realizations 는 gain_summary.tax_year 외 항목 자동 필터.
    모든 금액은 원 단위 절사 (ROUND_DOWN). 세금은 양식의 양도차익에서 직접
    산출하며 gain_summary 는 tax_year·기본공제 한도·교차검증값에만 쓴다.
    빈 입력은 영 폼 반환 (예외 없음).
    """
    tax_year = gain_summary.tax_year

    # 1. 필터 + 정렬
    filtered = sorted(
        (r for r in realizations if r.sell_date.year == tax_year),
        key=lambda r: (r.sell_date, r.market, r.ticker),
    )

    # 2. NTSSaleLine 변환 — 양도가액·취득가액 원 단위 절사 (NTS 신고서는 정수).
    sale_lines_list: list[NTSSaleLine] = []
    for r in filtered:
        proceeds = _truncate_won(r.total_proceeds_krw)
        acq_cost = _truncate_won(r.total_acq_cost_krw)
        sale_lines_list.append(
            NTSSaleLine(
                market=r.market,
                ticker=r.ticker,
                sell_date=r.sell_date,
                quantity=r.total_qty,
                proceeds_krw=proceeds,
                acquisition_cost_krw=acq_cost,
                realized_gain_krw=proceeds - acq_cost,  # 양도차익 = 양도가액 - 취득가액
            )
        )
    sale_lines = tuple(sale_lines_list)

    # 3. NTSMarketBreakdown 집계 (market asc)
    markets: dict[str, list[NTSSaleLine]] = {}
    for line in sale_lines:
        markets.setdefault(line.market, []).append(line)

    by_market = tuple(
        NTSMarketBreakdown(
            market=mkt,
            total_proceeds_krw=sum((sl.proceeds_krw for sl in lines), Decimal("0")),
            total_acquisition_cost_krw=sum((sl.acquisition_cost_krw for sl in lines), Decimal("0")),
            total_realized_gain_krw=sum((sl.realized_gain_krw for sl in lines), Decimal("0")),
            sale_count=len(lines),
        )
        for mkt, lines in sorted(markets.items())
    )

    # 4. Totals
    total_proceeds = sum((sl.proceeds_krw for sl in sale_lines), Decimal("0"))
    total_acq_cost = sum((sl.acquisition_cost_krw for sl in sale_lines), Decimal("0"))
    total_gain = sum((sl.realized_gain_krw for sl in sale_lines), Decimal("0"))
    sale_count = len(sale_lines)

    # 5. NTS 세금 계산 — 양식의 절사된 양도차익에서 직접 산출 (양식 자체 정합).
    basic_deduction = gain_summary.rules.basic_deduction_krw
    deduction_applied = (
        min(basic_deduction, total_gain) if total_gain > Decimal("0") else Decimal("0")
    )
    taxable_base = total_gain - deduction_applied
    if taxable_base < Decimal("0"):
        taxable_base = Decimal("0")
    national_tax = (taxable_base * NATIONAL_TAX_RATE).quantize(_ONE, rounding=ROUND_DOWN)
    local_tax = (national_tax * LOCAL_TAX_RATE_OF_NATIONAL).quantize(_ONE, rounding=ROUND_DOWN)
    total_tax = national_tax + local_tax

    # 6. 신고기간
    filing_start = date(tax_year + 1, 5, 1)
    filing_end = date(tax_year + 1, 5, 31)

    return NTSCapitalGainsForm(
        tax_year=tax_year,
        filing_period_start=filing_start,
        filing_period_end=filing_end,
        sale_lines=sale_lines,
        by_market=by_market,
        total_proceeds_krw=total_proceeds,
        total_acquisition_cost_krw=total_acq_cost,
        total_realized_gain_krw=total_gain,
        basic_deduction_krw=basic_deduction,
        deduction_applied_krw=deduction_applied,
        taxable_base_krw=taxable_base,
        national_tax_krw=national_tax,
        local_tax_krw=local_tax,
        total_tax_krw=total_tax,
        t003_combined_tax_krw=gain_summary.capital_gains_tax_krw,
        sale_count=sale_count,
    )


def export_summary_csv(form: NTSCapitalGainsForm) -> str:
    """폼 요약을 (field, value) 2열 CSV 로 직렬화."""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["항목", "금액(원)"])
    rows = [
        ("과세연도", str(form.tax_year)),
        ("신고기간 시작", str(form.filing_period_start)),
        ("신고기간 종료", str(form.filing_period_end)),
        ("매도건수", str(form.sale_count)),
        ("양도가액", str(form.total_proceeds_krw)),
        ("취득가액", str(form.total_acquisition_cost_krw)),
        ("양도차익", str(form.total_realized_gain_krw)),
        ("기본공제 한도", str(form.basic_deduction_krw)),
        ("기본공제 적용액", str(form.deduction_applied_krw)),
        ("과세표준", str(form.taxable_base_krw)),
        ("국세(양도소득세)", str(form.national_tax_krw)),
        ("지방소득세", str(form.local_tax_krw)),
        ("납부세액 합계", str(form.total_tax_krw)),
        ("손익통산 후 세액", str(form.t003_combined_tax_krw)),
    ]
    writer.writerows(rows)
    return buf.getvalue()


def export_detail_csv(form: NTSCapitalGainsForm) -> str:
    """종목별 sale_lines 를 CSV 행으로 직렬화 (헤더 포함)."""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "시장",
            "종목코드",
            "매도일",
            "수량",
            "양도가액(원)",
            "취득가액(원)",
            "양도차익(원)",
        ]
    )
    for line in form.sale_lines:
        writer.writerow(
            [
                line.market,
                line.ticker,
                str(line.sell_date),
                str(line.quantity),
                str(line.proceeds_krw),
                str(line.acquisition_cost_krw),
                str(line.realized_gain_krw),
            ]
        )
    return buf.getvalue()
