"""
A4 variant sweep — ATR-based stop, entry-timing shift, wider TP ladders.

Plan §7.5 permits ATR(14)*k as a stop variant. Tests:
  * Stop type: fixed pct vs ATR(14)*k for k in {1.0, 1.5, 2.0}
  * TP ladder: default +3/+5 vs wider +5/+10
  * Entry: trigger close vs next-day open

Each cell reports net mean / hit / KPI flags.
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from data_loader import compute_surge_ratios, get_kospi200, load_daily_bars_batch  # noqa
from gates import apply_daily_gates, load_gates  # noqa
from costs import DEFAULT  # noqa
import exit_rules  # noqa: E402

START, END, THR, H = "20250101", "20260508", 1.5, 5

# 1. Build the trigger set ONCE; re-use across variants.
tickers = get_kospi200(END)
bars = load_daily_bars_batch(tickers, START, END, verbose=False)
gates = load_gates()

triggers = []  # list of (entry_close, future_bars, atr14_at_entry, next_day_open, future_bars_from_open, entry_open)
for t, daily in bars.items():
    feats = compute_surge_ratios(daily, lookback=20, threshold=THR)
    if feats.empty:
        continue
    gp = apply_daily_gates(daily, gates, lookback=20).rename("gate_pass")
    feats = feats.join(gp)
    atr = exit_rules.compute_atr(daily, lookback=14)

    for date, row in feats[feats["triggered"]].iterrows():
        if not bool(row.get("gate_pass", False)):
            continue
        try:
            i = daily.index.get_loc(date)
        except KeyError:
            continue
        # Need at least horizon+1 future bars (one extra for next-day-open variant)
        future_close = daily.iloc[i + 1: i + 1 + H]
        future_open = daily.iloc[i + 1: i + 2 + H]
        if len(future_close) < H or len(future_open) < H + 1:
            continue
        atr_val = atr.iloc[i]
        if pd.isna(atr_val):
            continue
        entry_close = float(row["close"])
        next_open = float(future_open.iloc[0]["open"])
        # for next-day-open entry: bars from day t+2, with day t+1 incorporated
        # via "open of day t+1 is entry; intraday risk from day t+1 also counts"
        # Simplification: treat day t+1 as first sim bar but with entry=open
        # → use future_open as the bar series, but anchor entry at next_open.
        triggers.append({
            "ticker": t,
            "date": date,
            "entry_close": entry_close,
            "next_open": next_open,
            "atr14": float(atr_val),
            "future_from_close": future_close,
            "future_from_open": future_open,  # H+1 bars; entry on bar 0's open
            "surge_ratio": float(row["surge_ratio"]),
        })

print(f"[atr-sweep] {len(triggers)} triggers (gate-pass, ATR available)")


def run_variant(label, *, stop_mode, k_atr=None, stop_pct=None,
                tp1=0.03, tp2=0.05, trail=-0.015, entry="close"):
    # Mutate global params on exit_rules for TPs (cheap reuse)
    exit_rules.TP1_PCT = tp1
    exit_rules.TP2_PCT = tp2
    exit_rules.TRAIL_PCT = trail

    rets = []
    stop_outs = 0
    for tr in triggers:
        if entry == "close":
            entry_px = tr["entry_close"]
            future = tr["future_from_close"]
        else:  # next-day open
            entry_px = tr["next_open"]
            future = tr["future_from_open"]

        if stop_mode == "fixed":
            stop_px = entry_px * (1 + stop_pct)
        elif stop_mode == "atr":
            stop_px = entry_px - k_atr * tr["atr14"]
        else:
            raise ValueError(stop_mode)

        res = exit_rules.simulate_exit(entry_px, future, horizon=H, stop_px=stop_px)
        rets.append(res.realized_return)
        if res.exit_reason == "stop":
            stop_outs += 1

    s = pd.Series(rets)
    sn = s.apply(DEFAULT.net_return)
    mean_n = sn.mean()
    hit_n = (sn > 0).mean()
    flag_m = "M" if mean_n >= 0.012 else "."
    flag_h = "H" if hit_n >= 0.58 else "."
    print(f"  {label:<48} {s.mean():>+8.4f} {mean_n:>+8.4f} "
          f"{hit_n:>7.4f} {stop_outs/len(rets):>7.1%} {flag_m}{flag_h}")


hdr = f"  {'variant':<48} {'gross':>8} {'net':>8} {'hit':>7} {'stopout':>7}  KPI"
print(hdr)
print("  " + "-" * (len(hdr) - 2))

# Baseline (default plan §7.5 fixed -2%, +3/+5/-1.5, close entry)
run_variant("baseline fixed -2% / +3/+5 / close",
            stop_mode="fixed", stop_pct=-0.02)

# ATR variants (k = 1.0 / 1.5 / 2.0), default TP ladder, close entry
for k in (1.0, 1.5, 2.0):
    run_variant(f"ATR k={k} / +3/+5 / close",
                stop_mode="atr", k_atr=k)

# ATR k=1.5 with wider TP ladder
run_variant("ATR k=1.5 / +5/+10 / close",
            stop_mode="atr", k_atr=1.5, tp1=0.05, tp2=0.10, trail=-0.025)

# ATR k=2.0 with wider TP ladder
run_variant("ATR k=2.0 / +5/+10 / close",
            stop_mode="atr", k_atr=2.0, tp1=0.05, tp2=0.10, trail=-0.025)

# Entry-timing shift: enter at next-day open instead of close
run_variant("ATR k=1.5 / +3/+5 / NEXT-DAY OPEN",
            stop_mode="atr", k_atr=1.5, entry="open")
run_variant("ATR k=1.5 / +5/+10 / NEXT-DAY OPEN",
            stop_mode="atr", k_atr=1.5, tp1=0.05, tp2=0.10,
            trail=-0.025, entry="open")
run_variant("ATR k=2.0 / +5/+10 / NEXT-DAY OPEN",
            stop_mode="atr", k_atr=2.0, tp1=0.05, tp2=0.10,
            trail=-0.025, entry="open")

# More aggressive — let winners run further
run_variant("ATR k=2.0 / +7/+15 / close",
            stop_mode="atr", k_atr=2.0, tp1=0.07, tp2=0.15, trail=-0.03)
run_variant("ATR k=2.5 / +5/+10 / close",
            stop_mode="atr", k_atr=2.5, tp1=0.05, tp2=0.10, trail=-0.025)
run_variant("ATR k=2.5 / +7/+15 / close",
            stop_mode="atr", k_atr=2.5, tp1=0.07, tp2=0.15, trail=-0.03)
run_variant("ATR k=2.0 / +10/+20 / close",
            stop_mode="atr", k_atr=2.0, tp1=0.10, tp2=0.20, trail=-0.04)
