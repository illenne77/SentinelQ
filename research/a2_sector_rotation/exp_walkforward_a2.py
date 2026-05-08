"""A2 Sector Rotation Momentum — walk-forward backtest.

Implements PREREG-0004 V1-V5. Portfolio-level NAV simulator
(A4/A3 single-trade engine cannot be reused).

Mechanics (per PREREG §4-§5):
  At each rebal date t:
    1. compute sector momentum = mean log-return of constituents over (t-L, t]
    2. rank sectors desc, take top-K
    3. within each top sector, pick top-1 stock by RS (stock_logret - sector_mean_logret)
    4. close any held position whose ticker not in new picks
    5. open new picks at rebal-day open, each at NAV/K notional
  Daily mark-to-market on close. Intraday stop/TP at H/L touch.
  Max-hold L_h trading days (close exit). Round-trip cost 0.30%.

Outputs: walkforward_a2_results.txt with W1/W2/W3/FULL × V1-V5 cells.
"""
from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
A2 = ROOT / "research" / "a2_sector_rotation"
CACHE = ROOT / "data" / "cache" / "kis_daily"

UNIVERSE_FILES = [
    ROOT / "research" / "a4_liquidity_surge" / "universe_kospi_top80.txt",
    ROOT / "research" / "a4_liquidity_surge" / "universe_kosdaq_midcap.txt",
]

SECTOR_MAP_CSV = A2 / "sector_map.csv"
RESULTS_TXT = A2 / "walkforward_a2_results.txt"

ROUND_TRIP_COST = 0.0030

# Walk-forward windows (PREREG §7)
WINDOWS = {
    "W1": ("2023-01-01", "2023-12-31"),
    "W2": ("2024-01-01", "2024-12-31"),
    "W3": ("2025-01-01", "2026-05-08"),
    "FULL": ("2023-01-01", "2026-05-08"),
}

# Variants (PREREG §5)
VARIANTS = {
    "V1": dict(L=20, K=3, picks=1, stop=0.03, tp=0.12, max_hold=20, rebal="M"),
    "V2": dict(L=60, K=3, picks=1, stop=0.03, tp=0.12, max_hold=20, rebal="M"),
    "V3": dict(L=20, K=5, picks=1, stop=0.03, tp=0.12, max_hold=20, rebal="M"),
    "V4": dict(L=20, K=3, picks=1, stop=0.02, tp=0.10, max_hold=20, rebal="M"),
    "V5": dict(L=20, K=3, picks=1, stop=0.03, tp=0.12, max_hold=20, rebal="W"),
}


