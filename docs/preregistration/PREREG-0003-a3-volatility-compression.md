# PREREG-0003: A3 — Volatility Compression Breakout

**Status**: Active
**Created**: 2026-05-08
**Hypothesis**: A3 from plan v2.2 §6
**Linked**: [ADR-0003](../adr/ADR-0003-a4-a7-combined-failure.md) (A4+A7 dead → pivot to A3)

---

## 1. Why this prereg

A4 (raw) and A4+A7 (combined) declared not-viable in ADR-0002/0003. Plan
§6 lists A3 (Volatility Compression Breakout) as an alternative
hypothesis. A3 is mechanically opposite to A4: rather than buying spike
days, A3 buys days where volatility has collapsed and price breaks out
of a tight range. Failure modes are uncorrelated with A4's
regime-orthogonality, so A3's outcome is independent evidence.

This document freezes the search surface BEFORE any A3 measurement.

## 2. Plan-defined signal (plan §6 verbatim)

> 정의: ATR(20)이 직전 60일 최저 분위 20% 진입 후 거래량 동반 박스권
> 상단 돌파 시 추세 연장 경향.
>
> 진입 신호: ATR 분위 ≤ 20% + 20일 박스 상단 돌파 + 돌파 봉 거래량 ≥
> 평균의 1.5배.
>
> 청산: 진입 후 트레일링 스탑(ATR × 2) / 진입가 -2.5% 손절 / 추세선 이탈.
>
> 1차 KPI: 손익비(Profit Factor) ≥ 1.6, 평균 보유 기간 ≤ 15거래일.

## 3. Frozen signal definition (operationalised)

For each ticker on each day t:

```
atr20(t)           = ATR over past 20 days (Wilder)
atr20_pct_60d(t)   = percentile rank of atr20(t) within atr20[t-59..t]
box_high_20(t)     = max(high) over [t-19..t-1]
vol_ratio_20(t)    = volume(t) / mean(volume[t-19..t-1])

A3_TRIGGER(t) iff ALL:
    1. atr20_pct_60d(t-1) <= 0.20      (compression at prior close)
    2. close(t) > box_high_20(t)        (breakout on bar t)
    3. vol_ratio_20(t) >= 1.5           (volume confirmation)
    4. close(t) > open(t)               (positive bar; matches plan A4 pattern)
```

Entry: at close(t). Universe: same as PREREG-0001 (KOSPI top-80 +
delisted union; delisted file is empty placeholder per ADR-0002).

## 4. Frozen exit ladder

Per plan §6, with operational defaults aligned with A4 framework:

```
horizon (time exit)   = 15 trading days  (plan: "<= 15")
hard stop             = -2.5%             (plan literal)
trailing stop         = -ATR(14) * 2.0   (plan literal)
TP1                   = +5%, sell 50%     (operational; not plan-specified)
TP2                   = +12%, sell remainder (operational)
trend break exit      = close < SMA20      (proxy for "추세선 이탈")
```

The TP ladder is not plan-specified for A3 — locked here as the frozen
operational choice. Bonferroni budget below counts the TP variation as
a single tested ladder, not a search dimension.

## 5. Variants (locked)

| ID | Description | Notes |
|---|---|---|
| A3-V1 | Plan literal (above) | primary |
| A3-V2 | ATR pct <= 0.10 (tighter compression) | secondary |
| A3-V3 | Volume ratio >= 2.0 (tighter vol) | secondary |
| A3-V4 | Box high 40d (longer base) | secondary |
| A3-V5 | No SMA20 trend-break exit (let TP/stop run) | secondary |

5 variants × 4 windows = 20 test cells.

## 6. KPI gates

A3 graduates iff on test sides:

| KPI | Threshold | Source |
|---|---|---|
| Profit Factor | ≥ 1.6 | plan §6 |
| Avg holding period | ≤ 15 trading days | plan §6 |
| Net mean / trade | ≥ +1.20% | plan §7.3 (cross-cutting) |
| Hit rate | ≥ 50% | derived (PF≥1.6 + reasonable R:R implies ~50%) |
| Walk-forward stability | top variant rank stable across W1/W2/W3 (≤3) | this prereg |
| Bear-window alive | net mean > 0 in W1 test | this prereg |

Profit Factor = sum(net wins) / |sum(net losses)|. Computed on net
returns (after `costs.DEFAULT.net_return`).

## 7. Frozen test windows

Same as PREREG-0001 §5.

## 8. Out of scope (no amendment, no test)

- Different ATR window (locked at 20d)
- Different ATR-percentile lookback (locked at 60d)
- Different breakout box length (tested 20d primary, 40d as V4 only)
- Different volume window (locked at 20d)
- Sector or regime filtering (separate prereg if pursued)
- Entry timing other than close(t) (no intraday entry)

## 9. Multiple-testing budget update

Cumulative consumed: PREREG-0001 (28) + PREREG-0002 (24) = 52.
PREREG-0003 adds: 20.  Total: 72.  Bonferroni α/72 ≈ 0.00069.

## 10. Decision branches (predeclared)

- **A**: V1 graduates → A3 → Phase 0 alpha candidate
- **B**: V1 fails but another single Vk graduates → that Vk → re-prereg with single primary
- **C**: ≥2 Vk graduate but no rank stability → flag overfitting; do not promote
- **D**: No Vk graduates AND PF < 1.3 on all → kill A3 stream
- **E**: No Vk graduates BUT PF in [1.3, 1.6) on V1/V2 → A3 marginal; document as "not Phase 0 quality" but reservoir for ensemble

## 11. Amendments

(none yet)
