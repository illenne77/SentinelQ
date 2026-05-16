# PREREG-0008 Amendment 2 — 다중 증권사 CSV importer 재도입 + 홈택스·위택스 신고 강화

**Status**: Active amendment
**Date**: 2026-05-16
**Base**: [PREREG-0008](PREREG-0008-tax-tool.md) + [Amendment-1](PREREG-0008-amendment-1.md)
**Trigger**: 개인 SaaS 유료구독 전환 — 다중 증권사 통합이 핵심 차별화 요소

---

## 변경 근거

Amendment-1 (2026-05-11)에서 "KIS API 단독, CSV importer 폐기"로 결정했으나,
Phase 3 G1~G6 전체 PASS 후 유료화 검토 결과:

1. **KIS 앱도 무료로 예상세액 제공** — 단일 증권사 지원만으로 유료구독 정당화 어려움
2. **다중 증권사 통합이 핵심 공백** — 키움(시장점유율 30%+)·미래에셋 지원 시 경쟁 불가 영역 확보
3. **홈택스 신고서 수동 입력 부담** — 자동화 강화 시 "삼쩜삼 해외주식판" 포지션 가능
4. **위택스 지방세 별도 신고** — G2 실증에서 사용자가 직접 경험한 UX 이슈

사용자 결정 (2026-05-16): **개인 SaaS 유료구독 Step 1** — 다중 증권사 + 신고 자동화 강화.

---

## 변경 내역

### §2.1 거래내역 import (Amendment-1 §2.1 재변경)

Amendment-1 변경본:
```
| KIS (한국투자증권) | API fetch | P0 단독 |
```

→ 변경:
```
| 증권사          | 형식              | 우선순위 |
| KIS (한국투자증권) | API fetch (기존)  | P0 (유지) |
| 키움증권         | CSV export (HTS)  | P1 (재도입) |
| 미래에셋증권      | CSV export (HTS)  | P1 (재도입) |
| 토스증권         | CSV export        | P2 (보류) |
```

다중 증권사 CSV importer가 §3 OUT에서 **IN으로 복귀**.

### §2.5 출력 강화 (추가)

기존 §2.5 유지 + 다음 항목 추가:

```
신규:
- 홈택스 신고서 자동완성 가이드 (Excel — 신고서 필드별 값 자동 채움)
- 위택스 지방소득세 신고 안내 리포트 (신고 금액·절차 안내)
```

### §3 OUT 항목 변경

다음 항목을 §3 OUT에서 **제거** (IN 복귀):
```
- 키움·미래에셋 CSV importer (별도 PREREG 필요) → 본 amendment-2로 IN 복귀
```

다음 항목은 §3 OUT 유지:
```
- 토스증권·신한·NH 등 P2 증권사 (별도 amendment 필요)
- 홈택스 API 자동 신고 제출 (NTS 전자신고 API 미공개 — 추후 amendment)
- 자동 매매·알파 발견·시장 타이밍 (ADR-0011·0012 영구 종결)
```

### §4.1 모듈 구조 추가

```
adapters/kiwoom_csv.py        🆕 키움증권 HTS CSV parser (T009)
adapters/miraeasset_csv.py    🆕 미래에셋증권 HTS CSV parser (T010)
reports/hometax_guide.py      🆕 홈택스 신고서 자동완성 가이드 Excel 생성 (T011)
reports/wetax_guide.py        🆕 위택스 지방세 신고 안내 리포트 (T012)
```

### §4.2 신규 LOC 추정 (추가)

| 모듈 | 추정 LOC |
|---|---:|
| `kiwoom_csv.py` | 120 |
| `miraeasset_csv.py` | 100 |
| `hometax_guide.py` | 150 |
| `wetax_guide.py` | 80 |
| 테스트 4건 | 200 |
| **합계** | **650** |

---

## 신규 KPI (내부 기준, PREREG §5 게이트 추가 없음)

| 검증 항목 | 기준 |
|---|---|
| 키움 CSV 파싱 정확도 | 샘플 데이터 Transaction 변환 ±0원 |
| 미래에셋 CSV 파싱 정확도 | 샘플 데이터 Transaction 변환 ±0원 |
| 홈택스 가이드 생성 | nts_summary_2025.csv 입력 → Excel 생성 성공 |
| 위택스 안내 생성 | 지방세 금액·납부처·기한 정확 |

---

## 핵심 가정

1. 키움증권 영웅문 HTS 해외주식 체결내역 CSV 컬럼 형식이 본 amendment에 정의한 형식과 일치.
   - 미일치 시: 컬럼 매핑 config 파일(`data/private/kiwoom_col_map.json`)로 override.
2. 미래에셋증권 HTS 거래내역 CSV 컬럼 형식 동일.
3. 홈택스 Excel 업로드 미지원 — 가이드는 입력 보조용, 자동 제출 아님.
4. 위택스 API 미공개 — 안내 리포트만 생성 (자동 제출 아님).

---

## References

- [PREREG-0008](PREREG-0008-tax-tool.md) — 원본 frozen scope
- [Amendment-1](PREREG-0008-amendment-1.md) — KIS API 단독 결정 (본 amendment가 §2.1 재변경)
- [ADR-0013](../adr/ADR-0013-phase3-kr-investor-tools.md) — Phase 3 mandate
- G1~G6 게이트 전체 PASS 확인: `docs/phase3-graduation-review.md`
