"""G2 검증 스크립트 단위 테스트.

Coverage target: sentinelq/reports/g2_verify.py >= 90%
KPI Gate: G2 — CLI 산출값 vs 실제 NTS 신고 결과 ±100원 비교
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from sentinelq.reports.g2_verify import (
    compare,
    format_report,
    load_summary_csv,
    main,
    to_json,
)

# ── 공통 픽스처 ────────────────────────────────────────────


def _write_summary_csv(path: Path, fields: dict) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["field", "value"])
        for k, v in fields.items():
            writer.writerow([k, str(v)])


SAMPLE = {
    "tax_year": 2025,
    "filing_period_start": "2026-05-01",
    "filing_period_end": "2026-05-31",
    "sale_count": 5,
    "total_proceeds_krw": 50_000_000,
    "total_acquisition_cost_krw": 45_000_000,
    "total_realized_gain_krw": 5_000_000,
    "basic_deduction_krw": 2_500_000,
    "deduction_applied_krw": 2_500_000,
    "taxable_base_krw": 2_500_000,
    "national_tax_krw": 500_000,
    "local_tax_krw": 50_000,
    "total_tax_krw": 550_000,
    "t003_combined_tax_krw": 550_000,
}

EXACT_ACTUAL = {
    "total_realized_gain_krw": Decimal("5000000"),
    "taxable_base_krw": Decimal("2500000"),
    "national_tax_krw": Decimal("500000"),
    "local_tax_krw": Decimal("50000"),
    "total_tax_krw": Decimal("550000"),
}

COMPUTED = {
    k: Decimal(str(v))
    for k, v in SAMPLE.items()
    if isinstance(v, int) and k not in {"tax_year", "sale_count"}
}


# ── load_summary_csv ────────────────────────────────────────


class TestLoadSummaryCsv:
    def test_loads_numeric_fields(self, tmp_path):
        p = tmp_path / "s.csv"
        _write_summary_csv(p, SAMPLE)
        result = load_summary_csv(p)
        assert result["total_realized_gain_krw"] == Decimal("5000000")
        assert result["total_tax_krw"] == Decimal("550000")
        assert result["taxable_base_krw"] == Decimal("2500000")

    def test_skips_non_numeric_fields(self, tmp_path):
        p = tmp_path / "s.csv"
        _write_summary_csv(p, SAMPLE)
        result = load_summary_csv(p)
        assert "filing_period_start" not in result
        assert "filing_period_end" not in result

    def test_tax_year_and_sale_count_loaded(self, tmp_path):
        p = tmp_path / "s.csv"
        _write_summary_csv(p, SAMPLE)
        result = load_summary_csv(p)
        assert result["tax_year"] == Decimal("2025")
        assert result["sale_count"] == Decimal("5")


# ── compare ────────────────────────────────────────────────


class TestCompare:
    def test_perfect_match_all_pass(self):
        report = compare(COMPUTED, EXACT_ACTUAL, tax_year=2025)
        assert report.passed
        assert all(f.passed for f in report.fields)

    def test_within_100won_pass(self):
        actual = {**EXACT_ACTUAL, "total_realized_gain_krw": Decimal("5000100")}
        report = compare(COMPUTED, actual, tax_year=2025)
        assert report.passed

    def test_exactly_100won_diff_pass(self):
        actual = {**EXACT_ACTUAL, "national_tax_krw": Decimal("500100")}
        report = compare(COMPUTED, actual, tax_year=2025)
        gain_field = next(f for f in report.fields if f.field == "national_tax_krw")
        assert gain_field.passed

    def test_101won_diff_fail(self):
        actual = {**EXACT_ACTUAL, "national_tax_krw": Decimal("500101")}
        report = compare(COMPUTED, actual, tax_year=2025)
        national = next(f for f in report.fields if f.field == "national_tax_krw")
        assert not national.passed
        assert not report.passed

    def test_zero_tax_case_pass(self):
        zero_computed = {
            "total_realized_gain_krw": Decimal("1000000"),
            "taxable_base_krw": Decimal("0"),
            "national_tax_krw": Decimal("0"),
            "local_tax_krw": Decimal("0"),
            "total_tax_krw": Decimal("0"),
        }
        report = compare(zero_computed, zero_computed, tax_year=2025)
        assert report.passed

    def test_custom_tolerance(self):
        actual = {**EXACT_ACTUAL, "total_realized_gain_krw": Decimal("5000200")}
        report = compare(COMPUTED, actual, tax_year=2025, tolerance=Decimal("500"))
        assert report.passed

    def test_missing_field_treated_as_zero(self):
        report = compare({}, EXACT_ACTUAL, tax_year=2025)
        # computed=0, actual=5000000 → diff=5000000 > 100 → fail
        assert not report.passed

    def test_report_has_correct_tax_year(self):
        report = compare(COMPUTED, EXACT_ACTUAL, tax_year=2025)
        assert report.tax_year == 2025

    def test_all_5_fields_in_report(self):
        report = compare(COMPUTED, EXACT_ACTUAL, tax_year=2025)
        assert len(report.fields) == 5


# ── format_report / to_json ────────────────────────────────


class TestFormatReport:
    def test_pass_verdict_in_output(self):
        report = compare(COMPUTED, EXACT_ACTUAL, tax_year=2025)
        text = format_report(report)
        assert "PASS" in text
        assert "2025" in text

    def test_fail_verdict_in_output(self):
        actual = {**EXACT_ACTUAL, "national_tax_krw": Decimal("600000")}
        report = compare(COMPUTED, actual, tax_year=2025)
        text = format_report(report)
        assert "FAIL" in text


class TestToJson:
    def test_json_structure(self):
        report = compare(COMPUTED, EXACT_ACTUAL, tax_year=2025)
        data = json.loads(to_json(report))
        assert data["gate_g2_pass"] is True
        assert data["tax_year"] == 2025
        assert len(data["fields"]) == 5

    def test_fail_json(self):
        actual = {**EXACT_ACTUAL, "total_tax_krw": Decimal("600000")}
        report = compare(COMPUTED, actual, tax_year=2025)
        data = json.loads(to_json(report))
        assert data["gate_g2_pass"] is False


# ── main (CLI) ─────────────────────────────────────────────


class TestMain:
    def _csv(self, tmp_path) -> Path:
        p = tmp_path / "summary.csv"
        _write_summary_csv(p, SAMPLE)
        return p

    def _base_args(self, csv_path: Path) -> list[str]:
        return [
            "--summary",
            str(csv_path),
            "--actual-gain",
            "5000000",
            "--actual-taxable",
            "2500000",
            "--actual-national-tax",
            "500000",
            "--actual-local-tax",
            "50000",
            "--actual-total-tax",
            "550000",
        ]

    def test_perfect_match_returns_0(self, tmp_path):
        assert main(self._base_args(self._csv(tmp_path))) == 0

    def test_fail_returns_1(self, tmp_path):
        args = self._base_args(self._csv(tmp_path))
        args[args.index("--actual-national-tax") + 1] = "600000"
        assert main(args) == 1

    def test_missing_file_returns_2(self, tmp_path):
        args = [
            "--summary",
            str(tmp_path / "none.csv"),
            "--actual-gain",
            "0",
            "--actual-taxable",
            "0",
            "--actual-national-tax",
            "0",
            "--actual-local-tax",
            "0",
            "--actual-total-tax",
            "0",
        ]
        assert main(args) == 2

    def test_writes_json_report_on_pass(self, tmp_path):
        out = tmp_path / "report.json"
        args = [*self._base_args(self._csv(tmp_path)), "--out", str(out)]
        main(args)
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["gate_g2_pass"] is True
        assert data["tax_year"] == 2025

    def test_writes_json_report_on_fail(self, tmp_path):
        out = tmp_path / "report.json"
        args = self._base_args(self._csv(tmp_path))
        args[args.index("--actual-total-tax") + 1] = "999999"
        args = [*args, "--out", str(out)]
        main(args)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["gate_g2_pass"] is False

    def test_custom_tolerance_200won_pass(self, tmp_path):
        args = self._base_args(self._csv(tmp_path))
        args[args.index("--actual-gain") + 1] = "5000150"
        args = [*args, "--tolerance", "200"]
        assert main(args) == 0

    def test_custom_tolerance_50won_fail(self, tmp_path):
        args = self._base_args(self._csv(tmp_path))
        args[args.index("--actual-gain") + 1] = "5000051"
        args = [*args, "--tolerance", "50"]
        assert main(args) == 1
