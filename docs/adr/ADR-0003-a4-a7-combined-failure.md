# ADR-0003: A4+A7 Combined Strategy — 5y Walk-Forward Failure (Branch D)

**Status**: Accepted
**Date**: 2026-05-08
**Supersedes**: none (extends ADR-0002)
**Linked**: [PREREG-0002](../preregistration/PREREG-0002-a4-a7-combined.md), [ADR-0002](ADR-0002-a4-5y-walkforward-failure.md)

---

## Context

ADR-0002 declared raw A4 dead on 5y data. Plan v2.2 §8.0 specifies that
Phase 0's actual alpha is **A4 + A7 combined (1 combo)**, not A4 alone.
A7 is a meta-filter intended to skip/halve A4 entries when the broad
market is in a weak regime. The remaining question after ADR-0002 was:
does adding A7 rescue the combined strategy?

PREREG-0002 froze the A7 classifier and the decision table BEFORE any
measurement. Result: **PREREG-0002 §8 Branch D** — neither graduates
AND no meaningful MDD reduction → kill the entire stream.

## Evidence

`research/a4_liquidity_surge/walkforward_a7_results.txt` (committed).

**KPI table (test sides only)**:

| Variant | A7 mode | KPI hit/mean (≥58% / ≥+1.20%) | Avg MDD reduction |
|---|---|---|---|
| V1 (ATR 2.5 / +7/+15) | F-skip | 0 / 3 windows | **−2.4%** |
| V1 (ATR 2.5 / +7/+15) | F-half | 0 / 3 windows | **+2.4%** |
| V2 (ATR 2.0 / +10/+20) | F-skip | 0 / 3 windows | **−8.6%** |
| V2 (ATR 2.0 / +10/+20) | F-half | 0 / 3 windows | **−0.0%** |

PREREG-0002 §4 requires MDD reduction ≥ +30% AND KPI gates pass on all
three test windows. **No cell passes either.** F-skip frequently makes
MDD *worse* (W2: −10 to −13%; W1 V2: −6%), meaning trades the regime
filter removes are on average *better*, not worse, than trades it keeps.

**Per-window cuts** (V1 baseline → V1 F-skip):

| Window | Filtered % | Net mean Δ | Hit Δ | MDD Δ |
|---|---|---|---|---|
| W1 (bear in test, 22H2-23H1) | 5.6% | +0.06pp | +0.0011 | +4.6% |
| W2 (mixed, 2024) | 9.7% | −0.03pp | −0.0065 | −10.3% |
| W3 (bull-tilted, 2025-26) | 4.1% | −0.01pp | −0.0007 | −1.6% |

W1 (bear) shows tiny improvement, but absolute net is still negative
(−0.10% / trade). W2 actively rejects the filter — A7 is removing the
*winners*, not the *losers*, in 2024.

## Diagnosis

Three possible failure modes; evidence supports the third:

1. **A7 classifier wrong**: maybe trend+cross+vol isn't capturing real
   regime. Possible but the regime episodes (Jan-Mar 2022, Jun-Jul 2022,
   Oct 2022, Apr 2025) align with widely-recognised KR bear phases —
   classifier is plausible.
2. **A7 too sparse**: only 9.7% of days flagged WEAK; not enough samples
   to materially affect aggregate metrics. True but doesn't explain the
   *adverse* effect in W2.
3. **A4 signal is regime-orthogonal** (most likely): liquidity surges
   happen on bottoms-out days *during* WEAK regimes — these are exactly
   the trades that benefit from snap-back rallies. Filtering them out
   removes the few profitable ones in bear periods. The regime-filter
   premise (bear = bad for momentum-on-spike) doesn't apply when the
   spike *itself* is the signal of contrarian buying.

This is consistent with the literature on volume-spike strategies: they
tend to work better on capitulation days (which often coincide with
weak regimes), not on trending bull days. A regime filter designed
for trend-following systems mis-fires when applied to a spike-reversal
system.

## Decision

1. **A4 + A7 (combined) is declared not-viable** as a Phase 0 alpha
   strategy in its plan v2.2 §8.0 form.
2. **A7 itself is not vindicated**. Cannot be retained as a "universal
   filter for future strategies" without a separate validation against
   each candidate alpha — its premise is signal-dependent.
3. **Phase 0 design must be re-evaluated**. The plan's §8.0 commits
   Phase 0 paper-trading to A4+A7 as a single combo; that combo is
   empirically dead. Phase 0 cannot be entered as planned.

## Decision branches not taken

The PREREG-0002 §8 table predeclared four branches. We landed on **D**:

- ~~A: F-skip graduates~~ (it doesn't)
- ~~B: F-half graduates only~~ (it doesn't)
- ~~C: KPI fails but MDD reduction ≥ 30%~~ (no variant achieves this)
- **D: kill the stream** ← active

## Future paths

(none committed; surfaced to user as critical decision)

a. **Reformulate A4 signal**. Plan §6 lists A1, A2, A5, A6 as
   alternatives. PREREG-0001 §7 listed A2/A5 as priority secondaries.
   Move on to A2 (gap reversal) or A5 (52W-high momentum).
b. **Reformulate A7 classifier**. Try sector-level regime instead of
   index-level; or VIX-substitute via cross-sectional dispersion.
   Risk: increases the multiple-testing budget without clear ex-ante
   reason to expect different outcome.
c. **Hybrid: A4 conditional on intraday confirmation** (gap-up open
   after surge day, etc.) instead of regime gate. This is a different
   class of filter; would need new prereg.
d. **Re-design Phase 0 to skip an alpha entirely** — operate as
   pure paper-mode infra validation only, defer alpha selection to
   Phase 0.5/1. Reduces research pressure but also reduces information
   gained from Phase 0.

## Process integrity

PREREG-0002 was committed (`96d5594`) BEFORE measurement
(`walkforward_a7_results.txt` produced after the commit). Decision
table §8 was binding; result fell into the predeclared D bucket.
This is the second consecutive PREREG-driven kill (A4 raw → A4+A7);
the mechanism is functioning as intended — preventing post-hoc
narrative repair.

## Bias-prevention checklist (plan §7.4.2)

| Bias | Status | Note |
|---|---|---|
| Survivorship | ⚠️ partial | KOSPI top-80 mega-caps; delisted universe placeholder is empty. Effect estimated <5% per ADR-0002. |
| Look-ahead | ✅ | A7 uses only data ≤ entry date; signal date < execution date (exit_rules) |
| Data snooping | ✅ | Search surface frozen in PREREG-0002 before measurement; budget-tracked |
| Regime selection | ✅ | W1/W2/W3 explicitly span bear/mixed/bull |
| Cherry-picking | ✅ | All cells reported, decision table predeclared, branch D explicitly defined as a kill outcome |
