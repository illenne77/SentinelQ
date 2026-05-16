"""UI 헬퍼 함수 (T024) — 순수 함수, Streamlit 미의존.

PREREG: PREREG-0012 §2.1
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from sentinelq.adapters.dart_api import DisclosureRecord
from sentinelq.portfolio.after_tax import AfterTaxPortfolio
from sentinelq.portfolio.rebalance import RebalancePlan


def fmt_krw(amount: Decimal | int | float) -> str:
    """금액 → '1,234,567 원' 형식 (음수는 '-1,234,567 원')."""
    v = int(Decimal(str(amount)))
    sign = "-" if v < 0 else ""
    return f"{sign}{abs(v):,} 원"


def fmt_pct(pct: Decimal | float, *, decimals: int = 2) -> str:
    """비율 → '+1.23%' 형식."""
    return f"{float(pct):+.{decimals}f}%"


def validate_target_weights(weights: dict[str, float | int]) -> tuple[bool, str]:
    """목표 배분 합계 검증.

    합계가 100% ±1% 범위를 벗어나면 False와 오류 메시지를 반환한다.
    """
    if not weights:
        return False, "최소 1개 이상의 시장을 입력하세요."
    total = sum(float(v) for v in weights.values())
    if abs(total - 100.0) > 1.0:
        return False, f"목표 배분 합계가 100%이어야 합니다 (현재 {total:.1f}%)."
    return True, ""


def portfolio_to_rows(portfolio: AfterTaxPortfolio) -> list[dict[str, Any]]:
    """AfterTaxPortfolio → st.dataframe 표시용 행 목록."""
    return [
        {
            "종목코드": pos.ticker,
            "종목명": pos.name,
            "시장": pos.market,
            "수량": int(pos.quantity),
            "매입원가(원)": int(pos.cost_basis_krw),
            "평가금액(원)": int(pos.current_value_krw),
            "미실현손익(원)": int(pos.unrealized_gain_krw),
            "세전수익률(%)": float(pos.unrealized_return_pct),
            "예상세금(원)": int(pos.estimated_tax_krw),
            "세후손익(원)": int(pos.after_tax_gain_krw),
            "세후수익률(%)": float(pos.after_tax_return_pct),
        }
        for pos in portfolio.positions
    ]


def portfolio_summary(portfolio: AfterTaxPortfolio) -> dict[str, str]:
    """포트폴리오 요약 메트릭 (형식화된 문자열 dict)."""
    return {
        "총 매입원가": fmt_krw(portfolio.total_cost_krw),
        "총 평가금액": fmt_krw(portfolio.total_current_value_krw),
        "미실현 손익": fmt_krw(portfolio.total_unrealized_gain_krw),
        "세전 수익률": fmt_pct(portfolio.total_unrealized_return_pct),
        "예상 양도세": fmt_krw(portfolio.total_estimated_tax_krw),
        "세후 손익": fmt_krw(portfolio.total_after_tax_gain_krw),
        "세후 수익률": fmt_pct(portfolio.total_after_tax_return_pct),
        "잔여 기본공제": fmt_krw(portfolio.remaining_deduction_krw),
    }


def disclosures_to_rows(records: list[DisclosureRecord]) -> list[dict[str, Any]]:
    """DisclosureRecord 목록 → st.dataframe 표시용 행 목록."""
    return [
        {
            "중요도": ("🔴 HIGH" if r.importance == "HIGH" else "🔵 NORMAL"),
            "접수일": str(r.receipt_date),
            "종목코드": r.stock_code,
            "회사명": r.corp_name,
            "공시명": r.report_name,
            "URL": r.url,
        }
        for r in records
    ]


def rebalance_to_rows(plan: RebalancePlan) -> list[dict[str, Any]]:
    """RebalancePlan → st.dataframe 표시용 행 목록."""
    rows = []
    for alloc in plan.allocations:
        if alloc.trade_amount_krw < 0:
            action = "매도"
        elif alloc.trade_amount_krw > 0:
            action = "매수"
        else:
            action = "유지"
        rows.append(
            {
                "시장": alloc.market,
                "현재비중(%)": float(alloc.current_pct),
                "목표비중(%)": float(alloc.target_pct),
                "이탈도(%)": float(alloc.drift_pct),
                "거래금액(원)": int(alloc.trade_amount_krw),
                "액션": action,
                "예상세금(원)": int(alloc.estimated_sell_tax_krw),
            }
        )
    return rows


def rebalance_summary(plan: RebalancePlan) -> dict[str, str]:
    """리밸런싱 플랜 요약 메트릭 (형식화된 문자열 dict)."""
    return {
        "총 포트폴리오": fmt_krw(plan.total_portfolio_krw),
        "리밸런싱 필요": "예" if plan.is_rebalance_needed else "아니오",
        "총 매도금액": fmt_krw(plan.total_sell_amount_krw),
        "총 매수금액": fmt_krw(plan.total_buy_amount_krw),
        "예상 매도세": fmt_krw(plan.total_estimated_sell_tax_krw),
        "세후 순 포트폴리오": fmt_krw(plan.net_after_rebalance_sell_tax_krw),
    }


def env_status() -> dict[str, bool]:
    """필수 환경변수 설정 여부 확인."""
    return {
        "KIS API (KIS_APP_KEY)": bool(os.environ.get("KIS_APP_KEY")),
        "DART API (DART_API_KEY)": bool(os.environ.get("DART_API_KEY")),
        "텔레그램 봇 (TELEGRAM_BOT_TOKEN)": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "텔레그램 채팅 (TELEGRAM_CHAT_ID)": bool(os.environ.get("TELEGRAM_CHAT_ID")),
    }
