"""Tests for sentinelq.risk.engine."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from sentinelq.risk.engine import (
    OrderRequest,
    RiskCheckResult,
    RiskConfig,
    RiskEngine,
)


@dataclass
class FakePortfolio:
    """In-memory PortfolioState double for unit tests."""

    _nav: float = 10_000_000.0
    _cash: float = 10_000_000.0
    _position_count: int = 0
    _gross_exposure: float = 0.0
    _peak_nav: float = 10_000_000.0
    _drawdown: float = 0.0

    def nav(self):
        return self._nav

    def cash(self):
        return self._cash

    def position_count(self):
        return self._position_count

    def gross_exposure(self):
        return self._gross_exposure

    def peak_nav(self):
        return self._peak_nav

    def drawdown(self):
        return self._drawdown


def _engine() -> RiskEngine:
    return RiskEngine(
        RiskConfig(
            max_notional_per_order={"BIG": 500_000.0},
            max_position_count=3,
            max_gross_exposure_pct=1.0,
            max_single_position_pct=0.20,
            max_drawdown_pct=0.15,
            max_sector_pct={"SEMI": 0.30},
            order_submit_cooldown_sec=0.0,
        )
    )


def test_approves_normal_order():
    e = _engine()
    pf = FakePortfolio()
    res = e.check(OrderRequest("AAA", "BUY", 10, 100_000.0), pf)
    assert isinstance(res, RiskCheckResult)
    assert res.approved is True
    assert res.code == "ok"
    assert bool(res) is True
    approved, reason = res
    assert approved is True
    assert reason == ""


def test_rejects_per_ticker_notional_cap():
    e = _engine()
    pf = FakePortfolio()
    res = e.check(OrderRequest("BIG", "BUY", 10, 100_000.0), pf)
    assert not res.approved
    assert res.code == "ticker_notional"


def test_rejects_position_count_cap():
    e = _engine()
    pf = FakePortfolio(_position_count=3)
    res = e.check(OrderRequest("AAA", "BUY", 1, 1_000.0), pf)
    assert not res.approved
    assert res.code == "position_count"


def test_rejects_single_position_pct_cap():
    e = _engine()
    pf = FakePortfolio()
    res = e.check(OrderRequest("AAA", "BUY", 1, 2_500_000.0), pf)
    assert not res.approved
    assert res.code == "position_pct"


def test_rejects_gross_exposure_cap():
    e = _engine()
    pf = FakePortfolio(_gross_exposure=9_500_000.0)
    res = e.check(OrderRequest("AAA", "BUY", 10, 100_000.0), pf)
    assert not res.approved
    assert res.code == "gross_exposure"


def test_rejects_drawdown_circuit_breaker():
    e = _engine()
    pf = FakePortfolio(_drawdown=-0.20)
    res = e.check(OrderRequest("AAA", "BUY", 1, 1_000.0), pf)
    assert not res.approved
    assert res.code == "drawdown"


def test_rejects_sector_cap():
    e = _engine()
    pf = FakePortfolio()
    # SEMI cap is 30% of NAV = 3,000,000. 2,800,000 + 500,000 = 3,300,000.
    res = e.check(
        OrderRequest("AAA", "BUY", 5, 100_000.0, sector="SEMI"),
        pf,
        sector_exposures={"SEMI": 2_800_000.0},
    )
    assert not res.approved
    assert res.code == "sector_pct"


def test_sector_cap_passes_when_under_limit():
    e = _engine()
    pf = FakePortfolio()
    res = e.check(
        OrderRequest("AAA", "BUY", 5, 100_000.0, sector="SEMI"),
        pf,
        sector_exposures={"SEMI": 1_000_000.0},
    )
    assert res.approved


def test_rate_limit_cooldown():
    e = RiskEngine(
        RiskConfig(
            max_position_count=10,
            max_single_position_pct=1.0,
            max_drawdown_pct=1.0,
            order_submit_cooldown_sec=0.5,
        )
    )
    pf = FakePortfolio()
    order = OrderRequest("AAA", "BUY", 1, 1_000.0)
    assert e.check(order, pf).approved
    e.record_submit()
    res = e.check(order, pf)
    assert not res.approved
    assert res.code == "rate_limit"


def test_sell_does_not_consume_buy_only_caps():
    e = _engine()
    pf = FakePortfolio(_position_count=3, _gross_exposure=10_000_000.0)
    res = e.check(OrderRequest("AAA", "SELL", 10, 100_000.0), pf)
    assert res.approved
