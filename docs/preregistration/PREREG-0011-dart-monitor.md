# PREREG-0011: DART 공시 모니터링 봇 (frozen scope)

**Status**: Frozen
**Date**: 2026-05-16
**Mandate**: ADR-0013 Phase 3 Tool B (공시 모니터링)
**Linked**: [ADR-0013](../adr/ADR-0013-phase3-kr-investor-tools.md)

---

## 1. 목적 (Mandate)

KR 개인 투자자가 보유 종목의 DART 공시를 수동으로 확인하는 반복 작업을
자동화한다. 중요 공시(유상증자, 합병, 주요사항보고서 등) 발생 시 텔레그램
알림으로 즉시 통보하여 정보 우위와 큰 손실 회피에 기여한다.

ADR-0013 §Method "Phase 2 (B 도구) 후 본인 보유 종목 공시 누락률 < 10%"
KPI 게이트 달성을 목표로 한다.

---

## 2. Scope — IN

### §2.1 DART REST API 어댑터

- DART OpenAPI `list.json` 엔드포인트로 법인별 공시 목록 조회
- `corp_code.json` 캐시(data/cache/dart/)로 종목코드 → 법인코드 변환
- API 키: `DART_API_KEY` 환경변수 또는 `secrets/dart_api_key.txt`
- `DisclosureRecord` 데이터클래스 (접수번호·보고서명·접수일·중요도·URL)

### §2.2 공시 중요도 분류

보고서명 키워드 기반으로 HIGH / NORMAL 분류:

| HIGH (즉시 알림) | NORMAL (일반) |
|---|---|
| 유상증자·무상증자·감자 | 분기·반기·사업보고서 |
| 합병·분할·인수합병 | 임원 변경 |
| 최대주주 변경 | 기타 공시 |
| 전환사채·신주인수권 | |
| 상장폐지·관리종목 | |
| 주요사항보고서 | |
| 횡령·배임·영업정지·파산 | |

### §2.3 보유 종목 공시 조회

- KIS 잔고 API (PREREG-0009) 또는 `--tickers` CLI 인수로 보유 종목 확보
- 국내주식만 처리 (해외주식은 DART 대상 외)
- 조회 기간: 최근 N일 (기본 7일), `--days` 인수로 조정
- 접수번호 기준 중복 제거

### §2.4 텔레그램 알림

- 신규 공시 발생 시 텔레그램 봇으로 알림 전송
- 환경변수: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- 메시지 형식: 종목명·보고서명·접수일·DART 링크
- `--notify` 플래그로 활성화 (기본 stdout 출력만)

### §2.5 공시 모니터링 CLI

```
python scripts/run_dart_monitor.py --days 7
python scripts/run_dart_monitor.py --days 1 --importance ALL --notify
python scripts/run_dart_monitor.py --tickers 005930 000660 --days 30
python scripts/run_dart_monitor.py --env paper  # KIS 잔고로 종목 자동 조회
```

---

## 3. Scope — OUT

| 항목 | 이유 |
|------|------|
| 해외주식 공시 (SEC Form 4 등) | DART 영역 외, 별도 PREREG 필요 |
| 공시 내용 자동 분석 (LLM 요약) | MVP 범위 초과, 추후 PREREG 분리 |
| 자동 매매 연동 | ADR-0011 종결 (자동매매 금지) |
| 이메일 알림 | 텔레그램 우선, 이메일은 추후 확장 |
| 실시간 스트리밍 | DART API는 폴링 방식만 지원 |
| 사용자별 관심 종목 DB | SaaS 다중 사용자 기능 (추후 PREREG) |

---

## 4. 핵심 데이터 구조

```python
DisclosureRecord  # 공시 레코드 (corp_code, report_name, receipt_no, importance, url)
MonitorResult     # 모니터링 결과 (checked_from/to, disclosures, skipped_codes)
```

---

## 5. 테스트 기준

- `sentinelq/adapters/dart_api.py` coverage ≥ 90%
- `sentinelq/monitoring/dart_monitor.py` coverage ≥ 90%
- `sentinelq/notifications/telegram.py` coverage ≥ 90%
- 실제 DART API 미호출 (unittest.mock.patch 사용)
