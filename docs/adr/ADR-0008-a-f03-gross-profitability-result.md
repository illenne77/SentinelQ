# ADR-0008: A-F03 Gross Profitability — Standalone fails, but factor-cyclicality vs A-F01 motivates multi-factor

**Status**: Decided
**Date**: 2026-05-09
**Linked**: [PREREG-0006](../preregistration/PREREG-0006-a-f03-gross-profitability.md), [ADR-0007](ADR-0007-a-f01-book-to-market-result.md)

---

## Context

A-F03 (long-only top-quintile GP/A, Novy-Marx 2013) is the second
DART-fundamentals hypothesis tested. Five variants × four windows
(20 cells) pre-registered in PREREG-0006.

## Result

All 5 variants fail the full gate roll-up. V5 (positive ΔGP/A
screen) is the only variant that passes G1 alpha threshold, but
fails G2 hit-month and G4 window stability.

| Variant | FULL alpha | W1 (2023) | W2 (2024) | W3 (2025-26) | Gates |
|---|---:|---:|---:|---:|---|
| V1 (top quintile, monthly) | -6.69% | +9.7% | -0.1% | -28.0% | FAIL |
| V2 (top decile, monthly) | -15.05% | +19.0% | +3.9% | -60.9% | FAIL |
| V3 (quarterly) | -3.65% | +2.8% | +4.5% | -27.9% | FAIL |
| V4 (value+quality hybrid) | -14.05% | -1.0% | -13.8% | -23.3% | FAIL |
| V5 (ΔGP/A>0 screen) | **+3.46%** | +16.4% | +5.9% | -11.1% | G1 only |

## Diagnosis: A-F03 vs A-F01 are nearly mirror images

| Window | A-F01 V1 alpha | A-F03 V1 alpha | Interpretation |
|---|---:|---:|---|
| W1 (2023) | -33.1% | **+9.7%** | AI/EV theme — Quality defensive, Value crushed |
| W2 (2024) | +11.3% | -0.1% | Value-up policy launch — Value reflates, Quality flat |
| W3 (2025-26) | +11.9% | **-28.0%** | Value-up momentum continues — Value wins, Quality loses |

This is **textbook factor cyclicality**: Quality and Value are not
co-monotonic; they trade leadership across regimes. Fama-French
multi-factor models exploit exactly this — the *combination* is
more stable than either alone.

The W4 hybrid (intersection of high B/M ∩ high GP/A) failed
because intersection narrows the basket and amplifies *both*
factors' losses in their unfavorable regime. Linear combination
(rank-sum) is the correct construction, not intersection.

## Decision

**A-F03 standalone is REJECTED**, per PREREG-0006 §8 Branch E.
**A-F01 + A-F03 hybrid via rank-sum (composite Value+Quality
score) is the next test**, registered as A-FF01 in PREREG-0007.

The cyclicality data is itself the most informative finding of
this session — it justifies multi-factor combination on a priori
grounds rather than as an empirical fishing expedition.

**No reformulation of A-F03**. V5 (ΔGP/A>0 screen) passing G1
alone is statistically weak (1 of 5 cells; multiple-comparisons
overhead 132 cells in family-wise budget) and not pursued
standalone.

## Consequences

- A-F03 dead standalone. Cumulative dead alphas in Phase 0:
  A2, A3, A4 raw, A4+A7 regime, A3 vol-compression, broadened
  A4/A3, A-F01, A-F03 (8 alphas).
- The mirror-image regime pattern is a positive finding — it
  proves the two factors are non-redundant and that combination
  has a real chance.
- DART-fundamentals data infrastructure further validated:
  `income_assets_annual.parquet` reusable for A-FF01 and any
  future profitability/quality work.
- If A-FF01 also fails, that closes the DART-fundamentals chapter
  and forces a pivot to **alternative-data alphas** (news
  sentiment, ESG, options-flow proxy via investor flow once A6
  daemon collects 6 months of data).

## Limitations acknowledged

1. Annual-only signal — TTM (4Q rolling) version not tested.
   Acceptable for slow-moving Quality factor; revisit if A-FF01
   shows promise.
2. 119/136 ticker DART coverage — small caps and recently-listed
   names underrepresented. Material for headline GP/A but not
   for cross-sectional rank.
3. 2026 partial year (~5 months of W3 test data) — large W3
   number is the most impactful in FULL but smallest sample.

## References

- PREREG-0006 — frozen variant grid and KPI gates
- `research/a_f03_quality/exp_walkforward_f03.py` — backtest
- `research/a_f03_quality/walkforward_f03_results.txt` — full table
- `data/cache/dart/income_assets_annual.parquet` — 658 rows, 119 tickers
- Novy-Marx (2013) "The Other Side of Value"; Fama-French (1993, 2015)
