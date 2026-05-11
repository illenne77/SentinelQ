# ADR-0013: SentinelQ Archive 해제, Phase 3 mandate (KR Investor Tools)로 재출범

**Status**: Accepted (re-activates archived project)
**Date**: 2026-05-11
**Linked**: [ADR-0011](ADR-0011-project-termination.md), [ADR-0012](ADR-0012-direction-b-prime-no-go.md)

---

## Context

ADR-0011(2026-05-09)은 알파 사냥 mandate의 종료를 결정했고, ADR-0012
(2026-05-11)는 그 후속으로 검토된 방향 B'(Personal Index Bot + TLH)도
사용자 조건(KR 증권사 + 자금 5천만원 미만)에서 NO-GO 결론을 내렸다.

본 ADR은 그 두 결정을 **유지**하면서, 본 프로젝트에 축적된 코드·데이터·
워크플로 자산을 **다른 mandate로 재활용**할지에 대한 검토 결과이다.

### 보유 자산 인벤토리

코드 (총 1,327 LOC + 12개 스크립트):

| 모듈 | LOC | 가치 영역 |
|---|---:|---|
| `adapters/kis_*` | 308 | KIS REST 인증·시세·주문 |
| `portfolio/portfolio.py` | 255 | Fill-driven 부기 |
| `risk/engine.py` | 262 | 7-gate 사전거래 위험 체크 |
| `research/walkforward.py` | 310 | 검증 프레임워크 |
| `ports/` | 145 | 헥사고날 추상화 |
| `scripts/dart_*` (3) | — | DART 펀더멘털 백필 |
| `scripts/kis_*` (5) | — | KIS 데이터 수집·토큰 |

데이터:
- `dart/equity_quarterly.parquet`, `dart/income_assets_annual.parquet` (KR 분기·연 펀더멘털)
- `kis_daily/*.parquet` (136 종목 × 5년 일봉)

문서:
- ADR 12건 (실패 학습) + PREREG 7건

### 후보 프로젝트 평가

8개 재활용 후보 중 ROI·인프라 재사용·차별화 면에서 다음이 선정됨:

**A. 양도세 + 세제 한도 자동 계산기** (Phase 1 우선)

- 본인 사용 가치: 매년 5월 양도세 신고 시간 절약, 손익통산 최적화, IRP+연금+ISA 한도·세액공제 추적
- 인프라 재사용: 70% (portfolio/, adapters/kis_*, ports/)
- 외부 가치: KR 해외주식 신고자 50~80만명 시장

**B. DART 공시 모니터링 + 알림 봇** (Phase 2)

- 본인 사용 가치: 보유 종목 공시 즉시 알림, 정보 우위 → 큰 손실 회피
- 인프라 재사용: 80% (scripts/dart_*, ports/, DART 데이터셋)
- 외부 가치: KR 적극 투자자 20~50만명 시장

탈락 후보:
- C (다중 계좌 재무 대시보드): A+B의 자연 확장이므로 별도 mandate 불필요
- D (Korean Equity Fundamentals 공개 데이터셋): 일회성·외부 가치 작음
- E (KIS Python SDK): pykis 등 기존 라이브러리와 차별화 어려움
- F (PREREG 백테스트 프레임워크): Backtrader/vectorbt 등 강력한 기존 도구 존재, 본인이 알파 사냥 안 함
- G (SentinelQ 케이스 스터디 출판): 코드 무관, 문서 작업으로 별도 진행 가능
- H (TDF 복제 시뮬레이터): walk-forward 재사용은 좋으나 본인 사용 가치 작음

## Decision

**SentinelQ archive 상태를 해제하고 Phase 3: KR Investor Tools
mandate로 재출범한다.** ADR-0011 알파 사냥 종료 결정과 ADR-0012
방향 B' NO-GO 결정은 **유지**되며, 본 mandate는 그와 무관한 새 영역이다.

새 mandate 정의:

```
mandate : KR 개인 투자자가 매년·매월 반복적으로 수동 처리하는
         양도세 신고·세제 한도 관리·공시 모니터링을 자동화하는
         도구를 본인 사용 + 외부 공개 형태로 개발한다.

NOT mandate : 알파 발견, 자동매매, 시장 타이밍, 수익률 향상.
             이 영역은 ADR-0011·0012에 의해 종결되었다.
```

## Method

### 가설 (lesson 10 한 문장 우위)

> "KR 투자자가 다중 증권사 거래내역 통합 + 양도세 손익통산 + DART
> 공시 알림을 한 곳에서 처리하는 도구는 현재 부재하며, 본 프로젝트
> 인프라(KIS·DART 어댑터 + 포트폴리오 부기)는 이 빈틈을 다른
> 신규 진입자보다 빠르게 메울 수 있다."

차별화 가능성 평가:

| 경쟁 | 강점 | 본 프로젝트 차별 |
|---|---|---|
| 택스고·taxly.kr (양도세) | 무료·UI | 다중 증권사 통합·자동 import 부족 |
| 38커뮤니케이션·다트 (공시) | 정보량 | 보유종목 맞춤·즉시 알림 약함 |
| 증권사 앱 자체 기능 | 통합·신뢰 | 자기 거래만 처리, 타사 합산 X |
| **본 프로젝트** | A+B+다중 증권사 통합 | 빈틈 정확히 노림 |

차별화 지속성 한계: 증권사가 다중계좌 통합 기능 구현 시 사라짐 (1~3년 윈도 추정).

