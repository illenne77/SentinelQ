"""
KIS daily chart fetcher with pagination + parquet cache.

Endpoint: /uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice
TR ID:    FHKST03010100  (period chart)

Returns up to ~100 bars per request bounded by [start, end]. We paginate
backward by chunking the date range into 100-trading-day windows.

Cache: data/cache/kis_daily/<ticker>.parquet  (full series for that ticker)
On re-fetch, we read the cached series and only fetch the gap.

Schema (DataFrame index = pd.DatetimeIndex):
    open   high   low   close   volume   value
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "kis_daily"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
TR_ID = "FHKST03010100"

# KIS returns "output2" rows as list of dicts with keys:
#   stck_bsop_date  open  high  low  close (stck_clpr)  volume  value
_FIELD_MAP = {
    "stck_bsop_date": "date",
    "stck_oprc": "open",
    "stck_hgpr": "high",
    "stck_lwpr": "low",
    "stck_clpr": "close",
    "acml_vol": "volume",
    "acml_tr_pbmn": "value",
}


def _parse_rows(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    out = []
    for r in rows:
        try:
            row = {dst: r.get(src) for src, dst in _FIELD_MAP.items()}
            if not row["date"]:
                continue
            out.append(row)
        except Exception:
            continue
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    for c in ("open", "high", "low", "close", "volume", "value"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"])
    return df


def fetch_daily_chunk(client, ticker: str, start: str, end: str,
                      adj: str = "1") -> pd.DataFrame:
    """One API call. start/end format YYYYMMDD."""
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_DATE_1": start,
        "FID_INPUT_DATE_2": end,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": adj,  # "0" raw, "1" adjusted
    }
    payload = client.get(PATH, params, TR_ID)
    if payload.get("rt_cd") != "0":
        raise RuntimeError(
            f"KIS chart {ticker} {start}..{end} failed: "
            f"{payload.get('msg_cd')} {payload.get('msg1')}"
        )
    return _parse_rows(payload.get("output2") or [])


def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}.parquet"


def fetch_daily(client, ticker: str, start: str, end: str,
                *, use_cache: bool = True, verbose: bool = False) -> pd.DataFrame:
    """Fetch daily bars [start, end] inclusive. Paginates 100-day windows.
    start/end as YYYYMMDD strings.
    """
    cp = _cache_path(ticker)
    cached: Optional[pd.DataFrame] = None
    if use_cache and cp.exists():
        try:
            cached = pd.read_parquet(cp)
        except Exception:
            cached = None

    target_start = pd.Timestamp(start)
    target_end = pd.Timestamp(end)

    have_start = have_end = None
    if cached is not None and not cached.empty:
        have_start = cached.index.min()
        have_end = cached.index.max()

    # Determine fetch ranges (gap on either side of cache).
    fetch_ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    if cached is None or cached.empty:
        fetch_ranges.append((target_start, target_end))
    else:
        if target_start < have_start:
            fetch_ranges.append((target_start, have_start - timedelta(days=1)))
        if target_end > have_end:
            fetch_ranges.append((have_end + timedelta(days=1), target_end))

    new_frames: list[pd.DataFrame] = []
    for rs, re_ in fetch_ranges:
        # Chunk: KIS returns up to 100 trading days; ~140 calendar days safe.
        cur_end = re_
        while cur_end >= rs:
            cur_start = max(rs, cur_end - timedelta(days=140))
            chunk = fetch_daily_chunk(
                client, ticker,
                start=cur_start.strftime("%Y%m%d"),
                end=cur_end.strftime("%Y%m%d"),
            )
            if verbose:
                print(f"  [{ticker}] {cur_start.date()}..{cur_end.date()} -> {len(chunk)} rows")
            if chunk.empty:
                break
            new_frames.append(chunk)
            # Step back; KIS returns oldest..newest so stepping back by oldest-1
            oldest = chunk.index.min()
            if oldest <= rs:
                break
            cur_end = oldest - timedelta(days=1)

    if not new_frames and cached is not None:
        df = cached
    elif not new_frames:
        df = pd.DataFrame()
    else:
        parts = new_frames
        if cached is not None and not cached.empty:
            parts = [cached] + parts
        df = (pd.concat(parts)
              .sort_index()
              .loc[lambda d: ~d.index.duplicated(keep="last")])

    if use_cache and not df.empty:
        try:
            df.to_parquet(cp)
        except Exception as e:
            if verbose:
                print(f"  [{ticker}] cache write failed: {e}", file=sys.stderr)

    if df.empty:
        return df
    mask = (df.index >= target_start) & (df.index <= target_end)
    return df.loc[mask].copy()
