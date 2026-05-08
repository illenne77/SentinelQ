"""KIS investor flow — daily forward-collect.

Purpose: KIS `inquire-investor` (TR FHKST01010900) returns only the last
~30 trading days of investor net buying. To enable a future A6
(Foreign/Institutional Flow Bias) backtest, we must accumulate snapshots
forward starting now.

Strategy:
- Once per day, for the universe (136 tickers), fetch the 30-day window.
- Append new bars to data/cache/kis_investor/<ticker>.parquet
  (keyed by stck_bsop_date; on duplicate, keep latest fetch's value).
- Idempotent: re-running the same day is safe.

Schema saved per ticker (DataFrame index = pd.DatetimeIndex):
    close             prev day close
    prsn_ntby_qty     individual net buy (shares)
    frgn_ntby_qty     foreign net buy (shares)
    orgn_ntby_qty     institution net buy (shares)
    prsn_ntby_krw     individual net buy (KRW, raw 1000-unit)
    frgn_ntby_krw     foreign net buy (KRW)
    orgn_ntby_krw     institution net buy (KRW)

Run daily after market close (e.g. 18:00 KST).

Usage:
    py scripts/kis_investor_forward_collect.py [--limit N] [--verbose]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.kis_client import KisClient

CACHE_DIR = ROOT / "data" / "cache" / "kis_investor"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE_FILES = [
    ROOT / "research" / "a4_liquidity_surge" / "universe_kospi_top80.txt",
    ROOT / "research" / "a4_liquidity_surge" / "universe_kosdaq_midcap.txt",
]

PATH = "/uapi/domestic-stock/v1/quotations/inquire-investor"
TR_ID = "FHKST01010900"

FIELDS = {
    "stck_bsop_date": "date",
    "stck_clpr": "close",
    "prsn_ntby_qty": "prsn_ntby_qty",
    "frgn_ntby_qty": "frgn_ntby_qty",
    "orgn_ntby_qty": "orgn_ntby_qty",
    "prsn_ntby_tr_pbmn": "prsn_ntby_krw",
    "frgn_ntby_tr_pbmn": "frgn_ntby_krw",
    "orgn_ntby_tr_pbmn": "orgn_ntby_krw",
}


def load_universe() -> list[str]:
    seen, out = set(), []
    for f in UNIVERSE_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            t = line.strip().split("#", 1)[0].strip()
            if t and t.isdigit() and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def parse_payload(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    parsed = []
    for r in rows:
        try:
            row = {dst: r.get(src) for src, dst in FIELDS.items()}
            if not row["date"]:
                continue
            parsed.append(row)
        except Exception:
            continue
    if not parsed:
        return pd.DataFrame()
    df = pd.DataFrame(parsed)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fetch_one(client: KisClient, ticker: str) -> pd.DataFrame:
    payload = client.get(
        PATH,
        {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        TR_ID,
    )
    if payload.get("rt_cd") != "0":
        raise RuntimeError(f"{ticker}: {payload.get('msg_cd')} {payload.get('msg1')}")
    return parse_payload(payload.get("output") or [])


def merge_cache(ticker: str, fresh: pd.DataFrame) -> tuple[int, int]:
    """Returns (rows_added, total_rows)."""
    cp = CACHE_DIR / f"{ticker}.parquet"
    if fresh.empty:
        return (0, 0)
    if cp.exists():
        try:
            old = pd.read_parquet(cp)
        except Exception:
            old = pd.DataFrame()
    else:
        old = pd.DataFrame()
    if old.empty:
        merged = fresh
        added = len(fresh)
    else:
        # Keep fresh values on overlap (revisions are rare but possible).
        merged = (pd.concat([old, fresh])
                    .pipe(lambda d: d[~d.index.duplicated(keep="last")])
                    .sort_index())
        added = len(merged) - len(old)
    merged.to_parquet(cp)
    return (added, len(merged))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap tickers (debug)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    universe = load_universe()
    if args.limit:
        universe = universe[: args.limit]
    print(f"forward-collect: {len(universe)} tickers")

    client = KisClient.from_env(env="paper")
    t0 = time.time()
    ok = fail = 0
    total_added = 0
    for i, t in enumerate(universe, 1):
        try:
            fresh = fetch_one(client, t)
            added, total = merge_cache(t, fresh)
            ok += 1
            total_added += added
            if args.verbose:
                print(f"  [{i}/{len(universe)}] {t}: +{added} -> {total} rows")
        except Exception as e:
            fail += 1
            print(f"  [{i}/{len(universe)}] {t}: FAIL {e}", file=sys.stderr)

    dt = time.time() - t0
    print(f"done: ok={ok} fail={fail} added={total_added} elapsed={dt:.1f}s")


if __name__ == "__main__":
    main()
