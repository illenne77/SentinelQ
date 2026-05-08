# PREREG-0002: A4 + A7 Combined — Regime-Filtered Liquidity Surge

**Status**: Active
**Created**: 2026-05-08
**Author**: SentinelQ research
**Hypothesis**: A4 (Liquidity Surge) gated by A7 (Relative Strength Regime Filter)
**Linked**: [PREREG-0001](PREREG-0001-a4-multiyear-validation.md), [ADR-0002](../adr/ADR-0002-a4-5y-walkforward-failure.md)

---

## 1. Why this prereg

ADR-0002 declared raw A4 not-viable on 5y data. Plan v2.2 §6/§7.3/§8.0
specifies that Phase 0's actual alpha is **A4 + A7 (1 combo)**, not A4
alone. A7 was always intended as a meta-filter that shrinks/skips
A4 entries when the broad market is in a weak regime. Testing A4 without
A7 was therefore an incomplete test of the planned strategy.

This document freezes the A7 definition, the combined-strategy KPI gates,
and the search surface BEFORE any A4+A7 measurement is run. Same
discipline as PREREG-0001.

## 2. Frozen A7 regime classifier

A7 produces a daily binary state per KOSPI200 index:

```
state(t) = "WEAK" if ALL of:
    1. KODEX200(t).close < SMA200(KODEX200, lookback=200d)
    2. SMA(KODEX200, 20d) < SMA(KODEX200, 50d)
    3. realised_vol_20d(KODEX200) >= rolling 80th percentile over past 252d

state(t) = "OK" otherwise
```

**Index proxy**: KODEX 200 (ticker 069500) — KOSPI200-tracking ETF, used
because KIS index endpoints have not been integrated. Tracking error vs
KOSPI200 < 15bp/day — immaterial for regime classification. Documented
in the prereg as a deliberate substitution.

**VIX substitution**: plan §6 specifies "VIX > 25". KR has no liquid VIX.
We substitute "20d realised vol in top quintile of trailing 252d" as a
volatility-stress proxy. This is a definitional change relative to plan
v2.2 §6 and is recorded here as the frozen choice.

**Two filter strengths tested** (per plan §6 "비중 50% 축소"):

| Mode | Action when WEAK |
|---|---|
| **F-skip** (primary) | Skip trade entirely (binary gate) |
| **F-half** (secondary) | Take trade at 50% size (per plan §6 wording) |

F-half effectively scales the trade-level return by 0.5 (cost is also
0.5× since spread/commission scale with notional). Both are evaluated.

## 3. Frozen variant set

A4-side: only **2** A4 stop/TP combinations carry forward from
PREREG-0001 (the prereg primary + best of W3 test):

  V1. ATR k=2.5 / TP +7/+15 / trail -3%   (PREREG-0001 primary)
  V2. ATR k=2.0 / TP +10/+20 / trail -4%  (top-1 on every W test in PREREG-0001)

A7 side: 3 modes — `none` (raw A4 baseline), `F-skip`, `F-half`.

Total cells: **2 × 3 × 4 = 24** (V × A7 × {W1, W2, W3, FULL})
Plus train splits for completeness (24 more), but only test sides count
toward graduation.

## 4. KPI gates

**A4+A7 graduates** iff, when applying the A7 filter, the combined strategy
satisfies on test sides:

| KPI | Threshold | Notes |
|---|---|---|
| Net mean / trade | ≥ +1.20% | plan §7.3 |
| Hit rate | ≥ 58% | plan §7.3 |
| MDD reduction (vs raw A4) | ≥ 30% | plan §6 A7 KPI |
| Walk-forward stability | top variant rank stable across W1/W2/W3 | this prereg |
| Bear-window alive | net mean > 0 in W1 test | this prereg |

The MDD-reduction criterion is **central** to A7. Even if hit/mean fail,
demonstrating MDD reduction validates A7 as a useful component (would
inform a redesign rather than a kill).

Drawdown metric: `_max_drawdown_fixed_sized` per ADR-0002 (avg loss per
trade during worst additive cumulative-P&L drawdown).

## 5. Frozen test windows

Same as PREREG-0001 §5 (W1/W2/W3 + full). Re-stating:

| Window | Train | Test |
|---|---|---|
| W1 | 2021-01..2022-06 | 2022-07..2023-06 |
| W2 | 2022-01..2023-12 | 2024-01..2024-12 |
| W3 | 2023-01..2024-12 | 2025-01..2026-05 |
| FULL | — | 2021-01..2026-05 |

## 6. Out of scope (must not be touched without amendment)

- Different A7 classifier components (e.g., adding macro yield curve)
- Different volatility window (locked at 20d / 252d-percentile)
- Different SMA windows for A7 trend (locked at 20/50/200)
- Different regime states beyond binary WEAK/OK
- A4 surge_ratio threshold (locked at 1.5×)
- Universe (locked: KOSPI top-80 + delisted union per PREREG-0001)

## 7. Multiple-testing budget update

PREREG-0001 budget consumed: 7 × 4 = 28 test cells.
PREREG-0002 adds: 24 test cells.
Cumulative budget: 52. Bonferroni α/52 ≈ 0.00096 for any single claim.

## 8. Decision branches (predeclared)

After running:
- **A**: F-skip variant graduates → A4+A7 → Phase 0 entry plan
- **B**: F-half graduates but F-skip doesn't → adopt sized filter
- **C**: Neither graduates but MDD reduction ≥ 30% achieved → A7 confirmed
        useful; A4 still dead → kill A4+A7 combo, look for new alpha
        + retain A7 as universal filter for future strategies
- **D**: Neither graduates AND no MDD reduction → A7 ineffective on
        this signal too → kill the entire stream, re-evaluate Phase 0 design

Branch is determined by the data, not by post-hoc choice. The decision
table above is binding.

## 9. Amendments

(none yet)

---

**Authoritative for A4+A7 stream. Changes require amendment commit before
measurement.**
