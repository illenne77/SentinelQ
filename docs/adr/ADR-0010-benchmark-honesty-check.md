# ADR-0010: Benchmark honesty check — EW universe deflated alphas; mega-cap concentration is the structural story

**Status**: Accepted
**Date**: 2026-05-09
**Linked**: [ADR-0007](ADR-0007-a-f01-book-to-market-result.md), [ADR-0008](ADR-0008-a-f03-gross-profitability-result.md), [ADR-0009](ADR-0009-a-ff01-multifactor-result.md)
**Source**: `research/honesty_check/kospi200_benchmark.txt`

---

## Decision

After re-pricing the 15 DART-fundamentals variants against the **actual
KOSPI200 index** (proxied by KODEX 200 ETF, ticker 069500), the
conclusion of ADR-0007/8/9 (DART-fundamentals class is dead) is
**reinforced, not reversed**. ALL 15 variants now FAIL G1+G4 by an
even wider margin, with FULL alphas ranging from **-13% to -36% pa**.

However, the data also reveals a **crucial structural finding** that
re-frames Phase 0 alpha discovery: the 2023-2026 KR market is
extraordinarily mega-cap concentrated, and **any equal-weighted basket
strategy (regardless of factor) cannot beat KOSPI200 in this regime**.
This shifts the diagnosis from "fundamentals don't work" to "EW basket
construction doesn't work in mega-cap-led markets."

## Method

1. Fetched KODEX 200 ETF (069500) daily closes 2022-12-15 to 2026-05-08
   via FinanceDataReader (`FDR.DataReader('069500', ...)`). FDR's KRX
   index endpoint (`KS200`) returns LOGOUT errors; pykrx is broken
   (per ADR-0006). The KODEX 200 ETF tracks KOSPI200 with near-zero
   tracking error and is a reliable proxy.
2. Computed CAGR for each window (W1/W2/W3/FULL) using the ETF.
3. For each (variant, window) in F01/F03/FF01 result files, computed
   `alpha_ks200 = strategy_cagr - kospi200_cagr` and re-evaluated G1
   (alpha ≥ +1.5% pa, FULL) and G4 (alpha > 0 in all of W1/W2/W3).

## Results

### Benchmark CAGRs

| Window | EW universe (orig) | KOSPI200 (real) | Delta (pp) |
|---|---:|---:|---:|
| W1 (2023) | +41.9% | +26.0% | -15.9 |
| W2 (2024) | -5.5% | -10.0% | -4.5 |
| **W3 (2025-26)** | **+76.5%** | **+165.0%** | **+88.5** |
| FULL (2023-2026) | +37.2% | +53.7% | +16.5 |

W3 is the dominant story: KOSPI200 nearly tripled (+165% CAGR) while
the EW universe only doubled (+76.5% CAGR). The 88.5 pp gap reflects
the Value-up rally + AI mega-cap surge concentrated in the top ~10
names of the index.

### Variant verdicts (FULL alpha after KOSPI200 swap)

**A-F01 (B/M)**: -19.15% to -30.86% pa (was -2.7% to -14.4%)
**A-F03 (GP/A)**: -13.02% to -31.53% pa (was -3.7% to -15.1%)
**A-FF01 (rank-sum)**: -28.21% to -36.09% pa (was -11.7% to -19.6%)

**Zero variants pass G1.** Zero variants pass G4. The honesty check
moves all alphas decisively into the FAIL region.

## Why the EW universe over-stated benchmark performance

Three compounding effects:

1. **Constituency**: Our 136-ticker universe is biased toward
   mid-caps (KOSPI top 80 ex-KOSPI200 + KOSDAQ mid-cap by design).
   It under-represents the top-5 chaebol mega-caps that drove the
   2025-26 index rally.

2. **Weighting**: Equal-weight gives every name 0.74% weight. KOSPI200
   gives Samsung ~25%, SK Hynix ~10%, etc. When the top-5 cap-weighted
   names ran up 200-400% in 2025-26, our EW universe under-captured
   that rally by construction.

