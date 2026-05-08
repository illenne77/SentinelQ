# PREREG-0005: A-F01 Book-to-Market Value (KR equity)

**Status**: Frozen
**Date**: 2026-05-09
**Authors**: SentinelQ research
**Linked**: [ADR-0006](../adr/ADR-0006-a2-failure-phase0-stalled.md) (Z-path: pivot to fundamentals), `research/oss_review/alpha_catalog.md` §A-F01

---

## 1. Hypothesis

KR equities with **higher book-to-market** ratios (cheaper on book value)
outperform those with lower B/M, on a 1-3 month rebalance horizon.

This is the canonical Fama-French (1992, 1993) HML factor. KR-specific
literature (Kim & Kim 2003) reports a ~3–6% pa raw spread on KOSPI before
costs in pre-2010 data. Post-2024 the Korean government's
**"Corporate Value-up Program"** explicitly targets low-PBR firms,
creating policy-supported re-rating tailwind.

This is **information-source orthogonal** to A2/A3/A4: those alphas used
price-volume only (all dead). A-F01 uses **balance-sheet** input (DART
quarterly equity) — a class of signal not yet tested in this project.

---

## 2. Universe

136-ticker universe inherited from PREREG-0004 (KOSPI top-80 + KOSDAQ
mid-caps). After joining with DART corp-code map and filtering to
tickers with at least 16 quarters of consolidated-statement coverage:
**~110 tickers** (financial holding companies and insurers are
mechanically excluded — they file under different IFRS codes; this
matches the academic convention of excluding financials from value
factor studies).

The exact tradable universe at each rebalance date is computed
dynamically as the intersection of:
- ticker has DART quarterly 지배기업 소유주지분 within last 200 calendar days
- ticker has positive close on rebalance date
- ticker is not flagged as 관리종목 / 거래정지 (assumed available given KIS data)

Universe is *frozen by this PREREG*. Any broadening requires an amendment.

---

## 3. Signal definition

Notation: at rebalance date `t`, for ticker `i`:

```
ControllingEquity_i,q  = 지배기업 소유주지분 (KRW) from latest available DART
                          quarterly report with available_from ≤ t
shares_i               = current shares outstanding from KIS
                          inquire-price snapshot (constant proxy; see §13)
BPS_i,t                = ControllingEquity_i,q / shares_i        (KRW)
BM_i,t                 = BPS_i,t / close_i,t                    (unitless)
```

**Cross-sectional rank** of `BM_i,t` across the eligible universe
descending. A ticker is a **buy candidate** if it falls in the
**top quintile** (top 20%) of B/M.

A ticker is a **short candidate** if it falls in the bottom quintile.
This PREREG tests **long-only** primary; long-short reported as a
secondary diagnostic (no graduation gate).

---

## 4. Variants (5 cells, frozen)

| ID | Universe | Picks | Rebal | Hold logic | Top-K filter |
|---|---|---:|---|---|---|
| **V1 (PRIMARY)** | full | top quintile (~22) | monthly (1st trading day) | rebalance to current top-quintile, no stops | none |
| V2 | full | top decile (~11) | monthly | rebalance | none |
| V3 | full | top quintile | quarterly (1st of Mar/Jun/Sep/Dec) | rebalance | none |
| V4 | full | top quintile | monthly | rebalance | quality screen: ROE > 0 (trailing 4Q net income > 0) |
| V5 | full | top quintile | monthly | rebalance with -10% per-name stop | none |

V1 is the **PREREG primary** for stability ranking.

Position sizing: equal-weight 1/N where N = current pick count. Cash
earns 0%. No leverage, no shorts. Entry next-day open. Rebal: close
positions no longer in target set, open new positions, scale existing
to target weight.

---

## 5. Costs

Same as PREREG-0001/4: round-trip 0.30% (commission 0.015% × 2 +
slippage 0.20% + tax 0.23% on sells). Applied to gross returns.

---

## 6. Walk-forward windows

Same as PREREG-0001/3/4 for direct comparability:

| Window | Train | Test |
|---|---|---|
| W1 | 2020-01 .. 2022-12 | 2023-01 .. 2023-12 |
| W2 | 2021-01 .. 2023-12 | 2024-01 .. 2024-12 |
| W3 | 2022-01 .. 2024-12 | 2025-01 .. 2026-05-08 |
| FULL | n/a | 2023-01 .. 2026-05-08 |

Train periods are unused for parameter tuning (variants are frozen
above) but reported for diagnostics.

DART data starts 2020-Q1 (5y backfill). At test-window start (2023-01)
we have at least 11 quarterly observations per ticker, sufficient for
the latest-quarter-by-date lookup.

---

## 7. KPI gates (graduation)

A variant graduates only if **all** of the following hold on the
test set:

