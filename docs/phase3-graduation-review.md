# Phase 3 (A 도구) 졸업 심사 — G1~G6 KPI 게이트 실측 현황

**Status**: 코드 완성 / 졸업 실증 대기 (interim review)
**Date**: 2026-05-15
**Reviewer**: Generator (general-mode 졸업 심사)
**기준 문서**: [PREREG-0008 §5·§7](preregistration/PREREG-0008-tax-tool.md) + [amendment-1 §5](preregistration/PREREG-0008-amendment-1.md)
**Mandate**: [ADR-0013](adr/ADR-0013-phase3-kr-investor-tools.md)

---

## 0. 요약 (TL;DR)

Phase 1 (A 도구 — 양도세 + 세제 한도 자동 계산기)의 **계획 태스크 7개(T001~T007)가
모두 코드 완성**됐다. 파이프라인(KIS fetch → FIFO lot → 양도세 계산 → NTS 양식 →
CSV)이 엔드투엔드로 동작하며 165개 테스트가 회귀 0으로 통과한다.

그러나 **형식 졸업(Phase 1 완료 인정)은 아직 선언할 수 없다.** PREREG-0008 §5의
졸업 기준 게이트 G1·G2·G3는 의도적으로 **본인 실제 KIS 데이터 + 실제 NTS 신고
결과**를 요구하도록 설계됐고, 이는 코드가 아니라 **사용자 keystroke 영역**이다.

| 판정 | 게이트 | 상태 |
|---|---|---|
| ✅ 통과 | G4, G5 | 코드/시뮬레이션으로 자체 검증 완료 |
| 🟡 코드 완성·실증 대기 | G1, G3 | 모듈 완성 + 테스트 통과, 본인 데이터 실증 미실시 |
| ⏳ 미착수 | G2 | 본인 실제 NTS 신고 데이터 입력 필요 |
| ✅ 통과 | G6 | 사용자 판정 PASS (2026-05-16) |

**결론: Phase 1은 "코드 완성" 단계 도달. "졸업"은 사용자 실증 5개 액션(§5) 완료 후
재심사.** NO-GO 사유는 없다 — 8주 hard stop 대비 일정 여유(2026-05-11 출범 후 코드
완성까지 4일), 모든 게이트가 차단(blocked)이 아닌 대기(pending) 상태.

---

## 1. 태스크 완료 현황 (T001~T007)

| 태스크 | 산출물 | 상태 | 연계 게이트 |
|---|---|---|---|
| T001 | `adapters/kis_history.py` — KIS REST 거래내역 fetch | done | G1·G2 |
| T002 | `portfolio/tax_lots.py` — FIFO Tax Lot Tracker | done | G1 |
| T003 | `tax/capital_gains.py` — 양도세 계산 엔진 | done | G1 |
| T004 | `tax/deduction.py` — 세제 우대 한도 추적 | done | **G3** |
| T005 | `tax/loss_harvesting.py` — 12월 손실 인식 권장 | done | **G4** |
| T006 | `reports/nts_form.py` — NTS 양도세 신고서 양식 | done | **G1** |
| T007 | `reports/tax_report.py` + `scripts/run_tax_report.py` — 엔드투엔드 CLI | done | **G1** |

7/7 태스크 done. PREREG-0008-amendment-1 §6 타임라인 Week 1~6 작업 범위 전량 구현.

테스트·커버리지 실측 (2026-05-15):

```
pytest tests/        → 165 passed, 0 failed, 0 skipped
coverage (핵심 모듈):
  sentinelq/tax/capital_gains.py     100%
  sentinelq/tax/deduction.py         100%
  sentinelq/tax/loss_harvesting.py   100%
  sentinelq/portfolio/tax_lots.py     99%
  sentinelq/reports/nts_form.py      100%
  sentinelq/reports/tax_report.py     86%
```

---

## 2. KPI 게이트 G1~G6 실측 현황

게이트 정본 정의는 PREREG-0008 §5 + amendment-1 §5 (G1·G2 재정의). baseline.json
`kpi_gates`의 G1·G2 정의는 본 심사에서 amendment-1 정본에 맞춰 갱신했다 (§4 참조).

### G1 — 양도세 신고 양식 자동 출력 🟡 코드 완성 / 실증 대기

- **정본 정의** (amendment-1 §5): 본인 KIS 계정 인증 → 자동 fetch → 2025 양도세
  신고 양식 출력, **전체 15분 이내**
- **코드 상태**: ✅ 완성. `scripts/run_tax_report.py` 가 fetch→FIFO→계산→NTS
  양식→CSV 전 경로를 엮는다. `--from-json` offline 모드로 main() end-to-end
  테스트 통과 (`test_main_from_json_exit_zero`).
