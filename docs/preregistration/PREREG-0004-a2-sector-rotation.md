# PREREG-0004: A2 Sector Rotation Momentum (KR equity)

**Status**: Frozen
**Date**: 2026-05-08
**Authors**: SentinelQ research
**Linked**: [ADR-0005](../adr/ADR-0005-h1-universe-broadening-result.md) (H2 path), plan v2.2 §6 A2 spec

---

## 1. Hypothesis

KR equity sector relative-strength persists over 4-12 weeks. By
buying the strongest single-name within each of the top-K
performing sectors (rebalanced periodically), an investor can
generate alpha vs KOSPI200 that *survives transaction costs*.

This is mechanically distinct from A4/A3 (which targeted absolute
single-name price-volume signals — declared dead in ADR-0002/4/5).
A2 is **cross-sectional**: it ranks groups before ranking names.
The implicit thesis is that price-volume *cross-sectional ranking*
contains information even when *absolute* breakouts do not.

## 2. Universe

KOSPI top-80 + KOSDAQ mid-caps (the broadened H1 universe; 136
tickers; sector_map.csv at `research/a2_sector_rotation/`). Tickers
classified as `OTHER` (6 of 136, <5%) are excluded from sector
ranking and from stock selection.

This universe is *frozen* by this PREREG. Any future broadening or
narrowing requires an amendment ADR.

## 3. Sectors

8 sectors after consolidation of KRX 업종 (`build_sector_map.py`):
IT_HW, HEALTH, AUTO_HEAVY, CHEM, STEEL, FIN, CONS, UTIL_SVC, SVC.
Member counts at PREREG date: 27/13/15/19/3/12/6/10/25 respectively.

STEEL has 3 members — small but kept (collapsing to AUTO_HEAVY would
mix mechanically distinct cycles).

## 4. Signal definitions

Notation: at rebalance date `t`, with `L` = lookback in trading days.

- **Sector momentum**: equal-weighted mean of constituent log-returns
  over `(t-L, t]`.
- **Stock RS within sector**: stock log-return over `(t-L, t]` minus
  sector mean log-return over same window.
- **Sector ranking**: rank desc by sector momentum.
- **Stock selection per top sector**: top-1 by RS within sector
  (ties broken alphabetically by ticker for determinism).

## 5. Variants (5 cells, frozen)

| ID | Lookback `L` | Top-K sectors | Picks/sector | Bracket | Max-hold | Rebal |
|---|---:|---:|---:|---|---:|---|
| **V1 (PRIMARY)** | 20d (4w) | 3 | 1 | -3% / +12% | 20d | monthly (1st trading day) |
| V2 | 60d (12w) | 3 | 1 | -3% / +12% | 20d | monthly |
| V3 | 20d | 5 | 1 | -3% / +12% | 20d | monthly |
| V4 | 20d | 3 | 1 | -2% / +10% | 20d | monthly |
| V5 | 20d | 3 | 1 | -3% / +12% | 20d | weekly (Monday open) |

V1 is the **prereg primary** for stability ranking.

Position sizing: each open position weighted 1/K of NAV at entry.
Cash earns 0%. No leverage. No shorts. Entry on rebal-day open;
exits intraday at bracket touch (HL approximation), else at
max-hold close.

## 6. Costs

Same as PREREG-0001: round-trip 0.30% (commission 0.015% × 2 +
slippage 0.20% + tax 0.23% on sells). Applied to gross returns.

## 7. Walk-forward windows

Same as PREREG-0001/3 for direct comparability:

| Window | Train | Test |
|---|---|---|
| W1 | 2020-01 .. 2022-12 | 2023-01 .. 2023-12 |
| W2 | 2021-01 .. 2023-12 | 2024-01 .. 2024-12 |
| W3 | 2022-01 .. 2024-12 | 2025-01 .. 2026-05-08 |
| FULL | n/a | 2023-01 .. 2026-05-08 |

