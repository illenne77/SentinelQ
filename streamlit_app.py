"""SentinelQ — KR Investor Tools (Home).

PREREG: PREREG-0012 §2.2
실행: streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from sentinelq.ui.helpers import env_status

st.set_page_config(
    page_title="SentinelQ — KR Investor Tools",
    page_icon="📊",
    layout="wide",
)

st.title("📊 SentinelQ — KR Investor Tools")
st.markdown("**KR 개인 투자자를 위한 세금 계산 + 공시 모니터링 도구**")
st.divider()

# ── 기능 페이지 소개 ──────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.info(
        "### 💰 양도세 계산기\n\n"
        "키움/미래에셋 HTS CSV 업로드 → "
        "양도세 자동 계산 → NTS 홈택스 입력용 양식 출력\n\n"
        "← 사이드바에서 이동"
    )

with col2:
    st.info(
        "### 📈 포트폴리오 대시보드\n\n"
        "보유 종목 입력 → 세전·세후 수익률 비교 →"
        " 기본공제 잔여액 확인\n\n"
        "← 사이드바에서 이동"
    )

with col3:
    st.info(
        "### ⚖️ 리밸런싱 계산기\n\n"
        "목표 배분 설정 → 이탈도 계산 → "
        "세금 안분 거래금액 제안 (자동 주문 없음)\n\n"
        "← 사이드바에서 이동"
    )

with col4:
    st.info(
        "### 🔔 DART 공시\n\n"
        "보유 종목 코드 입력 → DART 신규 공시 조회 → "
        "HIGH 중요도 필터링\n\n"
        "← 사이드바에서 이동"
    )

st.divider()

# ── 환경변수 상태 ─────────────────────────────────────────────
st.subheader("⚙️ 환경변수 설정 현황")

status = env_status()
cols = st.columns(len(status))
for col, (label, is_set) in zip(cols, status.items(), strict=False):
    icon = "✅" if is_set else "❌"
    col.metric(label=label, value=f"{icon} {'설정됨' if is_set else '미설정'}")

st.caption(
    "환경변수는 프로젝트 루트의 `.env` 파일 또는 시스템 환경변수로 설정하세요. "
    "양도세 계산기·포트폴리오 기능은 환경변수 없이도 수동 입력으로 사용할 수 있습니다."
)
