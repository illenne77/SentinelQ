# SentinelQ — ARCHIVED

**Status**: 🛑 **ARCHIVED (terminated 2026-05-09)**

이 저장소는 종료된 KR 주식 시스템 트레이딩 연구 프로젝트의 read-only archive입니다.
종료 결정과 근거는 [`docs/adr/ADR-0011-project-termination.md`](docs/adr/ADR-0011-project-termination.md) 참조.

## 결과 요약

- **6개월 작업, 알파 후보 8개 검증, graduated 0개** (A2 / A3 / A4 / A6-blocked / A7 / F01 / F03 / FF01)
- KOSPI200 honesty check (ADR-0010) 결과, 실패의 구조적 원인은 2023–26 KR 메가캡
  집중 강세장에서 EW 바스켓이 cap-weighted 지수를 구조적으로 이길 수 없다는 환경 요인
- 무료 데이터 + 1인 + KR-only + long-only 제약 안에서 graduated 알파 도달 확률
  통계적으로 낮음을 실증
- 자기자본 운용 목적 관점에서 ETF 패시브 + 세제 활용 + 행동 통제 대비 기대값 열위
  결론, 종료 결정

## 알파 시도 기록

| 알파 | 가설 | 결과 | ADR |
|---|---|---|---|
| A2 | 섹터 로테이션 | FAIL | ADR-0006 |
| A3 | 변동성 압축 | FAIL | ADR-0004 |
| A4 | 유동성 급증 | FAIL | ADR-0001/2/3 |
| A6 | 외국인·기관 수급 | BLOCKED (데이터 30일 한계) | — |
| A7 | A4 결합 | FAIL | ADR-0003 |
| A-F01 | Book-to-Market | FAIL | ADR-0007 |
| A-F03 | Gross Profit/Assets | FAIL | ADR-0008 |
| A-FF01 | V+Q 멀티팩터 | FAIL | ADR-0009 |
| (honesty) | KOSPI200 재비교 | 모두 더 큰 음의 알파 | ADR-0010 |
| (final) | 종료 결정 | — | ADR-0011 |

## 살아남는 자산 (재사용 가치 있음)

```
docs/adr/                10건의 실패 학습 기록 (ADR-0001 ~ ADR-0011)
docs/preregistration/    PREREG 워크플로 템플릿 (p-hacking 방지)
sentinelq/portfolio/     Fill-driven 포트폴리오 부기
sentinelq/risk/          7-gate 사전거래 위험 엔진
sentinelq/research/      Walk-forward 검증 프레임워크
sentinelq/ports/         Hexagonal port 추상화 (DataPort/ClockPort/BrokerPort)
sentinelq/adapters/      KIS REST 어댑터 + 페이퍼 브로커
scripts/paper_trade.py   엔드투엔드 페이퍼 트레이드 하니스
tests/                   pytest 스모크
```

이 모듈들은 다른 도메인·시장 (미국 ETF, 멀티자산 CTA, 본인 도메인 종목 등)에
그대로 또는 부분 이식 가능. **방법론(PREREG + Walk-forward + ADR + Honesty
check)은 자산으로 살아남음.**

## 학습 정리

### 시장에 대한 학습

1. 2023–26 KR은 메가캡 집중 강세장 (삼성전자 4.5×, KOSPI200 W3 CAGR +165%).
   EW 분산은 이 체제에서 구조적 열위.
2. KR 거래세 23bps + 슬리피지가 회전율 높은 전략을 시작부터 불리하게 만듦.
3. 무료 데이터 풀에서 가능한 가설은 학계가 30년 갈고닦은 가장 효율적인 영역.
   개인 신규 알파 발견 확률 낮음.

### 방법론에 대한 학습

4. PREREG·Walk-forward·다중 벤치마크 honesty check는 자기기만 방지에 필수.
5. 단일 약한 알파 1개 검증 → 1개 폐기 사이클은 비효율. 5–20개 알파 합산이
   학술적으로 더 robust.

### 개인 운용에 대한 학습

6. **개인이 ETF를 이기는 거의 유일한 net 우위는 알파 사냥이 아니라 세제·비용·
   행동통제.** SPIVA·Dalbar 등 수십 년 일관된 메시지.
7. Behavior gap (충동 매매·panic-sell)이 알파 부재보다 큰 손실 원인일 수 있음.
8. **"내가 왜 돈을 번다고 생각하는지 한 문장으로 설명 못 하면, 시스템
   트레이딩 하지 말 것."**

## 자기자본 운용 전환 가이드

본 프로젝트 종료 후 운용 방향:

1. **세제 우대 계좌 최대 활용**
   - ISA 중개형: 연 200만원 × 5년 비과세
   - 연금저축 + IRP: 연 900만원 한도 세액공제 16.5%
2. **저보수 글로벌 분산 ETF** (KR 단일 시장 메가캡 집중 회피)
3. **자동이체 적립** (증권사 기능 활용, 봇 불필요)
4. **분기 1회 리밸런스** (캘린더 알림)
5. **충동 매매 차단** (시장 매일 안 보기, 뉴스 노출 최소화)

## 라이선스

Proprietary. Archived. All rights reserved.
