# PREREG-0008: A 도구 — 양도세 + 세제 한도 자동 계산기 (frozen scope)

**Status**: Frozen
**Date**: 2026-05-11
**Mandate**: ADR-0013 Phase 3
**Linked**: [ADR-0013](../adr/ADR-0013-phase3-kr-investor-tools.md)

---

## 1. 목적 (Mandate)

KR 개인 투자자가 매년 5월 양도세 신고 시 수동 처리하는 다음 작업을 자동화한다:

1. 다중 증권사 거래내역 통합·손익통산·양도세 계산
2. IRP+연금저축+ISA 한도·세액공제 추적
3. 12월 손실 인식 권장 (손익통산 최적화)

본 도구는 **본인 사용 우선**, 외부 공개는 Phase 3 후속 단계 (G1·G2·G3 통과 후) 결정.

## 2. Scope — IN

### 2.1 거래내역 import

| 증권사 | 형식 | 우선순위 |
|---|---|---|
| 한국투자증권 (KIS) | CSV export (HTS 거래내역 조회) | P0 |
| 키움증권 | CSV export | P1 |
| 미래에셋증권 | CSV export | P1 |
| 토스증권 | CSV export | P2 |
| 신한투자증권 | CSV export | P2 |
| 기타 | 표준 CSV format | P2 |

매수·매도·배당·환전·세금 항목 모두 처리.

### 2.2 양도세 계산 룰 (KR 2026 기준)

```
국내·해외 합산:
  - 기본공제: 연 250만원
  - 세율: 22% (지방소득세 포함)
  - 신고기간: 다음 해 5월 1일~31일
  - 손익통산: 같은 과세기간(1.1~12.31) 내 가능
  - 이월공제: 불가
  - 단일종목 wash sale 규제 없음 (익영업일 재매수 시 손실 인정)
  
계산 순서:
  1. 매도 종목별 양도차익·양도차손 계산 (선입선출 FIFO)
  2. 국내·해외 통산
  3. 250만원 공제
  4. 잔여 × 22% = 양도세
  5. 배당소득은 별도 처리 (15.4% 원천징수)
```

### 2.3 세제 우대 한도 추적

| 계좌 | 연 한도 | 누적 한도 | 세액공제 |
|---|---:|---:|---|
| 연금저축 | 600만원 | 무제한 | 13.2% (총소득 5500만↓ 시 16.5%) |
| 연금저축 + IRP 합산 | 900만원 | 무제한 | 동일 |
| ISA 일반형 | 2000만원 | 5년 1억 | 비과세 500만원/5년 |
| ISA 서민형 | 2000만원 | 5년 1억 | 비과세 1000만원/5년 |

납입액 추적 + 잔여 한도 + 예상 세액공제액 표시.

### 2.4 손실 인식 권장 (12월 한정)

```
조건 발동: 12월 1일~30일 사이
계산: 당해 누적 실현 양도차익 - 잠재 손실 인식 (보유 종목 미실현 손실)
권장: 양도차익이 250만원을 초과할 경우, 미실현 손실 중 통산 가능 분량 권장
주의: 단순 추천만 표시, 자동 매매 X
```

### 2.5 출력

- 양도세 신고서 폼 (NTS 홈택스 입력용 항목별)
- 세제 한도 남은 금액 시각화
- 손익통산 최적화 시뮬레이션 (12월 한정)
- CSV/PDF export

## 3. Scope — OUT (명시적 제외)

다음은 본 PREREG에 포함되지 않으며, 별도 후속 PREREG 없이는 구현 금지:

- 자동 매매 (KIS API 주문 호출)
- 시장 타이밍·매매 시그널·알파 발견
- 백테스트·walk-forward (Phase 0~2 영역, 미사용)
- 위험 엔진 통합 (Phase 4+ 이상)
- DART 공시 모니터링 (B 도구 = PREREG-0009)
- 다중 사용자·계정 시스템 (외부 공개 후 결정)
- 모바일 앱 UI (Phase 3 외부 공개 단계 결정)
- 실시간 시세·차트
- 회계 처리·세무사 보고서
- 비KR 거주자 양도세

위 항목들은 scope creep 방지를 위해 동결됨. 추가 시 별도 PREREG 작성 후.

## 4. Architecture

### 4.1 모듈 구조 (신규·재사용)

```
sentinelq/
  adapters/
    kis_data.py          ✅ 재사용 (가격·시세)
    kis_broker.py        ✅ 부분 재사용 (거래내역 fetch endpoint 추가)
    kis_history.py       🆕 거래내역 import
    csv_importer.py      🆕 키움·미래에셋·토스 등 표준 CSV import
  portfolio/
    portfolio.py         ✅ 70% 재사용 (FIFO 평단·실현 손익 계산)
    tax_lots.py          🆕 양도세 lot tracking (FIFO)
  tax/                   🆕
    capital_gains.py     🆕 양도세 계산 엔진
    deduction.py         🆕 세제 우대 한도 추적
    loss_harvesting.py   🆕 12월 손실 인식 권장
  reports/               🆕
    nts_form.py          🆕 홈택스 신고 양식
    pdf_export.py        🆕 PDF 출력
  ports/
    tax_port.py          🆕 TaxCalculator interface
    report_port.py       🆕 Reporter interface
scripts/
  run_tax_report.py      🆕 엔드투엔드 CLI
tests/
  test_tax_*.py          🆕 양도세 계산 정확성 테스트
  fixtures/              🆕 KIS·키움·미래에셋 sample CSV
```

### 4.2 신규 LOC 추정

