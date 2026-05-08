# ADR-0002: A4 (Liquidity Surge) — 5y Walk-Forward Failure

**Status**: Accepted
**Date**: 2026-05-08
**Decision-makers**: SentinelQ research
**Supersedes resolution claim in**: [ADR-0001](ADR-0001-a4-exit-ladder-mismatch.md) §"ATR Resolution"
**Linked**: [PREREG-0001](../preregistration/PREREG-0001-a4-multiyear-validation.md)

---

## Summary

A4 (Liquidity Surge) hypothesis as currently formulated **fails** the
PREREG-0001 §4 graduation criteria when validated against a 5.4-year
survivorship-corrected dataset (2021-01-01 .. 2026-05-08, KIS-backed).

The earlier "ATR resolution" claim recorded in ADR-0001 was a
**regime-selection artifact**: it was based on a single 1.4-year window
(2025-01..2026-05) that happened to be uniformly bull-trending. Across
multi-regime windows including the 2022 bear market, A4 produces
near-zero or negative net returns and never achieves the 58% hit-rate KPI.

**The hypothesis is hereby declared not-viable for Phase 0 graduation in
its current form.**

---

## Context

PREREG-0001 (committed before any 5y measurement) froze:
- 7 candidate variants (1 primary, 6 secondary)
- 3 disjoint walk-forward windows (W1/W2/W3)
- KPI thresholds per plan v2.2 §7.3 (hit ≥ 58%, mean ≥ +1.2%, MaxDD ≤ 15%)
- Bonferroni-adjusted significance budget

5y data was backfilled via the new `api/kis_chart.py` client over
KOSPI top-80 (today + delisted union; partial survivorship correction
acknowledged). Run via `research/a4_liquidity_surge/exp_walkforward_5y.py`.

## Evidence

### Primary variant (ATR k=2.5 / TP +7/+15 / trail -3%) test-side results

| Window | Period | n | Net mean | Hit rate | KPI |
|---|---|---:|---:|---:|---|
| W1 | 2022-07..2023-06 (bear) | 1214 | **-0.16%** | 45.96% | hit FAIL, mean FAIL |
| W2 | 2024-01..2024-12 (mixed) | 1398 | **-0.28%** | 47.00% | hit FAIL, mean FAIL |
| W3 | 2025-01..2026-05 (bull) | 2125 | +0.87% | 56.99% | hit FAIL (1pp), mean FAIL |
| FULL | 2021-01..2026-05 | 7326 | +0.06% | 48.92% | hit FAIL, mean FAIL |

### Across all 7×4 = 28 cells (test sides + full)

- Cells passing **hit ≥ 58%** KPI: **0/28**
- Cells passing **mean ≥ +1.2%** KPI: **0/28**
- Cells with positive net mean: **8/28** (all in W3 test or full-period for
  high-TP-ladder variants — driven by 2025-26 bull window)

### Walk-forward rank stability (PREREG §4)

| Window | Top-1 variant on test | Prereg primary rank |
|---|---|---:|
| W1 | ATR k=2.0 / +10/+20 | 3 |
| W2 | ATR k=2.0 / +10/+20 | 6 |
| W3 | ATR k=2.0 / +10/+20 | 2 |

Prereg primary ranks `[3, 6, 2]` → exceeds the ≤3 stability threshold. **FAIL.**

Note: even the consistent top-1 (ATR k=2.0 / +10/+20) does not pass either
hit or mean KPIs on its 3 test windows. There is **no** variant in the
prereg search surface that graduates.

## Diagnosis

**Why the 1.4y window misled us**:

1. 2025-01..2026-05 was a single-regime bull market for KOSPI mega-caps
   (semiconductor/AI rally). Volume-surge + price-up signals during a
   sustained uptrend trivially deliver positive forward returns.
2. ATR-adaptive stops widen in volatile names — exactly the names that
   participated in the bull rally — preserving right-tail wins.
3. n ≈ 2000 in a single regime created high statistical confidence in a
   regime-conditional truth that does not generalise.

**What the 5y data shows**:

1. In bear/mixed regimes, surge_ratio ≥ 1.5 with close > prev_close is
   **not** predictive of forward returns — hit rates collapse to 44-50%.
2. The information value of the volume surge signal vanishes when
   directional drift is absent or negative. A4 has no edge in
   volatility-driven (non-trend) volume spikes.
3. Stop-out rates remain reasonable (10-25% with ATR), but the un-stopped
   trades break even on average rather than producing the right-tail
   payoff seen in the bull window.

