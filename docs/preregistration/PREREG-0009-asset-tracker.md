# PREREG-0009: 자산관리 포트폴리오 대시보드

**Status**: Active
**Date**: 2026-05-16
**Mandate**: ADR-0013 Phase 3 (SaaS 유료구독 Step 2)
**Linked**: [PREREG-0008-amendment-2](PREREG-0008-amendment-2.md)

---

## 1. 목적

개인 투자자가 보유 포트폴리오의 **세후 실질 수익률**을 한눈에 확인한다.
증권사 앱이 세전 수익률만 제공하는 공백을 채운다.

---

## 2. Scope — IN

### 2.1 KIS 잔고 조회

| 기능 | 엔드포인트 |
|---|---|
| 국내주식 잔고 | `/uapi/domestic-stock/v1/trading/inquire-balance` (VTTC8434R) |
| 해외주식 잔고 | `/uapi/overseas-stock/v1/trading/inquire-balance` (VTTS3012R) |

반환 필드: 종목코드, 종목명, 보유수량, 평균단가(원), 현재가, 평가금액, 미실현 손익.

### 2.2 세후 수익률 계산

```
미실현 손익 = 현재평가금액 - 취득원가
예상 세금  = max(0, 미실현 손익 - 잔여기본공제) × 22%
  · 잔여기본공제 = max(0, 250만 - 당해 실현 손익)
세후 미실현 = 미실현 손익 - 예상 세금
세후 수익률 = 세후 미실현 / 취득원가 × 100%
```

### 2.3 포트폴리오 대시보드 리포트

- 종목별: 세전·세후 미실현 손익, 세후 수익률%
- 요약: 포트폴리오 전체 세후 수익률, 예상 세금
- 세제 한도 소진 현황 (기존 `deduction.py` 재사용)
- 출력: 텍스트 리포트 + CSV

### 2.4 CLI

```
python scripts/run_portfolio.py \
  --year 2025 \
  --fx-rates data/private/fx_rates.json \
  [--out data/output/]
```

---

## 3. Scope — OUT

```
- 타 증권사 잔고 API (P2 — CSV 잔고 파일은 별도 amendment)
- 실시간 시세 스트리밍 (웹소켓)
- 자동 리밸런싱 실행 (ADR-0011 금지)
- 배당·이자 수익 추적 (별도 PREREG)
- 복수 연도 수익률 (CAGR 등)
```

---

## 4. 모듈 구조

```
sentinelq/adapters/kis_history.py      기존 + HoldingRecord + inquire_*_balance (T013)
sentinelq/portfolio/after_tax.py       🆕 세후 수익률 계산 (T014)
sentinelq/reports/portfolio_report.py  🆕 포트폴리오 대시보드 리포트 (T015)
scripts/run_portfolio.py               🆕 CLI (T016)
```

---

## 5. 핵심 가정

1. KIS 잔고 API가 평균 취득단가를 제공함 (실측 후 미제공 시 TaxLotLedger로 계산).
2. 세후 수익률의 "예상 세금"은 당해 실현 손익 + 전액 매도 기준 시뮬레이션.
   정확한 세액은 실제 매도 시 결정됨 — 추정임을 리포트에 명시.
3. FX 환율은 --fx-rates 파일 또는 TaxLotLedger에 기록된 취득 환율 사용.

---

## References

- [PREREG-0008-amendment-2](PREREG-0008-amendment-2.md) — Step 1
- KIS Developers 포털: 잔고조회 `VTTC8434R`, `VTTS3012R`
