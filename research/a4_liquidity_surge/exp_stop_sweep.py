"""Stop-level sensitivity: how does relaxing the stop change KPI?"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from data_loader import compute_surge_ratios, get_kospi200, load_daily_bars_batch  # noqa
from gates import apply_daily_gates, load_gates  # noqa
from costs import DEFAULT  # noqa
import exit_rules  # noqa

START, END, THR, H = "20250101", "20260508", 1.5, 5
tickers = get_kospi200(END)
bars = load_daily_bars_batch(tickers, START, END, verbose=False)
gates = load_gates()

trigs = []
for t, daily in bars.items():
    feats = compute_surge_ratios(daily, lookback=20, threshold=THR)
    if feats.empty:
        continue
    gp = apply_daily_gates(daily, gates, lookback=20).rename("gate_pass")
    feats = feats.join(gp)
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
        trigs.append((float(row["close"]), future))

print(f"[sweep] {len(trigs)} triggers (gate-pass)")

variants = [
    ("default     -2%/+3%/+5%/-1.5%", -0.02, 0.03, 0.05, -0.015),
    ("loose stop  -3%/+3%/+5%/-1.5%", -0.03, 0.03, 0.05, -0.015),
    ("loose stop  -5%/+3%/+5%/-1.5%", -0.05, 0.03, 0.05, -0.015),
    ("wider TP    -3%/+5%/+8%/-2.0%", -0.03, 0.05, 0.08, -0.02),
    ("no stop     none/+3%/+5%/none", -0.99, 0.03, 0.05, -0.99),
]

hdr = f"{'variant':<35} {'gross':>8} {'net':>8} {'hit':>7} {'KPI':>4}"
print(hdr)
print("-" * len(hdr))
for label, sp, tp1, tp2, tr in variants:
    exit_rules.STOP_PCT = sp
    exit_rules.TP1_PCT = tp1
    exit_rules.TP2_PCT = tp2
    exit_rules.TRAIL_PCT = tr
    rets = []
    for entry, future in trigs:
        r = exit_rules.simulate_exit(entry, future, horizon=H).realized_return
        rets.append(r)
    s = pd.Series(rets)
    sn = s.apply(DEFAULT.net_return)
    hit = (sn > 0).mean()
    mean = sn.mean()
    flag = ("M" if mean >= 0.012 else ".") + ("H" if hit >= 0.58 else ".")
    print(f"{label:<35} {s.mean():>+8.4f} {mean:>+8.4f} {hit:>7.4f} {flag:>4}")
