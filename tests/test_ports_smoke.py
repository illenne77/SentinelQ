"""Smoke tests for sentinelq.ports + adapters wiring.

Run: py -m pytest tests/test_ports_smoke.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sentinelq.adapters.clock import RealClock, SimulatedClock
from sentinelq.adapters.kis_broker import KisBroker
from sentinelq.adapters.kis_data import KisData
from sentinelq.portfolio.portfolio import Portfolio
from sentinelq.ports.broker import OrderRequest, OrderStatus


def test_simulated_clock_advances_only_forward():
    c = SimulatedClock(pd.Timestamp("2025-01-02 09:00"))
    assert c.now() == pd.Timestamp("2025-01-02 09:00")
    c.advance_to(pd.Timestamp("2025-01-02 15:00"))
    with pytest.raises(ValueError):
        c.advance_to(pd.Timestamp("2025-01-01 09:00"))


def test_simulated_clock_market_open():
    c = SimulatedClock(pd.Timestamp("2025-01-06 10:00"))  # Monday
    assert c.is_market_open() is True
    c.advance_to(pd.Timestamp("2025-01-06 16:00"))
    assert c.is_market_open() is False
    c.advance_to(pd.Timestamp("2025-01-11 10:00"))  # Saturday
    assert c.is_market_open() is False


def test_real_clock_kst_offset():
    c = RealClock()
    n = c.now()
    assert isinstance(n, pd.Timestamp)
    # No tz; just sanity check it's recent
    delta = abs((pd.Timestamp.utcnow().replace(tzinfo=None) + pd.Timedelta(hours=9)) - n)
    assert delta < pd.Timedelta(seconds=5)


def test_order_request_validation():
    OrderRequest("005930", "BUY", 10)
    with pytest.raises(ValueError):
        OrderRequest("005930", "HOLD", 10)
    with pytest.raises(ValueError):
        OrderRequest("005930", "BUY", 0)
    with pytest.raises(ValueError):
        OrderRequest("005930", "BUY", 10, "LIMIT")  # no limit_price
    OrderRequest("005930", "BUY", 10, "LIMIT", limit_price=70000.0)


def test_kis_data_universe_loads():
    d = KisData()
    u = d.get_universe()
    assert len(u) > 0
    assert all(len(t) == 6 and t.isdigit() for t in u)


def test_kis_data_bars_for_known_ticker():
    d = KisData()
    bars = d.get_daily_bars("005930", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"))
    if bars.empty:
        pytest.skip("KIS daily cache empty for 005930")
    assert {"open", "high", "low", "close", "volume"}.issubset(bars.columns)
    assert (bars["close"] > 0).all()


def test_kis_broker_paper_market_order_round_trip():
    d = KisData()
    if d.latest_close("005930", pd.Timestamp("2025-06-30")) is None:
        pytest.skip("no price for smoke test")
    clock = SimulatedClock(pd.Timestamp("2025-06-30 10:00"))
    broker = KisBroker(data_port=d, clock_port=clock, phase="paper")
    portfolio = Portfolio(initial_cash=10_000_000)

    ack_buy = broker.submit(OrderRequest("005930", "BUY", 10, client_order_id="t1-buy"))
    assert ack_buy.accepted
    assert ack_buy.status == OrderStatus.FILLED
    fills = broker.fills_since(pd.Timestamp("1970-01-01"))
    assert len(fills) == 1
    portfolio.on_fill(fills[0])
    assert broker.positions().get("005930") == 10

    # Idempotent replay
    ack_replay = broker.submit(OrderRequest("005930", "BUY", 10, client_order_id="t1-buy"))
    assert ack_replay.accepted
    assert ack_replay.broker_order_id == ack_buy.broker_order_id
    assert len(broker.fills_since(pd.Timestamp("1970-01-01"))) == 1  # no new fill

    clock.advance_to(pd.Timestamp("2025-09-30 10:00"))
    ack_sell = broker.submit(OrderRequest("005930", "SELL", 10, client_order_id="t1-sell"))
    assert ack_sell.accepted
    assert "005930" not in broker.positions()


def test_kis_broker_live_blocked_without_env():
    d = KisData()
    clock = SimulatedClock(pd.Timestamp("2025-06-30"))
    with pytest.raises(PermissionError):
        KisBroker(data_port=d, clock_port=clock, phase="live")


def test_kis_broker_rejects_when_no_price():
    d = KisData()
    clock = SimulatedClock(pd.Timestamp("2010-01-01"))  # before any cache
    broker = KisBroker(data_port=d, clock_port=clock, phase="paper")
    ack = broker.submit(OrderRequest("999999", "BUY", 10))
    assert ack.accepted is False
    assert ack.status == OrderStatus.REJECTED
