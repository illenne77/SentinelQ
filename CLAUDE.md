# CLAUDE.md — SentinelQ Phase 3

## 프로젝트 컨텍스트

**SentinelQ**는 KR 개인 투자자 자동화 도구 프로젝트.

- **Phase 0~2** (2025-11 ~ 2026-05): 알파 사냥 — 8/8 실패, ADR-0011로 종료
- **Phase 2.5** (2026-05-11): 방향 B' (TLH 봇) 검토 — ADR-0012로 NO-GO
- **Phase 3** (2026-05-11~): **KR Investor Tools** — ADR-0013로 재출범
  - **현재 진행**: PREREG-0008 (A 도구 — 양도세 + 세제 한도 자동 계산기)
  - 4~6주 MVP, G1~G6 게이트, 8주 hard stop

**NOT mandate**: 알파 발견·자동매매·시장 타이밍·수익률 향상 (ADR-0011·0012로 종결).

## 에이전트 역할 (키워드 진입점)

첫 메시지 키워드로 역할이 결정된다. 해당 파일을 즉시 읽고 역할 수행.

| 키워드 | 역할 | 상세 지시 |
|--------|------|----------|
| `Plan: [작업]` | Planner | `.claude/agents/planner.md` 읽고 수행 |
| `Build: [T번호]` | Generator | `.claude/agents/generator.md` 읽고 수행. Phase C에서 evaluator sub-agent를 Agent tool로 호출. |
| `Review: [T번호]` | Evaluator | Agent tool로 `subagent_type=evaluator` 호출 — 독립 컨텍스트. |

키워드 없으면 일반 작업 모드.

---

## 세션 시작 필수 절차 (모든 역할 공통)

1. **`.claude/baseline.json` 확인** — Phase·KPI·테스트 기준선의 단일 진실 원천
2. **`docs/adr/ADR-0013-phase3-kr-investor-tools.md`** mandate·NOT mandate 재확인
3. **`docs/preregistration/PREREG-0008-tax-tool.md`** frozen scope 재확인
4. **Phase 1 진행 상황**: `.claude/queue/` 의 active task·spec·report 점검
5. 작업 전 가상환경: `.venv/` 활성화 (`. .venv/Scripts/Activate.ps1` Windows)

## 하네스 변경 시 필수 검증

`.claude/` 내부 변경 후:

```powershell
pwsh -File .claude/scripts/send_telegram.py "harness change" --status info
pytest tests/ -v
```

baseline.json의 `test.pass` 미달이면 변경 채택 금지.

---

## 작업 규칙

- **텔레그램 알림** (선택): 환경변수 `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID` 설정 시 작업 완료/실패 알림
  - `python .claude/scripts/send_telegram.py "Phase 1 Week 1 완료" --status success`
- **Mandate 위반 금지**: 알파 사냥·자동 매매 코드 작성 금지 (ADR-0011·0012)
- **Scope creep 방지**: PREREG-0008 §3 OUT 항목 추가 시 동결 + 별도 PREREG 작성

---

## 공통 금지사항

- **자동 매매 주문 호출 금지** — `kis_broker.py`의 주문 함수는 Phase 1에서 미사용 (조회만)
- **본인 거래내역 commit 금지** — `data/private/` gitignore 등록됨
- **KIS API 토큰 commit 금지** — `secrets/` gitignore 등록됨
- **baseline 숫자 박제 금지** — `.claude/baseline.json` 참조
- **알파 백테스트 재활성화 금지** — `sentinelq/research/walkforward.py`는 history 보존이지 Phase 3 미사용
- **mandate 외 기능 추가 금지** — 의심 시 PREREG-0008 §3 OUT 점검

---

## 기술 스택

| 분류 | 기술 |
|---|---|
| 언어 | Python 3.11+ |
| 테스트 | pytest, pytest-cov |
| 린트 | ruff (format + check) |
| 데이터 | pandas, parquet |
| HTTP | requests, urllib |
| API | KIS REST OpenAPI |
| 알림 | Telegram Bot API |
| OS | Windows 10/11 (PowerShell 7+) |

## 레이어 구조 (Phase 1 완료 시)

```
scripts/run_tax_report.py        ← CLI 엔트리
sentinelq/reports/               ← NTS 양식·PDF 출력
sentinelq/tax/                   ← 양도세 계산·세제 한도·손실 인식
sentinelq/portfolio/             ← FIFO lot tracker (재사용)
sentinelq/adapters/              ← KIS·CSV importer (재사용 + 신규)
sentinelq/ports/                 ← TaxPort·ReportPort (신규 인터페이스)
```

---

## 빌드·테스트 명령

```powershell
# 가상환경
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -e ".[dev]"

# 테스트
pytest tests/ -v --cov=sentinelq.tax --cov=sentinelq.portfolio

# 린트
ruff check sentinelq/ tests/
ruff format sentinelq/ tests/
```

---

## 참고 문서

- `docs/adr/ADR-0011-project-termination.md` — Phase 0~2 알파 사냥 종료
- `docs/adr/ADR-0012-direction-b-prime-no-go.md` — 방향 B' TLH 봇 NO-GO
- `docs/adr/ADR-0013-phase3-kr-investor-tools.md` — Phase 3 mandate
- `docs/preregistration/PREREG-0008-tax-tool.md` — A 도구 frozen scope
- `.claude/decisions/` — Lightweight 일상 결정 기록 (DiRux 패턴 차용)
- `.claude/baseline.json` — 단일 진실의 원천

## 출처 (하네스 인프라)

`.claude/` 폴더의 워크플로·decisions 템플릿·baseline.json 패턴은 DiRuxViewSolution 프로젝트(.NET WPF DICOM 솔루션)의 하네스 엔지니어링 자산에서 차용 (2026-05-11 P0+P1 이식). 정책 배경: DiRuxView `.claude/decisions/01-harness-validation-strategy.md`.
