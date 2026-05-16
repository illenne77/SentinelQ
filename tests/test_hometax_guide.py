"""홈택스·위택스 신고 가이드 생성 단위 테스트 (T011·T012).

Coverage target:
  sentinelq/reports/hometax_guide.py >= 90%
  sentinelq/reports/wetax_guide.py >= 90%
PREREG: PREREG-0008-amendment-2 §2.5
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

from sentinelq.reports.hometax_guide import (
    build_hometax_guide,
    build_hometax_trades_csv,
    export_hometax_guide,
)
from sentinelq.reports.nts_form import (
    NTSCapitalGainsForm,
    NTSMarketBreakdown,
    NTSSaleLine,
)
from sentinelq.reports.wetax_guide import build_wetax_guide, export_wetax_guide

# ── 공통 픽스처 ─────────────────────────────────────────────────


def _form(
    *,
    tax_year: int = 2025,
    national_tax: int = 738_243,
    local_tax: int = 73_824,
    taxable_base: int = 3_691_218,
    total_gain: int = 6_191_218,
    total_proceeds: int = 27_488_826,
    total_cost: int = 21_297_608,
    deduction: int = 2_500_000,
    sale_lines: tuple = (),
    by_market: tuple = (),
) -> NTSCapitalGainsForm:
    return NTSCapitalGainsForm(
        tax_year=tax_year,
        filing_period_start=date(tax_year + 1, 5, 1),
        filing_period_end=date(tax_year + 1, 5, 31),
        sale_lines=sale_lines,
        by_market=by_market,
        total_proceeds_krw=Decimal(total_proceeds),
        total_acquisition_cost_krw=Decimal(total_cost),
        total_realized_gain_krw=Decimal(total_gain),
        basic_deduction_krw=Decimal(2_500_000),
        deduction_applied_krw=Decimal(deduction),
        taxable_base_krw=Decimal(taxable_base),
        national_tax_krw=Decimal(national_tax),
        local_tax_krw=Decimal(local_tax),
        total_tax_krw=Decimal(national_tax + local_tax),
        t003_combined_tax_krw=Decimal(national_tax + local_tax),
        sale_count=2,
    )


_NVDA_LINE = NTSSaleLine(
    market="US",
    ticker="NVDA",
    sell_date=date(2025, 6, 12),
    quantity=80,
    proceeds_krw=Decimal("15649592"),
    acquisition_cost_krw=Decimal("13215548"),
    realized_gain_krw=Decimal("2434044"),
)

_AAPL_LINE = NTSSaleLine(
    market="US",
    ticker="AAPL",
    sell_date=date(2025, 11, 6),
    quantity=30,
    proceeds_krw=Decimal("11839234"),
    acquisition_cost_krw=Decimal("8082060"),
    realized_gain_krw=Decimal("3757174"),
)

_US_MARKET = NTSMarketBreakdown(
    market="US",
    total_proceeds_krw=Decimal("27488826"),
    total_acquisition_cost_krw=Decimal("21297608"),
    total_realized_gain_krw=Decimal("6191218"),
    sale_count=2,
)


# ── build_hometax_guide ─────────────────────────────────────────


class TestBuildHometaxGuide:
    def test_contains_tax_year(self):
        text = build_hometax_guide(_form())
        assert "2025년" in text

    def test_contains_filing_period(self):
        text = build_hometax_guide(_form())
        assert "2026-05-31" in text

    def test_contains_national_tax(self):
        text = build_hometax_guide(_form())
        assert "738,243" in text

    def test_contains_local_tax(self):
        text = build_hometax_guide(_form())
        assert "73,824" in text

    def test_contains_taxable_base(self):
        text = build_hometax_guide(_form())
        assert "3,691,218" in text

    def test_mentions_wetax(self):
        text = build_hometax_guide(_form())
        assert "위택스" in text

    def test_zero_tax_case(self):
        form = _form(national_tax=0, local_tax=0, taxable_base=0, total_gain=1_000_000)
        text = build_hometax_guide(form)
        assert "납부세액 없음" in text

    def test_sale_lines_in_guide(self):
        form = _form(sale_lines=(_NVDA_LINE, _AAPL_LINE))
        text = build_hometax_guide(form)
        assert "NVDA" in text
        assert "AAPL" in text

    def test_empty_sale_lines(self):
        form = _form(sale_lines=())
        text = build_hometax_guide(form)
        assert "매도 내역 없음" in text

    def test_market_breakdown_in_guide(self):
        form = _form(by_market=(_US_MARKET,))
        text = build_hometax_guide(form)
        assert "해외주식" in text

    def test_증빙서류_section_present(self):
        text = build_hometax_guide(_form())
        assert "증빙서류" in text


# ── build_hometax_trades_csv ────────────────────────────────────


class TestBuildHometaxTradesCsv:
    def test_header_present(self):
        form = _form(sale_lines=(_NVDA_LINE,))
        raw = build_hometax_trades_csv(form)
        rows = list(csv.DictReader(raw.splitlines()))
        assert "매도일" in rows[0] if rows else True
        header_line = raw.splitlines()[0]
        assert "양도가액(원)" in header_line

    def test_row_count(self):
        form = _form(sale_lines=(_NVDA_LINE, _AAPL_LINE))
        raw = build_hometax_trades_csv(form)
        rows = list(csv.reader(raw.splitlines()))
        assert len(rows) == 3  # header + 2 data

    def test_nvda_values(self):
        form = _form(sale_lines=(_NVDA_LINE,))
        raw = build_hometax_trades_csv(form)
        rows = list(csv.DictReader(raw.splitlines()))
        assert rows[0]["종목코드"] == "NVDA"
        assert rows[0]["양도가액(원)"] == "15649592"
        assert rows[0]["양도차익(원)"] == "2434044"

    def test_empty_sale_lines(self):
        form = _form(sale_lines=())
        raw = build_hometax_trades_csv(form)
        rows = list(csv.reader(raw.splitlines()))
        assert len(rows) == 1  # header only


# ── export_hometax_guide ────────────────────────────────────────


class TestExportHometaxGuide:
    def test_creates_two_files(self, tmp_path):
        form = _form(sale_lines=(_NVDA_LINE,))
        guide, trades = export_hometax_guide(form, tmp_path, stem="test")
        assert guide.exists()
        assert trades.exists()

    def test_guide_file_contains_tax(self, tmp_path):
        form = _form()
        guide, _ = export_hometax_guide(form, tmp_path, stem="g")
        content = guide.read_text(encoding="utf-8")
        assert "738,243" in content

    def test_trades_file_is_valid_csv(self, tmp_path):
        form = _form(sale_lines=(_NVDA_LINE, _AAPL_LINE))
        _, trades = export_hometax_guide(form, tmp_path, stem="g")
        rows = list(csv.DictReader(trades.open(encoding="utf-8")))
        assert len(rows) == 2


# ── build_wetax_guide ───────────────────────────────────────────


class TestBuildWetaxGuide:
    def test_contains_local_tax_amount(self):
        text = build_wetax_guide(_form())
        assert "73,824" in text

    def test_contains_wetax_url(self):
        text = build_wetax_guide(_form())
        assert "wetax.go.kr" in text

    def test_contains_filing_deadline(self):
        text = build_wetax_guide(_form())
        assert "2026-05-31" in text

    def test_zero_local_tax_message(self):
        form = _form(national_tax=0, local_tax=0, taxable_base=0, total_gain=500_000)
        text = build_wetax_guide(form)
        assert "납부할 지방소득세 없음" in text

    def test_contains_procedure_steps(self):
        text = build_wetax_guide(_form())
        assert "신고하기" in text

    def test_mentions_penalty(self):
        text = build_wetax_guide(_form())
        assert "가산세" in text

    def test_taxable_base_in_guide(self):
        text = build_wetax_guide(_form())
        assert "3,691,218" in text


# ── export_wetax_guide ───────────────────────────────────────────


class TestExportWetaxGuide:
    def test_creates_file(self, tmp_path):
        form = _form()
        path = export_wetax_guide(form, tmp_path, stem="wt")
        assert path.exists()

    def test_file_contains_tax(self, tmp_path):
        form = _form()
        path = export_wetax_guide(form, tmp_path, stem="wt")
        content = path.read_text(encoding="utf-8")
        assert "73,824" in content