- **실증 미실시 사유**: 게이트 측정 단위가 "본인 KIS 거래내역" + "15분 이내"라는
  **시간 측정**이다. 본인 KIS 계정 인증 후 실제 fetch·출력 1회 실행 필요.
- **선행 조건**: `.claude/decisions/T001-kis-api-period-limit.md` — KIS API 거래내역
  endpoint의 본인 계정 기간 한도 실측이 placeholder 상태. fetch 한도가 2025
  과세연도 + FIFO용 이전 매수분을 덮지 못하면 `--start-date` 조정 또는 amendment-2.

### G2 — KIS API vs 실제 신고 결과 ±100원 ⏳ 미착수

- **정본 정의** (amendment-1 §5): KIS API fetch 결과와 본인 **2025 실제 양도세
  신고 결과** 비교, **±100원 일치** (truth value 1년치 한정)
- **코드 상태**: 도구 출력측은 완성 (T003 양도세 계산 + T006 NTS 양식, 단위
  테스트로 룰 정확성 검증). 그러나 G2는 도구 단독으로 닫을 수 없다 —
  **비교 대상(본인 실제 NTS 신고 결과)** 이 외부 truth value.
- **미착수 사유**: (1) 본인 2025 실제 양도세 신고가 완료돼 있어야 하고, (2) KIS
  API에서 2025 거래내역 전량 fetch가 가능해야 한다 (G1 선행 조건과 동일).
- **±100원 허용 근거** (amendment-1 §5): 환율·수수료 round-off는 1~10원, ±100원
  초과 시 logic bug.

### G3 — 세제 한도 추적 정확 🟡 코드 완성 / 실증 대기

- **정본 정의** (PREREG §5, amendment-1 변경 없음): IRP+연금저축+ISA 한도·세액공제
  추적이 **증권사 공식 잔여한도와 일치**
- **코드 상태**: ✅ 완성. T004 `tax/deduction.py` — 연금저축 600만/IRP 합산 900만
  한도, 세액공제율 16.5%/13.2%, ISA 연간·5년 누적 한도. 커버리지 100%, 19건 테스트.
- **실증 미실시 사유**: 게이트 측정이 "증권사 공식 잔여한도와 일치"다. 본인 납입
  기록(contribution records)을 입력해 산출한 잔여한도를 본인 증권사 앱/명세서의
  공식 수치와 대조해야 한다.
- **주의**: `deduction.py` 입력인 납입 기록은 거래내역만으로 도출 불가하며, T007
  CLI는 deduction을 통합하지 않는다 (spec-T007 §2.2 OUT 명시). G3 실증은 현재
  `deduction.py` 를 직접 호출(납입 기록 수기 입력)하는 형태로 수행한다.

### G4 — 12월 손실 인식 절세 효과 ✅ 통과

- **정본 정의**: 12월 손실 인식 권장이 실제 절세 효과 입증 — **시뮬레이션으로
  +100만원 절세 시나리오 1건+**
- **측정 단위가 "시뮬레이션"** 이므로 본인 실데이터 불요. 게이트 자체 검증 가능.
- **실측**: `tests/test_loss_harvesting.py::test_g4_scenario_saving_over_1m` —
  gain=10,000,000 / loss=-6,000,000 시나리오에서 `estimated_max_saving_krw ==
  1,320,000` (≥ 1,000,000) 검증. **G4 충족.**

### G5 — tax/ 모듈 커버리지 ≥ 80% ✅ 통과

- **정본 정의**: 단위테스트 커버리지 ≥ 80% (`sentinelq/tax/` 모듈), `pytest --cov`
- **실측** (2026-05-15): `tax/capital_gains.py` 100%, `tax/deduction.py` 100%,
  `tax/loss_harvesting.py` 100%. 전 모듈 80% 기준 초과. **G5 충족.**

### G6 — 본인 사용 가치 연 50만원+ ✅ 통과

- **정본 정의**: 본인 사용 가치 연 50만원+ 입증 — **Phase 2 시작 전 자기 평가
  문서 작성**
- **판정**: **PASS** (2026-05-16, 사용자 판정)
- **근거**: 정량 입력 정보 충분하지 않아 수치 합산 검증 유보. 본인이 도구의
  사용 가치가 기준을 충족한다고 판단하여 통과 처리.
- **자기 평가 문서**: [docs/g6-self-evaluation.md](g6-self-evaluation.md)

---

## 3. 졸업 판정

PREREG-0008의 두 졸업 규칙:

- **§5**: "G1~G3 모두 통과 시 **Phase 1 완료 인정**"
- **§7.1 Graduation**: "G1·G2·G3·G6 모두 통과 → **Phase 2 (B 도구) 진행 결정**"

