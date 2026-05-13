"""ClockPort adapters: SimulatedClock for backtest, RealClock for paper/live."""

from __future__ import annotations

from datetime import datetime, time

import pandas as pd


class SimulatedClock:
    """Backtest clock — advances explicitly via ``advance_to(ts)``."""

    def __init__(self, start: pd.Timestamp):
        self._now = pd.Timestamp(start)

    def now(self) -> pd.Timestamp:
        return self._now

    def advance_to(self, ts: pd.Timestamp) -> None:
        ts = pd.Timestamp(ts)
        if ts < self._now:
            raise ValueError(f"clock cannot go backwards ({ts} < {self._now})")
        self._now = ts

    def is_market_open(self, ts: pd.Timestamp | None = None) -> bool:
        t = pd.Timestamp(ts) if ts is not None else self._now
        if t.weekday() >= 5:
            return False
        tt = t.time()
        return time(9, 0) <= tt < time(15, 30)

    def next_market_open(self, after: pd.Timestamp) -> pd.Timestamp:
        t = pd.Timestamp(after)
        # Advance day by day until we find a weekday, then snap to 09:00
        for _ in range(10):
            t = t + pd.Timedelta(days=1)
            if t.weekday() < 5:
                return pd.Timestamp(year=t.year, month=t.month, day=t.day, hour=9)
        raise RuntimeError("no market open in next 10 days")


class RealClock:
    """Wall-clock KST. ``now()`` returns tz-naive Asia/Seoul time."""

    def now(self) -> pd.Timestamp:
        # Convert UTC wall clock to KST (UTC+9), tz-naive
        utc_now = datetime.utcnow()
        return pd.Timestamp(utc_now) + pd.Timedelta(hours=9)

    def is_market_open(self, ts: pd.Timestamp | None = None) -> bool:
        t = pd.Timestamp(ts) if ts is not None else self.now()
        if t.weekday() >= 5:
            return False
        tt = t.time()
        return time(9, 0) <= tt < time(15, 30)

    def next_market_open(self, after: pd.Timestamp) -> pd.Timestamp:
        t = pd.Timestamp(after)
        for _ in range(10):
            t = t + pd.Timedelta(days=1)
            if t.weekday() < 5:
                return pd.Timestamp(year=t.year, month=t.month, day=t.day, hour=9)
        raise RuntimeError("no market open in next 10 days")