**The earlier mistake (root cause for retrospect)**:
- Insufficient regime diversity in the validation window
- Walk-forward done on a homogeneous regime is approximately no
  walk-forward at all
- We discovered this **only** because PREREG-0001 forced us to declare
  the search surface in advance and run multi-regime windows

This is a procedural success of the PREREG mechanism, despite the
unfavourable hypothesis result.

## Decision

1. **A4 (Liquidity Surge) — current formulation — is not promoted to Phase 0.**
   The hypothesis as defined in plan v2.2 §6/§7.3 (volume surge ≥ 1.5×
   SMA(20) + close-up + ATR exit ladder) does not meet adoption gates on
   5y data.

2. **Future paths for A4** (any one of these is a NEW research stream
   requiring its own pre-registration):

   a. **Bull-conditional A4**: gate the signal on broad-market
      regime classifier (e.g., KOSPI200 above 200d SMA). Effectively
      restrict A4 to strong-up regimes where it does work. Honest
      reformulation; needs new prereg.

   b. **Signal redesign**: replace volume-ratio with dollar-volume
      z-score, multi-day surge confirmation, or order-flow features.
      Substantively different hypothesis, not an A4 variant.

   c. **Pair filter only**: use A4 as a regime tag *for* another alpha
      (e.g., gate A2/A7 on A4-positive). Dependent role, not standalone.

3. **Current research stream pivots to A7** (Foreign Net-Buying Spike)
   per plan §6 and PREREG-0001 §7. A7 will receive its own prereg
   document before any backtesting begins.

4. **DD calculation bug fixed** in `exp_walkforward_5y.py`
   (`_max_drawdown_fixed_sized`): assumes equal fixed-dollar sizing per
   trade, computes additive cumulative P&L, reports avg loss per trade
   during worst drawdown. The previous cumulative-product DD was
   misleading for overlapping fixed-size trades and is removed.

## Consequences

**Positive**:
- Procedural validation of PREREG/ADR workflow caught a regime-bias
  failure that would have killed the strategy in production
- Multiple-testing budget (PREREG §8) was respected; no p-hacking
- 5y dataset and KIS chart pipeline are now reusable for A7 and beyond
- Documentation of "what doesn't work" is itself research output

**Negative**:
- ~5 sessions of work invested in A4 yields no tradeable alpha
- Phase 0 timeline shifts: A7 stream starts from zero
- KOSPI200 PIT gap remains (still using top-80 + small delisted union)

**Neutral**:
- ADR-0001 stands as a record of the exit-ladder mismatch finding (still
  valid: forward-return is not a sufficient KPI proxy). Its "Resolution"
  section is now superseded by this ADR; that section is updated with a
  pointer to ADR-0002 rather than rewritten, to preserve research history.

## Bias Checklist (final, A4 stream)

| Check | Status | Note |
|---|:---:|---|
| Lookahead | ✓ | `closed="left"` rolling |
| Survivorship | ⚠️ | Today's KOSPI top-80 + 0 delistings; partial only |
| Data leakage | ✓ | Forward returns separated |
| Hindsight | ✓ | PREREG-0001 froze surface before 5y measurement |
| Selection | ⚠️ | Universe expanded mid-research (acknowledged in ADR-0001) |
| Multiple-testing | ✓ | Within Bonferroni budget per PREREG §8 |
| LLM determinism | n/a | |
| Cost-net | ✓ | All KPIs net of 31bp |
| OOS walk-forward | ✓ (FAIL) | 3 disjoint windows, all sides recorded |
| Regime diversity | ✓ | 2022 bear + 2024 mixed + 2025 bull |

## References

- Plan v2.2 §6, §7.3, §7.4.2, §7.5, §8.0
- PREREG-0001 (multi-year validation pre-registration)
- ADR-0001 (exit-ladder mismatch finding; ATR-resolution section now
  superseded)
- Code:
  - `api/kis_client.py`, `api/kis_chart.py` — 5y data pipeline
  - `scripts/kis_backfill_5y.py` — backfill orchestrator
  - `research/a4_liquidity_surge/data_loader_kis.py`
  - `research/a4_liquidity_surge/exp_walkforward_5y.py`
  - `research/a4_liquidity_surge/walkforward_5y_results.txt` — full output
- Data cache: `data/cache/kis_daily/*.parquet` (79 tickers × ~1558 bars)

## Amendment history

(none yet)
