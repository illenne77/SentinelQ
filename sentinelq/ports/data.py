"""DataPort — abstraction for historical & latest market data."""
from __future__ import annotations

from typing import List, Optional, Protocol

import pandas as pd


class DataPort(Protocol):
    """Read-only market data accessor."""

    def get_universe(self) -> List[str]:
        """Tickers (6-digit zero-padded) currently in the strategy universe."""
        ...

    def get_daily_bars(
        self, ticker: str, start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DataFrame:
        """OHLCV with DatetimeIndex (tz-naive, KST trading dates).

        Required columns: ``open``, ``high``, ``low``, ``close``, ``volume``.
        Empty DataFrame if no data for the range. MUST NOT raise on
        unknown ticker; MUST raise IOError on transport failure.
        """
        ...

    def latest_close(self, ticker: str, asof: pd.Timestamp) -> Optional[float]:
        """Most recent close at-or-before ``asof``. None if unavailable."""
        ...
