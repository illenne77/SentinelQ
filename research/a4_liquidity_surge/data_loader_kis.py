"""
KIS-backed daily bar loader for A4 research — drop-in replacement for
the pykrx-based loader in data_loader.py.

Same return shape: dict[ticker -> DataFrame] with columns
    open, high, low, close, volume

Universe: today's KOSPI top-80 (static) + known-delisted union if file present.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO))

from api.kis_client import KisClient  # noqa
from api.kis_chart import fetch_daily  # noqa


def load_universe_5y() -> list[str]:
    """KOSPI top-80 + delisted union (best-effort survivorship correction)."""
    tickers: list[str] = []
    seen = set()
    for fname in ("universe_kospi_top80.txt", "universe_delisted_2020_2026.txt",
                  "universe_kosdaq_midcap.txt"):
        fp = ROOT / fname
        if not fp.exists():
            continue
        for line in fp.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            tk = line.split()[0].strip()
            if tk.isdigit() and len(tk) == 6 and tk not in seen:
                tickers.append(tk)
                seen.add(tk)
    return tickers


def load_daily_bars_batch_kis(
    tickers: Iterable[str], start: str, end: str,
    *, env: str = "paper", verbose: bool = True,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """KIS-backed batch loader. start/end as YYYY-MM-DD or YYYYMMDD."""
    client = KisClient.from_env(env=env)
    s = pd.Timestamp(start).strftime("%Y%m%d")
    e = pd.Timestamp(end).strftime("%Y%m%d")
    out: dict[str, pd.DataFrame] = {}
    tickers = list(tickers)
    n = len(tickers)
    for i, t in enumerate(tickers, 1):
        try:
            df = fetch_daily(client, t, s, e, use_cache=use_cache, verbose=False)
        except Exception as ex:
            if verbose:
                print(f"  [{i}/{n}] {t} FAILED: {ex}")
            continue
        if not df.empty:
            out[t] = df[["open", "high", "low", "close", "volume"]].copy()
        if verbose and (i % 10 == 0 or i == n):
            print(f"  [{i}/{n}] loaded={len(out)} (last={t} rows={len(df)})")
    return out


if __name__ == "__main__":
    # Smoke test
    uni = load_universe_5y()
    print(f"universe size = {len(uni)}")
    bars = load_daily_bars_batch_kis(uni[:3], "20200101", "20200601")
    for t, d in bars.items():
        print(f"  {t}: {len(d)} bars  {d.index.min().date()}..{d.index.max().date()}")
