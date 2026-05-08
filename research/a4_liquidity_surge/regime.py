"""A7 regime classifier — frozen per PREREG-0002 §2.

Inputs: KODEX200 (069500) daily bars.
Output: pd.Series indexed by date with values {"OK", "WEAK"}.

Frozen rule:
    WEAK iff ALL three:
      1. close < SMA(close, 200)
      2. SMA(close, 20) < SMA(close, 50)
      3. realised_vol_20d >= rolling 80th percentile over past 252d

Any change to this definition requires a PREREG-0002 amendment commit
that precedes the measurement timestamp.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from api.kis_client import KisClient
from api.kis_chart import fetch_daily

KODEX200 = "069500"


def load_kodex200(start: str = "2020-01-01", end: str = "2026-05-08",
                  env: str = "paper") -> pd.DataFrame:
    client = KisClient.from_env(env=env)
    return fetch_daily(client, KODEX200, start, end)


def classify_regime(bars: pd.DataFrame) -> pd.Series:
    """Return Series of 'OK'/'WEAK' aligned to bars.index."""
    close = bars["close"].astype(float)
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    log_ret = np.log(close / close.shift(1))
    realized_vol_20 = log_ret.rolling(20).std() * np.sqrt(252)
    # 252d rolling 80th percentile of vol
    vol_pct80 = realized_vol_20.rolling(252).quantile(0.80)

    cond_trend = close < sma200
    cond_cross = sma20 < sma50
    cond_vol = realized_vol_20 >= vol_pct80

    weak = cond_trend & cond_cross & cond_vol
    out = pd.Series(np.where(weak, "WEAK", "OK"), index=bars.index, name="regime")
    # before warmup (NaN), force "OK" (do not penalise; equivalent to no filter)
    warmup_mask = sma200.isna() | vol_pct80.isna()
    out.loc[warmup_mask] = "OK"
    return out


if __name__ == "__main__":
    import sys
    bars = load_kodex200()
    reg = classify_regime(bars)
    weak_pct = (reg == "WEAK").mean()
    print(f"KODEX200 bars: {bars.shape[0]} days  {bars.index.min().date()}..{bars.index.max().date()}")
    print(f"WEAK days: {(reg=='WEAK').sum()}  ({weak_pct:.1%})")
    # show contiguous WEAK regimes
    runs = []
    cur_start = None
    for d, v in reg.items():
        if v == "WEAK" and cur_start is None:
            cur_start = d
        elif v != "WEAK" and cur_start is not None:
            runs.append((cur_start, prev))
            cur_start = None
        prev = d
    if cur_start is not None:
        runs.append((cur_start, reg.index[-1]))
    print(f"\nWEAK regime episodes ({len(runs)}):")
    for s, e in runs:
        print(f"  {s.date()} .. {e.date()}  ({(e-s).days+1}d)")
