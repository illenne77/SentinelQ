"""리밸런싱 리포트 생성 단위 테스트 (T018).

Coverage target: sentinelq/reports/rebalance_report.py >= 90%
PREREG: PREREG-0010 §2.5
"""

from __future__ import annotations

import csv
from decimal import Decimal

from sentinelq.adapters.kis_history import HoldingRecord
from sentinelq.portfolio.after_tax import calculate_after_tax
from sentinelq.portfolio.rebalance import TargetAllocation, calculate_rebalance
from sentinelq.reports.rebalance_report import (
    build_rebalance_csv,
    build_rebalance_report,
    export_rebalance_report,
)


def _holding(ticker: str, *, market: str, cost: int, value: int) -> HoldingRecord:
    qty = 100
    return HoldingRecord(
        ticker=ticker,
        name=ticker,
        market=market,  # type: ignore[arg-type]
        quantity=qty,
        avg_price_krw=Decimal(cost) / qty,
        cost_basis_krw=Decimal(cost),
        current_price_krw=Decimal(value) / qty,
        current_value_krw=Decimal(value),
        unrealized_gain_krw=Decimal(value - cost),
        currency="KRW" if market == "KR" else "USD",  # type: ignore[arg-type]
    )


def _plan(kr_value: int = 8_000_000, us_value: int = 2_000_000, threshold: float = 5.0):
    holdings = [
        _holding("A", market="KR", cost=5_000_000, value=kr_value),
        _holding("B", market="US", cost=2_000_000, value=us_value),
    ]
    portfolio = calculate_after_tax(holdings)
    targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
    return calculate_rebalance(portfolio, targets, threshold_pct=Decimal(str(threshold)))


# ── build_rebalance_report ──────────────────────────────────────


class TestBuildRebalanceReport:
    def test_contains_market_kr(self):
        text = build_rebalance_report(_plan())
        assert "KR" in text

    def test_contains_market_us(self):
        text = build_rebalance_report(_plan())
        assert "US" in text

    def test_shows_rebalance_needed(self):
        text = build_rebalance_report(_plan())
        assert "리밸런싱 필요" in text

    def test_shows_no_rebalance_when_balanced(self):
        holdings = [
            _holding("A", market="KR", cost=3_000_000, value=3_000_000),
            _holding("B", market="US", cost=7_000_000, value=7_000_000),
        ]
        portfolio = calculate_after_tax(holdings)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        text = build_rebalance_report(plan)
        assert "리밸런싱 불필요" in text

    def test_shows_sell_guide_for_overweight(self):
        text = build_rebalance_report(_plan(kr_value=8_000_000, us_value=2_000_000))
        assert "매도" in text

    def test_shows_buy_guide_for_underweight(self):
        text = build_rebalance_report(_plan(kr_value=8_000_000, us_value=2_000_000))
        assert "매수" in text

    def test_as_of_date_shown(self):
        text = build_rebalance_report(_plan(), as_of="2026-05-16")
        assert "2026-05-16" in text

    def test_disclaimer_present(self):
        text = build_rebalance_report(_plan())
        assert "추정값" in text

    def test_threshold_shown_in_report(self):
        text = build_rebalance_report(_plan(threshold=7.5))
        assert "7.5" in text

    def test_total_portfolio_shown(self):
        text = build_rebalance_report(_plan(kr_value=8_000_000, us_value=2_000_000))
        assert "10,000,000" in text


# ── build_rebalance_csv ─────────────────────────────────────────


class TestBuildRebalanceCsv:
    def test_header_row(self):
        raw = build_rebalance_csv(_plan())
        header = raw.splitlines()[0]
        assert "시장" in header
        assert "목표비중(%)" in header
        assert "매수_매도금액(원)" in header

    def test_two_rows(self):
        raw = build_rebalance_csv(_plan())
        rows = list(csv.DictReader(raw.splitlines()))
        assert len(rows) == 2

    def test_kr_row_present(self):
        raw = build_rebalance_csv(_plan())
        rows = list(csv.DictReader(raw.splitlines()))
        markets = [r["시장"] for r in rows]
        assert "KR" in markets

    def test_target_pct_correct(self):
        raw = build_rebalance_csv(_plan())
        rows = {r["시장"]: r for r in csv.DictReader(raw.splitlines())}
        assert rows["KR"]["목표비중(%)"] == "30"
        assert rows["US"]["목표비중(%)"] == "70"

    def test_empty_portfolio_header_only(self):
        portfolio = calculate_after_tax([])
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        raw = build_rebalance_csv(plan)
        data_rows = list(csv.DictReader(raw.splitlines()))
        assert len(data_rows) == 2  # KR, US 모두 표시 (값 0)


# ── export_rebalance_report ─────────────────────────────────────


class TestExportRebalanceReport:
    def test_creates_two_files(self, tmp_path):
        txt, csv_path = export_rebalance_report(_plan(), tmp_path, stem="test")
        assert txt.exists()
        assert csv_path.exists()

    def test_txt_contains_market(self, tmp_path):
        txt, _ = export_rebalance_report(_plan(), tmp_path, stem="t")
        assert "KR" in txt.read_text(encoding="utf-8")

    def test_csv_valid_format(self, tmp_path):
        _, csv_path = export_rebalance_report(_plan(), tmp_path, stem="t")
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        assert len(rows) == 2
        assert "시장" in rows[0]
