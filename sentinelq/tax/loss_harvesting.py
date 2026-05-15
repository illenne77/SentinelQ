"""12월 손실 인식 권장 — KR 양도세 절세 시뮬레이션 (Phase 3 T005).

spec: ``.claude/queue/spec-T005.md``
PREREG: ``docs/preregistration/PREREG-0008-tax-tool.md`` §2.4
predecessor: T003 (``sentinelq.tax.capital_gains.TaxYearSummary`` 입력)

본 모듈 책임:

* 12월 1~30일 창에서 실현 양도차익이 기본공제를 초과할 경우
  보유 종목의 미실현 손실 중 통산 가능 분량을 계산하고 권장 목록을 반환한다.
* 자동 매매 X — 단순 추천만 표시, 최종 판단은 사용자 몫.
* 현재가(current_price_krw)는 외부에서 주입 — 본 모듈은 시세를 직접 조회하지 않는다.
* 절세액 계산은 TaxYearSummary.rules (TaxYearRules) 재사용 (22% 등 상수 중복 금지).

비스코프 (T005 OUT):

* 자동 매매·주문 호출 (mandate 위반, ADR-0011·0012·0013)
* 실시간 시세 fetch (KIS API 호출 — T001 어댑터 영역)
* ISA·연금저축 내 손실 (비과세 계좌 손익통산 불가)
* 배당소득 처리
* NTS 양식 PDF 출력 (T006 영역)
* 세제 우대 한도 추적 (T004 영역)
* 양도세 계산 자체 (T003 영역 — T005는 T003 결과 소비)

mandate 위반 금지 (ADR-0011·0012·0013): 알파·자동매매·시장 타이밍 코드 없음.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal

from sentinelq.tax.capital_gains import TaxYearSummary

# ---- 예외 ----


class LossHarvestingError(Exception):
    """loss_harvesting 모듈 공통 base 예외."""


# ---- 입력 타입 ----


@dataclass(frozen=True)
class HoldingSnapshot:
    """보유 종목 현재 상태 (외부 주입 — 본 모듈은 시세 미조회).

    current_price_krw: 현재 단가 KRW 환산 (해외주식은 fx_rate 환산 후 주입).
    avg_cost_krw: 평균 취득단가 KRW 환산 (T002 TaxLotLedger 등에서 산출 후 주입).
    """

    ticker: str
    market: str  # "KR" | "US"
    quantity: Decimal  # 보유 수량 (양수)
    avg_cost_krw: Decimal  # 평균 취득단가 KRW (양수)
    current_price_krw: Decimal  # 현재 단가 KRW (양수)

    @property
    def unrealized_gain_krw(self) -> Decimal:
        """미실현 손익 (음수 = 손실)."""
        return (self.current_price_krw - self.avg_cost_krw) * self.quantity


# ---- 결과 타입 ----


@dataclass(frozen=True)
class HarvestCandidate:
    """개별 손실 인식 권장 종목."""

    ticker: str
    market: str
    quantity: Decimal  # 전체 보유 수량 (전량 매도 시나리오 기준)
    unrealized_loss_krw: Decimal  # 미실현 손실 (음수 — 절대값이 클수록 절세 효과 큼)
    estimated_saving_krw: Decimal  # 전량 매도 시 절세액 (ROUND_DOWN, 양수)


@dataclass(frozen=True)
class LossHarvestingResult:
    """12월 손실 인식 권장 결과."""

    tax_year: int
    check_date: date
    is_december_window: bool  # 12월 1~30일 여부 (12월 31일 제외)
    current_realized_gain_krw: Decimal  # TaxYearSummary.total_realized_gain_krw
    current_tax_krw: Decimal  # TaxYearSummary.capital_gains_tax_krw
    loss_candidates: tuple[HarvestCandidate, ...]  # 손실 큰 순 (unrealized_loss 오름차순)
    total_harvestable_loss_krw: Decimal  # 모든 candidates 손실 합산 (≤ 0)
    loss_needed_to_zero_tax_krw: Decimal  # taxable_base_krw (이만큼 손실이면 세금 0)
    estimated_max_saving_krw: Decimal  # 전량 수확 시 최대 절세액 (ROUND_DOWN, ≥ 0)
    is_harvest_recommended: bool  # 12월 창 + gain > deduction + candidates exist


# ---- 내부 헬퍼 ----


def _is_december_window(d: date) -> bool:
    return d.month == 12 and 1 <= d.day <= 30


def _build_candidate(holding: HoldingSnapshot, tax_rate: Decimal) -> HarvestCandidate:
    loss = holding.unrealized_gain_krw  # 음수 보장 (호출 전 필터링됨)
    raw_saving = abs(loss) * tax_rate
    saving = raw_saving.quantize(Decimal("1"), rounding=ROUND_DOWN)
    return HarvestCandidate(
        ticker=holding.ticker,
        market=holding.market,
        quantity=holding.quantity,
        unrealized_loss_krw=loss,
        estimated_saving_krw=saving,
    )


# ---- public API ----


def recommend_loss_harvest(
    gain_summary: TaxYearSummary,
    holdings: Iterable[HoldingSnapshot],
    check_date: date | None = None,
) -> LossHarvestingResult:
    """12월 손실 인식 권장 계산.

    gain_summary: T003 calculate_year 결과 (당해 실현 손익·세금 기준선).
    holdings: 보유 종목 현재 상태 목록 (시세는 외부에서 주입).
    check_date: 날짜 기준 (None이면 date.today()).
                12월 1~30일이어야 is_december_window=True.
    """
    resolved_date = check_date if check_date is not None else date.today()
    in_window = _is_december_window(resolved_date)
    tax_rate = gain_summary.rules.tax_rate

    # 손실 후보 필터: 수량 > 0 이고 미실현 손실(gain < 0)인 종목만
    candidates: list[HarvestCandidate] = []
    for h in holdings:
        if h.quantity <= Decimal("0"):
            continue
        if h.unrealized_gain_krw >= Decimal("0"):
            continue
        candidates.append(_build_candidate(h, tax_rate))

    # 손실 큰 순 정렬 (unrealized_loss_krw 오름차순 = 음수가 더 작은 값이 앞)
    candidates.sort(key=lambda c: c.unrealized_loss_krw)

    total_loss = sum((c.unrealized_loss_krw for c in candidates), Decimal("0"))
    taxable_base = gain_summary.taxable_base_krw

    harvestable_abs = abs(total_loss)
    offset = min(harvestable_abs, taxable_base)
    raw_max_saving = offset * tax_rate
    max_saving = raw_max_saving.quantize(Decimal("1"), rounding=ROUND_DOWN)

    basic_deduction = gain_summary.rules.basic_deduction_krw
    is_recommended = (
        in_window and gain_summary.total_realized_gain_krw > basic_deduction and len(candidates) > 0
    )

    return LossHarvestingResult(
        tax_year=gain_summary.tax_year,
        check_date=resolved_date,
        is_december_window=in_window,
        current_realized_gain_krw=gain_summary.total_realized_gain_krw,
        current_tax_krw=gain_summary.capital_gains_tax_krw,
        loss_candidates=tuple(candidates),
        total_harvestable_loss_krw=total_loss,
        loss_needed_to_zero_tax_krw=taxable_base,
        estimated_max_saving_krw=max_saving,
        is_harvest_recommended=is_recommended,
    )
