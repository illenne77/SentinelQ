# ADR-0005: Universe Broadening (H1) — Inconclusive / H2 Confirmed

**Status**: Accepted
**Date**: 2026-05-08
**Linked**: [ADR-0004](ADR-0004-a3-vol-compression-failure.md) (H1 vs H2 framing)

---

## Context

ADR-0004 surfaced two structural hypotheses for three consecutive
PREREG-driven kills (A4, A4+A7, A3) on KOSPI top-80:

- **H1**: Universe is wrong. Mega-caps too efficient; signals may
  survive on mid/small caps.
- **H2**: KR mega-cap price-volume signal class is wrong. Need a
  fundamentally different signal class (flow, news, fundamental).

This ADR records the H1 test result.

## Method

1. Built `universe_kosdaq_midcap.txt` — 57 candidate KOSDAQ mid/large
   caps from public knowledge (pykrx and FDR ticker listings broken
   in 2026). All 57 fetched cleanly via KIS chart API.
2. Combined universe: 79 KOSPI top-80 + 57 KOSDAQ = **136 tickers**,
   208,456 daily rows.
3. Re-ran `exp_walkforward_5y.py` (A4) and `exp_walkforward_a3.py`
   (A3) unchanged on broadened universe.
4. No PREREG amendment needed: PREREG-0001 §2 universe was specified
   as KOSPI top-80; broadening is a *different* test of the same
   hypothesis class, properly recorded as a fresh measurement under
   ADR-0004's H1/H2 framing.

## Evidence

`research/a4_liquidity_surge/walkforward_5y_h1_results.txt`,
`research/a3_vol_compression/walkforward_a3_h1_results.txt`.

### A4 PREREG-0001 primary (ATR k=2.5 / +7/+15)

| Window | KOSPI-only | KOSPI+KOSDAQ | Δ |
|---|---:|---:|---:|
| W1 test net | −0.0016 | +0.0015 | +0.31pp |
| W2 test net | −0.0028 | −0.0032 | −0.04pp |
| W3 test net | +0.0087 | +0.0089 | +0.02pp |
| FULL net | +0.0006 | +0.0014 | +0.08pp |

Hit rates similar (W3 bull stays around 57% — same level as KOSPI-only).
**KPI gates (PF ≥ 1.6 / mean ≥ +1.20% / hit ≥ 58%) still fail on
every cell.**

**Rank stability of prereg primary**:
- KOSPI-only: ranks [3, 6, 2] across W1/W2/W3 — FAIL (max 6 > 3 limit)
- KOSPI+KOSDAQ: ranks **[3, 7, 3]** — also FAIL, and W2 rank
  *worsened* to dead last (7 of 7 variants).

The prereg primary in 2024 (W2) is the *worst* variant on the
broadened universe. This is not a small-sample effect: W2 has 2,168
test triggers.

### A3 V1 plan-literal

| Window | KOSPI-only | KOSPI+KOSDAQ |
|---|---:|---:|
| W1 net / PF | −0.12% / 0.91 | **−0.74% / 0.58** |
| W2 net / PF | −1.12% / 0.37 | −0.84% / 0.54 |
| W3 net / PF | −0.41% / 0.76 | **−0.60% / 0.67** |
| FULL net / PF | −0.69% / 0.59 | **−0.78% / 0.56** |

A3 is **uniformly worse** on KOSDAQ-augmented universe. KOSDAQ
breakouts fail-faster than KOSPI breakouts. Best PF observed across
all 20 cells: 0.72 — still well below 1.3 floor.

## Diagnosis

H1 (universe-wrong) is **not supported**:

1. A4's bull-window improvement is real but tiny (+0.02pp on W3 net).
   The mixed/bear regime (W2) actually got worse.
2. A3 is unambiguously worse on the broader universe. KOSDAQ
   breakouts have higher gap-fade dominance than mega-caps, the
   opposite of what literature predicts for KR retail-driven names.
3. No KPI gate becomes passable on either hypothesis.

H2 (signal class wrong) is now the **operating hypothesis**:

The pattern across A4 / A4+A7 / A3 / A4-broad / A3-broad is consistent
with: *price-volume momentum and breakout signals on KR equities (any
market-cap tier) carry economically insignificant edge after
transaction costs.* This is consistent with the broader literature
finding that KR market is dominated by foreign program flow that
arbitrages technical signals quickly.

What appeared to "work" on W3 (bull-tilted 2025-26) is regime-
selection — every long-biased strategy looks profitable in a
sustained bull. Hit rates of 57-60% confirm a small directional
edge exists, but mean returns of +0.5-0.9% per trade vs +1.2% target
indicates costs eat most of the gross alpha.

## Decision

1. **H1 declared unsupported**. Universe is not the binding
   constraint. Mid-cap KOSDAQ does not rescue these signals.
2. **Move to H2 path**: pivot to a different signal class.
3. **Eliminate A4, A4+A7, A3 from Phase 0 alpha candidate pool**.
4. **Eliminate price-volume-only signals as a class** for KR Phase 0
   purposes. This includes any future variant of A4/A3 mechanics
   without a fundamentally different data dimension. ("Don't try
   harder on a dead class" — discipline imposed by accumulated
   evidence.)

## Remaining plan §6 candidates (signal-class diversity)

| ID | Name | Signal class | Data status |
|---|---|---|---|
| A1 | PEAD | earnings surprise | needs consensus EPS source |
| **A2** | Sector Rotation | cross-sectional momentum | needs sector mapping |
| A5 | News Reversal | event-driven + LLM | needs news + LLM |
| **A6** | Inst/Foreign Flow Bias | order-flow imbalance | needs KIS investor endpoint |

A2 and A6 have the lowest data-acquisition friction. Both are KR-
appropriate signal classes that are *not* pure price-volume. They
are the natural next candidates.

A1 is high-quality alpha class globally but earnings consensus data
for KR mid/large caps is paid. Defer until A2/A6 are tested.

A5 requires LLM-classified news pipeline — defer until simpler
candidates are exhausted.

## Recommendation for next decision

**A6 (Institutional/Foreign Flow Bias) first.**

Reasons:
1. KR-specialty signal: literature on KR market consistently finds
   foreign net-buying has predictive power; this is the most-studied
   KR-specific anomaly.
2. KIS API has investor endpoints (`inquire-investor`,
   `inquire-member`); depth needs verification but the data class
   is squarely within our existing infrastructure.
3. Mechanically distinct from A1-A5 in plan §6: order-flow imbalance,
   not price action. Independent failure modes.
4. The A4+A7 attempt already gave us rate-limited KIS investor
   client structure; A6 fetcher is a parallel implementation, not a
   new dependency.

If A6's KIS endpoint depth is shallow (<5y), surface as decision:
either start daily snapshot collection now (only future data) or
fall back to A2 (sector rotation, OHLCV-derivable).

## Process integrity

H1 was explicitly framed *before* the broadening test in ADR-0004
(committed `caf035d`). Broadened-universe results were measured
*after* and recorded here. Pattern: continue using PREREG/ADR
mechanism as a no-cherry-pick guard.

## Bias-prevention checklist

| Bias | Status |
|---|---|
| Universe selection | ✅ explicitly tested via H1; verdict supports broader-class issue |
| Survivorship | ⚠️ partial; KOSDAQ list is 57 currently-listed names |
| Look-ahead | ✅ unchanged from prior runs |
| Data snooping | ✅ no parameter re-tuning done; same variants re-run on bigger universe |
| Regime selection | ✅ W1/W2/W3 unchanged |
| Cherry-picking | ✅ all cells reported in committed result files |
