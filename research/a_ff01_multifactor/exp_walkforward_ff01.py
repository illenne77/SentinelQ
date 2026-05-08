"""A-FF01 multi-factor (B/M + GP/A rank-sum) walk-forward backtest.

PREREG-0007. Long-only top-quintile composite score, monthly rebalance,
EW basket vs equal-weight universe benchmark.

V1 PRIMARY: rank-sum 0.5/0.5, monthly, no extra screen
V2: rank-sum 0.6 BM / 0.4 GPA, monthly
V3: rank-sum 0.4 BM / 0.6 GPA, monthly
V4: rank-sum 0.5/0.5, quarterly
V5: rank-sum 0.5/0.5, monthly, ΔGPA>0 screen

Output: research/a_ff01_multifactor/walkforward_ff01_results.txt
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
OUT_PATH = ROOT / "research" / "a_ff01_multifactor" / "walkforward_ff01_results.txt"

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


def build_bm_panel(close: pd.DataFrame, equity: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
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
        bm[ticker] = (eq_on_close / sh) / close[ticker]
    return bm


def build_gpa_panel(close: pd.DataFrame, income: pd.DataFrame) -> pd.DataFrame:
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


def build_score_panel(bm: pd.DataFrame, gpa: pd.DataFrame, w_bm: float, w_gpa: float) -> pd.DataFrame:
    cols = [c for c in bm.columns if c in gpa.columns]
    bm2 = bm[cols]
    gpa2 = gpa[cols]
    mask = bm2.notna() & gpa2.notna()
    bm_masked = bm2.where(mask)
    gpa_masked = gpa2.where(mask)
    rank_bm = bm_masked.rank(axis=1, ascending=False, method="average", pct=True)
    rank_gpa = gpa_masked.rank(axis=1, ascending=False, method="average", pct=True)
    score_bm = 1.0 - rank_bm
    score_gpa = 1.0 - rank_gpa
    return w_bm * score_bm + w_gpa * score_gpa


def first_trading_day(idx: pd.DatetimeIndex, year: int, month: int) -> Optional[pd.Timestamp]:
    days = idx[(idx.year == year) & (idx.month == month)]
    return days[0] if len(days) > 0 else None


def get_rebalance_dates(idx, start, end, monthly):
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
        cur += pd.DateOffset(months=1 if monthly else 3)
    return dates


def run_variant(close, score, dgpa, ts, te, pct, monthly, dgpa_pos):
    idx = close.index
    test_dates = idx[(idx >= ts) & (idx <= te)]
    rebal_dates = get_rebalance_dates(idx, test_dates[0], test_dates[-1], monthly)
    rebal_set = set(rebal_dates)
    nav_series = pd.Series(index=test_dates, dtype=float)
    holdings = {}
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
            row = score.loc[d]
            valid = row.dropna()
            valid = valid[valid.index.map(lambda tk: tk in close.columns
                                           and not pd.isna(close.loc[d, tk])
                                           and close.loc[d, tk] > 0)]
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
    universe_cols = [c for c in close.columns if c in score.columns]
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

    return {
        "cagr": cagr, "cagr_bench": cagr_b, "alpha_ann": cagr - cagr_b,
        "sharpe": float(sharpe), "max_dd": float(dd),
        "hit_month": float(hit_month), "n_obs": int(len(test_dates)),
        "n_rebal": len(rebal_dates), "final_nav": float(nav_series.iloc[-1]),
    }


VARIANTS = [
    ("V1", 0.50, 0.50, 0.20, True, False),
    ("V2", 0.60, 0.40, 0.20, True, False),
    ("V3", 0.40, 0.60, 0.20, True, False),
    ("V4", 0.50, 0.50, 0.20, False, False),
    ("V5", 0.50, 0.50, 0.20, True, True),
]


def main():
    print("Loading data...")
    close = load_close_panel()
    income = pd.read_parquet(INCOME_PQ)
    equity = pd.read_parquet(EQUITY_PQ)
    shares = pd.read_csv(SHARES_CSV, dtype={"ticker": str})
    shares["ticker"] = shares["ticker"].str.zfill(6)
    print("Building B/M panel..."); bm = build_bm_panel(close, equity, shares)
    print("Building GP/A panel..."); gpa = build_gpa_panel(close, income)
    print("Building dGPA panel..."); dgpa = build_dgpa_panel(close, income)

    cols = [c for c in bm.columns if c in gpa.columns]
    eligible = ((bm[cols].notna()) & (gpa[cols].notna())).any().sum()
    print(f"  Tickers with both signals: {eligible}")

    rows = []
    score_cache = {}
    for win_name, ts, te in WINDOWS:
        ts_t, te_t = pd.Timestamp(ts), pd.Timestamp(te)
        for vname, w_bm, w_gpa, pct, monthly, dgpa_pos in VARIANTS:
            key = (w_bm, w_gpa)
            if key not in score_cache:
                print(f"  Building score panel w_bm={w_bm} w_gpa={w_gpa} ...")
                score_cache[key] = build_score_panel(bm, gpa, w_bm, w_gpa)
            print(f"  Running {win_name} / {vname} ...")
            stats = run_variant(close, score_cache[key], dgpa, ts_t, te_t, pct, monthly, dgpa_pos)
            stats["window"] = win_name
            stats["variant"] = vname
            rows.append(stats)

    df = pd.DataFrame(rows)
    cols2 = ["window", "variant", "cagr", "cagr_bench", "alpha_ann",
             "sharpe", "max_dd", "hit_month", "n_obs", "n_rebal", "final_nav"]
    df = df[cols2]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_lines = []
    out_lines.append("PREREG-0007 A-FF01 Value+Quality multi-factor walk-forward results")
    out_lines.append(f"Generated: {datetime.now().isoformat()}")
    out_lines.append(f"Universe size (close): {len(close.columns)}; both-signal tickers: {eligible}")
    out_lines.append("")
    out_lines.append(df.to_string(index=False, float_format=lambda x: f"{x: .4f}"))
    out_lines.append("")
    out_lines.append("KPI gates (PREREG-0007 §6):")
    out_lines.append("  G1 alpha_ann >= +1.5% (FULL)")
    out_lines.append("  G2 hit_month >= 55% (FULL)")
    out_lines.append("  G3 max_dd >= -25% (FULL)")
    out_lines.append("  G4 alpha_ann > 0 in ALL of W1/W2/W3")
    out_lines.append("  G5 V1 rank <= 3 of 5 by alpha_ann in EACH of W1/W2/W3")
    out_lines.append("  G6 sharpe >= 0.6 (FULL)")
    out_lines.append("")
    print()
    print("\n".join(out_lines))

    full = df[df["window"] == "FULL"]
    out_lines.append("Gate evaluation:")
    for vname, *_ in VARIANTS:
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
    print("\n".join(out_lines[-len(VARIANTS) - 1:]))
    print(f"\nWritten: {OUT_PATH}")


if __name__ == "__main__":
    sys.exit(main() or 0)
