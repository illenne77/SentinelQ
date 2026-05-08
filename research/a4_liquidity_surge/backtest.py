"""
A4 Liquidity Surge — universe backtest v0.

Runs surge-ratio signal across KOSPI200 over a date range, aggregates
forward-return statistics. v0 deliberately ignores:
  * transaction costs / slippage / impact
  * survivorship (uses today's KOSPI200 throughout — bias acknowledged)
  * VI / managed-issue / warning gates (handled by Risk Engine, not signal)
  * regime (bull/bear) splits

These limitations are documented in research/a4_liquidity_surge/README.md
under the bias checklist. v0 is a feasibility check, NOT a graduation test.

Usage:
    python research/a4_liquidity_surge/backtest.py
    python research/a4_liquidity_surge/backtest.py 20240101 20260508 1.5 5
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from data_loader import (  # noqa: E402
    compute_surge_ratios,
    forward_return,
    get_kospi200,
    load_daily_bars_batch,
)
from costs import CONSERVATIVE, DEFAULT, CHEAP  # noqa: E402


def run(
    start: str = "20250101",
    end: str = "20260508",
    threshold: float = 1.5,
    horizon: int = 5,
) -> pd.DataFrame:
    print(f"[backtest] {start} → {end}  threshold={threshold}  horizon={horizon}d")

    universe_asof = end
    tickers = get_kospi200(universe_asof)
    print(f"[backtest] universe = KOSPI200 as of {universe_asof}: {len(tickers)} tickers")

    bars_by_ticker = load_daily_bars_batch(tickers, start, end, verbose=True)
    print(f"[backtest] loaded bars for {len(bars_by_ticker)} tickers")

    rows: list[dict] = []
    for t, daily in bars_by_ticker.items():
        feats = compute_surge_ratios(daily, lookback=20, threshold=threshold)
        if feats.empty:
            continue
        fwd = forward_return(daily, horizon=horizon).rename("ret_fwd")
        feats = feats.join(fwd)
        for date, row in feats[feats["triggered"]].iterrows():
            rows.append({
                "ticker": t,
                "date": date,
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "surge_ratio": float(row["surge_ratio"]),
                "ret_fwd": float(row["ret_fwd"]) if pd.notna(row["ret_fwd"]) else None,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        print("[backtest] no triggers")
        return df

    valid = df.dropna(subset=["ret_fwd"])
    print(f"\n[backtest] === results (gross) ===")
    print(f"  total triggers      : {len(df)}")
    print(f"  with forward return : {len(valid)}")
    print(f"  mean fwd {horizon}d return : {valid['ret_fwd'].mean():.4f}")
    print(f"  median               : {valid['ret_fwd'].median():.4f}")
    print(f"  std                  : {valid['ret_fwd'].std():.4f}")
    print(f"  hit rate (>0)        : {(valid['ret_fwd'] > 0).mean():.4f}")
    print(f"  win/loss avg         : "
          f"{valid[valid['ret_fwd']>0]['ret_fwd'].mean():.4f} / "
          f"{valid[valid['ret_fwd']<0]['ret_fwd'].mean():.4f}")

    # Apply transaction costs across multiple cost profiles.
    print(f"\n[backtest] === results (net of cost) ===")
    print(f"  {'profile':<14} {'rt_bps':>7} {'mean':>8} {'median':>8} {'hit':>6}")
    for name, cm in [("CHEAP", CHEAP), ("DEFAULT", DEFAULT), ("CONSERVATIVE", CONSERVATIVE)]:
        net = valid["ret_fwd"].apply(cm.net_return)
        print(f"  {name:<14} {cm.round_trip_bps():>7.1f} "
              f"{net.mean():>+8.4f} {net.median():>+8.4f} {(net > 0).mean():>6.3f}")

    # Bucket by surge intensity (gross + net default)
    print("\n  by surge_ratio bucket (DEFAULT cost):")
    df_v = valid.copy()
    df_v["bucket"] = pd.cut(
        df_v["surge_ratio"],
        bins=[1.5, 2.0, 3.0, 5.0, 100.0],
        labels=["1.5-2.0", "2.0-3.0", "3.0-5.0", "5.0+"],
    )
    df_v["ret_net"] = df_v["ret_fwd"].apply(DEFAULT.net_return)
    by_bucket = df_v.groupby("bucket", observed=True).agg(
        n=("ret_fwd", "count"),
        gross_mean=("ret_fwd", "mean"),
        net_mean=("ret_net", "mean"),
        net_hit=("ret_net", lambda s: (s > 0).mean()),
    )
    print(by_bucket.to_string())

    out = ROOT / "_cache" / f"backtest_{start}_{end}_t{threshold}_h{horizon}.parquet"
    df.to_parquet(out, index=False)
    print(f"\n[backtest] saved triggers to {out}")
    return df


if __name__ == "__main__":
    args = sys.argv[1:]
    start = args[0] if len(args) > 0 else "20250101"
    end = args[1] if len(args) > 1 else "20260508"
    threshold = float(args[2]) if len(args) > 2 else 1.5
    horizon = int(args[3]) if len(args) > 3 else 5
    run(start, end, threshold, horizon)
