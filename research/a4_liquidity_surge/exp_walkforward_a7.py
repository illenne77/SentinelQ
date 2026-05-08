"""A4+A7 combined walk-forward — runs PREREG-0002 §3 cells.

Variants:
    V1: ATR k=2.5 / TP +7/+15 / trail -3%   (PREREG-0001 primary)
    V2: ATR k=2.0 / TP +10/+20 / trail -4%  (best on PREREG-0001 tests)

A7 modes:
    none   -- raw A4 baseline (no filter)
    F-skip -- drop trade if regime[entry_date] == WEAK
    F-half -- take trade at 50% size when WEAK; full size when OK

Windows: PREREG-0001 §5 (W1/W2/W3 + FULL).

Output is the headline table needed for ADR-0003 decision branches A/B/C/D.
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent.parent))

from data_loader import compute_surge_ratios
from data_loader_kis import load_universe_5y, load_daily_bars_batch_kis
from gates import apply_daily_gates, load_gates
from costs import DEFAULT
import exit_rules
from regime import load_kodex200, classify_regime

THR, H = 1.5, 5
ENV = "paper"

WINDOWS = [
    ("W1 (bear in test)", "2021-01-01", "2022-06-30", "2022-07-01", "2023-06-30"),
    ("W2 (mixed)",        "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("W3 (bull-tilted)",  "2023-01-01", "2024-12-31", "2025-01-01", "2026-05-08"),
]

VARIANTS = [
    ("V1 ATR k=2.5 / +7/+15",
     dict(stop_mode="atr", k_atr=2.5, tp1=0.07, tp2=0.15, trail=-0.03)),
    ("V2 ATR k=2.0 / +10/+20",
     dict(stop_mode="atr", k_atr=2.0, tp1=0.10, tp2=0.20, trail=-0.04)),
]

A7_MODES = ["none", "F-skip", "F-half"]


# ---------------------------------------------------------------------------
def build_triggers(bars, gates):
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


def evaluate(triggers, regime_series, a7_mode, *,
             stop_mode, k_atr=None, stop_pct=None,
             tp1=0.03, tp2=0.05, trail=-0.015):
    exit_rules.TP1_PCT = tp1
    exit_rules.TP2_PCT = tp2
    exit_rules.TRAIL_PCT = trail
    rows = []
    stops = 0
    n_filtered = 0
    n_halved = 0
    for tr in triggers:
        # regime lookup; trades whose entry date is missing in the regime
        # series (should be rare) default to OK (no filter applied).
        try:
            reg = regime_series.loc[tr["date"]]
        except KeyError:
            # use as-of: latest known regime <= entry date
            idx = regime_series.index.searchsorted(tr["date"], side="right") - 1
            reg = regime_series.iloc[idx] if idx >= 0 else "OK"
        if a7_mode == "F-skip" and reg == "WEAK":
            n_filtered += 1
            continue
        size_mult = 1.0
        if a7_mode == "F-half" and reg == "WEAK":
            size_mult = 0.5
            n_halved += 1
        entry_px = tr["entry_close"]
        if stop_mode == "fixed":
            stop_px = entry_px * (1 + stop_pct)
        else:
            stop_px = entry_px - k_atr * tr["atr14"]
        res = exit_rules.simulate_exit(entry_px, tr["future"], horizon=H, stop_px=stop_px)
        # net: cost scales with size; size scales return linearly
        gross_ret = res.realized_return
        net_full = DEFAULT.net_return(gross_ret)
        net_sized = net_full * size_mult
        rows.append((tr["date"], gross_ret * size_mult, net_sized))
        if res.exit_reason == "stop":
            stops += 1
    if not rows:
        return {"n": 0, "gross": 0.0, "net": 0.0, "hit": 0.0,
                "stopout": 0.0, "max_dd": 0.0,
                "n_filtered": n_filtered, "n_halved": n_halved}
    df = pd.DataFrame(rows, columns=["date", "gross", "net"]).sort_values("date")
    return {
        "n": len(rows),
        "gross": float(df["gross"].mean()),
        "net": float(df["net"].mean()),
        "hit": float((df["net"] > 0).mean()),
        "stopout": stops / len(rows),
        "max_dd": _max_drawdown_fixed_sized(df),
        "n_filtered": n_filtered,
        "n_halved": n_halved,
    }


def _max_drawdown_fixed_sized(df):
    if df.empty:
        return 0.0
    cum = df["net"].cumsum()
    peak = cum.cummax()
    dd_raw = cum - peak
    n = len(df)
    return float(dd_raw.min() / n)


def fmt(r):
    flag_m = "M" if r["net"] >= 0.012 else "."
    flag_h = "H" if r["hit"] >= 0.58 else "."
    flag_d = "D" if r["max_dd"] >= -0.015 else "."
    extra = ""
    if r.get("n_filtered", 0):
        extra = f" filt={r['n_filtered']}"
    elif r.get("n_halved", 0):
        extra = f" half={r['n_halved']}"
    return (f"n={r['n']:>5}  net={r['net']:>+7.4f}  hit={r['hit']:>6.4f}  "
            f"stopout={r['stopout']:>6.1%}  ddPerTr={r['max_dd']:>+7.4f}  "
            f"{flag_m}{flag_h}{flag_d}{extra}")


# ---------------------------------------------------------------------------
print("[A4+A7] loading bars...")
uni = load_universe_5y()
bars = load_daily_bars_batch_kis(uni, "2020-01-01", "2026-05-08", env=ENV, verbose=False)
print(f"[A4+A7] loaded {len(bars)} tickers")

print("[A4+A7] loading KODEX200 + classifying regime...")
kdx = load_kodex200()
regime_series = classify_regime(kdx)
weak_pct = (regime_series == "WEAK").mean()
print(f"[A4+A7] regime: {(regime_series=='WEAK').sum()} WEAK days ({weak_pct:.1%})")

gates = load_gates()
print("[A4+A7] building triggers...")
all_triggers = build_triggers(bars, gates)
print(f"[A4+A7] total triggers = {len(all_triggers)}")


def slice_(triggers, s_iso, e_iso):
    s, e = pd.Timestamp(s_iso), pd.Timestamp(e_iso)
    return [t for t in triggers if s <= t["date"] <= e]


# ---------------------------------------------------------------------------
all_results = {}

for label, tr_s, tr_e, te_s, te_e in WINDOWS:
    print()
    print("=" * 110)
    print(f"  {label}    TEST: {te_s} .. {te_e}")
    print("=" * 110)
    test = slice_(all_triggers, te_s, te_e)
    print(f"  test triggers: {len(test)}")
    test_results = {}
    for v_label, kw in VARIANTS:
        for a7 in A7_MODES:
            r = evaluate(test, regime_series, a7, **kw)
            key = f"{v_label} | A7={a7}"
            test_results[key] = r
            print(f"  {key:<45}  {fmt(r)}")
    all_results[label] = test_results


# Full period
print()
print("=" * 110)
print("  FULL 2021-01-01 .. 2026-05-08")
print("=" * 110)
full = slice_(all_triggers, "2021-01-01", "2026-05-08")
print(f"  triggers: {len(full)}")
full_results = {}
for v_label, kw in VARIANTS:
    for a7 in A7_MODES:
        r = evaluate(full, regime_series, a7, **kw)
        key = f"{v_label} | A7={a7}"
        full_results[key] = r
        print(f"  {key:<45}  {fmt(r)}")


# ---------------------------------------------------------------------------
# MDD-reduction summary (A7 KPI per plan §6)
# ---------------------------------------------------------------------------
print()
print("=" * 110)
print("  A7 KPI: MDD reduction vs raw A4 baseline (per plan v2.2 §6)")
print("=" * 110)
print(f"  {'window':<22} {'variant':<24} {'mode':<8} "
      f"{'mdd':>10} {'mdd_red%':>10} {'hit':>7} {'net':>9}")
print("  " + "-" * 100)


def red_pct(base, alt):
    if base == 0:
        return 0.0
    # both negative; reduction means alt closer to 0 → (base - alt) / base
    return (1.0 - alt / base) * 100.0  # positive = improvement


def emit(window_label, results):
    for v_label, _ in VARIANTS:
        base = results[f"{v_label} | A7=none"]
        for a7 in A7_MODES:
            r = results[f"{v_label} | A7={a7}"]
            if a7 == "none":
                rp = ""
            else:
                rp = f"{red_pct(base['max_dd'], r['max_dd']):>9.1f}%"
            print(f"  {window_label:<22} {v_label:<24} {a7:<8} "
                  f"{r['max_dd']:>+10.4f} {rp:>10} {r['hit']:>7.4f} {r['net']:>+9.4f}")


for label, *_ in WINDOWS:
    emit(label, all_results[label])
emit("FULL", full_results)


# ---------------------------------------------------------------------------
# Decision-branch verdict (PREREG-0002 §8)
# ---------------------------------------------------------------------------
print()
print("=" * 110)
print("  PREREG-0002 §8 DECISION TABLE")
print("=" * 110)


def graduates(r):
    return r["net"] >= 0.012 and r["hit"] >= 0.58


# Test-side aggregate: a variant graduates only if it passes on all 3 test
# windows AND demonstrates >=30% MDD reduction averaged across them.
for v_label, _ in VARIANTS:
    for a7 in ("F-skip", "F-half"):
        passes = []
        mdd_reds = []
        for label, *_ in WINDOWS:
            r = all_results[label][f"{v_label} | A7={a7}"]
            base = all_results[label][f"{v_label} | A7=none"]
            passes.append(graduates(r))
            mdd_reds.append(red_pct(base["max_dd"], r["max_dd"]))
        avg_red = sum(mdd_reds) / len(mdd_reds)
        all_pass = all(passes)
        kpi_mdd = avg_red >= 30.0
        verdict = "GRADUATES" if (all_pass and kpi_mdd) else "FAIL"
        print(f"  {v_label} + A7={a7:<7}  KPI hit/mean: {sum(passes)}/3 windows  "
              f"avg MDD reduction: {avg_red:>+6.1f}%  -->  {verdict}")
print()
print("  Branch (per PREREG-0002 §8):")
print("  - A: F-skip graduates")
print("  - B: F-half graduates but F-skip doesn't")
print("  - C: Neither graduates BUT avg MDD reduction >= 30% on at least one variant")
print("  - D: Neither graduates AND no MDD reduction --> kill stream")
