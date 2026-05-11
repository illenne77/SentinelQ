# SentinelQ

**Status**: Active — Phase 3 (KR Investor Tools) — re-activated 2026-05-11

KR 개인 투자자를 위한 자동화 도구 프로젝트.
재출범 결정과 mandate는 [`docs/adr/ADR-0013-phase3-kr-investor-tools.md`](docs/adr/ADR-0013-phase3-kr-investor-tools.md) 참조.

## 현재 mandate (Phase 3)

KR 개인 투자자가 매년·매월 반복적으로 수동 처리하는 **양도세 신고·세제
한도 관리·DART 공시 모니터링**을 자동화하는 도구를 본인 사용 + 외부
공개 형태로 개발한다.

**NOT mandate**: 알파 발견·자동매매·시장 타이밍·수익률 향상. 이 영역은
ADR-0011·0012에 의해 종결되었다.

## Phase 3 도구 (개발 중)

| 도구 | 기능 | 상태 | 인프라 재사용 |
|---|---|---|---:|
| **A. 양도세 + 세제 한도 자동 계산기** | 다중 증권사 거래내역 통합, 손익통산 + 250만원 공제 + 22% 세율 자동, IRP+연금+ISA 한도·세액공제 추적, 12월 손실 인식 권장 | Phase 1 (4~6주) | 70% |
| **B. DART 공시 모니터링 + 알림 봇** | 보유 종목 공시 즉시 폴링, 텔레그램·이메일 알림, 공시 유형 필터 | Phase 2 (3~4주, G1·G2·G3 통과 후) | 80% |

## 살아남는 자산 (Phase 3에서 재사용)

```
docs/adr/                13건의 학습 기록 (ADR-0001 ~ ADR-0013)
docs/preregistration/    PREREG 워크플로 템플릿 (Phase 3 PREREG-0008 진행)
sentinelq/portfolio/     Fill-driven 포트폴리오 부기 (A 도구 70% 재사용)
sentinelq/risk/          7-gate 사전거래 위험 엔진 (Phase 4 이상에서 사용)
sentinelq/ports/         Hexagonal port 추상화 (A·B 도구 어댑터 추가)
sentinelq/adapters/      KIS REST 어댑터 (A 도구 거래내역 fetch)
sentinelq/research/      Walk-forward 검증 (Phase 3 미사용, 보존)
scripts/dart_*           DART 펀더멘털 백필 (B 도구 100% 재사용)
scripts/kis_*            KIS 데이터·토큰 (A·B 도구 부분 재사용)
data/cache/dart/         KR 펀더멘털 데이터셋 (B 도구 보조)
```

## 프로젝트 사이클 history

### Phase 0~2: 알파 사냥 (2025-11 ~ 2026-05) — TERMINATED

6개월간 KR 주식 시스템 트레이딩 알파 후보 8개 검증. 결과:

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
| (termination) | 종료 결정 | — | ADR-0011 |

**60 frozen cells / 0 graduated.** KOSPI200 honesty check 결과 실패의
구조적 원인은 2023–26 KR 메가캡 집중 강세장에서 EW 바스켓이
cap-weighted 지수를 구조적으로 이길 수 없는 환경 요인. ADR-0011 참조.

### Phase 2.5: 방향 B' 검토 (2026-05-11) — NO-GO

ETF 운용보수 vs 봇 우위 가설을 Personal Index Bot + Tax-Loss
Harvesting 형태로 검토. 사용자 조건(KR 증권사만 가능 + 자금 5천만원
미만)에서 net -30~80만원/년 적자 추정으로 NO-GO 결론. 재검토 트리거:
IBKR LLC 한국 거주자 가능 + 자금 1억+. ADR-0012 참조.

### Phase 3: KR Investor Tools (2026-05-11 ~) — ACTIVE

위 두 결정을 유지하면서 축적된 인프라를 KR 투자자 자동화 도구로
재활용. 본 mandate는 알파 사냥과 무관한 별개 영역. ADR-0013 참조.

## 학습 정리 (Phase 0~2 결산)

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

6. **개인이 ETF를 이기는 거의 유일한 net 우위는 알파 사냥이 아니라 세제·
   비용·행동통제.** SPIVA·Dalbar 등 수십 년 일관된 메시지.
7. Behavior gap (충동 매매·panic-sell)이 알파 부재보다 큰 손실 원인일 수 있음.
8. **"내가 왜 돈을 번다고 생각하는지 한 문장으로 설명 못 하면, 시스템
   트레이딩 하지 말 것."**

### 봇 운용에 대한 학습 (방향 B' 검토 추가)

9. 운용보수 < 봇 우위 가설은 매매 수수료 환경에서 검증해야 함. 미국
   wealth-tech의 TLH +0.5~1.5% pa 우위는 0~5bps 매매 수수료 환경의 결과.
   KR 25bps 환경에서는 재현 불가.
10. TLH 효과는 운용 자금 절대 규모에 선형 확대. Break-even 자금 규모는
    KR 환경에서 1억원 이상.
11. 자동매매로 일일 +0.5~1% 수익률 가설은 SentinelQ 최고 결과의 38~77배,
    르네상스 메달리온의 3.8~7.7배. 시장 효율성·세계 최고 트레이더 데이터로
    명백히 비현실.

## 자기자본 운용 가이드 (ADR-0011 권고, Phase 3 도구로 보조)

본 프로젝트의 자기자본 운용 권고는 ADR-0011·0012 그대로 유지:

1. **세제 우대 계좌 최대 활용** (가장 큰 확실 우위) ← **Phase 3 A 도구가 직접 보조**
   - ISA 중개형: 일반형 비과세 한도 500만원/5년 (2026 확대)
   - 연금저축 + IRP: 연 900만원 한도, 세액공제 최대 148.5만원
2. **저보수 글로벌 분산 ETF** (KR 단일 시장 메가캡 집중 위험 회피)
3. **자동이체 적립** (증권사 기능, 봇 불필요)
4. **분기 1회 리밸런스** (캘린더 알림)
5. **충동 매매 차단** (시장 매일 안 보기, 뉴스 노출 최소화)
6. **자금 1억+ 도래 시 ADR-0012 재검토 트리거 발동 검토**

## 라이선스

Proprietary. All rights reserved.
