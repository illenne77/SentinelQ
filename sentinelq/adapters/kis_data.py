"""KIS DataPort adapter — reads cached parquet bars and (optionally) live closes.

For backtest/paper use, this serves bars from ``data/cache/kis_daily/<ticker>.parquet``
which are produced by ``scripts/kis_chart_backfill.py``. ``latest_close`` falls
back to a live KIS REST call (``inquire-price``) when the cache is stale,
controlled by ``allow_live`` flag.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent


class KisData:
    """DataPort implementation. Read-only."""

    def __init__(
        self,
        cache_dir: Path = ROOT / "data" / "cache" / "kis_daily",
        universe_files: Optional[List[Path]] = None,
        allow_live: bool = False,
        kis_client=None,
    ):
        self.cache_dir = Path(cache_dir)
        self.allow_live = allow_live
        self._client = kis_client
        if universe_files is None:
            universe_files = [
                ROOT / "research" / "a4_liquidity_surge" / "universe_kospi_top80.txt",
                ROOT / "research" / "a4_liquidity_surge" / "universe_kosdaq_midcap.txt",
            ]
        self._universe_files = universe_files
        self._universe_cache: Optional[List[str]] = None
        self._bar_cache: dict = {}

    def get_universe(self) -> List[str]:
        if self._universe_cache is not None:
            return list(self._universe_cache)
        tickers = []
        for fp in self._universe_files:
            if not fp.exists():
                continue
            for line in fp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tk = line.split()[0].zfill(6)
                if tk not in tickers:
                    tickers.append(tk)
        self._universe_cache = tickers
        return list(tickers)

    def _load_full(self, ticker: str) -> pd.DataFrame:
        if ticker in self._bar_cache:
            return self._bar_cache[ticker]
        f = self.cache_dir / f"{ticker}.parquet"
        if not f.exists():
            df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        else:
            df = pd.read_parquet(f)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            need_cols = {"open", "high", "low", "close", "volume"}
            if not need_cols.issubset(df.columns):
                # Some caches store only close+volume; pad with close where missing
                for c in ("open", "high", "low"):
                    if c not in df.columns and "close" in df.columns:
                        df[c] = df["close"]
                if "volume" not in df.columns:
                    df["volume"] = 0
        self._bar_cache[ticker] = df
        return df

    def get_daily_bars(self, ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        df = self._load_full(ticker)
        if df.empty:
            return df
        m = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
        return df.loc[m].copy()

    def latest_close(self, ticker: str, asof: pd.Timestamp) -> Optional[float]:
        df = self._load_full(ticker)
        if not df.empty:
            sub = df.loc[df.index <= pd.Timestamp(asof)]
            if not sub.empty:
                cached = float(sub["close"].iloc[-1])
                # If cache covers asof's date, return it
                if sub.index[-1].date() >= pd.Timestamp(asof).date():
                    return cached
                if not self.allow_live:
                    return cached
        if self.allow_live and self._client is not None:
            try:
                resp = self._client.get(
                    "/uapi/domestic-stock/v1/quotations/inquire-price",
                    params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
                    tr_id="FHKST01010100",
                )
                px = resp.get("output", {}).get("stck_prpr")
                return float(px) if px is not None else None
            except Exception:
                return None
        return None
