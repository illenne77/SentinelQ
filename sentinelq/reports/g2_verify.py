"""G2 게이트 검증 — CLI 산출값 vs 실제 NTS 신고 결과 ±100원 비교.

KPI Gate G2 (PREREG-0008 amendment-1 §5):
  KIS API fetch 결과와 본인 2025 실제 양도세 신고 결과 비교, ±100원 일치
  (truth value 1년치 한정)

±100원 허용 근거: KIS API 환율·수수료 round-off 1~10원 단위 차이 정상.
±100원 초과는 logic bug.

사용 예::
    python scripts/verify_g2.py \\
        --summary data/output/nts_summary_2025.csv \\
        --actual-gain 5000000 \\
        --actual-taxable 2500000 \\
        --actual-national-tax 500000 \\
        --actual-local-tax 50000 \\
        --actual-total-tax 550000

종료코드: 0=PASS / 1=FAIL / 2=입력오류
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

DEFAULT_TOLERANCE = Decimal("100")

_COMPARE_FIELDS: list[tuple[str, str]] = [
    ("total_realized_gain_krw", "총 양도차익"),
    ("taxable_base_krw", "과세표준"),
    ("national_tax_krw", "산출세액(국세)"),
    ("local_tax_krw", "지방소득세"),
    ("total_tax_krw", "총 납부세액"),
]


@dataclass(frozen=True)
class FieldResult:
    field: str
    label: str
    computed: Decimal
    actual: Decimal
    diff: Decimal
    passed: bool


@dataclass(frozen=True)
class G2Report:
    tax_year: int
    tolerance_krw: Decimal
    fields: tuple[FieldResult, ...]

    @property
    def passed(self) -> bool:
        return all(f.passed for f in self.fields)


def load_summary_csv(path: Path) -> dict[str, Decimal]:
    """nts_summary_YYYY.csv (field, value) → 숫자 필드만 Decimal dict."""
    result: dict[str, Decimal] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            with contextlib.suppress(Exception):  # 날짜·문자열 필드는 Decimal 변환 불가
                result[row["field"]] = Decimal(row["value"])
    return result


def compare(
    computed: dict[str, Decimal],
    actual: dict[str, Decimal],
    tax_year: int = 0,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> G2Report:
    """computed·actual dict → G2Report (pass/fail per field)."""
    fields = []
    for field, label in _COMPARE_FIELDS:
        comp = computed.get(field, Decimal("0"))
        act = actual.get(field, Decimal("0"))
        diff = abs(comp - act)
        fields.append(
            FieldResult(
                field=field,
                label=label,
                computed=comp,
                actual=act,
                diff=diff,
                passed=diff <= tolerance,
            )
        )
    return G2Report(
        tax_year=tax_year,
        tolerance_krw=tolerance,
        fields=tuple(fields),
    )


def format_report(report: G2Report) -> str:
    """보고서를 사람이 읽기 좋은 문자열로."""
    lines = []
    sep = "=" * 64
    lines.append(f"\n{sep}")
    lines.append(
        f"G2 검증 결과 — {report.tax_year}년 양도세  (허용오차 ±{int(report.tolerance_krw)}원)"
    )
    lines.append(sep)
    header = f"{'항목':<18} {'CLI 산출':>14} {'실제 신고':>14} {'차이':>10} {'판정':>6}"
    lines.append(header)
    lines.append("-" * 64)
    for f in report.fields:
        status = "PASS" if f.passed else "FAIL ❌"
        lines.append(
            f"{f.label:<18} {int(f.computed):>14,} {int(f.actual):>14,}"
            f" {int(f.diff):>10,} {status:>6}"
        )
    lines.append(sep)
    verdict = "PASS ✅  — G2 게이트 통과" if report.passed else "FAIL ❌  — G2 게이트 미통과"
    lines.append(f"G2 종합 판정: {verdict}")
    lines.append(sep + "\n")
    return "\n".join(lines)


def to_json(report: G2Report) -> str:
    data = {
        "tax_year": report.tax_year,
        "tolerance_krw": int(report.tolerance_krw),
        "gate_g2_pass": report.passed,
        "fields": [
            {
                "field": f.field,
                "label": f.label,
                "computed_krw": int(f.computed),
                "actual_krw": int(f.actual),
                "diff_krw": int(f.diff),
                "passed": f.passed,
            }
            for f in report.fields
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_g2",
        description="G2 게이트 검증 — CLI 산출값 vs 실제 NTS 신고 결과 ±100원 비교",
    )
    parser.add_argument("--summary", required=True, help="nts_summary CSV 파일 경로")
    parser.add_argument("--actual-gain", type=int, required=True, help="실제 총 양도차익 원")
    parser.add_argument("--actual-taxable", type=int, required=True, help="실제 과세표준 원")
    parser.add_argument(
        "--actual-national-tax", type=int, required=True, help="실제 산출세액(국세) 원"
    )
    parser.add_argument("--actual-local-tax", type=int, required=True, help="실제 지방소득세 원")
    parser.add_argument("--actual-total-tax", type=int, required=True, help="실제 총 납부세액 원")
    parser.add_argument("--tolerance", type=int, default=100, help="허용 오차 원 단위 (기본 100)")
    parser.add_argument("--out", default=None, help="JSON 보고서 저장 경로 (선택)")
    args = parser.parse_args(argv)

    summary_path = Path(args.summary)
    if not summary_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다 — {summary_path}", file=sys.stderr)
        return 2

    try:
        computed = load_summary_csv(summary_path)
    except Exception as exc:
        print(f"오류: CSV 파싱 실패 — {exc}", file=sys.stderr)
        return 2

    tax_year = int(computed.get("tax_year", Decimal("0")))
    tolerance = Decimal(str(args.tolerance))

    actual = {
        "total_realized_gain_krw": Decimal(str(args.actual_gain)),
        "taxable_base_krw": Decimal(str(args.actual_taxable)),
        "national_tax_krw": Decimal(str(args.actual_national_tax)),
        "local_tax_krw": Decimal(str(args.actual_local_tax)),
        "total_tax_krw": Decimal(str(args.actual_total_tax)),
    }

    report = compare(computed, actual, tax_year=tax_year, tolerance=tolerance)
    print(format_report(report))

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(to_json(report), encoding="utf-8")
        print(f"보고서 저장: {out_path}")

    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
