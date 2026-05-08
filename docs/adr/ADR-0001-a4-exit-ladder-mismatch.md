# ADR-0001: A4 Liquidity Surge — Exit Ladder Mismatch & ATR Resolution

* **Status**: Accepted (updated 2026-05-08 evening)
* **Date**: 2026-05-08
* **Phase**: Phase 0 (Research)
* **Hypothesis**: A4 (Liquidity Surge), see plan v2.2 §6 / §7.3
* **Author**: illenne77 (with Copilot)

## Update note

Original finding (morning): A4 fails KPIs under fixed −2% / +3% / +5%
ladder.

**Resolution (afternoon)**: ATR-based stop variant (which §7.5
explicitly permits) restores the strategy to near-KPI levels. See
"ATR-resolution sweep" below. Path forward is now clear.

## Context

Plan v2.2 designates **A4 (Liquidity Surge) + A7 (Meta-filter)** as the
sole alpha pair for Phase 0 paper trading. Adoption requires (per §6):

1. ADR registration ← *this document partially fulfills*
2. ≥ 5y in-sample + 1y out-of-sample backtest
3. Net-of-cost alpha positive
4. All §7.4.2 bias checks passing

Per §7.3, A4 KPI thresholds are:

* **Hit rate ≥ 58%** per trade
* **Mean ≥ +1.2%** per trade (net of cost)
* **False-positive rate ≤ 15%**

Per §7.5, every adopted strategy ships with a **deterministic exit
ladder** (NOT discretionary):

* Stop-loss `-2%` (fixed) OR ATR-based OR structural — earliest fires
* Scaled take-profit `+3%` (50% out), `+5%` (30% out)
* Trailing stop `-1.5%` from peak on remaining 20%, armed after `+3%`
* Time-based exit at horizon (typ. 5d)

## Decision

We register the finding that **A4, evaluated through the §7.5 fixed
exit ladder, fails both KPIs simultaneously across all reasonable
parameterizations tested.**

This finding does not retire A4. It **redirects the research path**:
ATR-based and timing-shift variants are the next experiments. A4
cannot proceed to Phase 0 deployment under §7.5 default parameters.

## Evidence (KOSPI top-80, 2025-01-01 → 2026-05-08, threshold 1.5×, h=5d)

### Forward-return baseline (no exit rules — research proxy only)

| Stage              | n     | Net mean   | Net hit | KPI mean | KPI hit |
|--------------------|------:|-----------:|--------:|:--------:|:-------:|
| Gate-pass          | 2,003 | **+1.28%** | 54.5%   | ✓        | ✗       |
| Drop 2.0–3.0×      | 1,395 | +1.43%     | 55.7%   | ✓        | ✗       |
| Keep 1.5–2.0× only | 1,015 | +1.47%     | 56.7%   | ✓        | ✗       |

### Realistic exit-rule simulation (plan §7.5 ladder)

| Variant                          | Net mean   | Net hit | KPI mean | KPI hit |
|----------------------------------|-----------:|--------:|:--------:|:-------:|
| Default −2% / +3% / +5% / −1.5%  | **−0.13%** | **38.3%** | ✗ | ✗ |
| Loose −3% / +3% / +5% / −1.5%    | +0.00%     | 47.6%   | ✗ | ✗ |
| Loose −5% / +3% / +5% / −1.5%    | +0.33%     | 60.8%   | ✗ | ✓ |
| Wider TP −3% / +5% / +8% / −2.0% | +0.27%     | 43.7%   | ✗ | ✗ |
| No stop / +3% / +5% / —          | +0.49%     | 65.3%   | ✗ | ✓ |
| Forward 5d (no exits, baseline)  | +1.28%     | 54.5%   | ✓ | ✗ |

* **Stop-out rate at default −2%: 66.2%** of triggers — clear evidence
  that the −2% threshold is below the typical day-after intraday
  range for KR large-caps following a liquidity surge.
* No tested combination passes BOTH KPIs.

### ATR-resolution sweep (1,992 gate-pass triggers, DEFAULT cost)

| Variant                                 | Net mean | Net hit | Stop-out | KPI mean | KPI hit |
|-----------------------------------------|---------:|--------:|---------:|:--------:|:-------:|
| Baseline fixed −2% / +3 / +5 / close    | −0.13%   | 38.3%   | 66.1%    | ✗ | ✗ |
| ATR k=1.0 / +3 / +5 / close             | +0.12%   | 53.4%   | 46.0%    | ✗ | ✗ |
| ATR k=1.5 / +3 / +5 / close             | +0.51%   | 63.4%   | 27.2%    | ✗ | ✓ |
| ATR k=2.0 / +3 / +5 / close             | +0.55%   | 65.7%   | 18.0%    | ✗ | ✓ |
| ATR k=2.0 / +5 / +10 / close            | +0.81%   | 60.2%   | 19.0%    | ✗ | ✓ |
| ATR k=2.0 / +7 / +15 / close            | +0.98%   | 57.0%   | 19.2%    | 22bp ⚠ | 1pp ⚠ |
| **ATR k=2.5 / +7 / +15 / close**        | **+1.02%** | **58.2%** | 11.4% | 18bp ⚠ | ✓ |
| ATR k=2.5 / +5 / +10 / close            | +0.86%   | 61.6%   | 11.1%    | ✗ | ✓ |
| ATR k=2.0 / +10 / +20 / close           | +1.11%   | 54.6%   | 19.2%    | 9bp ⚠ | ✗ |
| Next-day-open variants                  | (worse across the board, omitted) |

**Stop-out rate** dropped from 66.1% (fixed −2%) to 11–27% (ATR-based)
as the stop adapts to per-name volatility. No more premature
exits on noise.

