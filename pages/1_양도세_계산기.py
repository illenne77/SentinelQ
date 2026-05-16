"""양도세 계산기 페이지 (T025).

PREREG: PREREG-0012 §2.3
CSV 업로드 → 양도세 계산 → NTS 양식 출력 + CSV 다운로드
"""

from __future__ import annotations

import tempfile
from dataclasses import replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="양도세 계산기 — SentinelQ", layout="wide")

st.title("💰 양도세 계산기")
st.markdown("키움증권·미래에셋증권 HTS 체결내역 CSV를 업로드하면 양도세를 자동 계산합니다.")

# ── 입력 ─────────────────────────────────────────────────────
col_left, col_right = st.columns([2, 1])

with col_left:
    broker = st.radio(
        "증권사 선택",
        ["키움증권", "미래에셋증권"],
        horizontal=True,
        help="영웅문 HTS > 체결내역조회 > 엑셀저장 CSV",
    )
    uploaded = st.file_uploader(
        "체결내역 CSV 파일",
        type=["csv"],
        help="UTF-8 BOM 또는 EUC-KR 인코딩 모두 지원",
    )

with col_right:
    current_year = date.today().year
    tax_year = st.number_input(
        "과세연도",
        min_value=2020,
        max_value=current_year,
        value=current_year - 1,
        step=1,
    )

with st.expander("💱 환율 입력 (USD 거래가 있는 경우)"):
    st.caption(
        "KIS API가 환율을 제공하지 않으므로, USD 거래의 매매일별 기준환율을 직접 입력합니다.\n\n"
        "형식: `YYYY-MM-DD: 환율` (예: `2025-01-15: 1465.0`)"
    )
    fx_text = st.text_area(
        "기준환율 (날짜: 환율, 한 줄에 하나씩)",
        height=120,
        placeholder="2025-01-15: 1465.0\n2025-03-20: 1432.5",
    )

# ── 계산 ─────────────────────────────────────────────────────
if st.button("계산하기 🔄", type="primary", disabled=uploaded is None):
    # 환율 파싱
    fx_rates: dict[str, Decimal] = {}
    if fx_text and fx_text.strip():
        for i, line in enumerate(fx_text.strip().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                d, r = line.split(":", 1)
                fx_rates[d.strip()] = Decimal(r.strip())
            except (ValueError, InvalidOperation):
                st.warning(f"환율 파싱 실패 (줄 {i}): {line!r} — 건너뜁니다.")

    # CSV 파싱
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(uploaded.read())
        tmp_path = Path(tmp.name)

    try:
        if broker == "키움증권":
            from sentinelq.adapters.kiwoom_csv import KiwoomParseError, parse_kiwoom_csv

            try:
                txs = parse_kiwoom_csv(tmp_path)
            except KiwoomParseError as exc:
                st.error(f"키움 CSV 파싱 오류: {exc}")
                st.stop()
        else:
            from sentinelq.adapters.miraeasset_csv import MiraeAssetParseError, parse_miraeasset_csv

            try:
                txs = parse_miraeasset_csv(tmp_path)
            except MiraeAssetParseError as exc:
                st.error(f"미래에셋 CSV 파싱 오류: {exc}")
                st.stop()
    finally:
        tmp_path.unlink(missing_ok=True)

    if not txs:
        st.warning("파싱된 거래 내역이 없습니다. CSV 파일과 증권사 선택을 확인해 주세요.")
        st.stop()

    # 환율 적용
    if fx_rates:
        updated = []
        for tx in txs:
            date_key = str(tx.trade_date)
            if tx.currency not in ("KRW", "") and date_key in fx_rates:
                updated.append(replace(tx, fx_rate=fx_rates[date_key]))
            else:
                updated.append(tx)
        txs = updated
        st.info(f"환율 적용: {len(fx_rates)}개 날짜")

    # 파이프라인 실행
    from sentinelq.reports.nts_form import export_detail_csv, export_summary_csv
    from sentinelq.reports.tax_report import run_pipeline

    with st.spinner("양도세 계산 중..."):
        try:
            form = run_pipeline(txs, int(tax_year))
        except Exception as exc:
            st.error(f"계산 오류: {exc}")
            st.stop()

    st.success(f"계산 완료! 총 {form.sale_count}건 매도, 과세연도 {form.tax_year}년")

    # ── 요약 메트릭 ─────────────────────────────────────────
    st.subheader("📋 NTS 양도소득세 신고서 요약")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("양도가액", f"{int(form.total_proceeds_krw):,} 원")
    m2.metric("취득가액", f"{int(form.total_acquisition_cost_krw):,} 원")
    m3.metric("양도차익", f"{int(form.total_realized_gain_krw):,} 원")
    m4.metric("기본공제", f"{int(form.deduction_applied_krw):,} 원")
    m5.metric("과세표준", f"{int(form.taxable_base_krw):,} 원")
    m6.metric("납부세액 합계", f"{int(form.total_tax_krw):,} 원")

    # ── 시장별 상세 ─────────────────────────────────────────
    if form.by_market:
        st.subheader("📊 시장별 집계")
        import pandas as pd

        mkt_rows = [
            {
                "시장": m.market,
                "양도가액(원)": int(m.total_proceeds_krw),
                "취득가액(원)": int(m.total_acquisition_cost_krw),
                "양도차익(원)": int(m.total_realized_gain_krw),
                "매도건수": m.sale_count,
            }
            for m in form.by_market
        ]
        st.dataframe(pd.DataFrame(mkt_rows), use_container_width=True, hide_index=True)

    # ── 다운로드 ─────────────────────────────────────────────
    st.subheader("⬇️ 다운로드")
    dl1, dl2 = st.columns(2)
    dl1.download_button(
        "요약 CSV (홈택스 입력용)",
        export_summary_csv(form),
        file_name=f"nts_{tax_year}_summary.csv",
        mime="text/csv",
    )
    dl2.download_button(
        "상세 CSV (종목별 매도내역)",
        export_detail_csv(form),
        file_name=f"nts_{tax_year}_detail.csv",
        mime="text/csv",
    )

else:
    st.info("📂 CSV 파일을 업로드하고 '계산하기' 버튼을 누르세요.")
