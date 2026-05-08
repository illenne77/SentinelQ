"""Single-currency (KRW) portfolio bookkeeper.

Implements the clean Portfolio interface from
``research/oss_review/architecture_patterns.md`` §4.3.

Design principles (adapted from ``nautilus_trader.portfolio``):
- Fills are the single source of truth for position state changes.
- Realized vs. unrealized PnL are tracked separately.
- ``equity = cash + sum(market_value)`` — no ad-hoc NAV adjustments.
- Peak NAV is tracked on every ``mark()`` so drawdown circuit
  breakers can be evaluated without recomputing the full series.

This module is broker-agnostic: KIS-specific commission and fill
mechanics live in the broker adapter (Phase 3) which produces
``Fill`` events that drive ``Portfolio.on_fill``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class Fill:
    """Atomic fill event — single source of truth for position changes.

    Attributes
    ----------
    ticker:
        Instrument identifier (KR ticker code or symbol).
    date:
        Timestamp of the fill (wall-clock for live, bar timestamp for backtest).
    side:
        ``"BUY"`` or ``"SELL"``. Long-only convention; shorting is not
        supported in Phase 1.
    quantity:
        Number of shares filled (positive integer).
    price:
        Fill price per share, in KRW.
    commission:
        Commission charged for this fill, in KRW. Caller is responsible for
        computing the per-side commission according to the venue fee schedule.
    """

    ticker: str
    date: pd.Timestamp
    side: str
    quantity: int
    price: float
    commission: float


@dataclass
class PositionState:
    """Open position state for a single ticker.

    Tracks share count, volume-weighted average cost, and accumulated
    realized PnL from prior partial closes.
    """

    ticker: str
    quantity: int
    avg_cost: float
    realized_pnl: float = 0.0

    def unrealized_pnl(self, current_price: float) -> float:
        """Return mark-to-market unrealized PnL at ``current_price``."""
        return self.quantity * (current_price - self.avg_cost)

    def market_value(self, current_price: float) -> float:
        """Return current market value of the open position."""
        return self.quantity * current_price


class Portfolio:
    """Single-currency (KRW) portfolio bookkeeper.

    Maintains cash, per-ticker positions, peak NAV, and a NAV time series.
    Decoupled from any broker or strategy — fed exclusively via
    :meth:`on_fill` (event) and :meth:`mark` (end-of-bar marking).

    Usage
    -----
    >>> p = Portfolio(initial_cash=10_000_000)
    >>> p.on_fill(Fill("005930", pd.Timestamp("2024-01-02"), "BUY",
    ...                10, 70_000.0, 100.0))
    >>> nav = p.mark(pd.Timestamp("2024-01-02"), {"005930": 71_000.0})
    """

    def __init__(self, initial_cash: float):
        self._cash: float = float(initial_cash)
        self._positions: Dict[str, PositionState] = {}
        self._peak_nav: float = float(initial_cash)
        self._nav_series: List[Tuple[pd.Timestamp, float]] = []
        self._total_commission: float = 0.0
        self._last_prices: Dict[str, float] = {}
        # Realized PnL from positions that have been fully closed and
        # dropped from ``self._positions``.
        self._closed_realized_pnl: float = 0.0

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_fill(self, fill: Fill) -> None:
        """Apply a fill to cash and position state.

        BUY: cash decreases by ``quantity * price + commission``; the
        position's ``avg_cost`` is updated as the volume-weighted average.

        SELL: cash increases by ``quantity * price - commission``; realized
        PnL is incremented by ``quantity * (price - avg_cost) - commission``.
        If the resulting position quantity is zero or less, the position
        is removed from the open positions map and its realized PnL is
        rolled into a closed-position accumulator.
        """
        self._total_commission += fill.commission
        pos = self._positions.get(fill.ticker)
        # Track the most recent traded price so the next nav() call
        # before an explicit mark() still reflects intra-day fills.
        self._last_prices[fill.ticker] = fill.price

        if fill.side == "BUY":
            cost = fill.quantity * fill.price + fill.commission
            self._cash -= cost
            if pos is None:
                self._positions[fill.ticker] = PositionState(
                    ticker=fill.ticker,
                    quantity=fill.quantity,
                    avg_cost=fill.price,
                )
            else:
                total_qty = pos.quantity + fill.quantity
                pos.avg_cost = (
                    pos.quantity * pos.avg_cost + fill.quantity * fill.price
                ) / total_qty
                pos.quantity = total_qty

        elif fill.side == "SELL":
            proceeds = fill.quantity * fill.price - fill.commission
            self._cash += proceeds
            if pos is not None:
                realized = (
                    fill.quantity * (fill.price - pos.avg_cost) - fill.commission
                )
                pos.realized_pnl += realized
                pos.quantity -= fill.quantity
                if pos.quantity <= 0:
                    self._closed_realized_pnl += pos.realized_pnl
                    del self._positions[fill.ticker]
        else:
            raise ValueError(
                "Fill.side must be 'BUY' or 'SELL', got {!r}".format(fill.side)
            )

    def mark(
        self, date: pd.Timestamp, prices: Dict[str, float]
    ) -> float:
        """End-of-bar mark-to-market.

        Updates the cached last-prices, refreshes the peak-NAV high-water
        mark, and appends a ``(date, nav)`` row to the NAV series.

        Returns the current NAV after the update.
        """
        self._last_prices.update(prices)
        nav = self.nav()
        if nav > self._peak_nav:
            self._peak_nav = nav
        self._nav_series.append((date, nav))
        return nav

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def nav(self) -> float:
        """Current NAV: cash + market value of all open positions."""
        return self._cash + self.gross_exposure()

    @property
    def equity(self) -> float:
        """Equity = cash + sum(market_value). Alias for :meth:`nav`."""
        return self.nav()

    def cash(self) -> float:
        """Available cash balance in KRW."""
        return self._cash

    def gross_exposure(self) -> float:
        """Total market value of all open positions at last known prices."""
        total = 0.0
        for ticker, pos in self._positions.items():
            price = self._last_prices.get(ticker, pos.avg_cost)
            total += pos.market_value(price)
        return total

    def unrealized_pnl(self, ticker: Optional[str] = None) -> float:
        """Unrealized PnL for ``ticker`` or summed across all positions."""
        if ticker is not None:
            pos = self._positions.get(ticker)
            if pos is None:
                return 0.0
            price = self._last_prices.get(ticker, pos.avg_cost)
            return pos.unrealized_pnl(price)
        total = 0.0
        for t, pos in self._positions.items():
            price = self._last_prices.get(t, pos.avg_cost)
            total += pos.unrealized_pnl(price)
        return total

    def realized_pnl(self, ticker: Optional[str] = None) -> float:
        """Realized PnL for ``ticker`` or summed (open + closed positions)."""
        if ticker is not None:
            pos = self._positions.get(ticker)
            return pos.realized_pnl if pos else 0.0
        open_realized = sum(p.realized_pnl for p in self._positions.values())
        return open_realized + self._closed_realized_pnl

    def peak_nav(self) -> float:
        """Highest NAV observed via :meth:`mark` since inception."""
        return self._peak_nav

    def drawdown(self) -> float:
        """Current drawdown from peak NAV.

        Returns a non-positive float where ``-0.05`` means -5% from peak.
        """
        if self._peak_nav == 0:
            return 0.0
        return (self.nav() / self._peak_nav) - 1.0

    def position_count(self) -> int:
        """Number of currently open positions."""
        return len(self._positions)

    def positions(self) -> Dict[str, PositionState]:
        """Snapshot copy of the open positions map."""
        return dict(self._positions)

    def total_commission(self) -> float:
        """Cumulative commission paid (KRW) across all fills."""
        return self._total_commission

    def nav_series(self) -> pd.Series:
        """NAV time series indexed by mark date."""
        if not self._nav_series:
            return pd.Series(dtype=float)
        s = pd.Series(
            {d: v for d, v in self._nav_series},
            dtype=float,
        )
        return s.sort_index()
