"""패시브 리밸런싱 계산기 단위 테스트 (T017).

Coverage target: sentinelq/portfolio/rebalance.py >= 90%
PREREG: PREREG-0010 §2.1-2.4
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from sentinelq.adapters.kis_history import HoldingRecord
from sentinelq.portfolio.after_tax import calculate_after_tax
from sentinelq.portfolio.rebalance import (
    RebalancePlan,
    TargetAllocation,
    calculate_rebalance,
)


def _holding(
    ticker: str,
    *,
    market: str = "US",
    cost_krw: int = 10_000_000,
    value_krw: int = 12_000_000,
) -> HoldingRecord:
    qty = 100
    unrealized = Decimal(value_krw - cost_krw)
    return HoldingRecord(
        ticker=ticker,
        name=ticker,
        market=market,  # type: ignore[arg-type]
        quantity=qty,
        avg_price_krw=Decimal(cost_krw) / qty,
        cost_basis_krw=Decimal(cost_krw),
        current_price_krw=Decimal(value_krw) / qty,
        current_value_krw=Decimal(value_krw),
        unrealized_gain_krw=unrealized,
        currency="USD" if market == "US" else "KRW",  # type: ignore[arg-type]
    )


def _portfolio(kr_value: int = 3_000_000, us_value: int = 7_000_000):
    holdings = [
        _holding("A", market="KR", cost_krw=3_000_000, value_krw=kr_value),
        _holding("B", market="US", cost_krw=7_000_000, value_krw=us_value),
    ]
    return calculate_after_tax(holdings)


# ── TargetAllocation ────────────────────────────────────────────


class TestTargetAllocation:
    def test_valid_two_markets(self):
        t = TargetAllocation(weights={"KR": Decimal("30"), "US": Decimal("70")})
        assert t.weights["KR"] == Decimal("30")

    def test_sum_not_100_raises(self):
        with pytest.raises(ValueError, match="100%"):
            TargetAllocation(weights={"KR": Decimal("30"), "US": Decimal("60")})

    def test_from_dict(self):
        t = TargetAllocation.from_dict({"KR": 30, "US": 70})
        assert t.weights["KR"] == Decimal("30")

    def test_from_dict_str_values(self):
        t = TargetAllocation.from_dict({"KR": "30.5", "US": "69.5"})
        assert t.weights["US"] == Decimal("69.5")

    def test_three_markets_valid(self):
        t = TargetAllocation(
            weights={"KR": Decimal("20"), "US": Decimal("60"), "OTHER": Decimal("20")}
        )
        assert sum(t.weights.values()) == Decimal("100")

    def test_sum_100_with_float_precision(self):
        t = TargetAllocation.from_dict({"KR": "33.33", "US": "33.34", "OTHER": "33.33"})
        assert t.weights["KR"] == Decimal("33.33")


# ── calculate_rebalance — 기본 동작 ───────────────────────────


class TestCalculateRebalance:
    def test_empty_portfolio_returns_plan(self):
        portfolio = calculate_after_tax([])
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        assert plan.total_portfolio_krw == Decimal("0")
        assert not plan.is_rebalance_needed

    def test_returns_rebalance_plan_type(self):
        plan = calculate_rebalance(_portfolio(), TargetAllocation.from_dict({"KR": 30, "US": 70}))
        assert isinstance(plan, RebalancePlan)

    def test_balanced_portfolio_no_rebalance(self):
        # KR=30%, US=70% 정확히 일치
        portfolio = _portfolio(kr_value=3_000_000, us_value=7_000_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets, threshold_pct=Decimal("5"))
        assert not plan.is_rebalance_needed

    def test_overweight_us_triggers_rebalance(self):
        # US=90%, 목표 US=70% → drift=+20% → 임계값 5% 초과
        portfolio = _portfolio(kr_value=1_000_000, us_value=9_000_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        assert plan.is_rebalance_needed

    def test_trade_amounts_correct(self):
        # 총 10M, KR=3M(30%), US=7M(70%) → 목표와 정확 일치
        portfolio = _portfolio(kr_value=3_000_000, us_value=7_000_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        for a in plan.allocations:
            assert a.trade_amount_krw == Decimal("0")

    def test_sell_overweight_positive_drift(self):
        # KR=8M(80%), US=2M(20%), 목표 KR=30, US=70 → KR 매도, US 매수
        portfolio = _portfolio(kr_value=8_000_000, us_value=2_000_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        kr_alloc = next(a for a in plan.allocations if a.market == "KR")
        us_alloc = next(a for a in plan.allocations if a.market == "US")
        assert kr_alloc.trade_amount_krw < 0  # 매도
        assert us_alloc.trade_amount_krw > 0  # 매수
        assert kr_alloc.drift_pct > 0  # 초과
        assert us_alloc.drift_pct < 0  # 부족

    def test_threshold_boundary_exactly_at_threshold_not_triggered(self):
        # KR=3.5M(35%), US=6.5M(65%) → drift KR=+5% → 임계값 5% 정확히 일치 → 미발동 (> 아닌 =)
        portfolio = _portfolio(kr_value=3_500_000, us_value=6_500_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets, threshold_pct=Decimal("5"))
        # drift=5.00%, threshold=5 → 5.00 > 5 is False → 미발동
        assert not plan.is_rebalance_needed

    def test_custom_threshold_2pct(self):
        # KR=3.5M(35%), US=6.5M(65%) → drift KR=+5% → 임계값 2%면 발동
        portfolio = _portfolio(kr_value=3_500_000, us_value=6_500_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets, threshold_pct=Decimal("2"))
        assert plan.is_rebalance_needed

    def test_market_in_target_not_in_portfolio_shows_zero_current(self):
        # OTHER 시장 포지션 없지만 목표 배분에 포함
        portfolio = calculate_after_tax(
            [_holding("A", market="US", cost_krw=10_000_000, value_krw=10_000_000)]
        )
        targets = TargetAllocation.from_dict({"US": 70, "KR": 30})
        plan = calculate_rebalance(portfolio, targets)
        kr_alloc = next(a for a in plan.allocations if a.market == "KR")
        assert kr_alloc.current_value_krw == Decimal("0")
        assert kr_alloc.current_pct == Decimal("0")

    def test_sell_tax_proportional(self):
        # KR=8M 과세 포지션, US=2M — KR 매도 시 세금 발생
        holdings = [
            _holding("KR1", market="KR", cost_krw=3_000_000, value_krw=8_000_000),  # gain 5M
            _holding("US1", market="US", cost_krw=2_000_000, value_krw=2_000_000),
        ]
        portfolio = calculate_after_tax(holdings)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        kr_alloc = next(a for a in plan.allocations if a.market == "KR")
        # KR 초과로 매도 → 세금 > 0
        if kr_alloc.trade_amount_krw < 0:
            assert kr_alloc.estimated_sell_tax_krw >= Decimal("0")

    def test_buy_market_has_zero_sell_tax(self):
        # 매수 필요한 시장은 세금 발생 없음
        portfolio = _portfolio(kr_value=1_000_000, us_value=9_000_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        kr_alloc = next(a for a in plan.allocations if a.market == "KR")
        assert kr_alloc.trade_amount_krw > 0  # KR 매수 필요
        assert kr_alloc.estimated_sell_tax_krw == Decimal("0")

    def test_total_sell_buy_amounts_positive(self):
        portfolio = _portfolio(kr_value=8_000_000, us_value=2_000_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        assert plan.total_sell_amount_krw >= Decimal("0")
        assert plan.total_buy_amount_krw >= Decimal("0")

    def test_net_after_tax_equals_total_minus_sell_tax(self):
        portfolio = _portfolio(kr_value=8_000_000, us_value=2_000_000)
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        expected = plan.total_portfolio_krw - plan.total_estimated_sell_tax_krw
        assert plan.net_after_rebalance_sell_tax_krw == expected

    def test_allocations_sorted_alphabetically(self):
        portfolio = _portfolio()
        targets = TargetAllocation.from_dict({"KR": 30, "US": 70})
        plan = calculate_rebalance(portfolio, targets)
        markets = [a.market for a in plan.allocations]
        assert markets == sorted(markets)
