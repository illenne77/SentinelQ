# ADR-0007: A-F01 Book-to-Market — Standalone Value factor fails KPI gates

**Status**: Decided
**Date**: 2026-05-09
**Linked**: [PREREG-0005](../preregistration/PREREG-0005-a-f01-book-to-market.md), [ADR-0006](ADR-0006-a2-failure-phase0-stalled.md)

---

## Context

A-F01 (long-only top-quintile B/M, monthly rebalance) is the first
DART-fundamentals hypothesis tested in this project, following the
death of price-volume alphas (A2/A3/A4 — see ADR-0001..0006). Five
variants × four windows (20 cells) were pre-registered in
PREREG-0005 with KPI gates G1–G6.

## Result

All 5 variants fail KPI G1 (alpha_ann ≥ +1.5%) on the FULL test
window 2023-01 .. 2026-05-08:

| Variant | FULL alpha_ann | W1 (2023) | W2 (2024) | W3 (2025-26) | Pass? |
|---|---:|---:|---:|---:|---|
| V1 (top quintile, monthly) | **-3.60%** | -33.1% | +11.3% | +11.9% | FAIL |
| V2 (top decile, monthly) | -5.96% | -39.7% | +12.1% | +12.0% | FAIL |
| V3 (top quintile, quarterly) | -2.67% | -39.2% | +0.6% | +5.2% | FAIL |
| V4 (V1 + ROE>0 quality) | -10.28% | -33.2% | -6.3% | +12.5% | FAIL |
| V5 (V1 + -10% stop) | -14.39% | -34.3% | -2.1% | -6.5% | FAIL |

KPI gate roll-up (V1, primary): G1=FAIL G2=FAIL G3=PASS G4=FAIL
G5=PASS G6=PASS. Sharpe is healthy (1.40 FULL) but driven by
benchmark beta, not alpha.

## Diagnosis

1. **2023 was a value-disaster year in KR equity**. Top-quintile B/M
   names (mostly cheap chaebol holdings, traditional manufacturers,
   utilities) lost ~33% relative to a universe dominated by AI/EV
   thematic winners (SK Hynix, Hanwha Aerospace, Doosan Robotics,
   etc.). A single-year wipeout of this magnitude is not recoverable
   by 2024+ Value-up tailwinds in a 3-year sample.

2. **W2/W3 alpha is real but bounded**. The +11–12% per-year alpha
   in 2024 and 2025-26 confirms the Value-up policy thesis, but
   cannot offset the 2023 hole within FULL.

3. **Quality screen V4 makes things worse, not better**. The
   trailing-4Q equity-growth screen is too coarse a quality proxy
   and excludes legitimate cyclical recovery names. Real ROE/GP/A
   screens (A-F03) may differ.

4. **Stop-loss V5 is catastrophic**. -10% per-name stop in a
   value basket churns through cost on every drawdown. Value
   investing requires drawdown tolerance; stops are mechanically
   incompatible.

## Decision

**A-F01 standalone is REJECTED for paper-trading graduation**, per
PREREG-0005 §8 Branch D.

**Do not reformulate or re-tune A-F01.** Re-fitting variants would
violate pre-registration discipline.

**Next**: Proceed to **A-F03 (Gross Profitability / Assets)** as the
next orthogonal fundamentals factor. Quality (Novy-Marx 2013) is
empirically uncorrelated with value and historically positive in
KR. PREREG-0006 will register A-F03 before any data analysis.

If A-F03 also fails standalone, multi-factor combination
(value+quality+momentum) will be tested as **A-FF01 FF5-style**,
also pre-registered, before declaring DART-fundamentals class dead.

## Consequences

- A-F01 dead. Cumulative dead alphas in Phase 0: A2, A3, A4 (raw),
  A4+A7 regime, A3 vol-compression, broadened A4/A3, A-F01.
- The 7+ failure pattern strongly suggests that **single-factor
  alphas in a 136-ticker KR universe with 3y test sample do not
  survive cost+universe-shock**. This is a methodology constraint,
  not a death-knell — it merely says factor *combinations* and
  *longer samples* are required.
- DART-fundamentals data infrastructure (`equity_quarterly.parquet`,
  `dart_equity_backfill.py`) is now reusable for A-F03/F04/FF01.
  Investment recovered.
- Phase 1 Portfolio/Risk/Walkforward modules executed cleanly under
  real strategy load; ready for Phase 2 abstractions.

## Limitations acknowledged in this result

1. Constant-shares-from-2026 approximation may bias B/M ranks for
   tickers with material 2020–25 buybacks/issuance (PREREG-0005 §13).
   Magnitude likely small for cross-sectional rank.
2. Universe (136 tickers) is selected with current 2026 membership
   filter — mild forward bias. Survivorship corrected universe is a
   follow-up task before any FF5 declaration.
3. Benchmark = equal-weighted universe. KOSPI200 actual TR
   benchmark may shift alpha by ±2% but unlikely to flip Branch
   D outcome given W1's -33% magnitude.

## References

- PREREG-0005 — frozen variant grid and KPI gates
- `research/a_f01_value/exp_walkforward_f01.py` — backtest engine
- `research/a_f01_value/walkforward_f01_results.txt` — full results
- Fama & French (1992); Korean Value-up Program 2024; Novy-Marx (2013)
