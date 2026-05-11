# PREREG-0008 Amendment 1 — CSV importer 폐기, KIS API 거래내역 fetch 단독 채택

**Status**: Active amendment
**Date**: 2026-05-11
**Base**: [PREREG-0008](PREREG-0008-tax-tool.md)
**Linked**: [ADR-0013](../adr/ADR-0013-phase3-kr-investor-tools.md)

---

## 변경 근거

PREREG-0008 §8.1 핵심 가정 "KIS HTS 거래내역 CSV 형식이 안정적이고 파싱 가능"의 변경.

본 세션 분석 (2026-05-11):

1. KIS Open API에 거래내역 조회 endpoint 존재 확인 — 공식 카테고리 "주문/계좌 조회"
   - 국내: `TTTC8001R` (일별 주문체결, 90일)·`CTSC9215R` (기간 손익)
   - 해외: `TTTS3035R`·`TTTS3012R`·`CTRP6504R`
2. 기존 SentinelQ `adapters/kis_broker.py`에 인증·토큰 인프라 보유, endpoint 추가만 필요
3. CSV export는 사용자 매년 수동 작업 부담 → 자동 fetch 우위 명확

사용자 결정: **KIS API 단독, CSV importer 폐기** (다중 증권사 확장 의도 없음, 단순성 우선).

## 변경 내역

### §2.1 거래내역 import (전면 교체)

기존:
```
| 증권사 | 형식 | 우선순위 |
| KIS | CSV export | P0 |
| 키움 | CSV export | P1 |
| ... | ... | P2 |
```

→ 변경:
```
| 증권사 | 형식 | 우선순위 |
| KIS (한국투자증권) | API fetch (REST endpoint) | P0 단독 |
```

다른 증권사 import는 §3 OUT으로 이동.

### §3 OUT 항목 추가

```
- 키움·미래에셋·토스 등 KIS 외 증권사 거래내역 import (별도 PREREG 필요)
- CSV importer 일반 라이브러리 (KIS 외 사용처 없음으로 폐기)
- 거래내역 수동 입력 UI (해당 없음)
```

### §4.1 모듈 구조 변경

기존:
```
adapters/csv_importer.py     🆕 표준 CSV import (폐기)
adapters/kis_history.py      🆕 거래내역 import
```

→ 변경:
```
adapters/kis_history.py      🆕 KIS REST 거래내역 fetch (확장)
  - inquire_overseas_period_trans  (해외주식 기간 거래내역)
  - inquire_domestic_daily_trans   (국내주식 일별 거래내역)
  - inquire_period_profit          (기간 손익 — G4 손실 인식 권장에 사용)
  - 페이지네이션 + rate limit 처리
  - 모의/실거래 환경 분리
```

### §4.2 신규 LOC 추정 변경

| 모듈 | 기존 LOC | 변경 LOC |
|---|---:|---:|
| `csv_importer.py` + `kis_history.py` | 200 | — |
| **`kis_history.py` (단일·확장)** | — | **250** |
| `tax_lots.py` | 150 | 150 |
| `tax/capital_gains.py` | 200 | 200 |
| `tax/deduction.py` | 150 | 150 |
| `tax/loss_harvesting.py` | 100 | 100 |
| `reports/nts_form.py` + `pdf_export.py` | 150 | 150 |
| `ports/*` | 50 | 50 |
| `scripts/run_tax_report.py` | 100 | 100 |
| 테스트 + fixtures | 200 | 200 |
| **합계** | **1,300** | **1,350** |

신규 LOC 약간 증가 (250 vs 200) — KIS API 페이지네이션·rate limit·환경 분리 처리 비용.

### §5 KPI Gate 변경

| Gate | 기존 | 변경 |
|---|---|---|
| **G1** | "본인 KIS 거래내역으로 2025 양도세 신고 자동 실행 (30분)" | "**본인 KIS 계정 인증 → 자동 fetch → 2025 양도세 신고 양식 출력 (전체 15분 이내)**" |
| **G2** | "KIS·키움 두 증권사 합산 손익통산 정확 (±1원)" | "**KIS API fetch 결과와 본인 2025 실제 양도세 신고 결과 비교 (±100원 일치)**" (truth value 1년치 한정) |
| G3·G4·G5·G6 | 변경 없음 | 변경 없음 |

G2 ±100원 허용 사유:
- KIS API 데이터에 환율·수수료 round-off 1~10원 단위 차이 가능
- 본인 실제 신고 결과는 NTS 시스템에 의한 최종값, KIS 데이터와 미세 차이 정상
- ±100원 미달이면 환율·수수료 round-off; 초과는 logic bug

