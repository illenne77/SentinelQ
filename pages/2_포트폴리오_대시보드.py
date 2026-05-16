"""포트폴리오 대시보드 페이지 (T025).

PREREG: PREREG-0012 §2.4
수동 입력 → 세후 수익률 계산 → 대시보드 표시
"""

from __future__ import annotations

import os
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

# ── KIS 계좌 자동 조회 (로컬 전용) ───────────────────────────
with st.expander("🔗 KIS 증권계좌 자동 조회 (로컬 실행 전용)", expanded=False):
    st.caption(
        "KIS OpenAPI를 통해 보유 종목을 자동으로 불러옵니다.\n\n"
        "⚠️ Streamlit Cloud에서는 KIS API 접근이 제한됩니다. 로컬에서만 동작합니다.\n\n"
        "사전 준비: `.env` 파일에 KIS 키 설정 후 `python scripts/kis_token.py live` 실행 필요."
    )

    _kis_key = os.environ.get("KIS_APP_KEY") or os.environ.get("KIS_LIVE_APP_KEY")
    _kis_secret = os.environ.get("KIS_APP_SECRET") or os.environ.get("KIS_LIVE_APP_SECRET")
    _kis_account = os.environ.get("KIS_ACCOUNT")
    _kis_ready = bool(_kis_key and _kis_secret and _kis_account)

    if not _kis_ready:
        st.warning("KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT 환경변수를 설정해야 합니다.")
    else:
        from sentinelq.adapters.kis_history import SECRETS_DIR

        _token_ok = (SECRETS_DIR / "kis_token_live.json").exists()
        if not _token_ok:
            st.warning(
                "KIS 토큰이 없습니다. 먼저 터미널에서 실행하세요:\n"
                "```\npython scripts/kis_token.py live\n```"
            )

        if st.button("KIS 잔고 조회 🔄", disabled=not _token_ok):
            if not os.environ.get("KIS_LIVE_APP_KEY"):
                os.environ["KIS_LIVE_APP_KEY"] = _kis_key
            if not os.environ.get("KIS_LIVE_APP_SECRET"):
                os.environ["KIS_LIVE_APP_SECRET"] = _kis_secret
            if not os.environ.get("KIS_LIVE_BASE_URL"):
                os.environ["KIS_LIVE_BASE_URL"] = "https://openapi.koreainvestment.com:9443"
            os.environ["SENTINELQ_LIVE_ALLOW"] = "1"

            from sentinelq.adapters.kis_history import fetch_balance

            with st.spinner("KIS 잔고 조회 중..."):
                try:
                    _auto_holdings = fetch_balance(env="live", confirm_live=True)
                except Exception as exc:
                    st.error(f"조회 오류: {exc}")
                    _err = str(exc).lower()
                    if any(k in _err for k in ("timed out", "network", "urlopen", "connection")):
                        st.info(
                            "💡 Streamlit Cloud에서는 KIS API 접근이 제한됩니다. "
                            "로컬에서 실행하세요:\n"
                            "```bash\nstreamlit run streamlit_app.py\n```"
                        )
                    st.stop()

            if not _auto_holdings:
                st.info("조회된 잔고가 없습니다.")
            else:
                st.success(f"{len(_auto_holdings)}개 종목 조회 완료. 아래 표에 자동 입력됩니다.")
                st.session_state["kis_holdings"] = _auto_holdings
                st.rerun()

# ── 보유 종목 입력 테이블 ─────────────────────────────────────
st.subheader("📋 보유 종목 입력")

if "kis_holdings" in st.session_state:
    st.caption("KIS 자동 조회 데이터가 로드됐습니다. 수정 후 계산하기를 누르세요.")
    _h = st.session_state["kis_holdings"]
    _initial = pd.DataFrame(
        [
            {
                "종목코드": h.ticker,
                "종목명": h.name,
                "시장": h.market,
                "수량": h.quantity,
                "평균단가(원)": int(h.avg_price_krw),
                "현재가(원)": int(h.current_price_krw),
            }
            for h in _h
        ]
    )
else:
    st.caption("아래 표에 직접 입력하거나 편집하세요.")
    _initial = pd.DataFrame(
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
    _initial,
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
            market_val = str(row["시장"]).strip()
            currency_val = "USD" if market_val == "US" else "KRW"
            holdings.append(
                HoldingRecord(
                    ticker=str(row["종목코드"]).strip(),
                    name=str(row["종목명"]).strip(),
                    market=market_val,
                    quantity=qty,
                    avg_price_krw=avg_price,
                    cost_basis_krw=cost,
                    current_price_krw=cur_price,
                    current_value_krw=value,
                    unrealized_gain_krw=value - cost,
                    currency=currency_val,
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

    st.session_state["portfolio"] = portfolio
    st.caption("※ 이 포트폴리오 데이터가 리밸런싱 계산기 페이지에서 자동 로드됩니다.")

else:
    st.info("위 표에 보유 종목을 입력하고 '계산하기' 버튼을 누르세요.")
