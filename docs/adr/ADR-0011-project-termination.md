# ADR-0011: 프로젝트 종료 결정

**Status**: Accepted (terminal)
**Date**: 2026-05-09
**Decision**: SentinelQ 프로젝트를 **종료(archive)**한다. 자기자본 운용은
ETF 기반 패시브 전략으로 전환한다.

## Context

본 프로젝트는 KR 주식 시장에서 시스템 트레이딩으로 자기자본 운용 시
ETF 패시브 대비 net 기대수익 우위를 확보하는 것을 목적으로 시작되었다.

6개월간의 작업 결과:

- **알파 후보 8개 모두 KPI 게이트 미통과** (A2/A3/A4/A6/A7/F01/F03/FF01)
- **A6**(외국인/기관 수급)은 데이터 부족으로 검증 불가 (KIS native depth 30일,
  pykrx 기능 손상). 누적까지 약 6개월 추가 대기 필요.
- **KOSPI200 honesty check (ADR-0010)** 결과, 실패의 일부는 알파 부재가 아니라
  EW 바스켓 구성이 메가캡 집중 강세장에서 cap-weighted 지수를 구조적으로
  이길 수 없다는 환경적 요인.
- 무료 데이터 + 1인 + KR-only + long-only 제약 안에서 graduated 알파에
  도달할 통계적 확률이 낮음을 확인.

## Decision

자기자본 운용 목적 관점에서 본 프로젝트의 추가 투자 한계효용은 **음(-)**
이라고 판단하여 종료한다.

근거:

1. **기대값 비교**

   | 운용 방식 | 연 net 기대 | 근거 |
   |---|---|---|
   | 본 프로젝트 알파 운용 | 5–6% | 6개월 8/8 실패, A6도 확률 낮음 |
   | KOSPI200 ETF 단순 | 7.5% | 장기 평균 |
   | ETF + 세제 활용 (ISA/연금/IRP) | 8.5% | 세액공제·비과세 |
   | ETF + 글로벌 분산 + 행동 통제 | 9–10% | 분산·behavior gap 회피 |

   알파 발견 확률 × 기대 알파 < ETF 패시브 운용의 기대 net 우위
   (세제 + 비용 + 행동편향 차단).

2. **개인 시스템 트레이더 수익 패턴 미스매치**

   학술적·실증적으로 개인이 시스템 트레이딩으로 net 수익을 내는 6가지 패턴
   (마이크로 비효율 / 도메인 우위 / 마이크로구조 / 변동성 매도 / CTA 트렌드
   / 암호화폐 차익) 중 본 프로젝트의 영역(KR 대형주 + EW + 가치/퀄리티)은
   학계가 30년 갈고닦은 가장 효율적이고 경쟁이 치열한 영역으로, 어느 패턴에도
   해당하지 않는다.

3. **매몰비용 회피**

   A6 데이터를 6개월 더 기다리는 것은 매몰비용 함정의 전형. A6가 통과하더라도
   net 우위가 ETF + 세제 활용을 능가할 확률은 낮다.

## Consequences

### 즉시 종료되는 항목

- 알파 연구 (A6 forward-collect 데몬 포함)
- Phase 0/1/2 추가 개발
- 모든 PREREG 작성·검증 작업
- KIS API 라이브 트레이딩 인프라

### 보존되는 자산 (archive)

repository는 read-only archive로 남기되, 다음은 학습/재사용 가치 있음:

- `docs/adr/` (10건의 실패 학습 기록)
- `docs/preregistration/` (PREREG 워크플로 템플릿)
- `sentinelq/portfolio/`, `sentinelq/risk/` (재사용 가능 모듈)
- `sentinelq/research/walkforward.py` (검증 프레임워크)
- `sentinelq/ports/`, `sentinelq/adapters/` (헥사고날 설계)

### 자기자본 운용 전환 가이드

본 프로젝트 종료 후 운용은 **단순 ETF 패시브 + 세제 활용**으로 전환:

