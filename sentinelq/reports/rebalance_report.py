"""리밸런싱 실행 계획 리포트 생성 (T018).

PREREG: PREREG-0010 §2.5

생성 결과:
- ``<stem>_rebalance.txt`` — 텍스트 리밸런싱 계획 (CLI 출력용)
- ``<stem>_rebalance.csv`` — 시장별 배분 데이터 (스프레드시트 가공용)
"""

from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
from pathlib import Path

from sentinelq.portfolio.rebalance import RebalancePlan


def _fmt(amount: Decimal | int) -> str:
    v = int(amount)
    sign = "-" if v < 0 else ""
    return f"{sign}{abs(v):,}"


def _pct_str(pct: Decimal) -> str:
    return f"{pct:+.2f}%"


def build_rebalance_report(plan: RebalancePlan, *, as_of: str = "") -> str:
    """RebalancePlan → 텍스트 리밸런싱 계획."""
    buf = StringIO()
    w = buf.write

    w("=" * 72 + "\n")
    w("  패시브 리밸런싱 실행 계획\n")
    if as_of:
        w(f"  기준일: {as_of}\n")
    w("=" * 72 + "\n\n")

    # 포트폴리오 현황
    w("■ 포트폴리오 현황\n")
    w(f"  총 자산    : {_fmt(plan.total_portfolio_krw)} 원\n")
    w(f"  발동 임계값: 편차 {plan.threshold_pct}% 이상 시 리밸런싱 권장\n")
    if plan.is_rebalance_needed:
        w("  상태       : 리밸런싱 필요\n")
    else:
        w("  상태       : 목표 배분 유지 중 (리밸런싱 불필요)\n")
    w("\n")

    # 시장별 배분 표
    w("■ 시장별 배분 현황\n")
    hdr = (
        f"  {'시장':<6} {'목표':>7} {'현재':>7} {'편차':>8}"
        f" {'현재금액(원)':>16} {'목표금액(원)':>16} {'매수/매도(원)':>16}\n"
    )
    w(hdr)
    w("  " + "-" * 84 + "\n")
    for a in plan.allocations:
        if a.trade_amount_krw > 0:
            trade_str = f"+{_fmt(a.trade_amount_krw)}"
        else:
            trade_str = _fmt(a.trade_amount_krw)
        w(
            f"  {a.market:<6} {a.target_pct!s:>6}% {a.current_pct!s:>6}%"
            f" {_pct_str(a.drift_pct):>8}"
            f" {_fmt(a.current_value_krw):>16}"
            f" {_fmt(a.target_value_krw):>16}"
            f" {trade_str:>16}\n"
        )
    w("\n")

    # 실행 요약
    w("■ 리밸런싱 실행 요약\n")
    w(f"  총 매도 필요금액  : {_fmt(plan.total_sell_amount_krw)} 원\n")
    w(f"  총 매수 필요금액  : {_fmt(plan.total_buy_amount_krw)} 원\n")
    w(f"  매도 시 예상 세금 : {_fmt(plan.total_estimated_sell_tax_krw)} 원\n")
    w(f"  세금 차감 후 자산 : {_fmt(plan.net_after_rebalance_sell_tax_krw)} 원\n")
    w("\n")

    # 실행 가이드 (리밸런싱 필요한 경우만)
    if plan.is_rebalance_needed:
        w("■ 실행 가이드 (시장 단위 — 종목 선정은 투자자 결정)\n")
        for a in plan.allocations:
            if a.trade_amount_krw < 0:
                w(
                    f"  ▼ {a.market} 시장 ETF/종목 {_fmt(abs(a.trade_amount_krw))}원 매도"
                    f"  (편차 {_pct_str(a.drift_pct)}"
                    f", 세금 추정 {_fmt(a.estimated_sell_tax_krw)}원)\n"
                )
            elif a.trade_amount_krw > 0:
                w(
                    f"  ▲ {a.market} 시장 ETF/종목 {_fmt(a.trade_amount_krw)}원 매수"
                    f"  (편차 {_pct_str(a.drift_pct)})\n"
                )
        w("\n")

    w("=" * 72 + "\n")
    w("  ※ 이 계획은 목표 배분 기준 기계적 추정값입니다.\n")
    w("     종목 선정·매매 시점은 투자자 본인이 결정하십시오.\n")
    w("     예상 세금은 해당 시장 보유분 전체 기준 비례 추정입니다.\n")
    w("=" * 72 + "\n")

    return buf.getvalue()


def build_rebalance_csv(plan: RebalancePlan) -> str:
    """시장별 배분 데이터 CSV."""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "시장",
            "목표비중(%)",
            "현재비중(%)",
            "편차(%)",
            "현재금액(원)",
            "목표금액(원)",
            "매수_매도금액(원)",
            "매도세금추정(원)",
        ]
    )
    for a in plan.allocations:
        writer.writerow(
            [
                a.market,
                str(a.target_pct),
                str(a.current_pct),
                str(a.drift_pct),
                int(a.current_value_krw),
                int(a.target_value_krw),
                int(a.trade_amount_krw),
                int(a.estimated_sell_tax_krw),
            ]
        )
    return buf.getvalue()


def export_rebalance_report(
    plan: RebalancePlan,
    out_dir: Path,
    stem: str = "rebalance",
    *,
    as_of: str = "",
) -> tuple[Path, Path]:
    """텍스트 리포트와 CSV를 파일로 저장.

    Returns
    -------
    (txt_path, csv_path)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / f"{stem}_rebalance.txt"
    csv_path = out_dir / f"{stem}_rebalance.csv"

    txt_path.write_text(build_rebalance_report(plan, as_of=as_of), encoding="utf-8")
    csv_path.write_text(build_rebalance_csv(plan), encoding="utf-8")

    return txt_path, csv_path
