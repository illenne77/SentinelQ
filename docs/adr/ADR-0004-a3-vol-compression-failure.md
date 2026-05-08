# ADR-0004: A3 Volatility Compression Breakout — 5y Walk-Forward Failure (Branch D)

**Status**: Accepted
**Date**: 2026-05-08
**Linked**: [PREREG-0003](../preregistration/PREREG-0003-a3-volatility-compression.md), [ADR-0002](ADR-0002-a4-5y-walkforward-failure.md), [ADR-0003](ADR-0003-a4-a7-combined-failure.md)

---

## Context

After A4 raw (ADR-0002) and A4+A7 (ADR-0003) declared not-viable,
pivoted to A3 per plan v2.2 §6. PREREG-0003 froze 5 variants × 4
windows = 20 cells. A3 mechanism (compression → breakout) is
uncorrelated with A4 (spike → reversal); independent test.

## Evidence

`research/a3_vol_compression/walkforward_a3_results.txt` (committed).

**Test-side summary (V1 plan-literal)**:

| Window | n | Net mean | Hit | PF | Avg hold |
|---|---:|---:|---:|---:|---:|
| W1 (bear) | 153 | −0.12% | 36.6% | 0.91 | 4.8d |
| W2 (mixed) | 102 | −1.12% | 24.5% | **0.37** | 2.9d |
| W3 (bull) | 199 | −0.41% | 31.2% | 0.76 | 3.2d |
| FULL | 778 | −0.69% | 28.1% | 0.59 | 3.7d |

PREREG-0003 §6 KPI: PF ≥ 1.6, hit ≥ 50%, net ≥ +1.20%. **Zero cells
pass; max PF observed across all 20 cells is 0.93.**

| Variant | KPI passes / 4 windows | Best PF | Verdict |
|---|---|---|---|
| V1 plan literal | 0/4 | 0.91 | FAIL |
| V2 tight compression | 0/4 | 0.93 | FAIL |
| V3 tight volume | 0/4 | 0.76 | FAIL |
| V4 longer base 40d | 0/4 | 0.65 | FAIL |
| V5 no SMA20 exit | 0/4 | 0.91 | FAIL |

PREREG-0003 §10 binding outcome: **Branch D — kill A3 stream.**
(V1 and V2 max PF = 0.93 < 1.3 floor.)

## Diagnosis

The 5y data shows breakouts on KOSPI top-80 fail-fast: avg holding
period ≤ 5 days, hit rate 24–37%, stop-out dominant. This is opposite
to what compression-breakout literature predicts.

Three plausible structural causes:

1. **Universe artifact**: KOSPI top-80 mega-caps are foreign-trading
   dominated; intraday breakouts get faded by program/algo flow before
   trends form. The classic compression-breakout literature is built
   on US small/mid caps where signal-to-noise is higher.

2. **Overnight gap dominance**: KR market opens with pent-up reaction
   to US session; mega-cap breakouts on day t often gap-down on day t+1
   regardless of intraday volume confirmation. Daily-bar testing can't
   capture this without explicit gap-fade modeling.

3. **SMA20 exit is too tight for fresh breakouts**: V5 (no SMA20 exit)
   produced identical results to V1 — the trend-break exit isn't the
   binding constraint. Hard −2.5% stop is firing first.

## Pattern across A4 / A4+A7 / A3

Three consecutive Branch-D kills on price-volume signals applied to
KOSPI top-80 (5.4y, 79 tickers, ~7,000–9,000 triggers each):

| Stream | Mechanism | Best test-side net | Best test-side hit |
|---|---|---:|---:|
| A4 (raw) | volume spike → continuation | +0.06% | 51.6% |
| A4+A7 | + regime filter | +0.11% | 51.5% |
| A3 | volatility compression → breakout | +0.04% (V2 W1) | 36.6% |

Common factor: **pure price-volume on KOSPI top-80**.

Two hypotheses for the structural pattern:

H1. **Universe is wrong**: KOSPI top-80 mega-caps are too efficient.
    Same hypotheses might work on mid/small cap (KOSDAQ250, KOSPI mid-cap).

H2. **KR mega-cap signal class is wrong**: price-volume alpha is arbed
    out in this universe; need fundamentally different signal classes
    (flow imbalance, news/event-driven, fundamental surprise).

Both can be tested. H1 requires re-running the same hypotheses on a
broader universe (data ingestion). H2 requires moving to A1/A2/A5/A6.

## Decision

1. **A3 declared not-viable** in current form on KOSPI top-80 5y data.
2. **No reformulation pursued** for A3 — moving to a different signal
   class is higher-EV than tweaking compression/box parameters.
3. **Surface to user** as critical decision: H1 (broaden universe) vs
   H2 (change signal class). Plan v2.2 §6 assumed alpha exists in
   price-volume on this universe; that assumption now appears false.

## Process integrity

PREREG-0003 was committed `86ed27d` BEFORE measurement. Decision table
§10 was binding. Branch D was a predeclared kill outcome. This is the
**third** consecutive PREREG-driven kill. The mechanism continues to
function — preventing post-hoc narrative repair on dead signals.

Cumulative Bonferroni budget consumed: 72 cells across PREREG-0001/2/3.
α/72 ≈ 0.00069 for any single survival claim. No claim has come close.

## Bias-prevention checklist (plan §7.4.2)

| Bias | Status |
|---|---|
| Survivorship | ⚠️ partial (KOSPI top-80, no delisted) |
| Look-ahead | ✅ all features use `.shift(1)` for prior-close evaluation |
| Data snooping | ✅ surface frozen pre-measurement; budget tracked |
| Regime selection | ✅ W1/W2/W3 span bear/mixed/bull |
| Cherry-picking | ✅ all cells reported; D explicitly predeclared as kill |
| Universe selection | ⚠️ recurring issue — explicitly raised as H1 |

## Open question for next decision

H1 vs H2: which to test first?

- H1 cost: significant (need KOSDAQ250 + mid-cap universe; KIS chart
  fetch + survivorship file build for ~250 more tickers; ~30min compute).
  Reuses existing A4/A3 code unchanged.
- H2 cost: medium-high (A2 needs sector mapping; A6 needs KIS investor
  endpoint validated for 5y depth; A1/A5 need data sources we don't have).

Recommendation: **H1 first** (broaden universe, re-run A4/A3 cheaply).
If H1 produces no graduate either, that's strong evidence the issue is
signal class (H2) not universe, and we move to A2/A6 with confidence.
