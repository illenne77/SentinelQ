# ADR-0006: A2 Sector Rotation Failure / Phase 0 Alpha-Discovery Stalled

**Status**: Accepted
**Date**: 2026-05-08
**Linked**: [PREREG-0004](../preregistration/PREREG-0004-a2-sector-rotation.md), [ADR-0005](ADR-0005-h1-universe-broadening-result.md)

---

## Context

ADR-0005 declared price-volume *absolute* signals dead and redirected to
A2 Sector Rotation, framed as a mechanically distinct cross-sectional
class. PREREG-0004 fixed 5 variants × 4 windows = 20 cells. This ADR
records the A2 backtest verdict.

## Evidence

`research/a2_sector_rotation/walkforward_a2_results.txt`. 5y bars on
136-ticker universe (KOSPI top-80 + KOSDAQ mid-cap). Sector map at
`research/a2_sector_rotation/sector_map.csv` (8 sectors, 130 classified,
6 OTHER excluded).

### Per-variant FULL test (2023-01..2026-05-08)

| Var | alpha_ann | CAGR raw | Sharpe | maxDD | hit-M | trades |
|---|---:|---:|---:|---:|---:|---:|
| **V1 (primary)** | -28.6% | +10.0% | 0.59 | -16.8% | 40% | 122 |
| V2 (12w mom) | -35.7% | +3.0%  | 0.17 | -23.6% | 35% | 123 |
| V3 (top-5 sec)| -29.3% | +9.4%  | 0.64 | -17.7% | 35% | 204 |
| V4 (-2/+10)   | -28.8% | +9.8%  | 0.62 | -13.3% | 40% | 123 |
| V5 (weekly)   | -13.7% | +24.9% | 0.77 | -40.4% | 45% | 488 |

### Per-window V1 alpha_ann

| Window | V1 alpha_ann | V1 CAGR raw | V1 hit-M |
|---|---:|---:|---:|
| W1 (2023) | -32.5% | +8.9% | 45.5% |
| W2 (2024) | -2.0%  | -7.1% | 36.4% |
| W3 (2025-26) | -58.6% | +22.6% | 31.2% |

### G5 primary rank stability (alpha rank, 1=best of 5)

V1 ranks in each window: **W1=3, W2=3, W3=3**. G5 threshold (≤3) PASSES.
But this is a hollow pass — V1 is the median variant in every window, no
variant being clearly better.

### KPI gate summary (PREREG-0004 §8)

| Variant | G1 alpha ≥1.5% | G2 hit-M ≥55% | G3 DD ≤20% | G4 stab | G5 rank | G6 Sharpe ≥0.7 |
|---|---|---|---|---|---|---|
| V1 | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ |
| V2 | ❌ | ❌ | ❌ | ❌ | ─ | ❌ |
| V3 | ❌ | ❌ | ✅ | ❌ | ─ | ❌ |
| V4 | ❌ | ❌ | ✅ | ❌ | ─ | ❌ |
| V5 | ❌ | ❌ | ❌ | ❌ | ─ | ✅ |

**No variant passes G1 (alpha gate). Decision branch D.**

## Diagnosis

### Benchmark caveat

PREREG-0004 §13 specified KOSPI200 as benchmark with fall-back to
equal-weighted basket of universe. KOSPI200 daily index data was not
available cleanly via the existing KIS chart endpoint without
additional engineering, so we used the prereg fall-back (equal-weighted
basket).

The equal-weighted basket of 130 KR mid-caps is a **harder benchmark**
than KOSPI200 in 2023-2025 because KOSDAQ mid-caps rallied harder than
the cap-weighted KOSPI200 over this period. Reported alpha numbers
above therefore overstate A2's underperformance vs KOSPI200.

However: V1's *raw* CAGR is **+10.0% annualised** over FULL period
(~3.4 years). Buy-and-hold KOSPI200 over the same period returned
approximately +15-20% annualised (rough estimate from public market
data). Even on the more lenient KOSPI200 benchmark, V1 is at best
0% alpha, more likely modestly negative. **A2 fails the +1.5% alpha
gate on either benchmark.**

### Cross-sectional ranking did not save us

The hope behind A2 was that *cross-sectional sector ranking* would
preserve information that *absolute* breakouts (A4/A3) destroyed.
Result: it does not. The five variants produce essentially the same
return profile (CAGR clustered in 3-25% range with similar Sharpe
0.17-0.77) — there is no coherent cross-sectional alpha signal. V5
(weekly) achieves higher CAGR by levering up turnover, paying for it
in -40% max DD.

### Window pattern

W2 (2024) is again the binding window — every variant has
near-zero or negative alpha in 2024, consistent with the same
2024-specific failure pattern observed for A4/A3. This is now a 6th
independent observation: 2024 KR equity has been hostile to
price-volume strategies of every form.

## Phase 0 alpha-discovery — cumulative status

