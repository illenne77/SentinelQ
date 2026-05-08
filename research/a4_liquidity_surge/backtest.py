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
from gates import apply_daily_gates, load_gates  # noqa: E402


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

    gates = load_gates()
    print(f"[backtest] gates: ADV>={gates.min_avg_daily_value_eokwon}억, "
          f"price∈[{gates.min_price_krw:,.0f}, {gates.max_price_krw:,.0f}] KRW")

    rows: list[dict] = []
    for t, daily in bars_by_ticker.items():
        feats = compute_surge_ratios(daily, lookback=20, threshold=threshold)
        if feats.empty:
            continue
        fwd = forward_return(daily, horizon=horizon).rename("ret_fwd")
        gate_pass = apply_daily_gates(daily, gates, lookback=20).rename("gate_pass")
        feats = feats.join(fwd).join(gate_pass)
        for date, row in feats[feats["triggered"]].iterrows():
            rows.append({
                "ticker": t,
                "date": date,
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "surge_ratio": float(row["surge_ratio"]),
                "ret_fwd": float(row["ret_fwd"]) if pd.notna(row["ret_fwd"]) else None,
                "gate_pass": bool(row["gate_pass"]) if pd.notna(row["gate_pass"]) else False,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        print("[backtest] no triggers")
        return df

    valid = df.dropna(subset=["ret_fwd"])
    gated = valid[valid["gate_pass"]]
    print(f"\n[backtest] === gate filter ===")
    print(f"  triggers (with fwd ret) : {len(valid)}")
    print(f"  passed daily gates       : {len(gated)}  ({len(gated)/len(valid):.1%})")

    print(f"\n[backtest] === results (gross) ===")
    for label, sub in [("ALL TRIGGERS", valid), ("GATE-PASS ONLY", gated)]:
        if sub.empty:
            print(f"  {label}: empty")
            continue
        print(f"  {label}:")
        print(f"    n                   : {len(sub)}")
        print(f"    mean fwd {horizon}d return : {sub['ret_fwd'].mean():+.4f}")
        print(f"    median               : {sub['ret_fwd'].median():+.4f}")
        print(f"    hit rate (>0)        : {(sub['ret_fwd'] > 0).mean():.4f}")
        print(f"    win/loss avg         : "
              f"{sub[sub['ret_fwd']>0]['ret_fwd'].mean():+.4f} / "
              f"{sub[sub['ret_fwd']<0]['ret_fwd'].mean():+.4f}")

    # Apply transaction costs across multiple cost profiles (gate-pass set).
    print(f"\n[backtest] === results net-of-cost (GATE-PASS ONLY) ===")
    print(f"  {'profile':<14} {'rt_bps':>7} {'mean':>8} {'median':>8} {'hit':>6}")
    if not gated.empty:
        for name, cm in [("CHEAP", CHEAP), ("DEFAULT", DEFAULT), ("CONSERVATIVE", CONSERVATIVE)]:
            net = gated["ret_fwd"].apply(cm.net_return)
            print(f"  {name:<14} {cm.round_trip_bps():>7.1f} "
                  f"{net.mean():>+8.4f} {net.median():>+8.4f} {(net > 0).mean():>6.3f}")

    # Bucket by surge intensity (GATE-PASS, gross + net default)
    if not gated.empty:
        print("\n  by surge_ratio bucket (GATE-PASS, DEFAULT cost):")
        df_v = gated.copy()
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

        # Bucket-exclusion experiment: drop the 2.0–3.0× weak-zone and
        # report the resulting net edge (DEFAULT cost). Baseline KPI from
        # plan v2.2 §7.3: hit rate ≥ 58%, mean ≥ +1.2% / trade.
        print("\n  === bucket-exclusion experiment (drop 2.0-3.0x, GATE-PASS, DEFAULT cost) ===")
        kept = df_v[df_v["bucket"] != "2.0-3.0"]
        dropped = df_v[df_v["bucket"] == "2.0-3.0"]
        if not kept.empty:
            n_kept = len(kept)
            n_drop = len(dropped)
            mean_g = kept["ret_fwd"].mean()
            mean_n = kept["ret_net"].mean()
            med_n = kept["ret_net"].median()
            hit_n = (kept["ret_net"] > 0).mean()
            print(f"  kept     : n={n_kept}  gross_mean={mean_g:+.4f}  net_mean={mean_n:+.4f}  net_median={med_n:+.4f}  net_hit={hit_n:.4f}")
            print(f"  dropped  : n={n_drop} (2.0-3.0x bucket)")
            kpi_mean_pass = "PASS" if mean_n >= 0.012 else "FAIL"
            kpi_hit_pass = "PASS" if hit_n >= 0.58 else "FAIL"
            print(f"  KPI v2.2 7.3:  mean >= +1.2% [{kpi_mean_pass}]   hit >= 58% [{kpi_hit_pass}]")

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
