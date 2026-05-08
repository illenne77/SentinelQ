"""ClockPort — abstraction over wall-clock vs simulated time."""
from __future__ import annotations

from typing import Optional, Protocol

import pandas as pd


class ClockPort(Protocol):
    def now(self) -> pd.Timestamp:
        """Current time, tz-naive KST."""
        ...

    def is_market_open(self, ts: Optional[pd.Timestamp] = None) -> bool:
        """True if KRX cash market is open at ``ts`` (or now())."""
        ...

    def next_market_open(self, after: pd.Timestamp) -> pd.Timestamp:
        """First market-open timestamp strictly greater than ``after``."""
        ...
