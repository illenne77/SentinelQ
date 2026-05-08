"""
A4 walk-forward OOS validation — does the ATR k=2.5 / +7/+15 winner survive?

Plan v2.2 §6 adoption gate requires walk-forward OOS pass. The exp_atr_sweep.py
result tested 13 variants on a single 2025-01..2026-05 window — high overfit
risk after multiple testing.

Setup
-----
  Train  : 2025-01-01 .. 2025-12-31  (12 months)
  Test   : 2026-01-01 .. 2026-05-08  ( ~4.3 months)

For each candidate variant we report (gross, net, hit, stop-out, KPI flags)
on TRAIN and TEST separately. Decision rules:

  PASS (variant viable for Phase 0 entry):
    - Test hit  >= 56%   (1pp tolerance vs 58% KPI given small-N test split)
    - Test net  >= +0.5% (mean degradation tolerated, but must stay positive)
    - Train rank == Test rank for top variant (no flip)

  FAIL conditions:
    - Top train variant ranks below median on test  → overfit
    - Test net  <= 0                                → strategy dies OOS
    - Test hit  <  50%                              → no edge

Output is a side-by-side table; downstream this informs ADR-0001 update.
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from data_loader import compute_surge_ratios, get_kospi200, load_daily_bars_batch  # noqa
from gates import apply_daily_gates, load_gates  # noqa
from costs import DEFAULT  # noqa
import exit_rules  # noqa: E402

START, END = "20250101", "20260508"
SPLIT = pd.Timestamp("2026-01-01")  # train: < SPLIT, test: >= SPLIT
THR, H = 1.5, 5

# 1. Build trigger set once (covers both train + test windows).
tickers = get_kospi200(END)
bars = load_daily_bars_batch(tickers, START, END, verbose=False)
gates = load_gates()

triggers = []
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
        future = daily.iloc[i + 1: i + 1 + H]
        if len(future) < H:
            continue
        atr_val = atr.iloc[i]
        if pd.isna(atr_val):
            continue
        triggers.append({
            "ticker": t,
            "date": pd.Timestamp(date),
            "entry_close": float(row["close"]),
            "atr14": float(atr_val),
            "future": future,
            "surge_ratio": float(row["surge_ratio"]),
        })

train = [tr for tr in triggers if tr["date"] < SPLIT]
test = [tr for tr in triggers if tr["date"] >= SPLIT]
print(f"[walk-forward] total={len(triggers)}  train={len(train)}  test={len(test)}")
if not test:
    sys.exit("[walk-forward] empty test split — aborting")


def evaluate(set_, *, stop_mode, k_atr=None, stop_pct=None,
             tp1=0.03, tp2=0.05, trail=-0.015):
    exit_rules.TP1_PCT = tp1
    exit_rules.TP2_PCT = tp2
    exit_rules.TRAIL_PCT = trail
    rets, stops = [], 0
    for tr in set_:
        entry_px = tr["entry_close"]
        if stop_mode == "fixed":
            stop_px = entry_px * (1 + stop_pct)
        else:
            stop_px = entry_px - k_atr * tr["atr14"]
        res = exit_rules.simulate_exit(entry_px, tr["future"], horizon=H, stop_px=stop_px)
        rets.append(res.realized_return)
        if res.exit_reason == "stop":
            stops += 1
    s = pd.Series(rets)
    sn = s.apply(DEFAULT.net_return)
    return {
        "n": len(rets),
        "gross": s.mean(),
        "net": sn.mean(),
        "hit": (sn > 0).mean(),
        "stopout": stops / max(len(rets), 1),
    }


def fmt(r):
    flag_m = "M" if r["net"] >= 0.012 else "."
    flag_h = "H" if r["hit"] >= 0.58 else "."
    return (f"n={r['n']:>4}  gross={r['gross']:>+7.4f}  net={r['net']:>+7.4f}  "
            f"hit={r['hit']:>6.4f}  stopout={r['stopout']:>6.1%}  {flag_m}{flag_h}")


VARIANTS = [
    ("baseline fixed -2% / +3/+5",
     dict(stop_mode="fixed", stop_pct=-0.02)),
    ("ATR k=1.5 / +3/+5",
     dict(stop_mode="atr", k_atr=1.5)),
    ("ATR k=2.0 / +5/+10",
     dict(stop_mode="atr", k_atr=2.0, tp1=0.05, tp2=0.10, trail=-0.025)),
    ("ATR k=2.0 / +7/+15",
     dict(stop_mode="atr", k_atr=2.0, tp1=0.07, tp2=0.15, trail=-0.03)),
    ("ATR k=2.0 / +10/+20",
     dict(stop_mode="atr", k_atr=2.0, tp1=0.10, tp2=0.20, trail=-0.04)),
    ("ATR k=2.5 / +5/+10",
     dict(stop_mode="atr", k_atr=2.5, tp1=0.05, tp2=0.10, trail=-0.025)),
    ("ATR k=2.5 / +7/+15  <-- prior winner",
     dict(stop_mode="atr", k_atr=2.5, tp1=0.07, tp2=0.15, trail=-0.03)),
]

print()
print("TRAIN (2025-01-01..2025-12-31)")
print("-" * 100)
train_results = {}
for label, kw in VARIANTS:
    r = evaluate(train, **kw)
    train_results[label] = r
    print(f"  {label:<42} {fmt(r)}")

print()
print("TEST  (2026-01-01..2026-05-08)  [OOS]")
print("-" * 100)
test_results = {}
for label, kw in VARIANTS:
    r = evaluate(test, **kw)
    test_results[label] = r
    print(f"  {label:<42} {fmt(r)}")

# Rank correlation: are best train variants also best on test?
print()
print("RANK COMPARISON (by net mean, descending)")
print("-" * 100)
train_rank = sorted(train_results.items(), key=lambda kv: -kv[1]["net"])
test_rank = sorted(test_results.items(), key=lambda kv: -kv[1]["net"])
print(f"  {'#':>3}  {'TRAIN winner':<42}  {'TEST winner':<42}")
for i, ((tl, _), (el, _)) in enumerate(zip(train_rank, test_rank), 1):
    flag = "  same" if tl == el else "  FLIP"
    print(f"  {i:>3}  {tl:<42}  {el:<42}{flag}")

# Specific verdict on prior winner
prior = "ATR k=2.5 / +7/+15  <-- prior winner"
tr_r, te_r = train_results[prior], test_results[prior]
print()
print("PRIOR WINNER VERDICT")
print("-" * 100)
print(f"  Train: {fmt(tr_r)}")
print(f"  Test : {fmt(te_r)}")
verdict_hit = "PASS" if te_r["hit"] >= 0.56 else "FAIL"
verdict_net = "PASS" if te_r["net"] >= 0.005 else "FAIL"
verdict_alive = "PASS" if te_r["net"] > 0 else "FAIL"
print(f"  Test hit >= 56%   : {verdict_hit}  ({te_r['hit']:.4f})")
print(f"  Test net >= +0.5% : {verdict_net}  ({te_r['net']:+.4f})")
print(f"  Test net > 0      : {verdict_alive}  (alive OOS)")
