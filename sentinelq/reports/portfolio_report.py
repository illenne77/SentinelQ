"""포트폴리오 대시보드 리포트 생성 (T015).

PREREG: PREREG-0009 §2.3
Mandate: 세전·세후 수익률 비교 대시보드 — SaaS 핵심 차별화 기능

생성 결과:
- ``<stem>_portfolio.txt``  — 텍스트 대시보드 (CLI 출력용)
- ``<stem>_portfolio.csv``  — 종목별 데이터 (스프레드시트 가공용)
"""

from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
from pathlib import Path

from sentinelq.portfolio.after_tax import AfterTaxPortfolio


def _fmt(amount: Decimal | int) -> str:
    v = int(amount)
    sign = "-" if v < 0 else ""
    return f"{sign}{abs(v):,}"


def _pct_str(pct: Decimal) -> str:
    return f"{pct:+.2f}%"


def build_portfolio_report(
    portfolio: AfterTaxPortfolio,
    *,
    as_of: str = "",
) -> str:
    """AfterTaxPortfolio → 텍스트 대시보드."""
    buf = StringIO()
    w = buf.write

    w("=" * 72 + "\n")
    w("  포트폴리오 세후 수익률 대시보드\n")
    if as_of:
        w(f"  기준일: {as_of}\n")
    w("=" * 72 + "\n\n")

    # ── 포트폴리오 요약 ──
    w("■ 포트폴리오 요약\n")
    w(f"  총 매입원가  : {_fmt(portfolio.total_cost_krw)} 원\n")
    w(f"  총 평가금액  : {_fmt(portfolio.total_current_value_krw)} 원\n")
    w(
        f"  미실현 손익  : {_fmt(portfolio.total_unrealized_gain_krw)} 원  "
        f"({_pct_str(portfolio.total_unrealized_return_pct)})\n"
    )
    w(f"  예상 양도세  : {_fmt(portfolio.total_estimated_tax_krw)} 원  (오늘 전량 매도 시 추정)\n")
    w(
        f"  세후 미실현  : {_fmt(portfolio.total_after_tax_gain_krw)} 원  "
        f"({_pct_str(portfolio.total_after_tax_return_pct)})\n"
    )
    w("\n")

    # ── 기본공제 현황 ──
    w("■ 기본공제 현황 (양도세 250만원 공제)\n")
    w(f"  당해 실현 손익  : {_fmt(portfolio.realized_gain_ytd_krw)} 원\n")
    w(f"  잔여 기본공제   : {_fmt(portfolio.remaining_deduction_krw)} 원\n")
    if portfolio.remaining_deduction_krw >= Decimal("2_500_000"):
        w("  → 아직 250만원 기본공제 전액 미사용\n")
    elif portfolio.remaining_deduction_krw > 0:
        w(f"  → 잔여 {_fmt(portfolio.remaining_deduction_krw)}원까지 추가 손익은 비과세\n")
    else:
        w("  → 기본공제 소진 — 추가 실현 손익에 22% 과세\n")
    w("\n")

    # ── 종목별 상세 ──
    w("■ 종목별 세후 손익\n")
    if not portfolio.positions:
        w("  (보유 종목 없음)\n")
    else:
        hdr = f"  {'종목':<8} {'시장':<4} {'수량':>6} {'매입원가':>14} {'평가금액':>14} {'세전손익':>14} {'세후손익':>14} {'세후수익률':>10}\n"
        w(hdr)
        w("  " + "-" * 86 + "\n")
        for pos in portfolio.positions:
            w(
                f"  {pos.ticker:<8} {pos.market:<4} {pos.quantity:>6,} "
                f"{_fmt(pos.cost_basis_krw):>14} "
                f"{_fmt(pos.current_value_krw):>14} "
                f"{_fmt(pos.unrealized_gain_krw):>14} "
                f"{_fmt(pos.after_tax_gain_krw):>14} "
                f"{_pct_str(pos.after_tax_return_pct):>10}\n"
            )
    w("\n")

    w("=" * 72 + "\n")
    w("  ※ 예상 양도세는 오늘 전량 매도 기준 추정값입니다.\n")
    w("     실제 세액은 매도 시점의 환율·취득가액에 따라 달라집니다.\n")
    w("=" * 72 + "\n")

    return buf.getvalue()


def build_portfolio_csv(portfolio: AfterTaxPortfolio) -> str:
    """종목별 세후 손익 CSV."""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "종목코드",
            "종목명",
            "시장",
            "수량",
            "매입원가(원)",
            "평가금액(원)",
            "미실현손익(원)",
            "세전수익률(%)",
            "예상세금(원)",
            "세후손익(원)",
            "세후수익률(%)",
        ]
    )
    for pos in portfolio.positions:
        writer.writerow(
            [
                pos.ticker,
                pos.name,
                pos.market,
                pos.quantity,
                int(pos.cost_basis_krw),
                int(pos.current_value_krw),
                int(pos.unrealized_gain_krw),
                str(pos.unrealized_return_pct),
                int(pos.estimated_tax_krw),
                int(pos.after_tax_gain_krw),
                str(pos.after_tax_return_pct),
            ]
        )
    return buf.getvalue()


def export_portfolio_report(
    portfolio: AfterTaxPortfolio,
    out_dir: Path,
    stem: str = "portfolio",
    *,
    as_of: str = "",
) -> tuple[Path, Path]:
    """텍스트 리포트와 CSV를 파일로 저장.

    Returns
    -------
    (txt_path, csv_path)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / f"{stem}_portfolio.txt"
    csv_path = out_dir / f"{stem}_portfolio.csv"

    txt_path.write_text(build_portfolio_report(portfolio, as_of=as_of), encoding="utf-8")
    csv_path.write_text(build_portfolio_csv(portfolio), encoding="utf-8")

    return txt_path, csv_path
