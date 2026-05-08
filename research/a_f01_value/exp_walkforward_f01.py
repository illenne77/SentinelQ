"""A-F01 Book-to-Market walk-forward backtest.

PREREG-0005. Long-only top-quintile B/M, monthly rebalance,
EW basket vs equal-weight universe benchmark.

V1 (PRIMARY):  top quintile, monthly rebalance, no stop
V2:            top decile,   monthly rebalance, no stop
V3:            top quintile, quarterly rebalance, no stop
V4:            top quintile, monthly rebalance, ROE>0 quality screen
V5:            top quintile, monthly rebalance, -10% per-name stop

Outputs:
    research/a_f01_value/walkforward_f01_results.txt
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent

EQUITY_PQ = ROOT / "data" / "cache" / "dart" / "equity_quarterly.parquet"
SHARES_CSV = ROOT / "data" / "cache" / "dart" / "shares_snapshot.csv"
SECTOR_CSV = ROOT / "research" / "a2_sector_rotation" / "sector_map.csv"
DAILY_DIR = ROOT / "data" / "cache" / "kis_daily"
OUT_PATH = ROOT / "research" / "a_f01_value" / "walkforward_f01_results.txt"

ROUND_TRIP_COST = 0.0030
ANNUAL_FACTOR = 252

WINDOWS = [
    ("W1", "2020-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("W2", "2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("W3", "2022-01-01", "2024-12-31", "2025-01-01", "2026-05-08"),
    ("FULL", "2020-01-01", "2022-12-31", "2023-01-01", "2026-05-08"),
]


def load_prices() -> Dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(DAILY_DIR.glob("*.parquet")):
        tk = f.stem
        df = pd.read_parquet(f)
        df = df[["close"]].copy()
        df.index = pd.to_datetime(df.index)
        out[tk] = df
    return out


def build_close_panel(prices: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    s = {tk: df["close"].astype(float) for tk, df in prices.items()}
    panel = pd.DataFrame(s).sort_index()
    return panel


def build_bm_panel(close: pd.DataFrame, equity: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """Build BM[date, ticker] using point-in-time equity / (close * shares)."""
    shares_map = dict(zip(shares["ticker"].astype(str).str.zfill(6), shares["shares"].astype(float)))

    eq = equity.copy()
    eq["ticker"] = eq["ticker"].astype(str).str.zfill(6)
    eq = eq.sort_values(["ticker", "available_from"])

    bm = pd.DataFrame(index=close.index, columns=close.columns, dtype=float)
    for ticker in close.columns:
        if ticker not in shares_map:
            continue
        sh = shares_map[ticker]
        if sh <= 0:
            continue
        sub = eq[eq["ticker"] == ticker][["available_from", "equity_controlling_krw"]].dropna()
        if sub.empty:
            continue
        sub = sub.sort_values("available_from")
        idx_dates = close.index
        eq_series = sub.set_index("available_from")["equity_controlling_krw"]
        # forward-fill onto close index
        eq_on_close = eq_series.reindex(idx_dates, method="ffill")
        bps = eq_on_close / sh
        bm[ticker] = bps / close[ticker]
    return bm


def build_roe_screen(equity: pd.DataFrame) -> Dict[str, pd.Series]:
    """Approx quality: trailing 4Q controlling-equity growth > 0 (sub for ROE).
    Returns: ticker -> Series indexed by available_from with bool 'quality_ok'.
    """
    eq = equity.copy()
    eq["ticker"] = eq["ticker"].astype(str).str.zfill(6)
    eq = eq.sort_values(["ticker", "available_from"])
    result = {}
    for tk, sub in eq.groupby("ticker"):
        sub = sub.set_index("available_from")["equity_controlling_krw"].sort_index()
        # 4Q growth proxy: equity(now) > equity(4Q ago)
        ok = sub > sub.shift(4)
        result[tk] = ok.fillna(False)
    return result


def first_trading_day_of_month(idx: pd.DatetimeIndex, year: int, month: int) -> Optional[pd.Timestamp]:
    days = idx[(idx.year == year) & (idx.month == month)]
    return days[0] if len(days) > 0 else None


def get_rebalance_dates(idx: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp,
                         monthly: bool) -> List[pd.Timestamp]:
    dates = []
    if monthly:
        cur = pd.Timestamp(start.year, start.month, 1)
    else:
        # quarterly: Mar/Jun/Sep/Dec
        m = ((start.month - 1) // 3) * 3 + 3
        cur = pd.Timestamp(start.year, m, 1)
    end_marker = pd.Timestamp(end.year, end.month, 1)
    while cur <= end_marker:
        d = first_trading_day_of_month(idx, cur.year, cur.month)
        if d is not None and start <= d <= end:
            dates.append(d)
        if monthly:
            cur = cur + pd.DateOffset(months=1)
        else:
            cur = cur + pd.DateOffset(months=3)
    return dates


def run_variant(close: pd.DataFrame, bm: pd.DataFrame,
                roe_ok: Dict[str, pd.Series],
                test_start: pd.Timestamp, test_end: pd.Timestamp,
                pct: float, monthly: bool, quality: bool, stop_pct: Optional[float]
                ) -> Tuple[pd.Series, pd.Series, dict]:
    """Returns (nav_series, bench_series, stats)."""
    idx = close.index
    test_mask = (idx >= test_start) & (idx <= test_end)
    test_dates = idx[test_mask]
    if len(test_dates) == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float), {}

    rebal_dates = get_rebalance_dates(idx, test_dates[0], test_dates[-1], monthly)

    # Strategy NAV
    nav_series = pd.Series(index=test_dates, dtype=float)
    holdings: Dict[str, float] = {}      # ticker -> shares
    entry_px: Dict[str, float] = {}
    cash = 1.0
    rebal_set = set(rebal_dates)

    def mtm_of(d: pd.Timestamp) -> float:
        v = 0.0
        for tk, sh in holdings.items():
            px = close.loc[d, tk] if tk in close.columns else None
            if px is None or pd.isna(px):
                continue
            v += sh * float(px)
        return v

    for d in test_dates:
        # Stop-loss check (sell at half-cost)
        if stop_pct is not None and holdings:
            to_close = []
            for tk in list(holdings.keys()):
                px = close.loc[d, tk] if tk in close.columns else None
                if px is None or pd.isna(px):
                    continue
                if float(px) <= entry_px[tk] * (1.0 + stop_pct):
                    to_close.append(tk)
            for tk in to_close:
                px = float(close.loc[d, tk])
                cash += holdings[tk] * px * (1 - ROUND_TRIP_COST / 2)
                del holdings[tk]
                del entry_px[tk]

        # Rebalance
        if d in rebal_set:
            # Liquidate at half-cost
            for tk, sh in list(holdings.items()):
                px = close.loc[d, tk] if tk in close.columns else None
                if px is None or pd.isna(px):
                    # carry forward at last value (rare); skip
                    continue
                cash += sh * float(px) * (1 - ROUND_TRIP_COST / 2)
            holdings = {}
            entry_px = {}

            # Pick targets
            row_bm = bm.loc[d]
            valid = row_bm.dropna()
            # require live close
            valid = valid[valid.index.map(lambda tk: tk in close.columns and not pd.isna(close.loc[d, tk]) and close.loc[d, tk] > 0)]
            if quality:
                ok_tk = []
                for tk in valid.index:
                    rsr = roe_ok.get(tk)
                    if rsr is None:
                        continue
                    rsr_pos = rsr[rsr.index <= d]
                    if len(rsr_pos) > 0 and bool(rsr_pos.iloc[-1]):
                        ok_tk.append(tk)
                valid = valid.loc[ok_tk]

            if len(valid) >= 5:
                n_pick = max(1, int(round(len(valid) * pct)))
                picks = valid.sort_values(ascending=False).head(n_pick).index.tolist()
                per_name = cash / len(picks)
                for tk in picks:
                    px = float(close.loc[d, tk])
                    eff_cash = per_name * (1 - ROUND_TRIP_COST / 2)
                    holdings[tk] = eff_cash / px
                    entry_px[tk] = px
                    cash -= per_name

        nav_series.loc[d] = cash + mtm_of(d)

    nav_series = nav_series.ffill().fillna(1.0)

    # Benchmark: EW of universe over same dates
    universe_cols = [c for c in close.columns if c in bm.columns]
    bench_close = close[universe_cols].loc[test_dates]
    bench_ret = bench_close.pct_change().mean(axis=1).fillna(0.0)
    bench = (1 + bench_ret).cumprod()

    # Stats
    days = (test_dates[-1] - test_dates[0]).days
    yrs = max(days / 365.25, 1e-6)
    cagr = nav_series.iloc[-1] ** (1 / yrs) - 1
    cagr_b = bench.iloc[-1] ** (1 / yrs) - 1
    ret = nav_series.pct_change().fillna(0.0)
    sharpe = ret.mean() / (ret.std() + 1e-12) * np.sqrt(ANNUAL_FACTOR)
    dd = (nav_series / nav_series.cummax() - 1).min()
    # Monthly hit rate
    monthly_nav = nav_series.resample("M").last()
    monthly_b = bench.resample("M").last()
    m_excess = monthly_nav.pct_change().fillna(0) - monthly_b.pct_change().fillna(0)
    hit_month = (m_excess > 0).mean() if len(m_excess) > 0 else 0.0

    stats = {
        "cagr": cagr,
        "cagr_bench": cagr_b,
        "alpha_ann": cagr - cagr_b,
        "sharpe": float(sharpe),
        "max_dd": float(dd),
        "hit_month": float(hit_month),
        "n_obs": int(len(test_dates)),
        "n_rebal": len(rebal_dates),
        "final_nav": float(nav_series.iloc[-1]),
    }
    return nav_series, bench, stats


VARIANTS = [
    ("V1", 0.20, True, False, None),
    ("V2", 0.10, True, False, None),
    ("V3", 0.20, False, False, None),
    ("V4", 0.20, True, True, None),
    ("V5", 0.20, True, False, -0.10),
]


def main():
    print("Loading data...")
    prices = load_prices()
    close = build_close_panel(prices)
    print(f"  Close panel: {close.shape}")

    equity = pd.read_parquet(EQUITY_PQ)
    shares = pd.read_csv(SHARES_CSV, dtype={"ticker": str})
    shares["ticker"] = shares["ticker"].str.zfill(6)
    print(f"  Equity: {equity.shape}; Shares: {shares.shape}")

    print("Building B/M panel...")
    bm = build_bm_panel(close, equity, shares)
    print(f"  BM panel: {bm.shape}; non-null cells: {bm.notna().sum().sum()}")

    print("Building ROE screen...")
    roe_ok = build_roe_screen(equity)

    rows = []
    for win_name, _, _, ts, te in WINDOWS:
        ts_t = pd.Timestamp(ts)
        te_t = pd.Timestamp(te)
        for vname, pct, monthly, quality, stop in VARIANTS:
            print(f"  Running {win_name} / {vname} ...")
            nav, bench, stats = run_variant(close, bm, roe_ok, ts_t, te_t, pct, monthly, quality, stop)
            stats["window"] = win_name
            stats["variant"] = vname
            rows.append(stats)

    df = pd.DataFrame(rows)
    cols = ["window", "variant", "cagr", "cagr_bench", "alpha_ann",
            "sharpe", "max_dd", "hit_month", "n_obs", "n_rebal", "final_nav"]
    df = df[cols]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_lines = []
    out_lines.append("PREREG-0005 A-F01 Book-to-Market walk-forward results")
    out_lines.append(f"Generated: {datetime.now().isoformat()}")
    out_lines.append(f"Universe size (in close panel): {len(close.columns)}")
    out_lines.append(f"Tickers with any BM signal: {(bm.notna().any()).sum()}")
    out_lines.append("")
    out_lines.append(df.to_string(index=False, float_format=lambda x: f"{x: .4f}"))
    out_lines.append("")
    out_lines.append("KPI gates (PREREG-0005 §7):")
    out_lines.append("  G1 alpha_ann ≥ +1.5% (FULL)")
    out_lines.append("  G2 hit_month ≥ 55% (FULL)")
    out_lines.append("  G3 max_dd ≥ -25% (FULL)")
    out_lines.append("  G4 alpha_ann > 0 in ALL of W1/W2/W3")
    out_lines.append("  G5 V1 rank ≤ 3 of 5 by alpha_ann in EACH of W1/W2/W3")
    out_lines.append("  G6 sharpe ≥ 0.6 (FULL)")
    out_lines.append("")

    full = df[df["window"] == "FULL"]
    print()
    print("\n".join(out_lines))

    # Gate evaluation per variant
    out_lines.append("Gate evaluation:")
    for vname, _, _, _, _ in VARIANTS:
        full_v = full[full["variant"] == vname].iloc[0]
        g1 = full_v["alpha_ann"] >= 0.015
        g2 = full_v["hit_month"] >= 0.55
        g3 = full_v["max_dd"] >= -0.25
        g6 = full_v["sharpe"] >= 0.6
        # G4 per-window
        per_win = df[(df["variant"] == vname) & (df["window"].isin(["W1", "W2", "W3"]))]
        g4 = (per_win["alpha_ann"] > 0).all()
        # G5 only meaningful for V1
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
    print(f"\nWritten: {OUT_PATH}")
    print("\n".join(out_lines[-10:]))


if __name__ == "__main__":
    sys.exit(main() or 0)