1. **세제 우대 계좌 최대 활용** (가장 큰 확실 우위)
   - ISA 중개형: 연 200만원 × 5년 비과세, 만기 후 분리과세 9.9%
   - 연금저축 + IRP: 연 900만원 한도 세액공제 16.5% 즉시 환급
2. **저보수 글로벌 분산 ETF** (KR 단일 시장 메가캡 집중 위험 회피)
3. **자동이체 적립** (증권사 기능, 봇 불필요)
4. **분기 1회 리밸런스 캘린더 알림** (수동 관리)
5. **충동 매매 차단 장치** (시장 매일 안 보기, 뉴스 노출 최소화)

### 미해결 / 검증 안 된 가설

다음은 본 프로젝트에서 검증되지 못했고, 추후 재시도 시 단서:

- A6 (외국인·기관 수급) — 데이터 부족으로 미검증
- A-FW01 (cap-weighted top-N) — ADR-0010 후속, 미작성
- 멀티 자산 트렌드 추종 (CTA-style) — 본 프로젝트 룰 외
- 본인 도메인 정보우위 영역 5–10 종목 long-only — 시스템 외 영역

## Lessons Learned

### 방법론적 자산 (살아남는 가치)

1. **PREREG (Pre-registration)**: 백테스트 전 가설·변종·KPI 게이트를 동결.
   p-hacking 방지에 결정적. 다른 도메인에 그대로 이식 가능.
2. **Walk-forward 검증**: 단일 기간 백테스트의 함정을 회피. W1/W2/W3 분할이
   체제 변화 노출에 필수.
3. **ADR 누적**: 실패의 학습이 곧 자산. 10건의 ADR이 다음 의사결정의 근거.
4. **Honesty check (ADR-0010)**: 모든 백테스트는 다중 벤치마크(EW + cap-weighted)
   비교가 필수. 단일 벤치마크는 자기기만의 위험.

### 시장에 대한 학습

5. **2023–26 KR은 메가캡 집중 강세장.** 삼성전자 4.5×, KOSPI200 W3 CAGR +165%.
   EW 분산은 이 체제에서 구조적 열위. 시장 체제(regime)는 알파 설계의 외생 변수.
6. **거래비용 + 세금 + 슬리피지가 백테스트 알파의 50–80%를 잡아먹는다.**
   KR 거래세 23bps + 슬리피지 → 회전율 높은 전략은 시작부터 불리.
7. **단일 약한 알파 합산이 강한 알파보다 robust** (본 프로젝트는 단일 알파
   1개씩 검증, 합산 단계까지 가지 못함). 다음 시도 시 5–20개 알파 합산 설계 필수.

### 개인 운용에 대한 학습

8. **개인이 ETF를 이기는 거의 유일한 net 우위는 세제·비용·행동통제**, 알파 사냥이
   아니다. SPIVA·Dalbar 등 수십 년 데이터의 일관된 메시지.
9. **Behavior gap (행동 편향에서 오는 손실)이 알파 부재보다 큰 손실 원인**일 수
   있음. 시스템화의 진짜 가치는 수익 향상이 아니라 행동 차단.
10. **"내가 왜 돈을 번다고 생각하는지 한 문장으로 설명할 수 없다면, 시스템
    트레이딩을 하지 말 것."** 본 프로젝트의 가설들은 학술적 일반론이지
    본인만의 우위가 없었다.

## Action Items (종료 작업)

- [x] A6 forward-collect Windows 작업 스케줄 해제
- [x] README를 ARCHIVED 상태로 갱신
- [x] 본 ADR-0011 작성 및 커밋
- [x] 모든 pending/blocked todos를 'closed' 처리
- [x] 최종 커밋·푸시 후 repo는 read-only archive로 보존

## References

- ADR-0001 ~ ADR-0010 (8개 알파 실패 + KOSPI200 honesty check)
- SPIVA US Year-End Report (S&P)
- Dalbar QAIB Annual Report (behavior gap)
- Barber & Odean (2000), "Trading is Hazardous to Your Wealth"
- Asness, Moskowitz, Pedersen (2013), "Value and Momentum Everywhere"
- Investment Plan v2.2 (`Doc/investment_agent_plan_v2.2.docx`)
