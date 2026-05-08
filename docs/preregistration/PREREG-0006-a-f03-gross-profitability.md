# PREREG-0006: A-F03 Gross Profitability / Assets (KR equity)

**Status**: Frozen
**Date**: 2026-05-09
**Authors**: SentinelQ research
**Linked**: [ADR-0007](../adr/ADR-0007-a-f01-book-to-market-result.md) (A-F01 dead),
[Novy-Marx 2013](https://rnm.simon.rochester.edu/research/OSoV.pdf),
`research/oss_review/alpha_catalog.md` §A-F03

---

## 1. Hypothesis

KR equities with higher **gross profitability** (gross profit /
total assets) outperform those with lower GP/A on a 1-3 month
rebalance horizon.

Novy-Marx (2013) showed in US data that GP/A is **the cleanest
quality measure**: it captures economic productivity before the
distortions of accounting earnings (depreciation, taxes, special
items). Empirically nearly orthogonal to value (B/M).

This is **information-source orthogonal** to A-F01 (value) and
A2/A3/A4 (price-volume). A-F03 uses **income statement +
balance sheet** input — the second class of DART-fundamental
signal tested.

---

## 2. Universe

Same 136-ticker universe as PREREG-0005, after joining with DART
fiscal-year coverage and filtering tickers with at least 4 annual
reports. Financial holding companies and insurers excluded by
construction (different IFRS revenue/COGS treatment).

Universe is *frozen by this PREREG*. Any broadening requires an
amendment ADR.

---

## 3. Signal definition

Notation: at rebalance date `t`, for ticker `i`, with `y` = the
most recent fiscal year for which the annual report has
`available_from ≤ t`:

```
GP_i,y     = ifrs-full_GrossProfit (annual, KRW)              (or
              Revenue - CostOfSales fallback if GP missing)
Assets_i,y = ifrs-full_Assets (annual balance, KRW)
GPA_i,t    = GP_i,y / Assets_i,y
```

**Cross-sectional rank** of `GPA_i,t` across the eligible universe
descending. Top quintile = buy candidates.

Annual-only GP is preferred over TTM in this PREREG to avoid the
quarterly cumulative-vs-period accounting trap. Reporting lag
assumed 90 calendar days (Annual filing window per K-IFRS).

---

## 4. Variants (5 cells, frozen)

| ID | Picks | Rebal | Quality screen | Notes |
|---|---|---|---|---|
| **V1 (PRIMARY)** | top quintile | monthly (1st td) | none | Pure GP/A |
| V2 | top decile | monthly | none | More concentrated |
| V3 | top quintile | quarterly | none | Slow rebalance |
| V4 | top quintile | monthly | also B/M ≥ universe median (combine value+quality) | hybrid alpha |
| V5 | top quintile | monthly | also positive ΔGP/A YoY | momentum-improving |

V1 is the **PREREG primary** for stability ranking.

Position sizing: equal-weight 1/N. Cash earns 0%. No leverage,
no shorts, no per-name stops.

V4 is intentionally a value+quality hybrid — it tests whether
combining the two failed/test-pending factors creates positive
alpha even if neither standalone passes.

---

## 5. Costs

Round-trip 0.30% — same convention as PREREG-0001/0004/0005.

---

## 6. Walk-forward windows

Identical to PREREG-0005:

| Window | Train | Test |
|---|---|---|
| W1 | 2020-01 .. 2022-12 | 2023-01 .. 2023-12 |
| W2 | 2021-01 .. 2023-12 | 2024-01 .. 2024-12 |
| W3 | 2022-01 .. 2024-12 | 2025-01 .. 2026-05-08 |
| FULL | n/a | 2023-01 .. 2026-05-08 |

DART annual data 2019-2024 backfill enables point-in-time signal
at every rebalance date in test windows.

---

## 7. KPI gates (graduation)

Identical to PREREG-0005:

| Gate | Threshold | Window |
|---|---|---|
| **G1** Alpha vs benchmark | ≥ +1.5% annualised | FULL |
| **G2** Hit-month | ≥ 55% positive-alpha months | FULL |
| **G3** Max DD | ≥ -25% | FULL |
| **G4** Window stability | alpha > 0 in ALL of W1/W2/W3 | per-window |
| **G5** Primary rank | V1 rank ≤ 3 of 5 by alpha | per-window |
| **G6** Sharpe | ≥ 0.6 | FULL |

Benchmark: equal-weighted universe (consistent with PREREG-0005
methodology). KOSPI200 reported as honesty check only.

---

## 8. Decision branches

| Branch | V1 PASS? | Action |
|---|---|---|
| A | All 6 gates | Graduate V1 to paper-trade. Write ADR-0008 (alpha discovery success). |
| B | G1-G3 + G6 pass; G4-G5 borderline | Surface; consider V2/V3 as alternates if they pass cleanly. |
| C | G1 alpha passes but inconsistent windows | Reject V1; check V4 hybrid. |
| D | No standalone variant passes G1, but V4 passes | Graduate V4 (value+quality hybrid). Write ADR-0008. |
| E | No variant passes G1 | A-F03 dead standalone. Proceed to A-FF01 (FF5 multi-factor) before declaring DART-fundamentals class dead. |

---

## 9. Multiple-comparisons accounting

This PREREG declares **5 variants × 4 windows = 20 cells**.
Cumulative pre-registered cells PREREG-0001..0006: 112 + 20 =
**132 cells**.

---

## 10. Ex-ante predictions

If A-F03 *works* in KR 2023-26:
- Top-quintile GP/A names will overweight IT/HW (high-margin
  semis, software) and pharma (high gross margin biotech).
- V4 hybrid (value+quality) should beat V1 — combining
  cheap+productive is the canonical Buffett-Graham play.
- V5 (improving GP/A) should be similar to V1 in steady state but
  pivot more during regime shifts.

If V1 alpha is positive but small (<1.5%), V4 hybrid is the most
likely path to graduation.

---

## 11. Failure modes (negative results to acknowledge)

If A-F03 fails:
- **GP/A rewards capital-light businesses too uniformly** — the
  KR universe is dominated by capital-intensive chaebols
  (semis, autos, steel, chem); high-GP/A names may be a small
  thematic basket (services, software) that suffers under any
  rate-rise regime.
- **Annual-only signal is too slow** for KR macro cycles.
- **Sample too short**: 3y test against a factor that mature
  US literature uses 30y+ samples for.

---

## 12. Implementation notes

- Backtest engine: reuse `research/a_f01_value/exp_walkforward_f01.py`
  pattern. New file: `research/a_f03_quality/exp_walkforward_f03.py`.
- Data fetcher: extend `scripts/dart_equity_backfill.py` pattern
  to a new `scripts/dart_income_assets_backfill.py` that pulls
  annual-only GP/Revenue/CostOfSales/Assets per ticker × year.
- Cache: `data/cache/dart/income_assets_annual.parquet`.
- Reproducibility: ranking ties broken alphabetically.

---

## 13. Known limitations

- **Annual-only signal** lags up to 15 months at the latest
  rebalance date (Annual report for FY ends 12-31, available
  ~3-31 of following year, used until 3-31 of year after).
  Acceptable for quality factors which are slow-moving.
- **Universe survivorship**: same caveat as PREREG-0005 §13.
  Mild forward bias.
- **Income statement of holding companies** may report
  "consolidated revenue" that double-counts intra-group
  transactions; partially addressed by financial-sector
  exclusion but residual noise remains.
- **No TTM**: a more refined version would use trailing-4-quarter
  GP, but quarterly cumulative-vs-period is error-prone.
  Future amendment if A-F03 is alive.
