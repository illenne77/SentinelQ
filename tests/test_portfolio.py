"""Tests for sentinelq.portfolio.portfolio."""
from __future__ import annotations

import pandas as pd
import pytest

from sentinelq.portfolio.portfolio import Fill, Portfolio, PositionState


def _ts(date: str) -> pd.Timestamp:
    return pd.Timestamp(date)


def test_initial_state():
    p = Portfolio(initial_cash=1_000_000.0)
    assert p.cash() == 1_000_000.0
    assert p.nav() == 1_000_000.0
    assert p.equity == 1_000_000.0
    assert p.position_count() == 0
    assert p.gross_exposure() == 0.0
    assert p.peak_nav() == 1_000_000.0
    assert p.drawdown() == 0.0
    assert p.unrealized_pnl() == 0.0
    assert p.realized_pnl() == 0.0


def test_buy_then_sell_round_trip_with_fees():
    """Open BUY -> mark -> SELL closes the position; cash and PnL net out."""
    p = Portfolio(initial_cash=1_000_000.0)

    p.on_fill(Fill("AAA", _ts("2024-01-02"), "BUY", 10, 50_000.0, 100.0))
    assert p.position_count() == 1
    pos = p.positions()["AAA"]
    assert isinstance(pos, PositionState)
    assert pos.quantity == 10
    assert pos.avg_cost == 50_000.0
    # cash = 1,000,000 - (10 * 50,000) - 100 = 499,900
    assert p.cash() == pytest.approx(499_900.0)

    nav = p.mark(_ts("2024-01-02"), {"AAA": 51_000.0})
    assert p.unrealized_pnl("AAA") == pytest.approx(10_000.0)
    assert nav == pytest.approx(p.cash() + 10 * 51_000.0)
    assert p.peak_nav() == pytest.approx(nav)

    p.on_fill(Fill("AAA", _ts("2024-01-03"), "SELL", 10, 52_000.0, 100.0))
    assert p.position_count() == 0
    # Realized = 10 * (52,000 - 50,000) - 100 = 19,900
    assert p.realized_pnl() == pytest.approx(19_900.0)
    # Cash = 499,900 + (10*52,000 - 100) = 1,019,800
    assert p.cash() == pytest.approx(1_019_800.0)
    assert p.nav() == pytest.approx(1_019_800.0)
    assert p.unrealized_pnl() == 0.0
    assert p.total_commission() == pytest.approx(200.0)


def test_buy_average_cost_on_add():
    p = Portfolio(initial_cash=10_000_000.0)
    p.on_fill(Fill("AAA", _ts("2024-01-02"), "BUY", 10, 50_000.0, 0.0))
    p.on_fill(Fill("AAA", _ts("2024-01-03"), "BUY", 10, 60_000.0, 0.0))
    pos = p.positions()["AAA"]
    assert pos.quantity == 20
    assert pos.avg_cost == pytest.approx(55_000.0)


def test_mark_tracks_peak_and_drawdown():
    p = Portfolio(initial_cash=1_000_000.0)
    p.on_fill(Fill("AAA", _ts("2024-01-02"), "BUY", 10, 50_000.0, 0.0))
    p.mark(_ts("2024-01-02"), {"AAA": 60_000.0})
    assert p.peak_nav() == pytest.approx(1_100_000.0)
    p.mark(_ts("2024-01-03"), {"AAA": 40_000.0})
    assert p.peak_nav() == pytest.approx(1_100_000.0)
    assert p.drawdown() == pytest.approx((900_000.0 / 1_100_000.0) - 1.0)
    s = p.nav_series()
    assert list(s.index) == [_ts("2024-01-02"), _ts("2024-01-03")]
    assert s.iloc[0] == pytest.approx(1_100_000.0)
    assert s.iloc[1] == pytest.approx(900_000.0)


def test_round_trip_cost_30bps_convention():
    """Half-on-entry / half-on-exit commission split totalling 0.30%.

    Matches the A2/A3/A4 walkforward convention (ROUND_TRIP_COST = 0.0030).
    """
    notional = 1_000_000.0
    half_bps = 0.0015
    qty = 10
    entry_px = notional / qty
    entry_commission = notional * half_bps
    exit_commission = notional * half_bps

    p = Portfolio(initial_cash=2_000_000.0)
    p.on_fill(Fill("AAA", _ts("2024-01-02"), "BUY", qty, entry_px, entry_commission))
    p.on_fill(Fill("AAA", _ts("2024-01-03"), "SELL", qty, entry_px, exit_commission))
    assert p.cash() == pytest.approx(2_000_000.0 - notional * 0.0030)
    assert p.position_count() == 0


def test_invalid_side_raises():
    p = Portfolio(initial_cash=100.0)
    with pytest.raises(ValueError):
        p.on_fill(Fill("AAA", _ts("2024-01-02"), "HOLD", 1, 1.0, 0.0))
