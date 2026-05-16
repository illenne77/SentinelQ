"""홈택스 양도소득세 신고서 자동완성 가이드 생성 (T011).

PREREG: PREREG-0008-amendment-2 §2.5
Mandate: 홈택스 입력 자동화 보조 — 입력값 자동 계산, 절차 안내

OUT-of-scope: 홈택스 API 자동 제출 (NTS 미공개), 종합소득세, 대주주 판정.

생성 결과:
- ``<stem>_hometax_guide.txt``  — 홈택스 입력 가이드 (절차 + 필드별 값)
- ``<stem>_hometax_trades.csv`` — 종목별 매도 명세 (홈택스 "자산명세" 화면 입력용)
"""

from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
from pathlib import Path

from sentinelq.reports.nts_form import NTSCapitalGainsForm


def _fmt(amount: Decimal | int) -> str:
    """원화 금액을 천 단위 쉼표 정수 문자열로."""
    return f"{int(amount):,}"


def build_hometax_guide(form: NTSCapitalGainsForm) -> str:
    """NTSCapitalGainsForm → 홈택스 입력 가이드 텍스트."""
    buf = StringIO()
    w = buf.write

    w("=" * 70 + "\n")
    w("  국세청 홈택스 양도소득세 신고서 입력 가이드\n")
    w(
        f"  과세기간: {form.tax_year}년 (신고기간: {form.filing_period_start} ~ {form.filing_period_end})\n"
    )
    w("=" * 70 + "\n\n")

    w("■ 신고 방법\n")
    w("  홈택스 (hometax.go.kr) 접속 → 로그인\n")
    w("  → [신고/납부] → [세금신고] → [양도소득세]\n")
    w("  → [확정신고] → [주식·파생상품등] → 일반 신고서 작성\n\n")

    w("■ 기본 정보 입력\n")
    w(f"  - 과세기간 시작: {form.tax_year}-01-01\n")
    w(f"  - 과세기간 종료: {form.tax_year}-12-31\n")
    w(f"  - 거래 건수: {form.sale_count}건\n\n")

    w("■ 홈택스 [자산양도명세] 화면 — 총괄 금액\n")
    w(f"  양도가액 합계  : {_fmt(form.total_proceeds_krw)} 원\n")
    w(f"  취득가액 합계  : {_fmt(form.total_acquisition_cost_krw)} 원\n")
    w("  필요경비 합계  : 0 원 (수수료는 취득가액에 포함)\n")
    w(f"  양도차익 합계  : {_fmt(form.total_realized_gain_krw)} 원\n\n")

    w("■ 시장별 구분 입력\n")
    for bd in form.by_market:
        label = "국내주식" if bd.market == "KR" else "해외주식"
        w(f"  [{label}] 양도가액: {_fmt(bd.total_proceeds_krw)} 원 / ")
        w(f"양도차익: {_fmt(bd.total_realized_gain_krw)} 원\n")
    w("\n")

    w("■ 홈택스 [세액계산] 화면\n")
    w(f"  양도소득금액 (양도차익 합계) : {_fmt(form.total_realized_gain_krw)} 원\n")
    w(f"  기본공제                    : {_fmt(form.deduction_applied_krw)} 원\n")
    w(f"  과세표준                    : {_fmt(form.taxable_base_krw)} 원\n")
    w("  세율                        : 20%\n")
    w(f"  산출세액 (국세)             : {_fmt(form.national_tax_krw)} 원\n")
    w(f"  지방소득세                  : {_fmt(form.local_tax_krw)} 원\n")
    w("    └ 국세청 홈택스가 아닌 [위택스]에서 별도 신고\n")
    w(f"  홈택스 납부세액             : {_fmt(form.national_tax_krw)} 원\n\n")

    if form.taxable_base_krw <= 0:
        w("  ※ 과세표준 ≤ 0 → 납부세액 없음 (신고 의무는 있음)\n\n")

    w("■ 증빙서류 준비 (신고 후 [증빙서류 제출] 화면)\n")
    w("  1. 주식 거래내역 확인서 — 증권사 앱/HTS에서 '거래내역 확인서' 발급\n")
    w("  2. 해외주식의 경우 환율 증빙 — 한국은행 기준환율 또는 매매기준율\n")
    w("  ※ SentinelQ 출력 CSV는 내부 검증용이며 NTS 공식 제출 서류가 아닙니다.\n")
    w("     증권사 발급 '거래내역 확인서'를 첨부하세요.\n\n")

    w("■ 종목별 자산명세 입력 (하단 참조 또는 *_hometax_trades.csv 파일)\n")
    if form.sale_lines:
        w(f"  {'매도일':<12} {'종목':<8} {'양도가액':>14} {'취득가액':>14} {'양도차익':>14}\n")
        w("  " + "-" * 68 + "\n")
        for sl in form.sale_lines:
            w(
                f"  {sl.sell_date!s:<12} {sl.ticker:<8} "
                f"{_fmt(sl.proceeds_krw):>14} {_fmt(sl.acquisition_cost_krw):>14} "
                f"{_fmt(sl.realized_gain_krw):>14}\n"
            )
    else:
        w("  (매도 내역 없음)\n")

    w("\n")
    w("■ 신고 마감일\n")
    w(f"  {form.filing_period_end} (성실신고확인서 미제출자 기준)\n\n")
    w("=" * 70 + "\n")
    w("  ※ 본 가이드는 SentinelQ가 자동 생성한 보조 자료입니다.\n")
    w("     최종 세액은 세무사 또는 국세청 홈택스를 통해 확인하세요.\n")
    w("=" * 70 + "\n")

    return buf.getvalue()


def build_hometax_trades_csv(form: NTSCapitalGainsForm) -> str:
    """종목별 매도 명세 CSV (홈택스 자산명세 입력용)."""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "매도일",
            "시장",
            "종목코드",
            "매도수량",
            "양도가액(원)",
            "취득가액(원)",
            "양도차익(원)",
        ]
    )
    for sl in form.sale_lines:
        writer.writerow(
            [
                str(sl.sell_date),
                sl.market,
                sl.ticker,
                sl.quantity,
                int(sl.proceeds_krw),
                int(sl.acquisition_cost_krw),
                int(sl.realized_gain_krw),
            ]
        )
    return buf.getvalue()


def export_hometax_guide(
    form: NTSCapitalGainsForm,
    out_dir: Path,
    stem: str = "hometax",
) -> tuple[Path, Path]:
    """가이드 텍스트·종목 CSV를 파일로 저장.

    Returns
    -------
    (guide_path, trades_csv_path)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    guide_path = out_dir / f"{stem}_hometax_guide.txt"
    trades_path = out_dir / f"{stem}_hometax_trades.csv"

    guide_path.write_text(build_hometax_guide(form), encoding="utf-8")
    trades_path.write_text(build_hometax_trades_csv(form), encoding="utf-8")

    return guide_path, trades_path
