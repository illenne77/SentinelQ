"""A-F03 Gross Profitability / Assets walk-forward backtest.

PREREG-0006. Long-only top-quintile GP/A, monthly rebalance,
EW basket vs equal-weight universe benchmark.

Reuses backtest engine pattern from research/a_f01_value/exp_walkforward_f01.py
with the signal swapped: GPA = gross_profit_krw / assets_krw,
forward-filled from latest available_from annual report.

V1 PRIMARY: top quintile, monthly, no screen
V2: top decile, monthly
V3: top quintile, quarterly
V4: top quintile, monthly, with B/M ≥ universe median (value+quality hybrid)
V5: top quintile, monthly, with positive ΔGP/A YoY

Output: research/a_f03_quality/walkforward_f03_results.txt
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent

EQUITY_PQ = ROOT / "data" / "cache" / "dart" / "equity_quarterly.parquet"
INCOME_PQ = ROOT / "data" / "cache" / "dart" / "income_assets_annual.parquet"
SHARES_CSV = ROOT / "data" / "cache" / "dart" / "shares_snapshot.csv"
DAILY_DIR = ROOT / "data" / "cache" / "kis_daily"
OUT_PATH = ROOT / "research" / "a_f03_quality" / "walkforward_f03_results.txt"

ROUND_TRIP_COST = 0.0030
ANNUAL_FACTOR = 252

WINDOWS = [
    ("W1", "2023-01-01", "2023-12-31"),
    ("W2", "2024-01-01", "2024-12-31"),
    ("W3", "2025-01-01", "2026-05-08"),
    ("FULL", "2023-01-01", "2026-05-08"),
]


def load_close_panel() -> pd.DataFrame:
    series = {}
    for f in sorted(DAILY_DIR.glob("*.parquet")):
        df = pd.read_parquet(f)[["close"]].copy()
        df.index = pd.to_datetime(df.index)
        series[f.stem] = df["close"].astype(float)
    return pd.DataFrame(series).sort_index()


def build_gpa_panel(close: pd.DataFrame, income: pd.DataFrame) -> pd.DataFrame:
    """GPA[date, ticker] = gross_profit / assets, ffill from last available_from."""
    inc = income.copy()
    inc["ticker"] = inc["ticker"].astype(str).str.zfill(6)
    inc = inc.dropna(subset=["gross_profit_krw", "assets_krw"])
    inc = inc[inc["assets_krw"] > 0]
    inc["gpa"] = inc["gross_profit_krw"] / inc["assets_krw"]
    inc = inc.sort_values(["ticker", "available_from"])

    out = pd.DataFrame(index=close.index, columns=close.columns, dtype=float)
    for tk, sub in inc.groupby("ticker"):
        if tk not in close.columns:
            continue
        s = sub.set_index("available_from")["gpa"].sort_index()
        out[tk] = s.reindex(close.index, method="ffill")
    return out


def build_dgpa_panel(close: pd.DataFrame, income: pd.DataFrame) -> pd.DataFrame:
    """ΔGPA YoY (current - prior year), ffill onto close grid."""
    inc = income.copy()
    inc["ticker"] = inc["ticker"].astype(str).str.zfill(6)
    inc = inc.dropna(subset=["gross_profit_krw", "assets_krw"])
    inc = inc[inc["assets_krw"] > 0]
    inc["gpa"] = inc["gross_profit_krw"] / inc["assets_krw"]
    inc = inc.sort_values(["ticker", "year"])
    inc["dgpa"] = inc.groupby("ticker")["gpa"].diff()

    out = pd.DataFrame(index=close.index, columns=close.columns, dtype=float)
    for tk, sub in inc.dropna(subset=["dgpa"]).groupby("ticker"):
        if tk not in close.columns:
            continue
        s = sub.set_index("available_from")["dgpa"].sort_index()
        out[tk] = s.reindex(close.index, method="ffill")
    return out


def build_bm_panel(close: pd.DataFrame, equity: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """Same as A-F01: B/M = controlling_equity / (close * shares_snapshot)."""
    shares_map = dict(zip(shares["ticker"].astype(str).str.zfill(6),
                          shares["shares"].astype(float)))
    eq = equity.copy()
    eq["ticker"] = eq["ticker"].astype(str).str.zfill(6)
    eq = eq.sort_values(["ticker", "available_from"])

    bm = pd.DataFrame(index=close.index, columns=close.columns, dtype=float)
    for ticker in close.columns:
        sh = shares_map.get(ticker)
        if not sh or sh <= 0:
            continue
        sub = eq[eq["ticker"] == ticker][["available_from", "equity_controlling_krw"]].dropna()
        if sub.empty:
            continue
        sub = sub.sort_values("available_from")
        eq_series = sub.set_index("available_from")["equity_controlling_krw"]
        eq_on_close = eq_series.reindex(close.index, method="ffill")
        bps = eq_on_close / sh
        bm[ticker] = bps / close[ticker]
    return bm


def first_trading_day(idx: pd.DatetimeIndex, year: int, month: int) -> Optional[pd.Timestamp]:
    days = idx[(idx.year == year) & (idx.month == month)]
    return days[0] if len(days) > 0 else None


def get_rebalance_dates(idx: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp,
                         monthly: bool) -> List[pd.Timestamp]:
    dates = []
    if monthly:
        cur = pd.Timestamp(start.year, start.month, 1)
    else:
        m = ((start.month - 1) // 3) * 3 + 3
        cur = pd.Timestamp(start.year, m, 1)
    end_marker = pd.Timestamp(end.year, end.month, 1)
    while cur <= end_marker:
        d = first_trading_day(idx, cur.year, cur.month)
        if d is not None and start <= d <= end:
            dates.append(d)
        if monthly:
            cur += pd.DateOffset(months=1)
        else:
            cur += pd.DateOffset(months=3)
    return dates


def run_variant(close: pd.DataFrame, signal: pd.DataFrame,
                bm: Optional[pd.DataFrame],
                dgpa: Optional[pd.DataFrame],
                test_start: pd.Timestamp, test_end: pd.Timestamp,
                pct: float, monthly: bool,
                hybrid_bm: bool, dgpa_pos: bool) -> Tuple[pd.Series, pd.Series, dict]:
    idx = close.index
    test_dates = idx[(idx >= test_start) & (idx <= test_end)]
    if len(test_dates) == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float), {}
    rebal_dates = get_rebalance_dates(idx, test_dates[0], test_dates[-1], monthly)
    rebal_set = set(rebal_dates)

    nav_series = pd.Series(index=test_dates, dtype=float)
    holdings: Dict[str, float] = {}
    cash = 1.0

    def mtm_of(d):
        v = 0.0
        for tk, sh in holdings.items():
            px = close.loc[d, tk] if tk in close.columns else None
            if px is None or pd.isna(px):
                continue
            v += sh * float(px)
        return v

    for d in test_dates:
        if d in rebal_set:
            for tk, sh in list(holdings.items()):
                px = close.loc[d, tk] if tk in close.columns else None
                if px is None or pd.isna(px):
                    continue
                cash += sh * float(px) * (1 - ROUND_TRIP_COST / 2)
            holdings = {}

            row_sig = signal.loc[d]
            valid = row_sig.dropna()
            valid = valid[valid.index.map(lambda tk: tk in close.columns
                                           and not pd.isna(close.loc[d, tk])
                                           and close.loc[d, tk] > 0)]
            # Hybrid B/M screen
            if hybrid_bm and bm is not None:
                bm_row = bm.loc[d].reindex(valid.index).dropna()
                if len(bm_row) >= 5:
                    bm_med = bm_row.median()
                    keep = bm_row[bm_row >= bm_med].index
                    valid = valid.loc[valid.index.intersection(keep)]
            # Positive ΔGP/A screen
            if dgpa_pos and dgpa is not None:
                dgpa_row = dgpa.loc[d].reindex(valid.index)
                keep = dgpa_row[dgpa_row > 0].index
                valid = valid.loc[valid.index.intersection(keep)]

            if len(valid) >= 5:
                n_pick = max(1, int(round(len(valid) * pct)))
                picks = valid.sort_values(ascending=False).head(n_pick).index.tolist()
                per_name = cash / len(picks)
                for tk in picks:
                    px = float(close.loc[d, tk])
                    eff_cash = per_name * (1 - ROUND_TRIP_COST / 2)
                    holdings[tk] = eff_cash / px
                    cash -= per_name

        nav_series.loc[d] = cash + mtm_of(d)

    nav_series = nav_series.ffill().fillna(1.0)

    # Benchmark: EW of universe over same dates
    universe_cols = [c for c in close.columns if c in signal.columns]
    bench_close = close[universe_cols].loc[test_dates]
    bench_ret = bench_close.pct_change().mean(axis=1).fillna(0.0)
    bench = (1 + bench_ret).cumprod()

    days = (test_dates[-1] - test_dates[0]).days
    yrs = max(days / 365.25, 1e-6)
    cagr = nav_series.iloc[-1] ** (1 / yrs) - 1
    cagr_b = bench.iloc[-1] ** (1 / yrs) - 1
    ret = nav_series.pct_change().fillna(0.0)
    sharpe = ret.mean() / (ret.std() + 1e-12) * np.sqrt(ANNUAL_FACTOR)
    dd = (nav_series / nav_series.cummax() - 1).min()
    monthly_nav = nav_series.resample("M").last()
    monthly_b = bench.resample("M").last()
    m_excess = monthly_nav.pct_change().fillna(0) - monthly_b.pct_change().fillna(0)
    hit_month = (m_excess > 0).mean() if len(m_excess) > 0 else 0.0

    return nav_series, bench, {
        "cagr": cagr, "cagr_bench": cagr_b, "alpha_ann": cagr - cagr_b,
        "sharpe": float(sharpe), "max_dd": float(dd),
        "hit_month": float(hit_month), "n_obs": int(len(test_dates)),
        "n_rebal": len(rebal_dates), "final_nav": float(nav_series.iloc[-1]),
    }


VARIANTS = [
    ("V1", 0.20, True, False, False),
    ("V2", 0.10, True, False, False),
    ("V3", 0.20, False, False, False),
    ("V4", 0.20, True, True, False),    # hybrid value+quality
    ("V5", 0.20, True, False, True),    # positive ΔGP/A
]


def main():
    print("Loading data...")
    close = load_close_panel()
    print(f"  Close panel: {close.shape}")
    income = pd.read_parquet(INCOME_PQ)
    equity = pd.read_parquet(EQUITY_PQ)
    shares = pd.read_csv(SHARES_CSV, dtype={"ticker": str})
    shares["ticker"] = shares["ticker"].str.zfill(6)
    print(f"  Income: {income.shape}; Equity: {equity.shape}")

    print("Building GP/A panel...")
    gpa = build_gpa_panel(close, income)
    print(f"  GPA non-null cells: {gpa.notna().sum().sum()}; tickers: {gpa.notna().any().sum()}")
    print("Building ΔGP/A panel...")
    dgpa = build_dgpa_panel(close, income)
    print("Building B/M panel (for V4 hybrid)...")
    bm = build_bm_panel(close, equity, shares)

    rows = []
    for win_name, ts, te in WINDOWS:
        ts_t, te_t = pd.Timestamp(ts), pd.Timestamp(te)
        for vname, pct, monthly, hybrid_bm, dgpa_pos in VARIANTS:
            print(f"  Running {win_name} / {vname} ...")
            _, _, stats = run_variant(close, gpa, bm, dgpa, ts_t, te_t,
                                       pct, monthly, hybrid_bm, dgpa_pos)
            stats["window"] = win_name
            stats["variant"] = vname
            rows.append(stats)

    df = pd.DataFrame(rows)
    cols = ["window", "variant", "cagr", "cagr_bench", "alpha_ann",
            "sharpe", "max_dd", "hit_month", "n_obs", "n_rebal", "final_nav"]
    df = df[cols]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_lines = []
    out_lines.append("PREREG-0006 A-F03 Gross Profitability / Assets walk-forward results")
    out_lines.append(f"Generated: {datetime.now().isoformat()}")
    out_lines.append(f"Universe size (close panel): {len(close.columns)}")
    out_lines.append(f"Tickers with any GP/A signal: {(gpa.notna().any()).sum()}")
    out_lines.append("")
    out_lines.append(df.to_string(index=False, float_format=lambda x: f"{x: .4f}"))
    out_lines.append("")
    out_lines.append("KPI gates (PREREG-0006 §7):")
    out_lines.append("  G1 alpha_ann ≥ +1.5% (FULL)")
    out_lines.append("  G2 hit_month ≥ 55% (FULL)")
    out_lines.append("  G3 max_dd ≥ -25% (FULL)")
    out_lines.append("  G4 alpha_ann > 0 in ALL of W1/W2/W3")
    out_lines.append("  G5 V1 rank ≤ 3 of 5 by alpha_ann in EACH of W1/W2/W3")
    out_lines.append("  G6 sharpe ≥ 0.6 (FULL)")
    out_lines.append("")
    print()
    print("\n".join(out_lines))

    full = df[df["window"] == "FULL"]
    out_lines.append("Gate evaluation:")
    for vname, _, _, _, _ in VARIANTS:
        full_v = full[full["variant"] == vname].iloc[0]
        g1 = full_v["alpha_ann"] >= 0.015
        g2 = full_v["hit_month"] >= 0.55
        g3 = full_v["max_dd"] >= -0.25
        g6 = full_v["sharpe"] >= 0.6
        per_win = df[(df["variant"] == vname) & (df["window"].isin(["W1", "W2", "W3"]))]
        g4 = (per_win["alpha_ann"] > 0).all()
        if vname == "V1":
            ranks_ok = []
            for w in ["W1", "W2", "W3"]:
                wdf = df[df["window"] == w].sort_values("alpha_ann", ascending=False).reset_index(drop=True)
                rank = wdf[wdf["variant"] == "V1"].index[0] + 1
                ranks_ok.append(rank <= 3)
            g5 = all(ranks_ok)
            verdict = all([g1, g2, g3, g4, g5, g6])
            out_lines.append(f"  {vname}: G1={g1} G2={g2} G3={g3} G4={g4} G5={g5} G6={g6} -> {'PASS' if verdict else 'FAIL'}")
        else:
            verdict = all([g1, g2, g3, g4, g6])
            out_lines.append(f"  {vname}: G1={g1} G2={g2} G3={g3} G4={g4}     G6={g6} -> {'PASS' if verdict else 'FAIL'}")

    OUT_PATH.write_text("\n".join(out_lines), encoding="utf-8")
    print("\nGate evaluation:")
    print("\n".join(out_lines[-len(VARIANTS):]))
    print(f"\nWritten: {OUT_PATH}")


if __name__ == "__main__":
    sys.exit(main() or 0)
