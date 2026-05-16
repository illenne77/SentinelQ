"""UI 헬퍼 함수 단위 테스트 (T024).

Coverage target: sentinelq/ui/helpers.py >= 90%
PREREG: PREREG-0012 §2.1
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sentinelq.adapters.dart_api import DisclosureRecord
from sentinelq.portfolio.after_tax import AfterTaxPortfolio, AfterTaxPosition
from sentinelq.portfolio.rebalance import MarketAllocation, RebalancePlan
from sentinelq.ui.helpers import (
    disclosures_to_rows,
    env_status,
    fmt_krw,
    fmt_pct,
    portfolio_summary,
    portfolio_to_rows,
    rebalance_summary,
    rebalance_to_rows,
    validate_target_weights,
)

# ── 픽스처 ────────────────────────────────────────────────────


def _position(
    ticker: str = "005930",
    market: str = "KR",
    gain: Decimal = Decimal("1_000_000"),
) -> AfterTaxPosition:
    return AfterTaxPosition(
        ticker=ticker,
        name="삼성전자",
        market=market,
        quantity=10,
        cost_basis_krw=Decimal("5_000_000"),
        current_value_krw=Decimal("5_000_000") + gain,
        unrealized_gain_krw=gain,
        unrealized_return_pct=Decimal("20.00"),
        estimated_tax_krw=Decimal("165_000"),
        after_tax_gain_krw=gain - Decimal("165_000"),
        after_tax_return_pct=Decimal("16.70"),
    )


def _portfolio(gain: Decimal = Decimal("1_000_000")) -> AfterTaxPortfolio:
    pos = _position(gain=gain)
    return AfterTaxPortfolio(
        positions=(pos,),
        total_cost_krw=Decimal("5_000_000"),
        total_current_value_krw=Decimal("5_000_000") + gain,
        total_unrealized_gain_krw=gain,
        total_unrealized_return_pct=Decimal("20.00"),
        total_estimated_tax_krw=Decimal("165_000"),
        total_after_tax_gain_krw=gain - Decimal("165_000"),
        total_after_tax_return_pct=Decimal("16.70"),
        realized_gain_ytd_krw=Decimal("0"),
        remaining_deduction_krw=Decimal("2_500_000"),
    )


def _disclosure(importance: str = "HIGH") -> DisclosureRecord:
    return DisclosureRecord(
        corp_code="00126380",
        corp_name="삼성전자",
        stock_code="005930",
        report_name="유상증자결정",
        receipt_no="20260514000111",
        filer_name="삼성전자",
        receipt_date=date(2026, 5, 14),
        importance=importance,  # type: ignore[arg-type]
        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260514000111",
    )


def _alloc(market: str, trade: Decimal, drift: Decimal = Decimal("10")) -> MarketAllocation:
    return MarketAllocation(
        market=market,
        target_pct=Decimal("50"),
        current_pct=Decimal("50") + drift,
        current_value_krw=Decimal("3_000_000"),
        target_value_krw=Decimal("2_500_000"),
        drift_pct=drift,
        trade_amount_krw=trade,
        estimated_sell_tax_krw=Decimal("33_000") if trade < 0 else Decimal("0"),
    )


def _plan(is_needed: bool = True) -> RebalancePlan:
    sell = _alloc("KR", Decimal("-600_000"))
    buy = _alloc("US", Decimal("600_000"), drift=Decimal("-10"))
    return RebalancePlan(
        total_portfolio_krw=Decimal("6_000_000"),
        allocations=(sell, buy),
        threshold_pct=Decimal("5"),
        is_rebalance_needed=is_needed,
        total_sell_amount_krw=Decimal("600_000"),
        total_buy_amount_krw=Decimal("600_000"),
        total_estimated_sell_tax_krw=Decimal("33_000"),
        net_after_rebalance_sell_tax_krw=Decimal("5_967_000"),
    )


# ── fmt_krw ───────────────────────────────────────────────────


class TestFmtKrw:
    def test_positive(self):
        assert fmt_krw(1_234_567) == "1,234,567 원"

    def test_negative(self):
        assert fmt_krw(-500_000) == "-500,000 원"

    def test_zero(self):
        assert fmt_krw(0) == "0 원"

    def test_decimal_input(self):
        assert fmt_krw(Decimal("2_500_000")) == "2,500,000 원"

    def test_float_input(self):
        result = fmt_krw(1000.9)
        assert result == "1,000 원"  # truncates to int


# ── fmt_pct ───────────────────────────────────────────────────


class TestFmtPct:
    def test_positive(self):
        assert fmt_pct(Decimal("20.00")) == "+20.00%"

    def test_negative(self):
        assert fmt_pct(Decimal("-5.30")) == "-5.30%"

    def test_zero(self):
        assert fmt_pct(0) == "+0.00%"

    def test_custom_decimals(self):
        assert fmt_pct(Decimal("1.5"), decimals=1) == "+1.5%"


# ── validate_target_weights ────────────────────────────────────


class TestValidateTargetWeights:
    def test_valid_two_markets(self):
        ok, msg = validate_target_weights({"KR": 30, "US": 70})
        assert ok is True
        assert msg == ""

    def test_empty_raises_false(self):
        ok, msg = validate_target_weights({})
        assert ok is False
        assert "최소 1개" in msg

    def test_over_100(self):
        ok, msg = validate_target_weights({"KR": 60, "US": 60})
        assert ok is False
        assert "100%" in msg

    def test_under_100(self):
        ok, msg = validate_target_weights({"KR": 30, "US": 30})
        assert ok is False
        assert "100%" in msg

    def test_tolerance_within_1pct(self):
        ok, _ = validate_target_weights({"KR": 30.5, "US": 70.0})
        assert ok is True

    def test_tolerance_exactly_1pct_ok(self):
        ok, _ = validate_target_weights({"KR": 30, "US": 71})
        assert ok is True

    def test_over_tolerance(self):
        ok, _ = validate_target_weights({"KR": 30, "US": 72})
        assert ok is False


# ── portfolio_to_rows ─────────────────────────────────────────


class TestPortfolioToRows:
    def test_single_position_fields(self):
        rows = portfolio_to_rows(_portfolio())
        assert len(rows) == 1
        r = rows[0]
        assert r["종목코드"] == "005930"
        assert r["시장"] == "KR"
        assert r["수량"] == 10
        assert r["매입원가(원)"] == 5_000_000
        assert r["세전수익률(%)"] == 20.0

    def test_empty_portfolio(self):
        empty = AfterTaxPortfolio(
            positions=(),
            total_cost_krw=Decimal("0"),
            total_current_value_krw=Decimal("0"),
            total_unrealized_gain_krw=Decimal("0"),
            total_unrealized_return_pct=Decimal("0"),
            total_estimated_tax_krw=Decimal("0"),
            total_after_tax_gain_krw=Decimal("0"),
            total_after_tax_return_pct=Decimal("0"),
            realized_gain_ytd_krw=Decimal("0"),
            remaining_deduction_krw=Decimal("2_500_000"),
        )
        assert portfolio_to_rows(empty) == []


# ── portfolio_summary ─────────────────────────────────────────


class TestPortfolioSummary:
    def test_keys_present(self):
        summary = portfolio_summary(_portfolio())
        expected_keys = {
            "총 매입원가",
            "총 평가금액",
            "미실현 손익",
            "세전 수익률",
            "예상 양도세",
            "세후 손익",
            "세후 수익률",
            "잔여 기본공제",
        }
        assert set(summary.keys()) == expected_keys

    def test_format_is_string(self):
        summary = portfolio_summary(_portfolio())
        for v in summary.values():
            assert isinstance(v, str)

    def test_remaining_deduction_value(self):
        summary = portfolio_summary(_portfolio())
        assert "2,500,000 원" in summary["잔여 기본공제"]


# ── disclosures_to_rows ────────────────────────────────────────


class TestDisclosuresToRows:
    def test_high_importance_tag(self):
        rows = disclosures_to_rows([_disclosure("HIGH")])
        assert "🔴" in rows[0]["중요도"]
        assert "HIGH" in rows[0]["중요도"]

    def test_normal_importance_tag(self):
        rows = disclosures_to_rows([_disclosure("NORMAL")])
        assert "🔵" in rows[0]["중요도"]
        assert "NORMAL" in rows[0]["중요도"]

    def test_fields_present(self):
        rows = disclosures_to_rows([_disclosure()])
        r = rows[0]
        assert r["종목코드"] == "005930"
        assert r["회사명"] == "삼성전자"
        assert "dart.fss.or.kr" in r["URL"]

    def test_empty_list(self):
        assert disclosures_to_rows([]) == []


# ── rebalance_to_rows ─────────────────────────────────────────


class TestRebalanceToRows:
    def test_sell_action(self):
        plan = _plan()
        rows = rebalance_to_rows(plan)
        kr_row = next(r for r in rows if r["시장"] == "KR")
        assert kr_row["액션"] == "매도"
        assert kr_row["거래금액(원)"] == -600_000

    def test_buy_action(self):
        rows = rebalance_to_rows(_plan())
        us_row = next(r for r in rows if r["시장"] == "US")
        assert us_row["액션"] == "매수"

    def test_hold_action(self):
        hold_alloc = MarketAllocation(
            market="EU",
            target_pct=Decimal("0"),
            current_pct=Decimal("0"),
            current_value_krw=Decimal("0"),
            target_value_krw=Decimal("0"),
            drift_pct=Decimal("0"),
            trade_amount_krw=Decimal("0"),
            estimated_sell_tax_krw=Decimal("0"),
        )
        plan = RebalancePlan(
            total_portfolio_krw=Decimal("1_000_000"),
            allocations=(hold_alloc,),
            threshold_pct=Decimal("5"),
            is_rebalance_needed=False,
            total_sell_amount_krw=Decimal("0"),
            total_buy_amount_krw=Decimal("0"),
            total_estimated_sell_tax_krw=Decimal("0"),
            net_after_rebalance_sell_tax_krw=Decimal("1_000_000"),
        )
        rows = rebalance_to_rows(plan)
        assert rows[0]["액션"] == "유지"


# ── rebalance_summary ─────────────────────────────────────────


class TestRebalanceSummary:
    def test_keys_present(self):
        summary = rebalance_summary(_plan())
        expected_keys = {
            "총 포트폴리오",
            "리밸런싱 필요",
            "총 매도금액",
            "총 매수금액",
            "예상 매도세",
            "세후 순 포트폴리오",
        }
        assert set(summary.keys()) == expected_keys

    def test_rebalance_needed_yes(self):
        assert rebalance_summary(_plan(is_needed=True))["리밸런싱 필요"] == "예"

    def test_rebalance_needed_no(self):
        assert rebalance_summary(_plan(is_needed=False))["리밸런싱 필요"] == "아니오"


# ── env_status ────────────────────────────────────────────────


class TestEnvStatus:
    def test_all_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            status = env_status()
        assert all(v is False for v in status.values())

    def test_kis_set(self):
        with patch.dict("os.environ", {"KIS_APP_KEY": "abc"}, clear=True):
            status = env_status()
        assert status["KIS API (KIS_APP_KEY)"] is True
        assert status["DART API (DART_API_KEY)"] is False

    def test_returns_four_keys(self):
        with patch.dict("os.environ", {}, clear=True):
            assert len(env_status()) == 4