### §6 Timeline 변경

기존 Week 1: "CSV importer + KIS 거래내역 fetch"

→ 변경 Week 1: **KIS API 거래내역 fetch 어댑터 (T001)** 단독

Week 2부터 1주씩 앞당김:

| Week | 작업 | KPI |
|---|---|---|
| 1 | KIS API 거래내역 fetch 어댑터 (kis_history.py) + 페이지네이션 | T001 PASS |
| 2 | FIFO tax_lots tracker + 기본 양도세 계산 (capital_gains.py) | T002·T003 PASS |
| 3 | 손익통산 + 250만원 공제 + 22% 세율 + 환율 처리 | G1 1차 통과 |
| 4 | 세제 한도 추적 (deduction.py) | G3 통과 |
| 5 | 12월 손실 인식 권장 (loss_harvesting.py) + NTS 양식 | G4 통과 |
| 6 | 테스트 + 본인 데이터 실증 + G1·G2·G3·G5·G6 평가 | 전체 |

**Week 7~8 grace 동일 (8주 hard stop 유지).**

### §8.1 핵심 가정 변경

기존:
```
1. KIS HTS 거래내역 CSV 형식이 안정적이고 파싱 가능
```

→ 변경:
```
1. KIS Open API 거래내역 endpoint (TTTS3035R·TTTC8001R 등)가 안정적이고
   페이지네이션·rate limit이 문서화된 한도 내에서 동작
1.1 KIS API 거래내역 제공 기간이 본인 양도세 검증에 충분 (G2 측정 가능)
   - Week 1 첫 작업에서 실제 fetch 한도 확인 후 미달 시 amendment-2 작성
```

### §8.2 위험 추가

| 위험 | 대응 |
|---|---|
| KIS API 거래내역 endpoint 기간 한도가 1년 미만 | Week 1 첫 fetch로 확인. amendment-2로 G2 truth value 정의 재조정 |
| API 페이지네이션·rate limit이 문서와 다름 | 백오프·재시도 로직 구현. 1일치씩 분할 fetch fallback |
| 모의/실거래 환경 분리 미준수 시 실거래 잘못 호출 | PREREG-0008 §3에 "Phase 1 paper-only" 명시. baseline.json `kis.required_env`에 `KIS_PAPER_MODE` 추가 |
| 본인 KIS 인증 정보 노출 위험 | `.env` + `secrets/kis_token.json` gitignore 등록 (기존) |

## §9 Out-of-band 변경 — Amendment-2 트리거

다음 발견 시 amendment-2 작성:

1. KIS API 거래내역 endpoint 기간 한도가 G2 검증 불가 수준 (예: 3개월 미만)
2. 페이지네이션 rate limit이 4년치 fetch에 24시간+ 소요
3. KIS API 거래내역 endpoint가 사용자 계정에서 미제공 (계좌 등급 등)

## §10 Sunk cost 점검

본 amendment의 도입 비용:
- 신규 LOC +50 (CSV importer 200 폐기 → kis_history 확장 +50)
- Week 1 작업 단순화 (1개 어댑터 단독)
- G2 검증 범위 4년 → 1년 축소 (정직한 측정 단위)

도입 후 이점:
- 사용자 매년 수동 export 사라짐 (단발적 인증만 필요)
- 자동 동기화 (Phase 2 DART 봇 + 분기 갱신)
- 코드 단순화 (CSV 어댑터 폐기)

**Sunk cost 분석**: Amendment 안 받았다면 사용자 매년 5월 30분~1시간 수동 작업 영구 부담. Amendment 도입은 1회성 +50 LOC로 그 부담 영구 제거. ROI 명확.

## Action Items

- [x] 본 amendment 작성
- [ ] `.claude/baseline.json` `active_prereg` 필드에 amendment-1 명시
- [ ] Week 1 T001 spec 작성: `Plan: KIS API 거래내역 fetch 어댑터 (kis_history.py)`
- [ ] Week 1 첫 fetch로 API 기간 한도 실측 → 기록 → 미달 시 amendment-2

## References

- PREREG-0008 §9 (Out-of-band 변경 규칙)
- ADR-0013 §Method (mandate 일관성 유지)
- 본 세션 WebSearch (2026-05-11): KIS Developers API 카테고리
- 기존 `sentinelq/adapters/kis_broker.py` 인증·토큰 인프라
- [KIS Developers 포털](https://apiportal.koreainvestment.com/apiservice)
- [koreainvestment/open-trading-api GitHub](https://github.com/koreainvestment/open-trading-api)
