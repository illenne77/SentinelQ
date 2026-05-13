# Copilot CLI Instructions — SentinelQ

이 파일은 GitHub Copilot CLI가 세션 시작 시 자동으로 읽는 행동 지침이다.
**프로젝트 전반 규칙·하네스·역할 정의는 `CLAUDE.md`가 단일 진실의 원천(SSOT)이다.**

## 즉시 읽어야 할 파일 (우선순위 순)

1. **`CLAUDE.md`** — 프로젝트 컨텍스트·에이전트 역할·금지사항·빌드/테스트 명령
2. **`.claude/baseline.json`** — Phase·KPI·테스트 기준선 SSOT
3. **`docs/adr/ADR-0013-phase3-kr-investor-tools.md`** — Phase 3 mandate / NOT mandate
4. **`docs/preregistration/PREREG-0008-tax-tool.md`** — 현재 작업(A 도구) frozen scope §3 OUT 포함

## 핵심 원칙 (요약 — 상세는 CLAUDE.md)

- **Phase 3 mandate**: KR 개인 투자자 세금 자동화 도구 (PREREG-0008 진행 중).
- **NOT mandate (절대 금지)**: 알파 사냥, 자동 매매 주문, 시장 타이밍, 수익률 향상 — ADR-0011·0012로 종결.
- **Scope creep 금지**: PREREG-0008 §3 OUT 항목 추가 시 frozen 처리 + 별도 PREREG 작성 필요.
- **하네스 변경 시 검증 필수**: `.claude/` 수정 후 `pytest tests/ -v` 통과 + baseline.json `test.pass` 미달이면 채택 금지.

## 작업 환경

- OS: Windows 10/11, PowerShell 7+
- 경로: 백슬래시(`\`) 사용
- 가상환경: `. .venv\Scripts\Activate.ps1`
- 빌드/테스트: `pytest tests/ -v --cov=sentinelq.tax --cov=sentinelq.portfolio`
- 린트: `ruff check sentinelq/ tests/` · `ruff format sentinelq/ tests/`

## 키워드 기반 역할 (CLAUDE.md와 동일)

사용자 첫 메시지가 다음 키워드로 시작하면 해당 역할 수행:

| 키워드 | 역할 | 참조 |
|---|---|---|
| `Plan: [작업]` | Planner | `.claude/agents/planner.md` |
| `Build: [T번호]` | Generator | `.claude/agents/generator.md` |
| `Review: [T번호]` | Evaluator | `.claude/agents/evaluator.md` |

키워드 없으면 일반 작업 모드.

## 금지 사항 (재확인)

- 자동 매매 주문 호출 (`kis_broker.py` 주문 함수 미사용 — 조회만)
- 본인 거래내역·KIS 토큰 commit (`data/private/`, `secrets/` gitignore)
- baseline 숫자 박제 (`.claude/baseline.json` 참조만)
- 알파 백테스트 재활성화 (`sentinelq/research/walkforward.py`는 history 보존 목적)
- mandate 외 기능 추가 — 의심 시 PREREG-0008 §3 OUT 점검

## 출처

- 본 파일 패턴: drvoss/everything-copilot-cli 레퍼런스 (2026-05-13 도입)
- 하네스 패턴: DiRuxViewSolution 프로젝트 자산 차용 (`.claude/` 전체)
