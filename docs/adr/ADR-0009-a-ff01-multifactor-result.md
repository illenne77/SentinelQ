# ADR-0009: A-FF01 Value+Quality multi-factor — REJECTED; DART-fundamentals class declared dead

**Status**: Accepted
**Date**: 2026-05-09
**Linked**: [PREREG-0007](../preregistration/PREREG-0007-a-ff01-multifactor.md), [ADR-0007](ADR-0007-a-f01-book-to-market-result.md), [ADR-0008](ADR-0008-a-f03-gross-profitability-result.md)

---

## Decision

**A-FF01 (B/M + GP/A rank-sum) is rejected** per PREREG-0007 Branch E.
All 5 variants fail every primary gate. The hoped-for regime
diversification did NOT materialize.

Per the pre-declared decision rule, the entire **DART-fundamentals
factor class** (A-F01 value, A-F03 quality, A-FF01 their
combination) is declared **dead** for the 2023-2026 sample period.
Phase 0 alpha discovery pivots away from fundamentals to
alternative data.

## Result table (PREREG-0007 V1-V5, FULL test 2023-01..2026-05)

| Variant | Composition | FULL alpha | W1 2023 | W2 2024 | W3 2025-26 | All gates |
|---|---|---:|---:|---:|---:|---|
| V1 (PRIMARY) | 0.5 BM + 0.5 GPA | -14.10% | -15.7% | -5.4% | -23.4% | FAIL |
| V2 | 0.6 BM + 0.4 GPA | -15.51% | -18.0% | -8.7% | -18.9% | FAIL |
| V3 | 0.4 BM + 0.6 GPA | -19.61% | -13.7% | -9.3% | -35.6% | FAIL |
| V4 | 0.5/0.5 quarterly | -11.74% | -22.2% | -3.2% | -19.9% | FAIL |
| V5 | 0.5/0.5 + ΔGPA>0 | -15.23% | -7.4% | -11.6% | -22.3% | FAIL |

(Comparison vs PREREG-0005/6 standalone, FULL alpha):

| Variant | A-F01 alone | A-F03 alone | A-FF01 V1 | Naive 0.5+0.5 expected |
|---|---:|---:|---:|---:|
| FULL | -2.0% | -6.7% | -14.1% | ~-4.3% |
| W1 | -33.1% | +9.7% | -15.7% | ~-12% |
| W2 | +11.3% | -0.1% | -5.4% | ~+5.5% |
| W3 | +11.9% | -28.0% | -23.4% | ~-8% |

## Why combination performed *worse* than naive average

This is the most counterintuitive finding of Phase 0. We expected
A-FF01 ≈ (A-F01 + A-F03) / 2. Instead it is **systematically below**
the naive average, especially in W2 and W3 where one factor was
positive.

Two causes identified:

1. **Universe restriction effect**. Eligibility requires *both*
   BM and GPA non-null → 107-ticker basket vs 127 (F01) and
   ~119 (F03). The dropped 12-20 tickers happen to be the ones
   that drove F01's W3 outperformance — primarily insurance/
   bank holding companies whose GP/A is undefined. Banks led the
   2024-26 KR Value-up rally; excluding them costs ~10% W3 alpha.

2. **Rank-sum picks the *intersection of moderate*, not the union
   of extremes**. Linear combination of two ranks selects names
   that are *both* moderately cheap AND moderately profitable —
   typically mid-cap industrials. The actual W3 winners
   (deep-value chaebol holdings) and the W1 winners (high-margin
   tech) sit at OPPOSITE corners of the BM × GPA grid; rank-sum
   never picks either pole. We end up systematically selecting
   the *boring middle*, which underperforms in *both* regimes
   it was supposed to hedge.

This is a classic limitation of linear factor combination that
the academic literature warns about (Asness et al. 2013), but
we judged a-priori that 3-year sample size made non-linear
methods (gradient boosting on factor scores) too easy to
overfit. We pre-registered the simpler form and accept the
result.

## Cumulative DART-fundamentals tally

| Test | Cells | Pass? |
|---|---|---|
| A-F01 (value)   | 20 | All FAIL |
| A-F03 (quality) | 20 | All FAIL |
| A-FF01 (combo)  | 20 | All FAIL |
| **Total**       | **60** | **0/60** |

60 frozen pre-registered cells. Zero positive alphas at any
gate. This is a **decisive negative result** for KR equity
fundamental factors in the 2023-2026 sample, sufficient
under our PREREG decision rule to declare the class dead and
move on.

## What this rules out (and what it doesn't)

**Ruled out (for 2023-2026 KR sample, 136-ticker universe)**:
- Long-only B/M tilt
- Long-only GP/A tilt
- Linear combinations thereof (5 weight schemes tested)
- Slow-rebalance (quarterly) variants
- Improving-quality screens

**Not ruled out (left for future work, NOT Phase 0)**:
- Long-short factor portfolios (different mandate)
- Sector-neutral rank construction (would need GICS membership data we don't have)
- Non-linear factor models (overfit risk too high in 3y sample)
- Larger universes (KOSPI200 was a sub-universe of KOSPI; small-caps may behave differently)
- Different time periods (factor regimes shift; 2023-26 may be unusually hostile to KR fundamentals)

## Pivot decision

**Phase 0 continues with alternative data alphas only.**
Per the prior research review (`research/oss_review/`), the
queued alternatives ranked by feasibility are:

1. **A-A01 News-sentiment alpha** — KR news headlines via
   FinanceDataReader / public news APIs, simple lexicon
   sentiment scoring. Daily granularity. Fresh data.
2. **A-A02 Investor-flow alpha** (waits for A6 daemon to
   accumulate 6 months of forward-collected institutional/
   foreign net buy data, currently ~3 weeks accumulated).
3. **A-A03 Options-flow proxy** (KOSPI200 options put/call
   ratio as market-wide signal; available via KRX).

A-A01 will be pre-registered next as PREREG-0008. A-A02
remains queued behind A6 data accumulation. A-A03 is
exploratory.

If A-A01 also fails, Phase 0 itself terminates and SentinelQ
restructures around a different domain (e.g., crypto, US
small-caps, or KR ETF rotation) where alpha-discovery is more
tractable.

## Lessons learned

1. **Cyclicality argument was real but insufficient.** ADR-0008
   showed F01 and F03 were genuinely mirror-cyclical, but
   linear combination did not capture the orthogonal nature of
   the regime shift; it averaged the *wrong* coordinate of the
   factor space.

2. **Pre-registration discipline saved time.** With 60 cells
   committed before testing, there is no ambiguity about
   whether to keep tweaking. The class is dead; we move on.

3. **Universe matters more than expected.** Banking/insurance
   exclusion via signal-availability filtering changed the
   alpha by ~10 pp in W3 alone. For future tests, eligibility
   intersection should be reported as a separate sensitivity.

4. **Pure cross-sectional rank ignores the magnitude of factor
   premium.** A high-conviction cheap name and a marginally
   cheap name receive nearly identical rank-sum scores when
   the other factor is moderate. Z-score weighting would help
   *if* the underlying distributions are stable, but a 3-year
   sample is too short to estimate factor volatilities reliably.

## Action items

- [x] Mark alpha-ff01-* todos done in SQL.
- [ ] Begin PREREG-0008 (A-A01 news sentiment) — next session.
- [ ] Continue A6 forward-collect daemon (3w/26w accumulated).
- [ ] Update README "Phase 0 status" section: 8/8 standalone
      alphas dead, fundamentals class dead, alt-data pivot.