### 기대값 base case

| 가치 원천 | 연 환산 |
|---|---:|
| 본인 사용 (양도세 자동·공시 알림·시간 절약) | +55~370만원 |
| 외부 수익 base case (월 30~50만원, 1년 운영 후) | +360~600만원 |
| 평판·포트폴리오·옵션 자산 | 정량 어려움 |
| **합계 base** | **연 415~970만원** |

기대값 distribution (1년 후):

| 결과 | 확률 |
|---|---:|
| 본인 사용만 + 외부 월 5만원 미만 | 40% |
| 본인 사용 + 외부 월 10~50만원 | 30% |
| 본인 사용 + 외부 월 50~150만원 | 20% |
| 외부 월 150만원+ | 10% |

기대값 = 월 평균 49만원 (외부 수익) + 본인 가치.

### Stop 조건 (KPI 게이트)

다음 조건 미달 시 본 mandate도 종료:

- [G1] **Phase 1 (A 도구) 4~6주 안에 본인 양도세 신고 자동 실행 도달**: 매년 5월 30분 안에 신고 완료 가능해야 함
- [G2] **Phase 2 (B 도구) 후 본인 보유 종목 공시 누락률 < 10%**: 알림 시스템 신뢰성 검증
- [G3] **Phase 1+2 완료 시점에 본인 사용 가치 연 50만원+ 입증**: 본인 사용 가치가 base case 하한 미달이면 외부 공개 불필요
- [G4] **외부 공개 후 6개월 안에 누적 다운로드·스타 100건+ 도달**: 마케팅 채널 가능성 검증
- [G5] **외부 공개 후 12개월 안에 월 수익 10만원+ 도달**: base case 시나리오 중 최소 25분위 달성

G1·G2·G3 중 1개라도 미통과 시 본 ADR도 NO-GO 처리하고 archive 재돌입.

## Consequences

### 즉시 변경

- README의 `ARCHIVED` 표기 제거
- Phase 3 mandate 섹션 추가
- ADR-0011·0012는 history로 보존 (re-affirm하지 않음, 영역이 다름)

### 신규 작업

- PREREG-0008 (A 도구 frozen scope, 본 ADR 후속)
- 인프라 재사용 매핑 plan (별도 문서)
- Phase 1 MVP 개발 4~6주
- Phase 2 MVP 개발 3~4주 (선택)
- Phase 3 외부 공개 3~6개월 (선택, G1·G2·G3 통과 후만)

### 폐기 또는 동결

- 알파 사냥 (ADR-0011 그대로)
- 방향 B' (TLH 봇, ADR-0012 그대로)
- Walk-forward 검증 인프라 (`research/walkforward.py`)는 archive 모듈로 유지하되 Phase 3에서 미사용
- PREREG-0001~0007은 history로 보존

### ADR-0011 권고와의 일관성

ADR-0011 §"자기자본 운용 전환 가이드"(ETF 패시브 + 세제 활용 + 행동
통제)는 **그대로 유효**. Phase 3의 A 도구가 그 권고를 실행 보조함:

- ETF 패시브 → 본 도구 외부 영역
- **세제 활용** → A 도구 (IRP+연금+ISA 한도 추적·세액공제 예상) 직접 보조
- 행동 통제 → 본 도구 외부 영역 (앱 삭제·시장 안 보기로 달성)

### 인지 편향 점검 (lesson 10 자기 평가)

본 ADR이 SentinelQ 6개월 환상 사이클을 반복하지 않는다는 근거:

1. **수익 가설이 명확한 distribution을 가짐**: 평균 월 49만원 (외부), 본인 가치 55~370만원/년 (확실)
2. **가설이 학계 검증 영역과 분리됨**: 시장 효율성·시장 타이밍과 무관, 사용자 통점 해결
3. **시장이 매우 좁고 차별화 지속성 1~3년**: 단기 윈도, 장기 정당화 X
4. **본인 사용 가치만으로 baseline ROI 확보**: 외부 수익 0이어도 손해 안 봄
5. **명시적 stop 조건**: G1~G5 미통과 시 archive 재돌입

이 5개 점검은 ADR-0011 lesson 10·11·12·13·14를 본 프로젝트에 적용한 것이다.

## Action Items

- [x] 본 ADR-0013 작성
- [ ] README.md 갱신 (ARCHIVED 제거 + Phase 3 mandate)
- [ ] PREREG-0008 작성 (A 도구 frozen scope)
- [ ] 인프라 재사용 매핑 plan 문서 (`docs/phase3-infra-mapping.md`)
- [ ] Phase 1 MVP 개발 시작
- [ ] (G1~G3 통과 후) Phase 2 MVP 개발
- [ ] (G1~G3 통과 후) Phase 3 외부 공개 형태 결정

## References

- ADR-0011 (알파 사냥 종료, base mandate)
- ADR-0012 (방향 B' NO-GO, TLH 검토)
- Lesson 8 (개인 net 우위 = 세제·비용·행동통제)
- Lesson 10 (한 문장 우위)
- Lesson 11~14 (방향 B' 검토 추가 lessons)
- NTS 2025 해외주식 양도세 통계 (50~80만명 신고)
- Statista 2024 KR 1인 개발자 부업 수익 분포
- 본 세션 분석: 일일 0.5% 환상·월 150만원 환상 → 월 30~50만원 base case 수용