| 단계 | 요구 게이트 | 현재 |
|---|---|---|
| Phase 1 완료 인정 | G1 + G2 + G3 | 🟡 G1·G3 코드 완성 / G2 실증 대기 |
| Phase 2 진행 결정 | G1 + G2 + G3 + G6 | 🟡 G6 ✅ — G2 실증 후 판정 가능 |

**판정: Phase 1 코드 완성(code-complete) 도달. 형식 졸업 미선언.**

이는 실패(NO-GO)가 아니다. PREREG-0008 §7.3 Rejection 조건은 "8주 안에 G1
미통과"인데, 2026-05-11 출범 후 4일 만에 전 태스크 코드 완성에 도달했고 게이트는
모두 **차단(blocked) 아닌 대기(pending)** 상태다. ADR-0014 NO-GO 작성 사유 없음.

---

## 4. baseline.json SSOT 수정 기록

본 심사 중 `.claude/baseline.json` `kpi_gates` 의 stale 정의를 amendment-1 정본에
맞춰 갱신했다.

| 키 | 변경 전 (stale) | 변경 후 (amendment-1 §5 정본) |
|---|---|---|
| G1 | "본인 거래내역으로 2025 양도세 NTS 양식 **30분** 안에 출력" | "KIS 계정 인증 → 자동 fetch → 신고 양식 출력 (**전체 15분 이내**)" |
| G2 | "KIS+**키움** 합산 손익통산 정확 (수동 계산과 **±1원**)" | "KIS API fetch 결과와 본인 실제 신고 결과 비교 (**±100원**, 1년치)" |

G3~G6은 amendment-1에서 변경 없음 — 그대로 유지. 수정 후 `pytest tests/` 165
passed 회귀 0 확인.

---

## 5. 형식 졸업까지 잔여 항목 (사용자 실증 액션)

모두 본인 KIS 계정·데이터가 필요한 keystroke 영역이다.

1. **[선행] KIS API fetch 기간 한도 실측** — `.claude/decisions/T001-kis-api-period-limit.md`
   의 측정 절차 실행, 표 채우기. 한도가 짧으면 amendment-2 트리거.
2. **[G1] 실증 실행** — 본인 KIS 계정으로 `python scripts/run_tax_report.py
   --tax-year 2025 --env live --confirm-live --account ...` 실행, NTS 양식 CSV
   출력까지 **15분 이내** 측정.
3. **[G2] 비교 검증** — 도구 출력(양도차익·과세표준·세액)을 본인 2025 실제 NTS
   신고 결과와 대조, **±100원 일치** 확인. 초과 시 logic bug 조사.
4. **[G3] 세제 한도 실증** — `tax/deduction.py` 에 본인 IRP·연금저축·ISA 납입
   기록 입력 → 산출된 잔여한도를 증권사 공식 수치와 대조.
5. **[G6] 자기 평가 문서 작성** — 본인 사용 가치 연 50만원+ 입증 문서. G1~G3
   실증 완료 후 작성 권장.

위 5개 완료 후 본 문서 재심사 → Phase 1 졸업 또는 (G6 미달 시) §7.2 Pivot.

---

## 6. Scope 점검 — 졸업이 요구하지 않는 것

다음은 spec-T007 §2.2 OUT에 "향후 별도 통합 태스크"로 명시된 항목으로, **G1~G6
졸업과 무관**하다. 졸업 전 착수는 scope creep (PREREG §7.4).

- deduction / loss_harvesting 의 CLI 자동 통합 (납입 기록·현재가 스냅샷이라는
  별도 입력 필요)
- 다년(多年) 통합 리포트 (`calculate_all`)
- `ports/tax_port.py` · `ports/report_port.py` 헥사고날 인터페이스
- PDF 렌더링 (`reports/pdf_export.py`)
- KIS 외 증권사 import (amendment-1 §3 OUT — 별도 PREREG 필요)

이 항목들은 졸업 후 Phase 2 진입 결정 또는 별도 PREREG에서 다룬다.

---

## 7. References

- [PREREG-0008 §5 KPI Gates / §7 Decision Rules](preregistration/PREREG-0008-tax-tool.md)
- [PREREG-0008-amendment-1 §5 G1·G2 재정의](preregistration/PREREG-0008-amendment-1.md)
- [ADR-0013 §Method Stop 조건](adr/ADR-0013-phase3-kr-investor-tools.md)
- `.claude/baseline.json` — `kpi_gates`, `test`, `stop_conditions`
- `.claude/decisions/T001-kis-api-period-limit.md` — KIS API 기간 한도 실측 (placeholder)
- `.claude/queue/impl-report-T00{1..7}.md` / `review-report-T00{2..7}.md`
