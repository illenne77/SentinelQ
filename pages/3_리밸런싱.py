"""리밸런싱 계산기 페이지 (T025).

PREREG: PREREG-0012 §2.5
목표 배분 입력 → 이탈도 계산 → 세금 안분 거래금액 제안
NOT in scope: 자동 주문 (ADR-0011·0012)
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from sentinelq.ui.helpers import (
    fmt_krw,
    rebalance_summary,
    rebalance_to_rows,
    validate_target_weights,
)

st.set_page_config(page_title="리밸런싱 계산기 — SentinelQ", layout="wide")

st.title("⚖️ 리밸런싱 계산기")
st.markdown(
    "목표 자산배분 대비 현재 포트폴리오 이탈도를 계산하고, "
    "리밸런싱 거래금액과 예상 양도세를 제시합니다."
)
st.caption("⚠️ 자동 주문 기능은 없습니다. 결과는 참고용 계획입니다.")

# ── 포트폴리오 소스 ────────────────────────────────────────────
portfolio = st.session_state.get("portfolio")

if portfolio is not None:
    st.success(
        f"포트폴리오 대시보드에서 로드됨 "
        f"(총 {len(portfolio.positions)}개 종목, "
        f"평가금액 {fmt_krw(portfolio.total_current_value_krw)})"
    )
else:
    st.info("포트폴리오 대시보드 페이지에서 먼저 계산하면 포트폴리오가 자동 로드됩니다.")
    st.markdown("**또는** 아래에서 총 포트폴리오 금액과 시장별 현재 비중을 직접 입력하세요.")

# ── 목표 배분 입력 ────────────────────────────────────────────
st.subheader("🎯 목표 자산배분 설정")

col1, col2 = st.columns(2)
with col1:
    kr_target = st.slider("국내주식(KR) 목표 비중 (%)", 0, 100, 30, step=5)
with col2:
    us_target = st.slider("해외주식(US) 목표 비중 (%)", 0, 100, 70, step=5)

weights = {"KR": kr_target, "US": us_target}
total_pct = kr_target + us_target

if total_pct != 100:
    st.warning(f"목표 배분 합계: {total_pct}% (100%가 되어야 합니다)")
else:
    st.success(f"목표 배분: KR {kr_target}% / US {us_target}%")

threshold = st.slider(
    "리밸런싱 발동 임계값 (%)",
    min_value=1,
    max_value=20,
    value=5,
    step=1,
    help="현재 비중이 목표 비중에서 이 값 초과로 이탈하면 리밸런싱이 필요합니다.",
)

# ── 계산 ─────────────────────────────────────────────────────
ok, err = validate_target_weights(weights)

if st.button("리밸런싱 계획 계산 🔄", type="primary", disabled=not ok):
    from sentinelq.portfolio.rebalance import TargetAllocation, calculate_rebalance

    if portfolio is None:
        st.error("포트폴리오가 없습니다. 포트폴리오 대시보드 페이지에서 먼저 계산해 주세요.")
        st.stop()

    targets = TargetAllocation.from_dict(weights)
    plan = calculate_rebalance(portfolio, targets, threshold_pct=Decimal(str(threshold)))

    # ── 요약 ─────────────────────────────────────────────────
    summary = rebalance_summary(plan)

    needed_icon = "🔴 예" if plan.is_rebalance_needed else "🟢 아니오"
    st.subheader(f"📊 리밸런싱 계획 — 필요 여부: {needed_icon}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 포트폴리오", summary["총 포트폴리오"])
    m2.metric("총 매도금액", summary["총 매도금액"])
    m3.metric("총 매수금액", summary["총 매수금액"])
    m4.metric("예상 매도세", summary["예상 매도세"])

    # ── 시장별 배분 상세 ─────────────────────────────────────
    st.subheader("📋 시장별 배분 상세")
    rows = rebalance_to_rows(plan)
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "이탈도(%)": st.column_config.ProgressColumn(
                    min_value=-30,
                    max_value=30,
                    format="%.2f%%",
                ),
            },
        )

    if plan.is_rebalance_needed:
        st.info(
            f"현재 비중이 목표 대비 {threshold}%p 초과로 이탈한 시장이 있습니다. "
            "위 거래금액은 세금 비용을 고려한 참고값입니다."
        )
    else:
        st.success(f"모든 시장의 이탈도가 임계값 {threshold}% 이내입니다. 리밸런싱 불필요.")

elif not ok:
    st.error(err)
else:
    st.info("목표 배분을 설정하고 '계산' 버튼을 누르세요.")
