# PREREG-0007: A-FF01 Value+Quality Multi-Factor (rank-sum)

**Status**: Frozen
**Date**: 2026-05-09
**Authors**: SentinelQ research
**Linked**: [ADR-0007](../adr/ADR-0007-a-f01-book-to-market-result.md), [ADR-0008](../adr/ADR-0008-a-f03-gross-profitability-result.md), `research/oss_review/alpha_catalog.md` §A-FF01

---

## 1. Hypothesis

A long-only basket constructed from a **rank-sum** of cross-sectional
B/M and GP/A scores generates positive risk-adjusted alpha
*because the two component factors trade leadership across regimes*
in the KR market 2023-2026.

Empirical motivation (from ADR-0007/0008 walk-forward results):

| Window | A-F01 (B/M) alpha | A-F03 (GP/A) alpha |
|---|---:|---:|
| W1 (2023) | **-33%** | **+10%** |
| W2 (2024) | +11% | 0% |
| W3 (2025-26) | **+12%** | **-28%** |

The ~2-window negative correlation is a textbook diversification
opportunity. This PREREG tests whether **simple linear rank-sum**
combination smooths the regime drag and produces positive FULL alpha.

This is *not* a freshly fitted hypothesis — the combination form
(rank-sum, equal-weight) and the gate thresholds were defined
*before* observing the cyclicality data. The cyclicality is *a
consequence* of the two PREREG'd factors, not a discovered
optimization.

## 2. Universe

Same 136-ticker universe as PREREG-0005/0006. After joining DART
B/M coverage (127 tickers) ∩ DART GP/A coverage (108 tickers) =
**~108 tickers** with both signals. Eligibility at rebalance
date `t` requires both BM and GPA non-null at `t`.

## 3. Signal definition

Notation: at rebalance date `t`, for ticker `i`:

```
BM_i,t   = controlling_equity_q / (close_t × shares_snapshot)   (PREREG-0005)
GPA_i,t  = gross_profit_y / assets_y     (PREREG-0006, annual ffill)

R_BM_i,t  = cross-sectional descending rank of BM in eligible set,
            normalized to [0, 1] (rank/(N-1)); 1 = best (highest BM)
R_GPA_i,t = same for GPA

Score_i,t = w_BM * R_BM_i,t + w_GPA * R_GPA_i,t
```

Cross-sectional descending rank of `Score`. Top quintile = buy.

## 4. Variants (5 cells, frozen)

| ID | w_BM / w_GPA | Picks | Rebal | Extra screen |
|---|---|---|---|---|
| **V1 (PRIMARY)** | 0.50 / 0.50 | top quintile | monthly | none |
| V2 | 0.60 / 0.40 | top quintile | monthly | (BM-tilted) |
| V3 | 0.40 / 0.60 | top quintile | monthly | (GPA-tilted) |
| V4 | 0.50 / 0.50 | top quintile | quarterly | (slow rebal) |
| V5 | 0.50 / 0.50 | top quintile | monthly | also ΔGPA YoY > 0 (improving quality) |

V1 is the **PREREG primary** for stability ranking.

Position sizing: equal-weight 1/N. No leverage, no shorts, no stops.
Cost: round-trip 0.30% (same as all prior PREREGs).

## 5. Walk-forward windows

Identical to PREREG-0005/6:

| Window | Train | Test |
|---|---|---|
| W1 | 2020-01 .. 2022-12 | 2023-01 .. 2023-12 |
| W2 | 2021-01 .. 2023-12 | 2024-01 .. 2024-12 |
| W3 | 2022-01 .. 2024-12 | 2025-01 .. 2026-05-08 |
| FULL | n/a | 2023-01 .. 2026-05-08 |

## 6. KPI gates (graduation)

Same as PREREG-0005/6:

| Gate | Threshold | Window |
|---|---|---|
| **G1** Alpha | ≥ +1.5% pa | FULL |
| **G2** Hit-month | ≥ 55% | FULL |
| **G3** Max DD | ≥ -25% | FULL |
| **G4** Window stability | alpha > 0 in ALL of W1/W2/W3 | per-window |
| **G5** Primary rank | V1 rank ≤ 3 of 5 | per-window |
| **G6** Sharpe | ≥ 0.6 | FULL |

Benchmark: equal-weighted 108-ticker eligible universe.

## 7. Decision branches

| Branch | V1 outcome | Action |
|---|---|---|
| A | All 6 gates pass | **Graduate V1 to paper-trade.** Write ADR-0009 (first alpha discovery). |
| B | G1 + G3 + G6 pass; G4 borderline | Surface; consider V2/V3 alternates. ADR-0009 with conditional approval. |
| C | G1 passes but G4 fails (one negative window) | Reject V1; check V5 (with ΔGPA screen). If V5 passes G1+G4 → graduate V5. |
| D | G1 fails on V1 but passes on any other variant | If V2/V3/V4/V5 passes all gates → graduate that variant. |
| E | No variant passes G1 | **A-FF01 standalone REJECTED. DART-fundamentals class declared dead.** Pivot to alternative data (sentiment/news/A6 forward-collected investor flow). Write ADR-0009 (negative). |

## 8. Multiple-comparisons accounting

This PREREG declares **5 variants × 4 windows = 20 cells**.
Cumulative pre-registered cells PREREG-0001..0007: 132 + 20 =
**152 cells**.

This is the **last pre-registered DART-fundamentals test in
Phase 0**. If A-FF01 fails, methodology pivots, not parameter
re-tuning.

## 9. Ex-ante predictions

If A-FF01 *works*:
- W1 alpha: between A-F01 (-33%) and A-F03 (+10%) → expect roughly -10% (still negative but much shallower than B/M alone)
- W2 alpha: ≈ +5% (average of +11% and 0%)
- W3 alpha: between A-F01 (+12%) and A-F03 (-28%) → expect ≈ -8% to 0%
- FULL alpha: weighted average of windows ≈ small positive (1-3%) if cyclicality argument holds

If V1 fails but V2 (BM-tilted) passes, this implies KR Value-up
2024-26 dominates the sample — flag in ADR but do not re-tune.
If V3 (GPA-tilted) passes instead, this implies the 2023 quality
defense was structurally important — flag and proceed.

## 10. Failure modes (negative results to acknowledge)

If A-FF01 fails:
- Linear combination is too crude — rank-sum loses information
  vs. proper factor model (Bayesian shrinkage or risk-adjusted
  weights). NOT a route for re-tuning; document and abandon
  DART-fundamentals.
- 3-year sample insufficient for FF-style tests (US literature
  uses 30y+).
- KR market microstructure differs from US (chaebol cross-holding,
  policy intervention) — academic factor models may not transfer
  cleanly. Acknowledged a priori; not surprising if true.

## 11. Implementation notes

- Reuses panels: `close`, `bm` (from F01 logic), `gpa`, `dgpa`
  (from F03 logic). No new data fetch required.
- New file: `research/a_ff01_multifactor/exp_walkforward_ff01.py`
- Both BM and GPA must be non-null for a ticker to be eligible
  in the rank-sum at any given date.
- Tie-breaking: alphabetical by ticker.

## 12. Known limitations

- Same constant-shares (B/M) and annual-only (GP/A) caveats from
  PREREG-0005/6 carry over.
- 108-ticker effective universe is smaller than 136 starting set.
- Equal-weight rank construction does not account for factor
  volatility differences. Acceptable for alpha discovery; refine
  if alive.
