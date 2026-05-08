"""A3 Volatility Compression Breakout walk-forward — PREREG-0003.

Variants frozen in PREREG-0003 §5:
    V1: plan literal (atr_pct<=0.20, box=20d, vol>=1.5x)
    V2: tighter compression (atr_pct<=0.10)
    V3: tighter volume (vol>=2.0x)
    V4: longer base (box=40d)
    V5: no SMA20 trend-break exit (let TP/stop run)

Reuses 5y KIS OHLCV cache (no new data).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent.parent))
sys.path.insert(0, str(ROOT.parent / "a4_liquidity_surge"))

from data_loader_kis import load_universe_5y, load_daily_bars_batch_kis
from costs import DEFAULT
import exit_rules

H = 15  # plan: hold <= 15 trading days
ENV = "paper"

WINDOWS = [
    ("W1 (bear in test)", "2021-01-01", "2022-06-30", "2022-07-01", "2023-06-30"),
    ("W2 (mixed)",        "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("W3 (bull-tilted)",  "2023-01-01", "2024-12-31", "2025-01-01", "2026-05-08"),
]

# (label, atr_pct_max, vol_ratio_min, box_len, use_sma20_exit)
VARIANTS = [
    ("V1 plan literal",         dict(atr_pct=0.20, vol_ratio=1.5, box_len=20, sma20_exit=True)),
    ("V2 tight comp atr<=0.10", dict(atr_pct=0.10, vol_ratio=1.5, box_len=20, sma20_exit=True)),
    ("V3 tight vol >=2.0x",     dict(atr_pct=0.20, vol_ratio=2.0, box_len=20, sma20_exit=True)),
    ("V4 longer base 40d",      dict(atr_pct=0.20, vol_ratio=1.5, box_len=40, sma20_exit=True)),
    ("V5 no SMA20 exit",        dict(atr_pct=0.20, vol_ratio=1.5, box_len=20, sma20_exit=False)),
]


def compute_a3_signals(daily: pd.DataFrame, atr_pct: float, vol_ratio: float,
                       box_len: int) -> pd.DataFrame:
    """Return DataFrame indexed by date with columns: triggered, atr14."""
    if len(daily) < max(80, box_len + 5):
        return pd.DataFrame()
    atr20 = exit_rules.compute_atr(daily, lookback=20)
    atr14 = exit_rules.compute_atr(daily, lookback=14)
    # ATR percentile rank within trailing 60d (atr20 of the *prior* close)
    atr20_prev = atr20.shift(1)
    pct_60 = atr20_prev.rolling(60, min_periods=60).rank(pct=True)
    box_high = daily["high"].rolling(box_len, min_periods=box_len).max().shift(1)
    vol_mean = daily["volume"].rolling(20, min_periods=20).mean().shift(1)
    vol_r = daily["volume"] / vol_mean

    cond = (
        (pct_60 <= atr_pct)
        & (daily["close"] > box_high)
        & (vol_r >= vol_ratio)
        & (daily["close"] > daily["open"])
    )
    return pd.DataFrame({
        "triggered": cond.fillna(False),
        "atr14": atr14,
        "close": daily["close"],
    })


def build_triggers_a3(bars: dict, **params) -> list:
    sma20_exit = params.pop("sma20_exit")
    triggers = []
    for t, daily in bars.items():
        feats = compute_a3_signals(daily, **params)
        if feats.empty:
            continue
        sma20 = daily["close"].rolling(20, min_periods=20).mean()
        for date, row in feats[feats["triggered"]].iterrows():
            try:
                i = daily.index.get_loc(date)
            except KeyError:
                continue
            future = daily.iloc[i + 1: i + 1 + H]
            if len(future) < H:
                continue
            atr_val = float(row["atr14"])
            if pd.isna(atr_val):
                continue
            triggers.append({
                "ticker": t,
                "date": pd.Timestamp(date),
                "entry_close": float(row["close"]),
                "atr14": atr_val,
                "future": future,
                "sma20_future": sma20.iloc[i + 1: i + 1 + H] if sma20_exit else None,
            })
    return triggers


def simulate_a3_exit(tr):
    """A3 exit: hard stop -2.5%, ATR*2 trailing stop, TP1 +5%/50%, TP2 +12%/rest,
    optional SMA20 trend-break exit."""
    entry = tr["entry_close"]
    atr14 = tr["atr14"]
    future = tr["future"]
    sma20_fut = tr["sma20_future"]

    hard_stop_px = entry * (1 - 0.025)
    tp1_px = entry * 1.05
    tp2_px = entry * 1.12

    pos_tp1 = 0.50
    pos_tp2 = 0.30
    pos_trail = 0.20

    leg_state = {"tp1": "open", "tp2": "open", "trail": "open"}
    leg_ret = {"tp1": 0.0, "tp2": 0.0, "trail": 0.0}

    peak_high = entry
    last_close = entry
    exit_day = len(future) - 1

    for i in range(len(future)):
        row = future.iloc[i]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        last_close = close

        # ATR trailing stop level (worst-case: applied if peak set previously)
        peak_high = max(peak_high, high)
        atr_trail_px = peak_high - 2.0 * atr14
        # effective stop = max of hard_stop and atr_trail (both lift only after price moved up)
        eff_stop_px = max(hard_stop_px, atr_trail_px) if peak_high > entry else hard_stop_px

        # Stop check (worst-case ordering: stop fires before TPs intra-day)
        if low <= eff_stop_px:
            stop_ret = (eff_stop_px / entry) - 1.0
            for leg in leg_state:
                if leg_state[leg] == "open":
                    leg_state[leg] = "stopped"
                    leg_ret[leg] = stop_ret
            exit_day = i
            break

        # TP1
        if leg_state["tp1"] == "open" and high >= tp1_px:
            leg_state["tp1"] = "tp1"
            leg_ret["tp1"] = 0.05
        # TP2
        if leg_state["tp2"] == "open" and high >= tp2_px:
            leg_state["tp2"] = "tp2"
            leg_ret["tp2"] = 0.12

        # SMA20 trend-break exit (any open leg → close at today's close)
        if sma20_fut is not None:
            sma_val = sma20_fut.iloc[i]
            if not pd.isna(sma_val) and close < sma_val:
                tb_ret = (close / entry) - 1.0
                for leg in leg_state:
                    if leg_state[leg] == "open":
                        leg_state[leg] = "trend_break"
                        leg_ret[leg] = tb_ret
                exit_day = i
                break

        if all(s != "open" for s in leg_state.values()):
            exit_day = i
            break

    # Time exit for any still-open leg
    if any(s == "open" for s in leg_state.values()):
        time_ret = (last_close / entry) - 1.0
        for leg in leg_state:
            if leg_state[leg] == "open":
                leg_state[leg] = "time"
                leg_ret[leg] = time_ret

    realized = (leg_ret["tp1"] * pos_tp1
                + leg_ret["tp2"] * pos_tp2
                + leg_ret["trail"] * pos_trail)
    states = set(leg_state.values())
    if states == {"stopped"}:
        reason = "stop"
    elif "stopped" in states:
        reason = "mixed_stop"
    elif "trend_break" in states:
        reason = "trend_break"
    elif states <= {"tp1", "tp2", "time"}:
        reason = "tp_or_time"
    else:
        reason = "mixed"
    return realized, reason, exit_day


def evaluate_a3(triggers: list) -> dict:
    if not triggers:
        return {"n": 0}
    rows = []
    stops = 0
    holds = []
    for tr in triggers:
        gross, reason, ed = simulate_a3_exit(tr)
        net = DEFAULT.net_return(gross)
        rows.append((tr["date"], gross, net))
        holds.append(ed + 1)
        if reason in ("stop", "mixed_stop"):
            stops += 1
    df = pd.DataFrame(rows, columns=["date", "gross", "net"]).sort_values("date")
    nets = df["net"]
    wins = nets[nets > 0].sum()
    losses = -nets[nets <= 0].sum()
    pf = float(wins / losses) if losses > 1e-12 else float("inf") if wins > 0 else 0.0
    return {
        "n": len(rows),
        "gross": float(df["gross"].mean()),
        "net": float(nets.mean()),
        "hit": float((nets > 0).mean()),
        "pf": pf,
        "avg_hold": float(np.mean(holds)) if holds else 0.0,
        "stopout": stops / len(rows),
        "max_dd": _mdd(df),
    }


def _mdd(df):
    if df.empty:
        return 0.0
    cum = df["net"].cumsum()
    peak = cum.cummax()
    return float((cum - peak).min() / len(df))


def fmt(r):
    if r["n"] == 0:
        return "n=0"
    pf = r["pf"]
    pf_s = f"{pf:>5.2f}" if pf != float("inf") else "  inf"
    flag_pf = "P" if pf >= 1.6 else "."
    flag_h = "H" if r["hit"] >= 0.50 else "."
    flag_m = "M" if r["net"] >= 0.012 else "."
    flag_t = "T" if r["avg_hold"] <= 15 else "."
    return (f"n={r['n']:>4}  net={r['net']:>+7.4f}  hit={r['hit']:>5.3f}  "
            f"PF={pf_s}  hold={r['avg_hold']:>4.1f}d  ddPerTr={r['max_dd']:>+7.4f}  "
            f"{flag_pf}{flag_h}{flag_m}{flag_t}")


# ---------------------------------------------------------------------------
print("[A3] loading bars...")
uni = load_universe_5y()
bars = load_daily_bars_batch_kis(uni, "2020-01-01", "2026-05-08", env=ENV, verbose=False)
print(f"[A3] loaded {len(bars)} tickers")


def slice_(triggers, s_iso, e_iso):
    s, e = pd.Timestamp(s_iso), pd.Timestamp(e_iso)
    return [t for t in triggers if s <= t["date"] <= e]


# Build triggers PER VARIANT (signal params differ)
print("[A3] building triggers per variant...")
variant_triggers = {}
for v_label, params in VARIANTS:
    trigs = build_triggers_a3(bars, **dict(params))  # copy
    variant_triggers[v_label] = trigs
    print(f"  {v_label:<32} -> {len(trigs)} triggers")

all_results = {}
for label, _, _, te_s, te_e in WINDOWS:
    print()
    print("=" * 110)
    print(f"  {label}    TEST: {te_s} .. {te_e}")
    print("=" * 110)
    test_results = {}
    for v_label, _ in VARIANTS:
        test = slice_(variant_triggers[v_label], te_s, te_e)
        r = evaluate_a3(test)
        test_results[v_label] = r
        print(f"  {v_label:<32}  {fmt(r) if r.get('n') else 'n=0'}")
    all_results[label] = test_results

# Full
print()
print("=" * 110)
print("  FULL 2021-01-01 .. 2026-05-08")
print("=" * 110)
full_results = {}
for v_label, _ in VARIANTS:
    full = slice_(variant_triggers[v_label], "2021-01-01", "2026-05-08")
    r = evaluate_a3(full)
    full_results[v_label] = r
    print(f"  {v_label:<32}  {fmt(r) if r.get('n') else 'n=0'}")


# ---------------------------------------------------------------------------
# Decision-branch verdict (PREREG-0003 §10)
# ---------------------------------------------------------------------------
print()
print("=" * 110)
print("  PREREG-0003 §10 DECISION TABLE")
print("=" * 110)


def graduates(r):
    if r.get("n", 0) == 0:
        return False
    return (r["pf"] >= 1.6 and r["avg_hold"] <= 15
            and r["net"] >= 0.012 and r["hit"] >= 0.50)


# rank stability (by PF on test sides)
ranks = {}
for label, _, _, _, _ in WINDOWS:
    sorted_v = sorted(all_results[label].items(),
                      key=lambda kv: -(kv[1].get("pf") or 0))
    ranks[label] = [v[0] for v in sorted_v]

print(f"  {'variant':<32}  {'W1 grad':<8} {'W2 grad':<8} {'W3 grad':<8} "
      f"{'FULL grad':<10} {'rank stable':<12}")
print("  " + "-" * 100)
graduating = []
for v_label, _ in VARIANTS:
    grads = []
    for label, *_ in WINDOWS:
        grads.append(graduates(all_results[label][v_label]))
    full_g = graduates(full_results[v_label])
    test_ranks = [ranks[l].index(v_label) + 1 for l, *_ in WINDOWS]
    stable = max(test_ranks) <= 3
    print(f"  {v_label:<32}  {str(grads[0]):<8} {str(grads[1]):<8} "
          f"{str(grads[2]):<8} {str(full_g):<10} "
          f"ranks={test_ranks} {'YES' if stable else 'NO':<4}")
    if all(grads) and stable:
        graduating.append(v_label)

print()
v1 = "V1 plan literal"
v1_pf_test = [all_results[l][v1].get("pf", 0) for l, *_ in WINDOWS]
print(f"  V1 PF on test windows: {[f'{x:.2f}' for x in v1_pf_test]}")
print()
print("  Branch outcome:")
if graduates(all_results[WINDOWS[0][0]][v1]) and all(graduates(all_results[l][v1]) for l, *_ in WINDOWS):
    print("  --> A: V1 graduates")
elif graduating:
    print(f"  --> B: V1 fails but {graduating} graduate")
else:
    pf_max = max(v1_pf_test) if v1_pf_test else 0
    pf_v1_v2 = max(
        max([all_results[l][v].get("pf", 0) for l, *_ in WINDOWS])
        for v in ("V1 plan literal", "V2 tight comp atr<=0.10")
    )
    if pf_v1_v2 < 1.3:
        print("  --> D: kill A3 (PF below 1.3 across V1/V2)")
    else:
        print("  --> E: A3 marginal (PF in [1.3, 1.6) on V1 or V2)")