Train periods are *unused for parameter tuning* (variants are
frozen above) but reported for sector stability sanity checks.

## 8. KPI gates (graduation)

A variant graduates only if **all** of the following hold on the
test set (FULL or windowed as specified):

| Gate | Threshold | Window |
|---|---|---|
| **G1 Alpha vs KOSPI200** | ≥ **+1.5%** annualised | FULL test |
| **G2 Hit-month** | ≥ **55%** months with positive alpha | FULL test |
| **G3 Max DD** | ≤ **20%** | FULL test |
| **G4 Window stability** | mean alpha > 0 in **all 3** of W1/W2/W3 | per-window |
| **G5 Primary rank** | V1 rank ≤ 3 of 5 in **each** of W1/W2/W3 by alpha | per-window |
| **G6 Sharpe** | ≥ **0.7** annualised | FULL test |

KOSPI200 benchmark is total-return; we approximate with KOSPI200
index price (without dividends) — small bias acknowledged, applies
equally to all variants.

## 9. Decision branches

| Branch | Variant V1 PASS? | Action |
|---|---|---|
| A | All 6 gates | Graduate V1 to paper-trade. |
| B | G1-G3 + G6 pass; G4-G5 borderline | Surface; consider V2/V3 as alternates if they pass cleanly. |
| C | G1 alpha passes but inconsistent windows | Reject V1; investigate variant V2-V5 for one-window-out-of-three failures only. No reformulation. |
| D | No variant passes G1 | A2 dead. Pivot to A1/A5 path or revisit data infrastructure. |
| E | Multiple variants pass cleanly | Pick V1 (primary). Note others as candidates for ensemble (separate ADR). |

## 10. Multiple-comparisons accounting

This PREREG declares **5 variants × 4 windows = 20 cells** (W1, W2, W3,
FULL × 5). With Bonferroni at family-wise α=0.05, individual cell
α=0.0025. We do not assert statistical significance per cell; we
rely on KPI threshold gates (above), which are economic not
statistical, plus G4 stability (out-of-sample replication).

Cumulative pre-registered cells across PREREG-0001/0002/0003/0004:
72 + 20 = **92 cells**. Family-wise discipline: any future
hypothesis must be PREREG'd before measurement.

## 11. Ex-ante predictions

If A2 *works* in KR market:
- IT_HW and HEALTH should dominate top-K most often (2024-26 chip+bio cycles).
- V2 (12w lookback) should outperform V1 in trending sub-periods.
- V5 (weekly rebal) should slightly underperform V1 net of higher costs.

If V2 outperforms V1 by a wide margin, that suggests our 4w-window
choice (plan literal) was sub-optimal — *flag in ADR but do not
re-tune*. Re-tuning is a graduation-eligibility violation.

## 12. Bias-prevention checklist

| Bias | Mitigation |
|---|---|
| Look-ahead | Sector membership static (snapshot 2026 Q1); ranking uses only data ≤ rebal date open. |
| Survivorship | Acknowledged: KOSPI top-80 + KOSDAQ list both static-as-of-2026Q1; expected effect small over 5y. |
| Universe selection | Frozen above (§2). H1 broadened universe re-used for apples-to-apples vs A4/A3. |
| Data-snooping | Variants frozen pre-measurement (§5). |
| Cherry-picking | Decision branches frozen (§9); all 20 cells will be reported. |
| Multiple comparisons | §10 cumulative budget tracked. |

## 13. Implementation

- Backtest engine: `research/a2_sector_rotation/exp_walkforward_a2.py`
  (new — A2 is portfolio-level, A4/A3 engine cannot be reused).
- Bars: `data/cache/kis_daily/` (existing).
- Sector map: `research/a2_sector_rotation/sector_map.csv`.
- Benchmark: KOSPI200 via KIS (ticker `0001` — or use index endpoint).
  If unavailable cleanly, fall back to equal-weighted basket of
  universe as benchmark; document choice in walkforward results.
