"""5y KIS backfill — populates parquet cache for all top-80 tickers."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.a4_liquidity_surge.data_loader_kis import (
    load_universe_5y, load_daily_bars_batch_kis,
)

START, END = "20200101", "20260508"

uni = load_universe_5y()
print(f"[backfill] universe={len(uni)} range={START}..{END}")
t0 = time.time()
bars = load_daily_bars_batch_kis(uni, START, END, verbose=True)
elapsed = time.time() - t0

total_rows = sum(len(d) for d in bars.values())
print()
print(f"[backfill] done in {elapsed:.1f}s")
print(f"[backfill] tickers loaded = {len(bars)}/{len(uni)}")
print(f"[backfill] total daily rows = {total_rows:,}")
if bars:
    sample = next(iter(bars.values()))
    print(f"[backfill] sample range = {sample.index.min().date()} .. {sample.index.max().date()}")