| Gate | Threshold | Window |
|---|---|---|
| **G1 Alpha vs KOSPI200** | ≥ **+1.5%** annualised | FULL test |
| **G2 Hit-month** | ≥ **55%** months with positive alpha | FULL test |
| **G3 Max DD** | ≤ **25%** | FULL test (looser than A2 because long-only quintile basket is more diversified) |
| **G4 Window stability** | mean alpha > 0 in **all 3** of W1/W2/W3 | per-window |
| **G5 Primary rank** | V1 rank ≤ 3 of 5 in **each** of W1/W2/W3 by alpha | per-window |
| **G6 Sharpe** | ≥ **0.6** annualised | FULL test (looser than A2 because broad basket) |

KOSPI200 benchmark fall-back same as PREREG-0004 §13: equal-weighted
basket of the eligible universe (acknowledged harsher benchmark; if
V1 fails on EW basket, also reported against actual KOSPI200 from
KIS index endpoint as honesty check, but graduation is judged on
EW basket).

---

## 8. Decision branches

| Branch | V1 PASS? | Action |
|---|---|---|
| A | All 6 gates | Graduate V1 to paper-trade. Write ADR-0007 (alpha discovery success). |
| B | G1-G3 + G6 pass; G4-G5 borderline | Surface; consider V2/V3 as alternates if they pass cleanly. |
| C | G1 alpha passes but inconsistent windows | Reject V1; check V4 (quality screen) for combined value+quality. |
| D | No variant passes G1 | A-F01 dead as standalone. Reformulate as part of multi-factor (FF5) before next test. ADR records decision. |
| E | Multiple variants pass cleanly | Pick V1; note others for ensemble (separate ADR). |

---

## 9. Multiple-comparisons accounting

This PREREG declares **5 variants × 4 windows = 20 cells**. Cumulative
pre-registered cells across PREREG-0001/0002/0003/0004/0005: 92 + 20 =
**112 cells**. Family-wise discipline: any future hypothesis must be
PREREG'd before measurement.

---

## 10. Ex-ante predictions

If A-F01 *works* in KR 2023-26:
- Positive alpha concentrated in 2024+ (Value-up policy era).
- Long-short spread > long-only excess (deep-value premium).
- Quality-screened V4 should beat V1 (avoiding value traps in
  shrinking chaebol subsidiaries).
- Quarterly rebalance V3 should approximately match V1 (B/M is slow-moving).

If V4 dominates V1 by >2% alpha, that suggests value+quality is the
right combination — **flag in ADR but do not re-tune** to avoid
graduation-eligibility violation.

---

## 11. Failure modes (negative results to acknowledge)

If A-F01 fails:
- **Value trap dominance**: cheapest-quintile mostly contains shrinking
  chaebol subsidiaries with cross-holding-inflated book values.
- **Crowded trade**: post-Value-up, low-PBR names already re-rated by
  early 2025; entering 2025+ captures only the tail.
- **Measurement error from constant-shares approximation** (§13).
- **Universe survivorship**: 136 tickers selected from 2020 KOSPI200
  + KOSDAQ150 with current 2026 membership filter (mild forward bias;
  acknowledged here, not corrected — re-running on a true point-in-time
  universe is a follow-up task).

---

## 12. Implementation notes

- Backtest engine: existing `_run_v2` portfolio NAV simulator from
  `research/a2_sector_rotation/exp_walkforward_a2.py`, adapted for
  long-only quintile basket. New file:
  `research/a_f01_value/exp_walkforward_f01.py`.
- DART data source: `data/cache/dart/equity_quarterly.parquet`
  (2,315 rows, 128 tickers, 2020-2024).
- Shares snapshot: `data/cache/dart/shares_snapshot.csv` (136 rows).
- Reproducibility: seeded ranking ties broken alphabetically.

---

## 13. Known limitations

- **Constant-shares approximation**: shares outstanding is treated as
  the current snapshot (2026-05) for the entire 2020-26 period. This
  is **wrong** for tickers with material buybacks, splits, or new
  issuance. The cross-sectional rank is preserved well for tickers
  with stable share counts (the majority); error is concentrated in
  a minority. Acceptable for alpha discovery (rank-based);
  unacceptable for production. Replace with quarterly DART
  stockTotqySttus before live deployment.
- **Financials excluded**: ~12 financial holding/insurance tickers
  return only 6 quarters of `EquityAttributableToOwnersOfParent`
  under the standard CFS account ID. Excluding them is academically
  conventional for value studies and ALSO removes a confound.
- **Missing tickers**: 005387, 005935 (preferred shares with no
  separate filing). Excluded from universe.
- **Look-ahead control**: every signal at date `t` uses only DART
  reports with `available_from ≤ t` and prices `close ≤ t`. Filter
  enforced in code; verified by spot-check on Samsung 2024 reports.