| Hypothesis | Class | Universe | Verdict |
|---|---|---|---|
| A4 raw | absolute liquidity surge | KOSPI top-80 | dead (ADR-0002) |
| A4+A7 | regime-conditional A4 | KOSPI top-80 | dead (ADR-0003) |
| A3 | volatility compression breakout | KOSPI top-80 | dead (ADR-0004) |
| A4 / A3 broadened | same, KOSPI+KOSDAQ | broadened | dead (ADR-0005) |
| **A2 sector rotation** | cross-sectional momentum | broadened | **dead (this ADR)** |

5 hypotheses, 4 ADRs of failure, 92 prereg'd cells. **All
price-volume-derived signals tested have failed in KR equity over
the 2020-2026 sample.**

This is itself a meaningful finding. KR equity price-volume signals
appear to be efficiently arbitraged in our test sample, plausibly by:

- Foreign institutional program trading dominating intraday flow
- Retail-driven KOSDAQ moves being mean-reverting too fast for daily
  signal extraction
- 2024-specific structural shift (election year, FX volatility,
  semiconductor cycle peak) that most pre-2024 patterns failed to
  generalise across

## Decision

1. **A2 declared dead.** No reformulation; PREREG-0004 closed.
2. **Eliminate price-volume-derived signal classes from Phase 0**.
   This includes any further variants of momentum, breakout,
   compression, ranking, or regime-conditional versions of the above.
   ("Don't try harder on a dead family.")
3. **Phase 0 alpha-discovery is stalled** under the current data
   infrastructure. Remaining plan §6 candidates (A1 PEAD, A5 News
   Reversal, A6 Flow Bias) all require new data infrastructure that
   we have not built.

## Path forward — surface to user

Three honest options:

### Option X — Build new data infrastructure (foreground)

- A1 PEAD: requires KR equity earnings consensus EPS time series.
  Sources: WiseFn (paid), FnGuide (paid), Bloomberg (paid). Estimated
  build effort: 2-4 weeks plus licensing.
- A5 News Reversal: requires KR financial news corpus + LLM
  classification pipeline. Sources: Naver News scraping or paid
  newswire. Estimated build effort: 3-6 weeks.
- Both blocked by data licensing decisions that need user input.

### Option Y — Wait for A6 forward-collected data

KIS investor flow daemon (committed `96a454e`) accumulates ~20-30
new daily snapshots per ticker per day across 136 tickers. To run a
meaningful 6-month walk-forward we need ~6 months of accumulation.
**Phase 0 paused for ~6 months in this option.** During the pause we
can build infrastructure (Option X data sources or system layers).

### Option Z — Accept Phase 0 negative result, pivot to system layers

Treat the cumulative result as a *finding*: "in our 2020-2026 sample
on the available data infrastructure, no price-volume KR alpha
graduated; we will not pursue further price-volume hypotheses without
new data". Pivot research effort to:

- **Published-strategy replication**: implement an academic-literature
  KR multi-factor model (size+value+momentum+quality) with a known
  expected Sharpe of 0.5-0.8. Trade off custom alpha for known-
  literature alpha.
- **System layers**: risk management, execution, monitoring,
  reporting are all incomplete. Build them so that when an alpha is
  eventually discovered (via Option X or Y), the rest of the system
  is ready.

This is the most plan-aligned option for moving forward without
spending more time on dead alpha hunts.

### Recommendation

**Option Z** is the highest-EV path:
1. Honest acknowledgement of the negative result protects future
   integrity (no "torturing data until it confesses").
2. System infrastructure (risk, execution, monitoring, paper trading
   harness) needs to exist regardless of which alpha eventually wins.
3. Forward-collect daemon (A6) keeps Option Y alive in background at
   zero cost.
4. If user wants to fund data licensing for A1/A5 (Option X), can be
   started in parallel with system layers.

A multi-factor literature-replication strategy can act as a paper-
trade benchmark target while the system is built — even modest alpha
(0.5 Sharpe) is acceptable as a vehicle for system testing.

## Process integrity

- 5 PREREG-driven kills now. No reformulations or post-hoc rescues
  attempted.
- 92 cells pre-declared cumulatively. No statistical claims made
  beyond economic threshold gates.
- Negative findings published with full per-cell results, not
  cherry-picked.
- Universe broadening (ADR-0005) was correctly flagged as exploratory.

## Bias-prevention checklist

| Bias | Status |
|---|---|
| Look-ahead | ✅ sector ranking uses bars strictly < rebal date |
| Survivorship | ⚠️ static universe; effect bounded |
| Universe selection | ✅ frozen by PREREG-0004 §2 |
| Data-snooping | ✅ variants frozen pre-measurement |
| Cherry-picking | ✅ all 20 cells reported |
| Multiple comparisons | ✅ §10 cumulative budget tracked |
| Benchmark selection | ⚠️ KOSPI200 unavailable; equal-weighted fall-back disclosed; raw CAGR also reported for comparison |
