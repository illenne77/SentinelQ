# PREREG-0001: A4 Liquidity Surge — Multi-Year Validation Pre-Registration

**Status**: Active
**Created**: 2026-05-08
**Author**: SentinelQ research
**Hypothesis**: A4 (Liquidity Surge) per plan v2.2 §6, §7.3
**Linked ADR**: [ADR-0001](../adr/ADR-0001-a4-exit-ladder-mismatch.md)

---

## 1. Why pre-register?

To date 16+ parameter variants have been tested on a single 1.4y window without
Bonferroni correction. Continuing to sweep without locking the search surface
in advance would make any "win" un-falsifiable (Texas-sharpshooter fallacy).

This document **freezes** the variants, KPI thresholds, and decision rules we
will use for the upcoming multi-year + bear-market + cross-hypothesis work.
Anything tested **outside** this list must be added as an amendment **before**
its result is computed, with rationale.

---

## 2. Frozen primary variant

The single primary candidate going into 5y validation:

| Parameter | Value |
|---|---|
| Stop type | ATR(14) × k |
| k | 2.5 |
| TP1 | +7% (50% of position) |
| TP2 | +15% (30% of position) |
| Trailing | -3.0% on remaining 20%, armed after TP1 |
| Time exit | horizon = 5 trading days |
| Entry | trigger close |
| Surge threshold | volume_ratio ≥ 1.5× SMA(20) |
| Universe | KOSPI200 PIT (constituents-as-of) |
| Cost | DEFAULT round-trip 31bp |

Rationale: best balance of hit-rate (58.2%) and stop-out (11.4%) on the
2025-01..2026-05 window in `exp_atr_sweep.py`; passed walk-forward OOS test
(`exp_walkforward.py`) on 2026-Q1 split.

## 3. Frozen secondary variants (allowed comparators)

Only these 6 variants may be reported alongside the primary. No others.

1. baseline fixed -2% / +3/+5  (negative control)
2. ATR k=1.5 / +3/+5
3. ATR k=2.0 / +5/+10
4. ATR k=2.0 / +7/+15
5. ATR k=2.0 / +10/+20
6. ATR k=2.5 / +5/+10

Same TP/trail/horizon ratios as the primary.

## 4. KPI pass criteria (per plan v2.2 §7.3)

A4 is declared **graduated to Phase 0 → Phase 1** iff **all** of the following
hold on the 5y survivorship-corrected dataset:

| KPI | Threshold | Source |
|---|---|---|
| Hit rate (net) | ≥ 58% | plan §7.3 |
| Mean return (net) | ≥ +1.20% / trade | plan §7.3 |
| Max drawdown (cumulative net) | ≤ 15% | plan §7.4.1 |
| Walk-forward stability | top variant rank stable across ≥3 disjoint test windows | this prereg |
| Bear-regime survival | net mean ≥ 0 in every full bear sub-window | this prereg |

A bear sub-window is any contiguous ≥2 month period where KOSPI200 returned ≤ -8%
peak-to-trough. Identified ex-ante from index data, not from A4 returns.

## 5. Frozen test sub-windows (5y backfill)

Once 5y data lands, the following walk-forward splits are computed:

| Window | Train | Test | Regime |
|---|---|---|---|
| W1 | 2021-01..2022-06 | 2022-07..2023-06 | bear (2022 drawdown in test) |
| W2 | 2022-01..2023-12 | 2024-01..2024-12 | mixed |
| W3 | 2023-01..2024-12 | 2025-01..2026-05 | bull-tilted |

Plus a **single full-period** evaluation (2021-01..2026-05) with KPIs reported.

Sub-windows beyond these three may NOT be reported as primary evidence.
Exploratory deeper splits are allowed but must be flagged as such in any
write-up and excluded from graduation calculus.

## 6. Frozen synthetic-shock scenarios (bear-stress test)

For (4) synthetic-shock validation prior to 5y data landing:

| ID | Scenario | How |
|---|---|---|
| S1 | 2022-replay | Re-scale 2025-01..2026-05 daily returns to the empirical 2022 KOSPI200 monthly mean/vol (historical) |
| S2 | -10% gap shock | Inject one -10% gap-down day at random within each held position; report worst-case |
| S3 | Vol-doubling | Multiply daily ATR by 2× system-wide; re-run exit ladder |

A4 must survive S1 (net mean ≥ 0) and degrade gracefully under S2/S3 (no
catastrophic stop-out chain). Pass criteria recorded but not used as primary
KPI.

## 7. Frozen secondary hypotheses (for future cross-validation)

If A4 graduates, the following pair-candidates are pre-listed for future
meta-filter design (per plan §6 alpha pairing principle). No other
hypotheses to be backtested in this stream without amending this prereg:

| ID | Description | Expected role |
|---|---|---|
| A7 | Foreign net-buying spike | Conviction filter for A4 |
| A2 | Earnings post-announcement drift | Independent alpha (low correlation) |
| A9 | Disclosure surprise | Event filter |

## 8. Multiple-testing budget

Total **primary** comparisons going forward = 7 variants × 4 windows × 2 entry
modes = **at most 56**. Bonferroni-adjusted α for any single claim = 0.05/56 ≈
0.0009. Any "significant" finding must clear this bar.

Exploratory results may be presented but flagged "EXPLORATORY — NOT GATING".

## 9. Amendment rules

Changes to sections 2, 3, 4, 5, 6, 7, 8 require:
1. New section 11 entry: date + reason + diff
2. Commit before any result that would benefit from the amendment
3. Amendment timestamps must precede measurement timestamps in git history

## 10. Open data dependencies (block primary work until resolved)

| Dep | Source | Status |
|---|---|---|
| KOSPI200 historical PIT constituents (2021-01..) | KIS or KRX OTP scraper | not started |
| Daily OHLCV with delisted names | KIS `inquire-daily-itemchartprice` (FHKST03010100) | API connection not started |
| Index-level KOSPI200 daily | KIS or pykrx | partial |

## 11. Amendments

(none yet)

---

**This document is the authoritative search-surface declaration for A4
multi-year validation. Any deviation must be recorded as an amendment.**