3. **Survivor selection**: The universe was frozen in 2026-05 (current
   members). Stocks delisted between 2020-26 are absent. This is a
   smaller effect (~2-3 pp) but adds to the optimistic bias of the EW
   benchmark.

## Structural insight: why ALL equal-weight factor strategies failed

The 88.5 pp KOSPI200 outperformance in W3 is concentrated in ~10 names
(Samsung, SK Hynix, Hyundai Motor, KB Financial, Shinhan, etc.). In a
top-quintile EW basket of 27 names, even if 5 of those 10 winners are
selected, they get 5 × 3.7% = 18.5% portfolio weight — vs ~50%
combined weight in KOSPI200. The remaining 22 picks (lower-quality
mid-caps) drag the EW basket return down. This is a **structural
limitation of EW basket construction in concentrated bull markets**,
not a failure of the underlying factor signals.

The factor signals themselves (B/M, GP/A) may still have predictive
power within the cross-section — what they cannot do is **beat the
index when the index is being driven by 10 names doing 3-5x**.

## Implications for Phase 0 strategy

This insight changes the recommendation in ADR-0009 §"Pivot decision".
Instead of jumping straight to A-A01 news sentiment (still valid for
later), we should consider:

### NEW: Cap-weighted factor-tilted construction (deferred to A-FW01)

A natural follow-up to A-FF01 would be **cap-weighted top-quintile**
instead of equal-weighted: keep the same factor selection but weight
by market cap within the basket. This would partially replicate
KOSPI200's mega-cap loading and isolate whether the factors add
*marginal* alpha on top of cap-weighting. **NOT pre-registered yet**;
add to the queue for Phase 0.5 if needed.

### Confirmation: A6 (institutional/foreign flow) remains highest priority

Investor flow signals (A6) are KNOWN in the literature to predict
cap-weighted index returns short-term, not just cross-sectional
returns. They sidestep the EW-vs-cap-weight construction issue
entirely. The forward-collect daemon (now scheduled daily) is the
right bet to wait for.

### Alternative-data alphas (A-A01 news sentiment) are still in the queue but lower priority than originally stated

News sentiment, like fundamentals, would face the same EW
construction handicap if implemented as a long-only quintile basket.
Implementing it now would likely reproduce the "factor signal works
cross-sectionally but EW basket loses to index" failure pattern.
Defer until either (a) we have a cap-weighted construction harness,
or (b) A6 produces enough data to test alongside.

## Lessons learned

1. **Always benchmark against the real market index.** EW-universe
   benchmarks make positive results look better than they are and
   negative results look less bad. The honesty check should be a
   pre-registered step in every PREREG going forward.

2. **Construction methodology matters as much as signal selection.**
   In a concentrated bull market, the choice of weighting scheme can
   dominate any cross-sectional signal. Future PREREGs should
   include `weighting=ew | cap | sqrt_cap` as a frozen variant axis.

3. **A 3-year sample with one extreme regime is genuinely small.**
   2025-26 KR is so unusual that it makes the entire sample
   non-stationary. Conclusions should be hedged: "doesn't work
   2023-26" is more honest than "doesn't work, period."

4. **Library breakage is a real Phase 0 cost.** pykrx broken, FDR's
   KRX index endpoint broken, KIS native investor depth = 30d only.
   Each forced detours costing days. Document data infrastructure
   limitations explicitly in PREREGs.

## Action items

- [x] Honesty-check script `research/honesty_check/bench_kospi200.py` committed.
- [x] A6 daemon scheduled task registered (daily 18:00 KST).
- [ ] Update README with current Phase 0 status (next).
- [ ] Phase 2 port abstractions (next).
- [ ] If A6 data sufficient → run A6 backtest with **both** EW and
      cap-weighted baskets; report against KOSPI200 benchmark.
- [ ] Backlog: A-FW01 cap-weighted factor-tilted variant of A-FF01,
      deferred to Phase 0.5 contingent on A6 result.

## What this does NOT change

- DART-fundamentals long-only EW quintile class is still dead (ADR-0009).
- A2/A3/A4/A7 price-volume alphas are still dead.
- 8/8 standalone alpha failure tally stands.
- A6 remains the highest-prior next bet; daemon now running.
