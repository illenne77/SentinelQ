"""DART 공시 모니터링 페이지 (T025).

PREREG: PREREG-0012 §2.6
종목코드 입력 → DART API → 공시 목록 조회 + 중요도 필터
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from sentinelq.ui.helpers import disclosures_to_rows

st.set_page_config(page_title="DART 공시 — SentinelQ", layout="wide")

st.title("🔔 DART 공시 모니터링")
st.markdown("보유 종목의 신규 공시를 DART에서 조회합니다.")

# ── 입력 ─────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])

with col1:
    tickers_input = st.text_input(
        "종목코드 (쉼표 또는 공백 구분)",
        placeholder="005930, 000660, AAPL",
        help="국내주식 6자리 코드 (예: 005930). 해외주식은 DART 미지원.",
    )

with col2:
    days_back = st.number_input("조회 기간 (일)", min_value=1, max_value=90, value=7, step=1)

col3, col4 = st.columns(2)
with col3:
    importance = st.radio(
        "중요도 필터",
        ["HIGH만", "전체"],
        horizontal=True,
        help="HIGH: 유상증자·합병·상장폐지 등 주요 이슈만 표시",
    )

with col4:
    dart_api_key = st.text_input(
        "DART API 키",
        value=os.environ.get("DART_API_KEY", ""),
        type="password",
        help="미입력 시 DART_API_KEY 환경변수 사용. opendart.fss.or.kr에서 발급.",
    )

# ── 조회 ─────────────────────────────────────────────────────
if st.button("공시 조회 🔄", type="primary"):
    if not tickers_input.strip():
        st.warning("종목코드를 입력해 주세요.")
        st.stop()

    if not dart_api_key.strip():
        st.error("DART API 키를 입력하거나 DART_API_KEY 환경변수를 설정해 주세요.")
        st.stop()

    # 종목코드 파싱 (쉼표·공백 구분)
    raw = tickers_input.replace(",", " ").split()
    stock_codes = [t.strip().zfill(6) for t in raw if t.strip()]

    if not stock_codes:
        st.warning("유효한 종목코드가 없습니다.")
        st.stop()

    importance_filter = "HIGH" if importance == "HIGH만" else None

    from sentinelq.adapters.dart_api import load_corp_code_map
    from sentinelq.monitoring.dart_monitor import run_monitor

    corp_map = load_corp_code_map()
    if not corp_map:
        st.warning(
            "법인코드 캐시 파일(`data/cache/dart/corp_code.json`)이 없습니다. "
            "`scripts/dart_smoke.py`를 먼저 실행하거나, 법인코드 없이는 공시 조회 불가합니다."
        )

    with st.spinner(f"{len(stock_codes)}개 종목 공시 조회 중 (최근 {days_back}일)..."):
        try:
            result = run_monitor(
                stock_codes,
                days_back=int(days_back),
                importance_filter=importance_filter,
                api_key=dart_api_key.strip(),
                corp_map=corp_map if corp_map else None,
                rate_limit_sleep=0.3,
            )
        except Exception as exc:
            st.error(f"조회 오류: {exc}")
            if "timed out" in str(exc).lower() or "urlopen" in str(exc).lower():
                st.info(
                    "💡 **Streamlit Cloud에서는 DART API(opendart.fss.or.kr)에 접근이 제한됩니다.**\n\n"
                    "로컬에서 실행하세요:\n"
                    "```bash\n"
                    "streamlit run streamlit_app.py\n"
                    "```\n"
                    "또는 CLI로 조회:\n"
                    "```bash\n"
                    "python scripts/run_dart_monitor.py --tickers 005930 000660 --days 7\n"
                    "```"
                )
            st.stop()

    # ── 결과 표시 ───────────────────────────────────────────
    st.subheader(f"📋 공시 결과 — {result.checked_from} ~ {result.checked_to}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("조회 종목", len(result.stock_codes_checked))
    m2.metric("건너뜀 (법인코드 없음)", len(result.skipped_codes))
    m3.metric("🔴 HIGH 공시", result.high_count)
    m4.metric("🔵 NORMAL 공시", result.normal_count)

    if result.skipped_codes:
        st.warning(f"법인코드 없어 건너뜀: {', '.join(result.skipped_codes)}")

    if not result.disclosures:
        st.success("조회 기간 내 신규 공시가 없습니다.")
    else:
        rows = disclosures_to_rows(result.disclosures)
        df = pd.DataFrame(rows)

        # URL을 클릭 가능한 링크로 표시
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "URL": st.column_config.LinkColumn("공시 링크"),
            },
        )

        st.caption(f"총 {len(result.disclosures)}건 공시 (HIGH {result.high_count}건)")

else:
    st.info(
        "종목코드와 DART API 키를 입력하고 '공시 조회' 버튼을 누르세요.\n\n"
        "법인코드 매핑이 필요합니다 (`data/cache/dart/corp_code.json`). "
        "없으면 `python scripts/dart_smoke.py`를 먼저 실행하세요."
    )
