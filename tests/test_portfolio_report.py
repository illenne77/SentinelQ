"""포트폴리오 대시보드 리포트 단위 테스트 (T015).

Coverage target: sentinelq/reports/portfolio_report.py >= 90%
PREREG: PREREG-0009 §2.3
"""

from __future__ import annotations

import csv
from decimal import Decimal

from sentinelq.adapters.kis_history import HoldingRecord
from sentinelq.portfolio.after_tax import calculate_after_tax
from sentinelq.reports.portfolio_report import (
    build_portfolio_csv,
    build_portfolio_report,
    export_portfolio_report,
)


def _holding(ticker: str, *, cost: int, value: int) -> HoldingRecord:
    return HoldingRecord(
        ticker=ticker,
        name=ticker + " Inc.",
        market="US",
        quantity=100,
        avg_price_krw=Decimal(cost) / 100,
        cost_basis_krw=Decimal(cost),
        current_price_krw=Decimal(value) / 100,
        current_value_krw=Decimal(value),
        unrealized_gain_krw=Decimal(value - cost),
        currency="USD",
    )


def _portfolio(cost: int = 10_000_000, value: int = 13_000_000, realized: int = 0):
    h = _holding("NVDA", cost=cost, value=value)
    return calculate_after_tax([h], realized_gain_ytd_krw=Decimal(realized))


# ── build_portfolio_report ──────────────────────────────────────


class TestBuildPortfolioReport:
    def test_contains_ticker(self):
        text = build_portfolio_report(_portfolio())
        assert "NVDA" in text

    def test_contains_cost_basis(self):
        text = build_portfolio_report(_portfolio(cost=10_000_000))
        assert "10,000,000" in text

    def test_contains_after_tax_section(self):
        text = build_portfolio_report(_portfolio())
        assert "세후" in text

    def test_contains_deduction_section(self):
        text = build_portfolio_report(_portfolio())
        assert "기본공제" in text

    def test_as_of_date_shown(self):
        text = build_portfolio_report(_portfolio(), as_of="2026-05-16")
        assert "2026-05-16" in text

    def test_empty_portfolio(self):
        from sentinelq.portfolio.after_tax import calculate_after_tax

        empty = calculate_after_tax([])
        text = build_portfolio_report(empty)
        assert "보유 종목 없음" in text

    def test_full_deduction_available_message(self):
        # realized = 0 → 전액 미사용
        text = build_portfolio_report(_portfolio(realized=0))
        assert "전액 미사용" in text

    def test_deduction_exhausted_message(self):
        # realized = 3,000,000 → 기본공제 소진
        text = build_portfolio_report(_portfolio(realized=3_000_000))
        assert "소진" in text

    def test_partial_deduction_message(self):
        text = build_portfolio_report(_portfolio(realized=1_000_000))
        assert "잔여" in text

    def test_loss_position_shown(self):
        h = _holding("LOSS", cost=10_000_000, value=8_000_000)
        p = calculate_after_tax([h])
        text = build_portfolio_report(p)
        assert "LOSS" in text

    def test_disclaimer_present(self):
        text = build_portfolio_report(_portfolio())
        assert "추정값" in text


# ── build_portfolio_csv ─────────────────────────────────────────


class TestBuildPortfolioCsv:
    def test_header_row(self):
        raw = build_portfolio_csv(_portfolio())
        header = raw.splitlines()[0]
        assert "종목코드" in header
        assert "세후수익률(%)" in header

    def test_nvda_row_present(self):
        raw = build_portfolio_csv(_portfolio())
        rows = list(csv.DictReader(raw.splitlines()))
        assert rows[0]["종목코드"] == "NVDA"

    def test_cost_basis_correct(self):
        raw = build_portfolio_csv(_portfolio(cost=10_000_000))
        rows = list(csv.DictReader(raw.splitlines()))
        assert rows[0]["매입원가(원)"] == "10000000"

    def test_empty_portfolio_header_only(self):
        from sentinelq.portfolio.after_tax import calculate_after_tax

        empty = calculate_after_tax([])
        raw = build_portfolio_csv(empty)
        rows = list(csv.reader(raw.splitlines()))
        assert len(rows) == 1  # header only


# ── export_portfolio_report ─────────────────────────────────────


class TestExportPortfolioReport:
    def test_creates_two_files(self, tmp_path):
        txt, csv_path = export_portfolio_report(_portfolio(), tmp_path, stem="test")
        assert txt.exists()
        assert csv_path.exists()

    def test_txt_contains_ticker(self, tmp_path):
        txt, _ = export_portfolio_report(_portfolio(), tmp_path, stem="t")
        assert "NVDA" in txt.read_text(encoding="utf-8")

    def test_csv_valid_format(self, tmp_path):
        _, csv_path = export_portfolio_report(_portfolio(), tmp_path, stem="t")
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        assert len(rows) == 1
        assert rows[0]["종목코드"] == "NVDA"
