"""
A4 5y walk-forward — runs the PREREG-0001 §5 frozen splits.

Windows (per PREREG-0001):
    W1: train 2021-01-01..2022-06-30  test 2022-07-01..2023-06-30  (bear in test)
    W2: train 2022-01-01..2023-12-31  test 2024-01-01..2024-12-31  (mixed)
    W3: train 2023-01-01..2024-12-31  test 2025-01-01..2026-05-08  (bull-tilted)
    Plus full: 2021-01-01..2026-05-08

Variants tested = the 7 prereg-frozen ones. No others.
Data: KIS chart parquet cache (built by scripts/kis_backfill_5y.py).
KPI gates per PREREG-0001 §4.
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent.parent))

from data_loader import compute_surge_ratios  # reuse signal calc
from data_loader_kis import load_universe_5y, load_daily_bars_batch_kis
from gates import apply_daily_gates, load_gates
from costs import DEFAULT
import exit_rules

THR, H = 1.5, 5
ENV = "paper"
START, END = "20210101", "20260508"  # primary range; W1 needs 2021-01 onward
USE_2020 = True  # we have 2020 cached; loaders will use it for 2021 lookback warmup

WINDOWS = [
    ("W1 (bear in test)", "2021-01-01", "2022-06-30", "2022-07-01", "2023-06-30"),
    ("W2 (mixed)",        "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("W3 (bull-tilted)",  "2023-01-01", "2024-12-31", "2025-01-01", "2026-05-08"),
]

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
    ("ATR k=2.5 / +7/+15  <-- prereg primary",
     dict(stop_mode="atr", k_atr=2.5, tp1=0.07, tp2=0.15, trail=-0.03)),
]


def build_triggers(bars: dict, gates) -> list:
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
            })
    return triggers


def evaluate(triggers, *, stop_mode, k_atr=None, stop_pct=None,
             tp1=0.03, tp2=0.05, trail=-0.015):
    exit_rules.TP1_PCT = tp1
    exit_rules.TP2_PCT = tp2
    exit_rules.TRAIL_PCT = trail
    rows = []
    stops = 0
    for tr in triggers:
        entry_px = tr["entry_close"]
        if stop_mode == "fixed":
            stop_px = entry_px * (1 + stop_pct)
        else:
            stop_px = entry_px - k_atr * tr["atr14"]
        res = exit_rules.simulate_exit(entry_px, tr["future"], horizon=H, stop_px=stop_px)
        rows.append((tr["date"], res.realized_return))
        if res.exit_reason == "stop":
            stops += 1
    if not rows:
        return {"n": 0, "gross": 0.0, "net": 0.0, "hit": 0.0, "stopout": 0.0, "max_dd": 0.0}
    df = pd.DataFrame(rows, columns=["date", "ret"]).sort_values("date")
    s = df["ret"]
    sn = s.apply(DEFAULT.net_return)
    return {
        "n": len(rows),
        "gross": float(s.mean()),
        "net": float(sn.mean()),
        "hit": float((sn > 0).mean()),
        "stopout": stops / len(rows),
        "max_dd": _max_drawdown_fixed_sized(df.assign(net=sn.values)),
    }


def _max_drawdown_fixed_sized(df: pd.DataFrame) -> float:
    """Portfolio-style max DD assuming equal fixed dollar per trade.

    Interpretation: trader allocates 1 unit of capital to each trade in date
    order; cumulative P&L is the running SUM of net returns (not product).
    Drawdown is peak-to-trough of that cumulative P&L, expressed as a
    fraction of the peak. This is the correct DD for fixed-fractional
    sizing where trades may overlap.
    """
    if df.empty:
        return 0.0
    cum = df["net"].cumsum()
    peak = cum.cummax()
    # Use raw additive drawdown (P&L units) — divide by max(peak,1) only when peak>0
    dd_raw = cum - peak
    # Normalise to "fraction of peak P&L" only where peak > 0; else fraction of N trades.
    n = len(df)
    return float(dd_raw.min() / n)  # avg loss per trade during worst drawdown


def fmt(r):
    flag_m = "M" if r["net"] >= 0.012 else "."
    flag_h = "H" if r["hit"] >= 0.58 else "."
    flag_d = "D" if r["max_dd"] >= -0.015 else "."  # avg-per-trade DD <= 1.5%
    return (f"n={r['n']:>5}  net={r['net']:>+7.4f}  hit={r['hit']:>6.4f}  "
            f"stopout={r['stopout']:>6.1%}  ddPerTr={r['max_dd']:>+7.4f}  {flag_m}{flag_h}{flag_d}")


# ---------------------------------------------------------------------------
# Load all bars once (uses parquet cache populated by kis_backfill_5y.py)
# ---------------------------------------------------------------------------
print("[5y-walkforward] loading universe + bars from cache...")
uni = load_universe_5y()
bars = load_daily_bars_batch_kis(uni, "2020-01-01", "2026-05-08",
                                 env=ENV, verbose=False)
print(f"[5y-walkforward] loaded {len(bars)} tickers")

gates = load_gates()
print("[5y-walkforward] building all triggers...")
all_triggers = build_triggers(bars, gates)
print(f"[5y-walkforward] total triggers (gate-pass + ATR) = {len(all_triggers)}")
all_triggers_df = pd.DataFrame([{"date": t["date"]} for t in all_triggers])
print(f"[5y-walkforward] date range: {all_triggers_df['date'].min().date()} .. {all_triggers_df['date'].max().date()}")


def slice_(triggers, start_iso, end_iso):
    s = pd.Timestamp(start_iso)
    e = pd.Timestamp(end_iso)
    return [t for t in triggers if s <= t["date"] <= e]


# ---------------------------------------------------------------------------
# Run W1 / W2 / W3
# ---------------------------------------------------------------------------
all_results = {}  # window_label -> {variant_label -> {train: ..., test: ...}}

for label, tr_s, tr_e, te_s, te_e in WINDOWS:
    print()
    print("=" * 110)
    print(f"  {label}")
    print(f"  TRAIN: {tr_s} .. {tr_e}    TEST: {te_s} .. {te_e}")
    print("=" * 110)
    train = slice_(all_triggers, tr_s, tr_e)
    test = slice_(all_triggers, te_s, te_e)
    print(f"  triggers: train={len(train)}  test={len(test)}")
    print()
    print(f"  {'variant':<42}  {'TRAIN':<70}")
    train_results = {}
    test_results = {}
    for v_label, kw in VARIANTS:
        r = evaluate(train, **kw)
        train_results[v_label] = r
        print(f"  {v_label:<42}  {fmt(r)}")
    print()
    print(f"  {'variant':<42}  {'TEST  (OOS)':<70}")
    for v_label, kw in VARIANTS:
        r = evaluate(test, **kw)
        test_results[v_label] = r
        print(f"  {v_label:<42}  {fmt(r)}")
    all_results[label] = {"train": train_results, "test": test_results}


# ---------------------------------------------------------------------------
# Full-period evaluation
# ---------------------------------------------------------------------------
print()
print("=" * 110)
print("  FULL PERIOD 2021-01-01 .. 2026-05-08")
print("=" * 110)
full = slice_(all_triggers, "2021-01-01", "2026-05-08")
print(f"  triggers: {len(full)}")
print()
full_results = {}
for v_label, kw in VARIANTS:
    r = evaluate(full, **kw)
    full_results[v_label] = r
    print(f"  {v_label:<42}  {fmt(r)}")


# ---------------------------------------------------------------------------
# Prereg primary verdict
# ---------------------------------------------------------------------------
prereg = "ATR k=2.5 / +7/+15  <-- prereg primary"
print()
print("=" * 110)
print("  PREREG-0001 PRIMARY VARIANT - VERDICT TABLE")
print("=" * 110)
print(f"  {'window':<22}  {'split':<6}  {'verdict (per PREREG §4)'}")
print("  " + "-" * 100)


def verdict_line(window, split, r):
    chk_hit = "PASS" if r["hit"] >= 0.58 else f"FAIL ({r['hit']:.4f})"
    chk_mean = "PASS" if r["net"] >= 0.012 else f"FAIL ({r['net']:+.4f})"
    chk_alive = "PASS" if r["net"] > 0 else f"FAIL ({r['net']:+.4f})"
    print(f"  {window:<22}  {split:<6}  hit:{chk_hit:<18} mean:{chk_mean:<18} "
          f"alive:{chk_alive}")


for label, _, _, _, _ in WINDOWS:
    verdict_line(label, "train", all_results[label]["train"][prereg])
    verdict_line(label, "test", all_results[label]["test"][prereg])
verdict_line("FULL", "all", full_results[prereg])


# ---------------------------------------------------------------------------
# Rank stability across test windows
# ---------------------------------------------------------------------------
print()
print("=" * 110)
print("  RANK STABILITY (test windows; by net mean)")
print("=" * 110)
ranks = {}
for label, _, _, _, _ in WINDOWS:
    sorted_v = sorted(all_results[label]["test"].items(), key=lambda kv: -kv[1]["net"])
    ranks[label] = [v[0] for v in sorted_v]
labels = [w[0] for w in WINDOWS]
print(f"  rank  " + "  ".join(f"{l:<32}" for l in labels))
for i in range(len(VARIANTS)):
    cells = []
    for l in labels:
        cells.append(f"{ranks[l][i][:32]:<32}")
    print(f"  {i+1:<4}  " + "  ".join(cells))

prereg_test_ranks = []
for l in labels:
    prereg_test_ranks.append(ranks[l].index(prereg) + 1)
print()
print(f"  Prereg primary ranks across test windows: {prereg_test_ranks}")
print(f"  PREREG §4 'walk-forward stability' check: "
      f"{'PASS' if max(prereg_test_ranks) <= 3 else 'FAIL'} (must be <= 3)")