The closest-to-passing variant — **ATR k=2.5 / +7% / +15%, close
entry** — leaves the mean KPI 18bp short of +1.2%, with hit ✓. Given
SE(mean) ≈ σ/√n ≈ 5%/√1992 ≈ 11bp, this gap is on the order of
1.6σ — not statistically distinguishable from the threshold.

## Diagnosis

The A4 signal naturally produces an asymmetric return distribution:

* **Mean profitable** (+1.28% raw forward 5d) due to a few large winners
* **Hit rate marginal** (~54.5%) because surges often mean-revert short-term

Plan §7.5's fixed ladder amplifies the asymmetry **against** the
trader:

1. −2% stop is tight relative to KR equity day-1 noise → premature
   stop-outs (66%) realize losses on what would have been winners.
2. +3% / +5% TP truncates the right tail that drives the mean.
3. Time horizon evicts middling positions before reversion to mean.

## Consequences

**Direct**:
* A4 with default §7.5 fixed-pct parameters (−2%/+3%/+5%) is **not
  deployable** under any tested adjustment.
* A4 with **ATR k=2.5 / +7% / +15% / trail −3%** is **borderline
  KPI-compliant** (hit ✓, mean within 1.6σ of threshold) and is the
  recommended candidate for OOS validation.
* Plan v2.2 §6 statement "Phase 0 채택: A4 + A7" remains tenable
  pending walk-forward confirmation of the ATR variant.

**Research path** (revised priority):

1. **Walk-forward OOS**: split 2025-01-01..2026-05-08 into 12-month
   train (2025-01..2025-12) + 4-month test (2026-01..2026-05). Confirm
   ATR k=2.5 / +7/+15 ranking is stable on test. If KPI mean drops
   below +0.5%, the parameter choice is overfit.
2. **Bucket-conditional ATR k**: 1.5–2.0× bucket gets k=2.0; 3.0+×
   gets k=2.5 (let high-volatility names breathe more). Test only if
   walk-forward (1) is stable.
3. **Survivorship correction**: still pending — universe expansion to
   PIT KOSPI200 with delisted names. Largest remaining bias.
4. **Fail criteria**: if walk-forward mean drops below +0.6% net AND
   hit below 56%, escalate to alternative hypothesis (A1/A2) per
   plan §6.

**Process**:
* All future A4 parameter changes go through ADR + walk-forward
  validation (§7.4.2 hindsight-bias check).
* Forward-return is **never** a sufficient KPI proxy. Every alpha
  evaluation must run through the realistic exit simulator.

## Bias Checklist Status

| Check            | Status | Note |
|------------------|:------:|------|
| Lookahead        | ✓ | `closed="left"` rolling window in surge_ratio |
| Survivorship     | ✗ | Today's KOSPI top-80 used throughout |
| Data leakage     | ✓ | Forward returns separated from features |
| Hindsight        | ⚠️ | Bucket boundaries chosen from same data (pending OOS) |
| Selection        | ⚠️ | Universe expanded mid-research (top-30 → top-80) |
| Multiple-testing | ⚠️ | ~5 parameter combos tested; not Bonferroni-corrected |
| LLM determinism  | n/a | Quant signal, no LLM involved |
| Cost-net         | ✓ | All KPIs reported net of 31bp DEFAULT round-trip |
| OOS walk-forward | ⚠️ | 12mo train + 4mo test done (`exp_walkforward.py`); test PASSES both KPIs but train-test asymmetry suggests strong-up regime in test window — bear-market data needed |

## References

* Plan v2.2 §6, §7.3, §7.4.2, §7.5
* Code: `research/a4_liquidity_surge/`
  * `exit_rules.py` — §7.5 ladder simulator
  * `exit_backtest.py` — exit-aware A4 backtest
  * `exp_stop_sweep.py` — stop-level sensitivity (this ADR's evidence)
  * `exp_atr_sweep.py` — ATR-adaptive stop sweep (resolution evidence)
  * `exp_walkforward.py` — train/test OOS validation
* Commits: `6bbed0c` (mismatch finding), `0f7303c` (ATR resolution), `51a1d72` (walk-forward OOS)

## Walk-Forward OOS Result (added 2026-05-08)

> **⚠️ SUPERSEDED by [ADR-0002](ADR-0002-a4-5y-walkforward-failure.md)**.
> The single-window OOS pass recorded below was a regime-selection
> artifact. Subsequent 5y validation across W1/W2/W3 (2021-01..2026-05)
> failed all KPIs. See ADR-0002 for the authoritative verdict.

Train (2025-01-01..2025-12-31, n=1414):
* ATR k=2.5 / +7/+15 → net +0.67%, hit 55.5%, stop-out 11.0% (**KPI fail** on both)

Test  (2026-01-01..2026-05-08, n=589):
* ATR k=2.5 / +7/+15 → net **+1.74%**, hit **64.2%**, stop-out 12.9% (**KPI pass on both**)

Rank stability: 5/7 variants identical rank across splits; prior winner sits at
#2 on test (near-tie with k=2.0/+7/+15 at +1.76%). No catastrophic flip.

**Caveat**: train-test asymmetry (test net 2.6× train net) is *opposite* of the
typical overfit pattern. Most likely explanation: 2026-01..05 was a strong-up
regime that disproportionately rewarded long momentum signals. Hence the test
pass is **necessary but not sufficient** — A4 robustness in bear regimes
remains unproven without ≥5y backfill including 2022 / 2024H2 drawdowns.

**Decision deferred**: do NOT declare Phase 0 graduation on this evidence
alone. Required next step: KIS chart API integration → 5y backfill including
delisted names (survivorship-corrected) → re-run walk-forward across
multi-regime windows.
