# PREREG-0012 — Streamlit Web UI (Step B)

**상태**: ACTIVE  
**작성일**: 2026-05-16  
**담당**: illenne77

---

## 1. 목적

SentinelQ CLI 도구들을 브라우저 기반 멀티페이지 Streamlit 앱으로 제공한다.
비기술 사용자도 CSV 업로드 → 세금 계산 → 공시 모니터링을 사용할 수 있도록 한다.

---

## 2. IN scope

### §2.1 순수 헬퍼 모듈 (`sentinelq/ui/helpers.py`)
- Streamlit 미의존 순수 함수 — 단위 테스트 대상
- 포맷 함수: `fmt_krw`, `fmt_pct`
- 유효성 검사: `validate_target_weights`
- 변환 함수: `portfolio_to_rows`, `portfolio_summary`, `disclosures_to_rows`, `rebalance_to_rows`, `rebalance_summary`
- 상태 확인: `env_status`
- Coverage target: ≥ 90%

### §2.2 Home 페이지 (`streamlit_app.py`)
- 앱 소개 + 4개 기능 페이지 링크
- 환경변수 설정 현황 (KIS/DART/Telegram)

### §2.3 Page 1 — 양도세 계산기 (`pages/1_양도세_계산기.py`)
- 증권사 선택 (키움/미래에셋)
- CSV 파일 업로드 → Transaction 파싱
- 과세연도 입력
- 환율 수동 입력 (USD 거래 시)
- NTS 양식 계산 → 요약 메트릭 표시
- 요약 CSV / 상세 CSV 다운로드

### §2.4 Page 2 — 포트폴리오 대시보드 (`pages/2_포트폴리오_대시보드.py`)
- 수동 종목 입력 (ticker, 시장, 수량, 평균단가, 현재가)
- AfterTaxPortfolio 계산 → 세후 수익률 표시
- 포트폴리오 요약 메트릭 + 종목별 상세 테이블

### §2.5 Page 3 — 리밸런싱 계산기 (`pages/3_리밸런싱.py`)
- 시장별 목표 배분 입력 (KR/US/기타)
- 임계값 슬라이더 (1~20%)
- Page 2 포트폴리오 세션 연동 or 독립 입력
- 리밸런싱 플랜 표시 (거래금액, 예상 세금)

### §2.6 Page 4 — DART 공시 (`pages/4_DART_공시.py`)
- 종목코드 입력 (쉼표 구분)
- 조회 기간 (최근 N일)
- 중요도 필터 (HIGH / ALL)
- DART API 키 입력 (환경변수 없을 시)
- 공시 목록 테이블 + URL 링크

---

## 3. OUT scope

- PDF 렌더링
- 사용자 계정 / 로그인
- 자동 KIS API 연결 (환경변수 설정 방식 유지)
- 자동 주문·알파·시그널 (ADR-0011·0012)
- 배포 인프라 (Docker, cloud hosting)
- Streamlit Cloud 배포

---

## 4. 테스트 전략

- `tests/test_ui_helpers.py` — helpers.py 순수 함수 단위 테스트 (≥ 20건)
- Streamlit 페이지: `streamlit run streamlit_app.py` 수동 검증
- ruff clean 필수

---

## 5. 의존성

```toml
[project.optional-dependencies]
ui = ["streamlit>=1.32"]
```

설치: `pip install -e ".[dev,ui]"`
실행: `streamlit run streamlit_app.py`
