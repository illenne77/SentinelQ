"""포트폴리오 대시보드 페이지 (T025).

PREREG: PREREG-0012 §2.4
수동 입력 → 세후 수익률 계산 → 대시보드 표시
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from sentinelq.ui.helpers import fmt_krw, portfolio_summary, portfolio_to_rows

st.set_page_config(page_title="포트폴리오 대시보드 — SentinelQ", layout="wide")

st.title("📈 포트폴리오 대시보드")
st.markdown("보유 종목을 입력하면 세전·세후 수익률을 비교해 줍니다.")

# ── 당해 실현 손익 입력 ───────────────────────────────────────
with st.expander("📅 당해 연도 기 실현 손익 (기본공제 계산용)", expanded=False):
    realized_gain = st.number_input(
        "당해 연도 기 실현 양도차익 (원)",
        min_value=0,
        value=0,
        step=100_000,
        help="올해 이미 실현한 양도차익. 0이면 기본공제 250만원 전액 미사용.",
    )

st.subheader("📋 보유 종목 입력")
st.caption("아래 표에 직접 입력하거나 편집하세요.")

# ── 기본 예시 데이터 ─────────────────────────────────────────
_DEFAULT = pd.DataFrame(
    {
        "종목코드": ["005930", "AAPL"],
        "종목명": ["삼성전자", "Apple Inc"],
        "시장": ["KR", "US"],
        "수량": [10, 5],
        "평균단가(원)": [70_000, 1_800_000],
        "현재가(원)": [78_000, 2_100_000],
    }
)

edited = st.data_editor(
    _DEFAULT,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "시장": st.column_config.SelectboxColumn(options=["KR", "US"], required=True),
        "수량": st.column_config.NumberColumn(min_value=0, step=1),
        "평균단가(원)": st.column_config.NumberColumn(min_value=0, step=1_000),
        "현재가(원)": st.column_config.NumberColumn(min_value=0, step=1_000),
    },
)

if st.button("계산하기 🔄", type="primary"):
    if edited.empty or len(edited) == 0:
        st.warning("종목을 1개 이상 입력해 주세요.")
        st.stop()

    # HoldingRecord 생성
    from sentinelq.adapters.kis_history import HoldingRecord
    from sentinelq.portfolio.after_tax import calculate_after_tax

    holdings = []
    errors = []
    for i, row in edited.iterrows():
        try:
            qty = int(row["수량"])
            avg_price = Decimal(str(int(row["평균단가(원)"])))
            cur_price = Decimal(str(int(row["현재가(원)"])))
            if qty <= 0:
                continue
            cost = avg_price * qty
            value = cur_price * qty
            holdings.append(
                HoldingRecord(
                    ticker=str(row["종목코드"]).strip(),
                    name=str(row["종목명"]).strip(),
                    market=str(row["시장"]).strip(),
                    quantity=qty,
                    cost_basis_krw=cost,
                    current_value_krw=value,
                    unrealized_gain_krw=value - cost,
                )
            )
        except Exception as exc:
            errors.append(f"행 {i + 1}: {exc}")

    if errors:
        for e in errors:
            st.warning(e)

    if not holdings:
        st.warning("유효한 종목이 없습니다.")
        st.stop()

    portfolio = calculate_after_tax(
        holdings,
        realized_gain_ytd_krw=Decimal(str(int(realized_gain))),
    )

    # ── 요약 메트릭 ─────────────────────────────────────────
    st.subheader("📊 포트폴리오 요약")
    summary = portfolio_summary(portfolio)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 평가금액", summary["총 평가금액"])
    m2.metric("미실현 손익", summary["미실현 손익"], delta=summary["세전 수익률"])
    m3.metric("세후 손익", summary["세후 손익"], delta=summary["세후 수익률"])
    m4.metric("예상 양도세", summary["예상 양도세"])

    m5, m6 = st.columns(2)
    m5.metric("잔여 기본공제", summary["잔여 기본공제"])
    if portfolio.remaining_deduction_krw >= Decimal("2_500_000"):
        m6.info("250만원 기본공제 전액 미사용")
    elif portfolio.remaining_deduction_krw > 0:
        m6.info(f"잔여 {fmt_krw(portfolio.remaining_deduction_krw)}까지 추가 손익 비과세")
    else:
        m6.warning("기본공제 소진 — 추가 실현 손익에 22% 과세")

    # ── 종목별 상세 ─────────────────────────────────────────
    st.subheader("📋 종목별 세후 손익")
    rows = portfolio_to_rows(portfolio)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("보유 종목 없음")

    # 세션 상태에 포트폴리오 저장 (리밸런싱 페이지 연동)
    st.session_state["portfolio"] = portfolio
    st.caption("※ 이 포트폴리오 데이터가 리밸런싱 계산기 페이지에서 자동 로드됩니다.")

else:
    st.info("위 표에 보유 종목을 입력하고 '계산하기' 버튼을 누르세요.")
