"""
A4 backtest with realistic exit rules (plan v2.2 §7.5).

Replaces forward_return-based scoring with the actual deterministic
exit ladder: stop -2% / scaled TP +3%/+5% / trailing -1.5% / time horizon.

Compares:
  baseline forward-return  vs  exit-rule realized return.
Reports KPI vs plan §7.3 thresholds (mean ≥ +1.2%, hit ≥ 58%).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from data_loader import (  # noqa: E402
    compute_surge_ratios,
    get_kospi200,
    load_daily_bars_batch,
)
from costs import DEFAULT, CHEAP, CONSERVATIVE  # noqa: E402
from gates import apply_daily_gates, load_gates  # noqa: E402
from exit_rules import simulate_exit  # noqa: E402


def run(
    start: str = "20250101",
    end: str = "20260508",
    threshold: float = 1.5,
    horizon: int = 5,
) -> pd.DataFrame:
    print(f"[exit-bt] {start} -> {end}  threshold={threshold}  horizon={horizon}d")
    print(f"[exit-bt] exit rules: stop=-2%, tp1=+3%(50%), tp2=+5%(30%), "
          f"trail=-1.5%(20%), time={horizon}d")

    tickers = get_kospi200(end)
    print(f"[exit-bt] universe: {len(tickers)} tickers")

    bars_by_ticker = load_daily_bars_batch(tickers, start, end, verbose=False)
    print(f"[exit-bt] loaded bars for {len(bars_by_ticker)} tickers")

    gates = load_gates()

    rows: list[dict] = []
    for t, daily in bars_by_ticker.items():
        feats = compute_surge_ratios(daily, lookback=20, threshold=threshold)
        if feats.empty:
            continue
        gate_pass = apply_daily_gates(daily, gates, lookback=20).rename("gate_pass")
        feats = feats.join(gate_pass)
        triggers = feats[feats["triggered"]]

        for trigger_date, row in triggers.iterrows():
            entry_close = float(row["close"])
            # future bars start the day AFTER the trigger
            try:
                trigger_idx = daily.index.get_loc(trigger_date)
            except KeyError:
                continue
            future = daily.iloc[trigger_idx + 1: trigger_idx + 1 + horizon]
            if len(future) < horizon:
                continue  # incomplete window — skip (don't peek partial)

            exit_result = simulate_exit(entry_close, future, horizon=horizon)

            # Also compute naive forward return for comparison
            fwd_close = float(future.iloc[-1]["close"])
            ret_fwd = (fwd_close / entry_close) - 1.0

            rows.append({
                "ticker": t,
                "date": trigger_date,
                "entry_close": entry_close,
                "surge_ratio": float(row["surge_ratio"]),
                "gate_pass": bool(row["gate_pass"]) if pd.notna(row["gate_pass"]) else False,
                "ret_fwd": ret_fwd,
                "ret_exit": exit_result.realized_return,
                "exit_reason": exit_result.exit_reason,
                "exit_day": exit_result.exit_day,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        print("[exit-bt] no triggers")
        return df

    gated = df[df["gate_pass"]].copy()
    print(f"\n[exit-bt] === sample sizes ===")
    print(f"  total triggers : {len(df)}")
    print(f"  gate-pass      : {len(gated)}  ({len(gated)/len(df):.1%})")

    # Compare forward-return (current proxy) vs exit-rule realized return
    print(f"\n[exit-bt] === forward return vs exit-rule (GATE-PASS) ===")
    print(f"  {'metric':<14} {'fwd-ret':>9} {'exit-rule':>11}")

    # Apply DEFAULT cost to both (round-trip 31bp)
    gated["fwd_net"] = gated["ret_fwd"].apply(DEFAULT.net_return)
    gated["exit_net"] = gated["ret_exit"].apply(DEFAULT.net_return)

    print(f"  {'mean (gross)':<14} {gated['ret_fwd'].mean():>+9.4f} "
          f"{gated['ret_exit'].mean():>+11.4f}")
    print(f"  {'mean (net)':<14} {gated['fwd_net'].mean():>+9.4f} "
          f"{gated['exit_net'].mean():>+11.4f}")
    print(f"  {'median (net)':<14} {gated['fwd_net'].median():>+9.4f} "
          f"{gated['exit_net'].median():>+11.4f}")
    print(f"  {'hit (net)':<14} {(gated['fwd_net']>0).mean():>9.4f} "
          f"{(gated['exit_net']>0).mean():>11.4f}")
    print(f"  {'win avg (net)':<14} "
          f"{gated.loc[gated['fwd_net']>0,'fwd_net'].mean():>+9.4f} "
          f"{gated.loc[gated['exit_net']>0,'exit_net'].mean():>+11.4f}")
    print(f"  {'loss avg (net)':<14} "
          f"{gated.loc[gated['fwd_net']<0,'fwd_net'].mean():>+9.4f} "
          f"{gated.loc[gated['exit_net']<0,'exit_net'].mean():>+11.4f}")

    # KPI check
    mean_n = gated["exit_net"].mean()
    hit_n = (gated["exit_net"] > 0).mean()
    kpi_m = "PASS" if mean_n >= 0.012 else "FAIL"
    kpi_h = "PASS" if hit_n >= 0.58 else "FAIL"
    print(f"\n[exit-bt] === KPI v2.2 §7.3 (exit-rule, GATE-PASS, DEFAULT cost) ===")
    print(f"  mean >= +1.2%  : {mean_n:+.4f}  [{kpi_m}]")
    print(f"  hit  >= 58.0%  : {hit_n:.4f}  [{kpi_h}]")

    # Exit-reason breakdown
    print(f"\n[exit-bt] === exit reason breakdown (GATE-PASS, exit-rule) ===")
    rb = gated.groupby("exit_reason").agg(
        n=("exit_net", "count"),
        net_mean=("exit_net", "mean"),
        net_hit=("exit_net", lambda s: (s > 0).mean()),
    ).sort_values("n", ascending=False)
    rb["pct"] = (rb["n"] / rb["n"].sum() * 100).round(1)
    print(rb.to_string())

    # By bucket
    print(f"\n[exit-bt] === bucket x exit-rule (GATE-PASS, DEFAULT cost) ===")
    gated["bucket"] = pd.cut(
        gated["surge_ratio"],
        bins=[1.5, 2.0, 3.0, 5.0, 100.0],
        labels=["1.5-2.0", "2.0-3.0", "3.0-5.0", "5.0+"],
    )
    bb = gated.groupby("bucket", observed=True).agg(
        n=("exit_net", "count"),
        gross_mean=("ret_exit", "mean"),
        net_mean=("exit_net", "mean"),
        net_hit=("exit_net", lambda s: (s > 0).mean()),
    )
    print(bb.to_string())

    out = ROOT / "_cache" / f"exit_backtest_{start}_{end}_t{threshold}_h{horizon}.parquet"
    df.to_parquet(out, index=False)
    print(f"\n[exit-bt] saved to {out}")
    return df


if __name__ == "__main__":
    args = sys.argv[1:]
    start = args[0] if len(args) > 0 else "20250101"
    end = args[1] if len(args) > 1 else "20260508"
    threshold = float(args[2]) if len(args) > 2 else 1.5
    horizon = int(args[3]) if len(args) > 3 else 5
    run(start, end, threshold, horizon)