| 모듈 | 추정 LOC |
|---|---:|
| `csv_importer.py` + `kis_history.py` | 200 |
| `tax_lots.py` (FIFO lot tracker) | 150 |
| `tax/capital_gains.py` | 200 |
| `tax/deduction.py` | 150 |
| `tax/loss_harvesting.py` | 100 |
| `reports/nts_form.py` + `pdf_export.py` | 150 |
| `ports/*` 신규 인터페이스 | 50 |
| `scripts/run_tax_report.py` | 100 |
| 테스트 + fixtures | 200 |
| **합계** | **1,300 LOC** |

기존 1,327 LOC + 신규 1,300 LOC = 약 2,600 LOC 도구 완성형.

## 5. KPI Gates (graduation 기준)

| Gate | 조건 | 측정 |
|---|---|---|
| **G1** | 본인 KIS 거래내역으로 2025 양도세 신고 자동 실행 | 30분 안에 NTS 양식 출력 |
| **G2** | KIS·키움 두 증권사 합산 손익통산 정확 | 수동 계산과 ±1원 일치 |
| **G3** | 세제 한도 추적 정확 (IRP+연금+ISA) | 증권사 공식 잔여한도와 일치 |
| **G4** | 12월 손실 인식 권장이 실제 절세 효과 입증 | 시뮬레이션으로 +100만원 절세 시나리오 1건+ |
| **G5** | 단위테스트 커버리지 ≥ 80% (tax/ 모듈) | pytest --cov |
| **G6** | 본인 사용 가치 연 50만원+ 입증 | Phase 2 시작 전 자기 평가 문서 작성 |

**G1~G3 모두 통과 시 Phase 1 완료 인정.** G6 미통과 시 외부 공개 단계(Phase 3) 진입 보류.

## 6. Timeline & Milestones

| Week | 작업 | 산출물 |
|---|---|---|
| 1 | CSV importer + KIS 거래내역 fetch | KIS export 파일 정상 파싱 |
| 2 | FIFO lot tracker + 기본 양도세 계산 | 단순 매매 케이스 정확 |
| 3 | 손익통산 + 250만원 공제 + 22% 세율 | G1 1차 통과 |
| 4 | 세제 한도 추적 모듈 | G3 통과 |
| 5 | 12월 손실 인식 권장 + NTS 양식 | G4 통과 |
| 6 | 테스트 + 본인 데이터 실증 + 문서 | G1·G2·G3·G5·G6 통과 |

**총 4~6주.** 6주 초과 시 scope 재검토 + ADR-0014 작성.

## 7. Decision Rules

### 7.1 Graduation (성공)

G1·G2·G3·G6 모두 통과 → Phase 2 (B 도구) 진행 결정

### 7.2 Pivot (조건부)

- G1·G2·G3는 통과하나 G6 미통과 (본인 사용 가치 < 50만원/년) → Phase 2 보류, 본 도구만 유지
- G1·G2·G3 중 일부만 통과 → 6주 초과 시 ADR-0014 작성, scope 축소

### 7.3 Rejection (실패)

- 6주 + 2주 grace = 총 8주 안에 G1 미통과 → 본 PREREG 폐기, ADR-0014 NO-GO
- 본 ADR-0013의 G1 stop 조건 발동

### 7.4 Bias prevention

- **Scope creep 방지**: §3 OUT 항목 추가 시 본 PREREG 동결, 별도 후속 PREREG 작성
- **Sunk cost 방지**: 6주 안에 G1 미통과면 즉시 종료, "조금만 더"는 ADR-0006 함정
- **본인 사용 가치 입증 강제**: G6를 통한 외부 공개 전 baseline 확인 의무

## 8. Risk & Assumptions

### 8.1 핵심 가정

1. KIS HTS 거래내역 CSV 형식이 안정적이고 파싱 가능
2. NTS 2026년 양도세 룰이 본 PREREG 작성 시점과 일치 (큰 변동 시 ADR-0014)
3. 본인이 1개 이상 증권사 거래내역을 보유 (테스트 가능)

### 8.2 알려진 위험

| 위험 | 대응 |
|---|---|
| 증권사 CSV 포맷 변경 | 표준 어댑터로 추상화, 변경 시 adapter만 수정 |
| 양도세 룰 개정 | 핵심 룰을 config 분리, 매년 5월 전 검토 |
| 본인 거래량 부족으로 테스트 한계 | 가상 거래 fixtures로 보완 |
| 환율·세금 round-off 오차 | round-half-even, NTS 공식 가이드 반영 |

### 8.3 NOT 가정

- 외부 사용자 확보 (Phase 3 외부 공개 단계에서 검증)
- 마케팅·SEO·앱스토어 노출 (PREREG-0010+ 영역)
- 수익화 (PREREG-0010+ 영역)

## 9. Out-of-band 변경

본 PREREG는 다음 사유로만 수정 가능:

- KR 세제 룰 개정 (필수)
- 핵심 가정 §8.1 위반 (조건 변경)
- G1~G6 게이트 측정 방법 불명확 (clarification만, 게이트 자체 변경 X)

수정 시 본 PREREG는 동결 유지하고 PREREG-0008-amendment-N 형태 별도 문서로 추가.

## References

- ADR-0013 (mandate)
- ADR-0011 lesson 6, 8 (세제·비용 우위)
- 국세청 [국외주식 양도소득세 안내](https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=8800)
- [한국투자증권 해외주식 수수료·환전](https://securities.koreainvestment.com/main/customer/guide/_static/TF04ae010000.jsp)
- 본 세션 분석 (2026-05-11 WebSearch): wash sale 규제 부재, 익영업일 재매수 시 손실 인정
