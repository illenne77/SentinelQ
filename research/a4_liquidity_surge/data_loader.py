"""
A4 Liquidity Surge — data loader (v0).

Sources:
  * pykrx       — KR equity daily OHLCV + universe (KOSPI200/KOSDAQ150).
                  Free, no auth, but scraper-fragile. Sufficient for daily-bar
                  v0 backtests of the volume surge hypothesis.
  * KIS API     — chart endpoints, used later for minute-bar precision.

Caching:
  All loads are cached as parquet under ./_cache/ (gitignored). Re-runs are
  cheap. Delete _cache/ to force-refresh.

A4 hypothesis (recap, see ./README.md):
    surge_ratio(t) = volume(t) / mean(volume[t-20 : t-1])
    signal: surge_ratio >= 1.5 AND close(t) > close(t-1)
    test:   forward return over [t+1, t+5] vs benchmark
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "_cache"
CACHE.mkdir(exist_ok=True)
(CACHE / "daily").mkdir(exist_ok=True)
(CACHE / "universe").mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def get_kospi200(asof: str) -> list[str]:
    """Return KOSPI200 constituent tickers as of YYYYMMDD.

    NOTE: pykrx.get_index_portfolio_deposit_file is currently broken
    (returns empty DataFrame regardless of date). Falls back to the
    static universe file at ./universe_kospi_top30.txt.
    """
    cache_path = CACHE / "universe" / f"kospi200_{asof}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)["ticker"].tolist()
    try:
        tickers = stock.get_index_portfolio_deposit_file("1028", date=asof)
        if hasattr(tickers, "empty") and tickers.empty:
            tickers = []
        elif not isinstance(tickers, list):
            tickers = list(tickers) if hasattr(tickers, "__iter__") else []
    except Exception:
        tickers = []
    if not tickers:
        tickers = _load_static_universe()
    pd.DataFrame({"ticker": tickers}).to_parquet(cache_path, index=False)
    return tickers


def _load_static_universe() -> list[str]:
    """Fallback: read static ticker file, comments stripped. Prefers top-80
    over top-30 if available."""
    for filename in ["universe_kospi_top80.txt", "universe_kospi_top30.txt"]:
        path = ROOT / filename
        if not path.exists():
            continue
        out: list[str] = []
        seen: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and len(line) == 6 and line.isdigit() and line not in seen:
                out.append(line)
                seen.add(line)
        if out:
            return out
    return []


def get_kosdaq150(asof: str) -> list[str]:
    """Return KOSDAQ150 constituent tickers as of YYYYMMDD."""
    cache_path = CACHE / "universe" / f"kosdaq150_{asof}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)["ticker"].tolist()
    tickers = stock.get_index_portfolio_deposit_file("2203", date=asof)
    pd.DataFrame({"ticker": tickers}).to_parquet(cache_path, index=False)
    return tickers


# ---------------------------------------------------------------------------
# Daily bars
# ---------------------------------------------------------------------------

_KR_TO_EN = {
    "시가": "open", "고가": "high", "저가": "low",
    "종가": "close", "거래량": "volume", "등락률": "pct_change",
}


def load_daily_bars(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Daily OHLCV for `ticker` over [start, end] (inclusive, YYYYMMDD).

    Returns DataFrame indexed by date (DatetimeIndex), columns:
        open, high, low, close, volume, pct_change
    Cached at _cache/daily/<ticker>_<start>_<end>.parquet.
    """
    cache_path = CACHE / "daily" / f"{ticker}_{start}_{end}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    df = stock.get_market_ohlcv(start, end, ticker)
    if df is None or df.empty:
        return pd.DataFrame(columns=list(_KR_TO_EN.values()))
    df = df.rename(columns=_KR_TO_EN)
    df.index.name = "date"
    df.to_parquet(cache_path)
    return df


def load_daily_bars_batch(
    tickers: Iterable[str], start: str, end: str, *, verbose: bool = True
) -> dict[str, pd.DataFrame]:
    """Batch loader. Returns {ticker: DataFrame}. Skips empties."""
    out: dict[str, pd.DataFrame] = {}
    tickers = list(tickers)
    for i, t in enumerate(tickers, 1):
        if verbose and i % 25 == 0:
            print(f"  [{i}/{len(tickers)}] loaded")
        df = load_daily_bars(t, start, end)
        if not df.empty:
            out[t] = df
    return out


# ---------------------------------------------------------------------------
# A4 features
# ---------------------------------------------------------------------------

@dataclass
class A4Signal:
    ticker: str
    date: pd.Timestamp
    surge_ratio: float
    close: float
    close_up: bool      # close(t) > close(t-1)
    triggered: bool     # surge_ratio >= threshold AND close_up


def compute_surge_ratios(
    daily: pd.DataFrame, lookback: int = 20, threshold: float = 1.5
) -> pd.DataFrame:
    """Add surge_ratio + trigger columns. Input must be the output of
    load_daily_bars (date index, volume/close columns)."""
    if len(daily) <= lookback:
        return pd.DataFrame()
    df = daily.copy()
    df["vol_avg"] = df["volume"].rolling(lookback, closed="left").mean()
    df["surge_ratio"] = df["volume"] / df["vol_avg"]
    df["close_up"] = df["close"] > df["close"].shift(1)
    df["triggered"] = (df["surge_ratio"] >= threshold) & df["close_up"]
    return df.dropna(subset=["surge_ratio"])


def forward_return(daily: pd.DataFrame, horizon: int = 5) -> pd.Series:
    """Close-to-close return from t to t+horizon. NaN at the tail."""
    return daily["close"].shift(-horizon) / daily["close"] - 1.0


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else "005930"
    start = sys.argv[2] if len(sys.argv) > 2 else "20250101"
    end = sys.argv[3] if len(sys.argv) > 3 else "20260508"

    print(f"[a4-loader] ticker={ticker} {start} → {end}")
    bars = load_daily_bars(ticker, start, end)
    print(f"  loaded {len(bars)} bars")
    if bars.empty:
        sys.exit(1)

    feats = compute_surge_ratios(bars, lookback=20, threshold=1.5)
    fwd = forward_return(bars, horizon=5)
    feats = feats.join(fwd.rename("ret_5d"))

    triggers = feats[feats["triggered"]]
    print(f"  triggers: {len(triggers)} of {len(feats)} bars")
    if not triggers.empty:
        ret = triggers["ret_5d"].dropna()
        print(f"  mean fwd 5d return on trigger: {ret.mean():.4f}  (n={len(ret)})")
        print(f"  hit rate (>0):                  {(ret > 0).mean():.4f}")
        print("  recent triggers:")
        print(triggers[["close", "volume", "surge_ratio", "ret_5d"]].tail(10))
