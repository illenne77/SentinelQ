# PREREG-0010: 패시브 리밸런싱 제안 (frozen scope)

**Status**: Frozen
**Date**: 2026-05-16
**Mandate**: ADR-0013 Phase 3 (SaaS Step 3)
**Linked**: [ADR-0013](../adr/ADR-0013-phase3-kr-investor-tools.md), [PREREG-0009](PREREG-0009-asset-tracker.md)

---

## 1. 목적 (Mandate)

KR 개인 투자자가 ETF 패시브 전략을 실행할 때 반복적으로 수동 계산하는
**목표 자산배분 유지·리밸런싱 실행 계획**을 자동화한다.

ADR-0011 §"자기자본 운용 전환 가이드"(ETF 패시브 + 세제 활용 + 행동통제)
권고를 실행 보조하는 도구이다.

---

## 2. Scope — IN

### §2.1 목표 자산배분 설정

- 사용자가 시장별 목표 비중(%)을 정의 (예: KR=30%, US=70%)
- JSON 파일 또는 CLI 인수로 입력
- 합계가 100%인지 검증

### §2.2 현재 vs 목표 배분 비교

- PREREG-0009 AfterTaxPortfolio에서 시장별 현재 평가금액 집계
- 목표 비중과 현재 비중 비교 → 편차(drift) 계산
- 발동 임계값(기본 ±5%): 어떤 시장이든 |편차| ≥ 임계값이면 리밸런싱 권장

### §2.3 리밸런싱 실행 계획

- 목표 금액 = 총 자산 × 목표 비중
- 매수/매도 필요 금액 = 목표 금액 - 현재 금액
- 매수/매도는 시장 단위 (종목 선정은 사용자 결정)

### §2.4 세금 영향 추정

- 매도 필요 시장의 AfterTaxPosition.estimated_tax_krw를 매도 비율만큼 안분
- 리밸런싱 전략 선택에 세금 비용 반영 (차별화 기능)

### §2.5 리밸런싱 리포트

- 텍스트 대시보드: 시장별 배분 표, 매수/매도 실행 가이드, 세금 영향
- CSV: 시장, 목표비중, 현재비중, 편차, 거래금액, 세금추정

### §2.6 리밸런싱 CLI

```
python scripts/run_rebalance.py --target KR=30 US=70
python scripts/run_rebalance.py --target-file targets.json --env live
```

---

## 3. Scope — OUT

| 항목 | 이유 |
|------|------|
| 종목 선정 (어떤 ETF/주식을 살지) | 투자 판단 영역 — 사용자 결정 |
| 시장 타이밍 (언제 리밸런싱할지) | ADR-0011 종결 (시장 타이밍 = NOT mandate) |
| 알파 발견·수익률 예측 | ADR-0011 종결 |
| 자동 주문 실행 | ADR-0011·0012 종결 (자동매매 금지) |
| 개별 종목 수준 리밸런싱 | MVP 범위 초과 (시장 단위만 지원) |
| 글로벌 지수 가격·시장 동향 데이터 조회 | 시장 타이밍 영역 진입 위험 |

---

## 4. 핵심 데이터 구조

```python
TargetAllocation  # 시장별 목표 비중 (%)
MarketAllocation  # 시장별 현재 vs 목표 배분 + 거래 필요금액
RebalancePlan     # 전체 리밸런싱 계획 (AfterTaxPortfolio 기반)
```

---

## 5. 차별화 포인트

증권사 앱의 리밸런싱 기능 대비:
- **세금 비용 포함**: 리밸런싱 시 발생하는 양도세 추정 포함 (단순 금액 계산이 아님)
- **다중 증권사 통합**: KIS + 키움 + 미래에셋 합산 기준 (Step 1 CSV 연계)
- **임계값 발동**: 매일 확인할 필요 없이 임계값 초과 시만 알림

---

## 6. 테스트 기준

- `sentinelq/portfolio/rebalance.py` coverage ≥ 90%
- `sentinelq/reports/rebalance_report.py` coverage ≥ 90%
- 단위 테스트: 빈 포트폴리오, 균형 포트폴리오, 임계값 경계, 세금 안분 등