# ------------------------------------------------------------------ #
# Data loading
# ------------------------------------------------------------------ #
def load_universe() -> list[str]:
    seen, out = set(), []
    for f in UNIVERSE_FILES:
        for line in f.read_text(encoding="utf-8").splitlines():
            t = line.strip().split("#", 1)[0].strip()
            if t.isdigit() and len(t) == 6 and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def load_sector_map() -> dict[str, str]:
    out = {}
    with SECTOR_MAP_CSV.open(encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            if row["sector"] != "OTHER":
                out[row["ticker"]] = row["sector"]
    return out


def load_bars() -> dict[str, pd.DataFrame]:
    out = {}
    for t in load_universe():
        p = CACHE / f"{t}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if df.empty or "close" not in df.columns:
            continue
        out[t] = df.sort_index()
    return out


# ------------------------------------------------------------------ #
# Backtest engine
# ------------------------------------------------------------------ #
@dataclass
class Position:
    ticker: str
    sector: str
    entry_date: pd.Timestamp
    entry_price: float
    notional: float          # initial notional in NAV units at entry
    days_held: int = 0
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    exit_reason: str = ""

    def stop_level(self, stop: float) -> float:
        return self.entry_price * (1 - stop)

    def tp_level(self, tp: float) -> float:
        return self.entry_price * (1 + tp)


def trading_days(bars: dict[str, pd.DataFrame], start: str, end: str) -> pd.DatetimeIndex:
    """Union of trading days observed across universe in [start, end]."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    idx = None
    for df in bars.values():
        d = df.index[(df.index >= s) & (df.index <= e)]
        idx = d if idx is None else idx.union(d)
    return idx.sort_values() if idx is not None else pd.DatetimeIndex([])


def rebalance_dates(td: pd.DatetimeIndex, mode: str) -> set[pd.Timestamp]:
    """First trading day of each month (M) or each week-Monday (W)."""
    if mode == "M":
        seen = set()
        out = []
        for d in td:
            key = (d.year, d.month)
            if key not in seen:
                seen.add(key)
                out.append(d)
        return set(out)
    elif mode == "W":
        seen = set()
        out = []
        for d in td:
            iso = d.isocalendar()
            # pandas Timestamp.isocalendar returns tuple in old versions, named in new
            if hasattr(iso, "year"):
                key = (iso.year, iso.week)
            else:
                key = (iso[0], iso[1])
            if key not in seen:
                seen.add(key)
                out.append(d)
        return set(out)
    else:
        raise ValueError(mode)


def sector_momentum(
    bars: dict[str, pd.DataFrame],
    sector_map: dict[str, str],
    t: pd.Timestamp,
    L: int,
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """Returns (sector_mom, stock_logret_per_sector).
    sector_mom[s] = mean log-return of sector members over last L trading days
                    ending strictly before t (no look-ahead).
    """
    sector_logrets: dict[str, list[float]] = {}
    stock_lr: dict[str, dict[str, float]] = {}

    for ticker, sector in sector_map.items():
        df = bars.get(ticker)
        if df is None:
            continue
        # Use bars strictly before t (entry is on t open)
        sub = df.loc[df.index < t].tail(L + 1)
        if len(sub) < L + 1:
            continue
        c0 = sub["close"].iloc[0]
        c1 = sub["close"].iloc[-1]
        if c0 <= 0 or c1 <= 0:
            continue
        lr = math.log(c1 / c0)
        sector_logrets.setdefault(sector, []).append(lr)
        stock_lr.setdefault(sector, {})[ticker] = lr

    sector_mom = {s: float(np.mean(v)) for s, v in sector_logrets.items() if v}
    return sector_mom, stock_lr


def select_picks(
    sector_mom: dict[str, float],
    stock_lr: dict[str, dict[str, float]],
    K: int,
    picks: int,
) -> list[tuple[str, str]]:
    """Returns list of (ticker, sector) — top-`picks` stocks within each top-`K` sector by RS."""
    top_sectors = sorted(sector_mom, key=lambda s: -sector_mom[s])[:K]
    out = []
    for s in top_sectors:
        members = stock_lr.get(s, {})
        if not members:
            continue
        sec_mean = sector_mom[s]
        rs = sorted(members.items(), key=lambda kv: -(kv[1] - sec_mean))
        for ticker, _ in rs[:picks]:
            out.append((ticker, s))
    return out


def run_backtest(
    bars: dict[str, pd.DataFrame],
    sector_map: dict[str, str],
    start: str,
    end: str,
    variant: dict,
) -> dict:
    L = variant["L"]
    K = variant["K"]
    picks = variant["picks"]
    stop = variant["stop"]
    tp = variant["tp"]
    max_hold = variant["max_hold"]
    rebal = variant["rebal"]

    td = trading_days(bars, start, end)
    if len(td) == 0:
        return {"nav": pd.Series(dtype=float), "trades": []}
    rebals = rebalance_dates(td, rebal)

    nav = 1.0
    nav_series = []
    open_positions: list[Position] = []
    closed_trades: list[Position] = []

    slots = K * picks  # equal-weight target

    def get_bar(t, d):
        df = bars.get(t)
        if df is None or d not in df.index:
            return None
        row = df.loc[d]
        return float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])

    for d in td:
        # 1. Daily MTM on existing positions before any rebal action.
        #    Also handle stop/TP intraday touches and max-hold.
        new_open = []
        for pos in open_positions:
            bar = get_bar(pos.ticker, d)
            if bar is None:
                # Missing bar — keep, no MTM update for this position
                new_open.append(pos)
                continue
            o, h, l, c = bar

            # Intraday stop/TP check (entry day itself: skip — we already entered at open)
            if d != pos.entry_date:
                pos.days_held += 1
                stop_lvl = pos.stop_level(stop)
                tp_lvl = pos.tp_level(tp)
                hit_stop = l <= stop_lvl
                hit_tp = h >= tp_lvl
                # If both touch in same bar, assume worst (stop first) — conservative
                if hit_stop:
                    pos.exit_date = d
                    pos.exit_price = stop_lvl
                    pos.exit_reason = "stop"
                    closed_trades.append(pos)
                    continue
                if hit_tp:
                    pos.exit_date = d
                    pos.exit_price = tp_lvl
                    pos.exit_reason = "tp"
                    closed_trades.append(pos)
                    continue
                if pos.days_held >= max_hold:
                    pos.exit_date = d
                    pos.exit_price = c
                    pos.exit_reason = "maxhold"
                    closed_trades.append(pos)
                    continue
            new_open.append(pos)
        open_positions = new_open

        # 2. Rebalance action (if d is rebal day): open at next bar open?
        #    Convention: rebal *signal* uses bars STRICTLY BEFORE d; entry on d's open.
        if d in rebals:
            sec_mom, stock_lr = sector_momentum(bars, sector_map, d, L)
            picks_list = select_picks(sec_mom, stock_lr, K, picks)
            target_tickers = {t for t, _ in picks_list}

            # Close held positions not in target
            still = []
            for pos in open_positions:
                if pos.ticker in target_tickers:
                    still.append(pos)
                else:
                    bar = get_bar(pos.ticker, d)
                    if bar is None:
                        still.append(pos)
                        continue
                    pos.exit_date = d
                    pos.exit_price = bar[0]   # exit at d open (rebal)
                    pos.exit_reason = "rebal"
                    closed_trades.append(pos)
            open_positions = still
            held_tickers = {p.ticker for p in open_positions}

            # Compute current NAV for sizing new entries
            mtm_nav = nav  # use carry-forward NAV; positions repriced below

            # Open new picks
            slot_notional = mtm_nav / slots if slots > 0 else 0.0
            for ticker, sector in picks_list:
                if ticker in held_tickers:
                    continue
                bar = get_bar(ticker, d)
                if bar is None:
                    continue
                o, _, _, _ = bar
                if o <= 0:
                    continue
                pos = Position(
                    ticker=ticker, sector=sector,
                    entry_date=d, entry_price=o, notional=slot_notional,
                )
                open_positions.append(pos)

        # 3. Compute end-of-day NAV.
        #    NAV = sum_open(slot_notional * close/entry) + cash
        #    Cash = nav_at_last_rebal - sum(slot_notional for each opened)
        #    Simpler: maintain explicit cash account.
        #
        # To keep state minimal, we recompute NAV fully each day:
        #   for each open: slot_notional * (close/entry_price)
        #   cash = nav_at_open_of_today - sum(slot_notional initially allocated still open)
        #
        # Trick: we set positions' notional at rebal time and never resize.
        # Closed positions release their realized PnL into cash.

        # Use a simpler per-trade-PnL accumulator: NAV diff = sum of (close-prev_close)/entry * slot
        # implemented as a recompute every day.
        # We'll just track a NAV by direct simulation:

        # End-of-day NAV recompute:
        # cash = NAV(t-1) + sum_closed_today(realized_pnl) - sum_opened_today(slot_notional)
        # market_value = sum_open(slot_notional * close/entry)
        # NAV(t) = cash + market_value
        # But this needs day-by-day cash bookkeeping. Let's do it explicitly.
        # See below: we'll redo this loop with explicit cash tracking.

        nav_series.append((d, nav))  # placeholder; will be overwritten by run_backtest_v2

    # Ineffective placeholder above — actual NAV computed in v2 loop:
    return _run_v2(bars, sector_map, td, rebals, variant)


def _run_v2(bars, sector_map, td, rebals, variant) -> dict:
    """Cleaner second-pass simulator with explicit cash tracking."""
    L = variant["L"]; K = variant["K"]; picks = variant["picks"]
    stop = variant["stop"]; tp = variant["tp"]; max_hold = variant["max_hold"]
    slots = K * picks

    cash = 1.0
    open_positions: list[Position] = []
    closed: list[Position] = []
    nav_series = []

    def get_bar(t, d):
        df = bars.get(t)
        if df is None or d not in df.index:
            return None
        r = df.loc[d]
        return float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])

    for d in td:
        # 1. Process existing positions for stop/TP/maxhold intraday.
        survivors = []
        for pos in open_positions:
            bar = get_bar(pos.ticker, d)
            if bar is None:
                survivors.append(pos)
                continue
            o, h, l, c = bar
            if d == pos.entry_date:
                survivors.append(pos)
                continue
            pos.days_held += 1
            stop_lvl = pos.stop_level(stop)
            tp_lvl = pos.tp_level(tp)
            exit_at = None
            reason = ""
            if l <= stop_lvl:
                exit_at = stop_lvl; reason = "stop"
            elif h >= tp_lvl:
                exit_at = tp_lvl; reason = "tp"
            elif pos.days_held >= max_hold:
                exit_at = c; reason = "maxhold"
            if exit_at is not None:
                gross = pos.notional * (exit_at / pos.entry_price)
                cash += gross * (1 - ROUND_TRIP_COST)
                pos.exit_date = d; pos.exit_price = exit_at; pos.exit_reason = reason
                closed.append(pos)
            else:
                survivors.append(pos)
        open_positions = survivors

        # 2. Rebalance.
        if d in rebals:
            sec_mom, stock_lr = sector_momentum(bars, sector_map, d, L)
            picks_list = select_picks(sec_mom, stock_lr, K, picks)
            target_tickers = {t for t, _ in picks_list}

            # Close non-target holdings at d open (rebal exit; cost applied)
            still = []
            for pos in open_positions:
                if pos.ticker in target_tickers:
                    still.append(pos); continue
                bar = get_bar(pos.ticker, d)
                if bar is None:
                    still.append(pos); continue
                exit_at = bar[0]
                gross = pos.notional * (exit_at / pos.entry_price)
                cash += gross * (1 - ROUND_TRIP_COST)
                pos.exit_date = d; pos.exit_price = exit_at; pos.exit_reason = "rebal"
                closed.append(pos)
            open_positions = still

            # Size new entries from current NAV
            mtm = sum(p.notional * (get_bar(p.ticker, d)[3] / p.entry_price)
                      for p in open_positions if get_bar(p.ticker, d) is not None)
            current_nav = cash + mtm
            slot_notional = current_nav / slots if slots > 0 else 0.0
            held = {p.ticker for p in open_positions}
            for ticker, sector in picks_list:
                if ticker in held:
                    continue
                bar = get_bar(ticker, d)
                if bar is None:
                    continue
                o = bar[0]
                if o <= 0:
                    continue
                # Spend slot_notional from cash; cost taken at entry too (half of round-trip)
                spend = slot_notional
                if spend > cash:
                    spend = cash
                if spend <= 0:
                    continue
                # Apply half cost on entry, half on exit -> total = ROUND_TRIP_COST
                effective_notional = spend * (1 - ROUND_TRIP_COST / 2)
                cash -= spend
                pos = Position(
                    ticker=ticker, sector=sector,
                    entry_date=d, entry_price=o,
                    notional=effective_notional,
                )
                open_positions.append(pos)

        # 3. End-of-day NAV.
        mtm = 0.0
        for p in open_positions:
            bar = get_bar(p.ticker, d)
            if bar is None:
                # carry at entry
                mtm += p.notional
            else:
                mtm += p.notional * (bar[3] / p.entry_price)
        # Apply remaining half exit cost notionally (mark MTM net)
        nav = cash + mtm * (1 - ROUND_TRIP_COST / 2)
        nav_series.append((d, nav))

    nav_s = pd.Series({d: v for d, v in nav_series}).sort_index()
    return {"nav": nav_s, "trades": closed, "n_open_end": len(open_positions)}


# ------------------------------------------------------------------ #
# Metrics
# ------------------------------------------------------------------ #
def compute_metrics(nav: pd.Series, bench: pd.Series) -> dict:
    """Annualised returns, alpha vs benchmark, Sharpe, max DD, hit-month."""
    if nav.empty:
        return {}
    rets = nav.pct_change().dropna()
    bench_rets = bench.reindex(nav.index).pct_change().dropna()
    common = rets.index.intersection(bench_rets.index)
    rets = rets.loc[common]
    bench_rets = bench_rets.loc[common]

    n = len(rets)
    if n < 5:
        return {}
    ann = 252
    cum = (1 + rets).prod() - 1
    cum_b = (1 + bench_rets).prod() - 1
    years = n / ann
    cagr = (1 + cum) ** (1 / years) - 1 if years > 0 else 0.0
    cagr_b = (1 + cum_b) ** (1 / years) - 1 if years > 0 else 0.0
    alpha_ann = cagr - cagr_b
    vol = rets.std() * math.sqrt(ann)
    sharpe = (cagr / vol) if vol > 1e-9 else 0.0
    # Max DD on NAV
    peak = nav.cummax()
    dd = (nav / peak - 1).min()

    # Hit-month: monthly NAV diff vs monthly bench diff
    nav_m = nav.resample("M").last()
    bench_m = bench.reindex(nav.index).resample("M").last()
    mret = nav_m.pct_change().dropna()
    bret = bench_m.pct_change().dropna()
    common_m = mret.index.intersection(bret.index)
    excess_m = mret.loc[common_m] - bret.loc[common_m]
    hit_m = float((excess_m > 0).mean()) if len(excess_m) > 0 else 0.0

    return {
        "n_days": n, "cagr": cagr, "cagr_bench": cagr_b,
        "alpha_ann": alpha_ann, "vol": vol, "sharpe": sharpe,
        "max_dd": float(dd), "hit_month": hit_m, "n_months": len(excess_m),
    }


def equal_weight_benchmark(bars: dict[str, pd.DataFrame],
                           tickers: list[str],
                           start: str, end: str) -> pd.Series:
    """Equal-weight rebalanced-monthly basket of given tickers as proxy benchmark.
    Approximates KOSPI200 (we don't have clean index series in cache)."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    closes = []
    for t in tickers:
        df = bars.get(t)
        if df is None or "close" not in df.columns:
            continue
        sub = df.loc[(df.index >= s) & (df.index <= e), "close"]
        if not sub.empty:
            closes.append(sub.rename(t))
    if not closes:
        return pd.Series(dtype=float)
    px = pd.concat(closes, axis=1).sort_index().ffill()
    rets = px.pct_change().fillna(0.0)
    eq = rets.mean(axis=1)
    nav = (1 + eq).cumprod()
    return nav


# ------------------------------------------------------------------ #
# Driver
# ------------------------------------------------------------------ #
def main():
    bars = load_bars()
    sector_map = load_sector_map()
    print(f"loaded bars: {len(bars)} tickers, sector_map: {len(sector_map)} tickers")

    bench = equal_weight_benchmark(
        bars, list(sector_map.keys()), "2020-01-01", "2026-05-08"
    )

    out_lines = []
    out_lines.append("A2 Sector Rotation Walk-Forward Results")
    out_lines.append("PREREG-0004 V1-V5  x  W1/W2/W3/FULL")
    out_lines.append("Benchmark: equal-weighted basket of universe (proxy for KOSPI200)")
    out_lines.append("Cost: 0.30% round-trip")
    out_lines.append("=" * 78)

    # Per-window per-variant metrics
    grid = {}    # (window, variant) -> metrics
    for win, (ws, we) in WINDOWS.items():
        for vn, vparams in VARIANTS.items():
            res = _run_v2(
                bars, sector_map,
                trading_days(bars, ws, we),
                rebalance_dates(trading_days(bars, ws, we), vparams["rebal"]),
                vparams,
            )
            nav = res["nav"]
            if nav.empty:
                grid[(win, vn)] = {}
                continue
            m = compute_metrics(nav, bench)
            grid[(win, vn)] = m
            out_lines.append(
                f"[{win}] {vn:3s}  L={vparams['L']:>2d} K={vparams['K']} "
                f"stop={vparams['stop']:.2f} tp={vparams['tp']:.2f} reb={vparams['rebal']}  "
                f"alpha_ann={m.get('alpha_ann',0)*100:+.2f}%  "
                f"cagr={m.get('cagr',0)*100:+.2f}%  "
                f"sharpe={m.get('sharpe',0):.2f}  "
                f"maxDD={m.get('max_dd',0)*100:+.1f}%  "
                f"hitM={m.get('hit_month',0)*100:.1f}%  "
                f"trades={len(res['trades'])}"
            )
        out_lines.append("-" * 78)

    # KPI gate evaluation (PREREG §8)
    out_lines.append("")
    out_lines.append("KPI GATE EVAL (PREREG-0004 §8) — all gates on FULL test except G4-G5")
    out_lines.append("=" * 78)
    for vn in VARIANTS:
        full = grid.get(("FULL", vn), {})
        w1 = grid.get(("W1", vn), {})
        w2 = grid.get(("W2", vn), {})
        w3 = grid.get(("W3", vn), {})

        g1 = full.get("alpha_ann", -1) >= 0.015
        g2 = full.get("hit_month", 0) >= 0.55
        g3 = full.get("max_dd", -1) >= -0.20
        g4 = all(grid.get(("W" + str(i), vn), {}).get("alpha_ann", -1) > 0 for i in (1, 2, 3))
        g6 = full.get("sharpe", 0) >= 0.7

        # G5 evaluated below across all variants
        out_lines.append(
            f"{vn}: G1_alpha={'PASS' if g1 else 'FAIL'} ({full.get('alpha_ann',0)*100:+.2f}%) "
            f"G2_hitM={'PASS' if g2 else 'FAIL'} ({full.get('hit_month',0)*100:.1f}%) "
            f"G3_DD={'PASS' if g3 else 'FAIL'} ({full.get('max_dd',0)*100:+.1f}%) "
            f"G4_winstab={'PASS' if g4 else 'FAIL'} "
            f"G6_sharpe={'PASS' if g6 else 'FAIL'} ({full.get('sharpe',0):.2f})"
        )

    # G5 primary rank stability
    out_lines.append("")
    out_lines.append("G5 PRIMARY RANK STABILITY (V1 alpha rank in each window, of 5)")
    for win in ("W1", "W2", "W3"):
        ranks = sorted(VARIANTS, key=lambda v: -(grid.get((win, v), {}).get("alpha_ann", -999)))
        rank_v1 = ranks.index("V1") + 1
        out_lines.append(f"  {win}: V1 rank = {rank_v1}/5  (order: {ranks})")

    text = "\n".join(out_lines)
    print(text)
    RESULTS_TXT.write_text(text, encoding="utf-8")
    print(f"\nwrote {RESULTS_TXT}")


if __name__ == "__main__":
    main()
