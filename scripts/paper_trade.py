"""Paper-trade harness — wires DataPort + ClockPort + BrokerPort + Portfolio.

This is the minimal end-to-end loop. A strategy is a callable
``(data_port, clock_port, current_positions) -> List[OrderRequest]``
called once per ``rebalance_dates``.

Phase 0 status: harness is functional; no live alpha to deploy.
The default strategy is a no-op so this script's primary purpose is
**integration smoke test** of the port wiring. When A6 (or any other
alpha) graduates, plug a real strategy callable in.

Usage:
    py scripts/paper_trade.py --start 2025-01-01 --end 2026-05-08 --capital 10000000
    py scripts/paper_trade.py --strategy noop  --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sentinelq.adapters.clock import SimulatedClock
from sentinelq.adapters.kis_broker import KisBroker
from sentinelq.adapters.kis_data import KisData
from sentinelq.portfolio.portfolio import Portfolio
from sentinelq.ports.broker import OrderRequest

Strategy = Callable[["KisData", "SimulatedClock", Dict[str, int]], List[OrderRequest]]


def noop_strategy(data, clock, positions) -> List[OrderRequest]:
    return []


def equal_weight_top5_strategy(data, clock, positions) -> List[OrderRequest]:
    """Demo: equal-weight top-5 by 30-day momentum. NOT a graduated alpha."""
    universe = data.get_universe()
    now = clock.now()
    lookback_start = now - pd.Timedelta(days=45)
    momentum: Dict[str, float] = {}
    for tk in universe[:60]:  # cap for speed
        bars = data.get_daily_bars(tk, lookback_start, now)
        if len(bars) < 20:
            continue
        ret = (bars["close"].iloc[-1] / bars["close"].iloc[0]) - 1
        momentum[tk] = float(ret)
    if not momentum:
        return []
    top5 = sorted(momentum.items(), key=lambda kv: kv[1], reverse=True)[:5]
    targets = {tk for tk, _ in top5}
    orders: List[OrderRequest] = []
    for tk, qty in positions.items():
        if tk not in targets and qty > 0:
            orders.append(OrderRequest(ticker=tk, side="SELL", qty=qty,
                                       client_order_id=f"sell-{tk}-{now.isoformat()}"))
    held_targets = {tk for tk in targets if tk in positions}
    new_targets = [tk for tk in targets if tk not in positions]
    if new_targets:
        # naive equal-weight allocation among new targets only (not full rebalance)
        for tk in new_targets:
            px = data.latest_close(tk, now)
            if px is None or px <= 0:
                continue
            qty = max(1, int(2_000_000 // px))  # 2M KRW per name slot
            orders.append(OrderRequest(ticker=tk, side="BUY", qty=qty,
                                       client_order_id=f"buy-{tk}-{now.isoformat()}"))
    return orders


STRATEGIES: Dict[str, Strategy] = {
    "noop": noop_strategy,
    "demo_momentum": equal_weight_top5_strategy,
}


def get_rebalance_dates(start: pd.Timestamp, end: pd.Timestamp) -> List[pd.Timestamp]:
    cur = pd.Timestamp(start.year, start.month, 1)
    out = []
    while cur <= end:
        # first business day of the month
        bd = cur
        while bd.weekday() >= 5:
            bd = bd + pd.Timedelta(days=1)
        if start <= bd <= end:
            out.append(pd.Timestamp(year=bd.year, month=bd.month, day=bd.day, hour=9, minute=0))
        cur = (cur + pd.DateOffset(months=1))
    return out


def run(start: str, end: str, capital: float, strategy_name: str, dry_run: bool) -> int:
    strategy = STRATEGIES[strategy_name]
    data = KisData()
    universe = data.get_universe()
    if not universe:
        print("ERROR: empty universe; ensure universe files exist.", file=sys.stderr)
        return 2
    print(f"Universe: {len(universe)} tickers")

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    clock = SimulatedClock(start_ts.replace(hour=9))
    broker = KisBroker(data_port=data, clock_port=clock, phase="paper")
    portfolio = Portfolio(initial_cash=capital)

    rebal_dates = get_rebalance_dates(start_ts, end_ts)
    print(f"Rebalance dates: {len(rebal_dates)}")

    last_fill_ts = pd.Timestamp("1970-01-01")
    for d in rebal_dates:
        clock.advance_to(d)
        positions = broker.positions()
        orders = strategy(data, clock, positions)
        if dry_run:
            for o in orders:
                px = data.latest_close(o.ticker, d)
                print(f"  DRY {d.date()} {o.side} {o.qty} {o.ticker} ~{px}")
            continue
        for o in orders:
            ack = broker.submit(o)
            if not ack.accepted:
                print(f"  REJECT {d.date()} {o.side} {o.qty} {o.ticker}: {ack.reason}")
        new_fills = broker.fills_since(last_fill_ts)
        for f in new_fills:
            portfolio.on_fill(f)
        last_fill_ts = clock.now()
        # mark portfolio
        prices = {tk: data.latest_close(tk, d) for tk in broker.positions().keys()}
        prices = {k: v for k, v in prices.items() if v is not None}
        nav = portfolio.mark(d, prices)
        print(f"  {d.date()}  positions={len(broker.positions())}  nav={nav:,.0f}")

    print()
    final_prices = {tk: data.latest_close(tk, end_ts) for tk in broker.positions()}
    final_prices = {k: v for k, v in final_prices.items() if v is not None}
    final_nav = portfolio.mark(end_ts, final_prices)
    print(f"Final NAV: {final_nav:,.0f}  (return: {(final_nav/capital - 1)*100:+.2f}%)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-05-08")
    ap.add_argument("--capital", type=float, default=10_000_000)
    ap.add_argument("--strategy", default="noop", choices=list(STRATEGIES.keys()))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return run(args.start, args.end, args.capital, args.strategy, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
