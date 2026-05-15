"""T007 — 오케스트레이션 파이프라인 테스트.

Coverage target: sentinelq/reports/tax_report.py >= 85%
AC 범위: AC1-AC15 (spec-T007.md §5)
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sentinelq.adapters.kis_history import Transaction
from sentinelq.reports.nts_form import export_detail_csv, export_summary_csv
from sentinelq.reports.tax_report import (
    main,
    run_pipeline,
    transactions_from_json,
    transactions_to_json,
    write_report,
)

_D = Decimal


# ---- 헬퍼 팩토리 ----


def _kr(
    trade_date: date,
    side: str,
    qty: int,
    price: str,
    fee: str = "0",
    tax: str = "0",
    ticker: str = "005930",
) -> Transaction:
    return Transaction(
        trade_date=trade_date,
        settle_date=None,
        ticker=ticker,
        market="KR",
        side=side,
        quantity=qty,
        price=_D(price),
        currency="KRW",
        fee=_D(fee),
        tax=_D(tax),
    )


def _us(
    trade_date: date,
    side: str,
    qty: int,
    price: str,
    fx_rate: str = "1300",
    fee: str = "0",
    tax: str = "0",
    ticker: str = "AAPL",
) -> Transaction:
    return Transaction(
        trade_date=trade_date,
        settle_date=None,
        ticker=ticker,
        market="US",
        side=side,
        quantity=qty,
        price=_D(price),
        currency="USD",
        fee=_D(fee),
        tax=_D(tax),
        fx_rate=_D(fx_rate),
    )


def _write_json_fixture(txs: list[Transaction], tmp_path: Path) -> Path:
    p = tmp_path / "transactions.json"
    p.write_text(transactions_to_json(txs), encoding="utf-8")
    return p


# ---- 순수 파이프라인 ----


def test_run_pipeline_kr_buy_sell():
    """AC1: KR 매수→매도 1쌍, 양도차익·과세표준·세금 수동 계산과 일치."""
    txs = [
        _kr(date(2025, 1, 10), "BUY", 100, "10000"),
        _kr(date(2025, 6, 15), "SELL", 100, "40000"),
    ]
    form = run_pipeline(txs, 2025)
    # gain = 100 * (40000 - 10000) = 3_000_000
    assert form.total_realized_gain_krw == _D("3000000")
    # taxable = 3_000_000 - 2_500_000 = 500_000
    assert form.taxable_base_krw == _D("500000")
    # national = floor(500_000 * 0.20) = 100_000
    assert form.national_tax_krw == _D("100000")
    # local = floor(100_000 * 0.10) = 10_000
    assert form.local_tax_krw == _D("10000")
    assert form.total_tax_krw == _D("110000")
    assert form.sale_count == 1


def test_run_pipeline_us_with_fx():
    """AC2: US 매수→매도 fx 환산 정확."""
    txs = [
        _us(date(2025, 2, 1), "BUY", 10, "100", fx_rate="1300"),
        _us(date(2025, 9, 1), "SELL", 10, "150", fx_rate="1350"),
    ]
    form = run_pipeline(txs, 2025)
    # cost_per_share = 100 * 1300 = 130000
    # proceeds_per_share = 150 * 1350 = 202500
    # gain = (202500 - 130000) * 10 = 725000
    assert form.total_realized_gain_krw == _D("725000")
    assert form.sale_count == 1
    assert len(form.by_market) == 1
    assert form.by_market[0].market == "US"


def test_run_pipeline_kr_us_mixed():
    """AC3: KR+US 혼합 → by_market 2개, 합산 양도차익 정확."""
    txs = [
        _kr(date(2025, 1, 1), "BUY", 100, "10000"),
        _kr(date(2025, 6, 1), "SELL", 100, "40000"),  # KR gain=3_000_000
        _us(date(2025, 2, 1), "BUY", 10, "100", fx_rate="1300"),
        _us(date(2025, 9, 1), "SELL", 10, "150", fx_rate="1350"),  # US gain=725_000
    ]
    form = run_pipeline(txs, 2025)
    assert form.sale_count == 2
    assert len(form.by_market) == 2
    assert form.total_realized_gain_krw == _D("3725000")
    # taxable = 3_725_000 - 2_500_000 = 1_225_000
    assert form.taxable_base_krw == _D("1225000")


def test_run_pipeline_empty():
    """AC4: 빈 입력 → 영 폼, crash 없음, exit 개념 없음."""
    form = run_pipeline([], 2025)
    assert form.sale_count == 0
    assert form.total_realized_gain_krw == _D("0")
    assert form.total_tax_krw == _D("0")
    assert form.taxable_base_krw == _D("0")


def test_run_pipeline_filters_other_years():
    """AC5: 2024·2025 매도 섞임, tax_year=2025 → 2025 매도만 form 반영."""
    txs = [
        _kr(date(2023, 1, 1), "BUY", 200, "10000"),
        _kr(date(2024, 3, 1), "SELL", 100, "20000"),  # 2024 매도 → 제외
        _kr(date(2025, 6, 1), "SELL", 100, "40000"),  # 2025 매도 → 포함
    ]
    form = run_pipeline(txs, 2025)
    assert form.sale_count == 1
    # 2025 sell: cost=10000*100=1_000_000, proceeds=40000*100=4_000_000
    assert form.total_realized_gain_krw == _D("3000000")


def test_run_pipeline_buy_before_tax_year():
    """AC6: 과세연도 이전 매수 lot을 당해 매도에서 정상 소비 (FIFO)."""
    txs = [
        _kr(date(2023, 5, 1), "BUY", 50, "8000"),  # 이전 연도 매수
        _kr(date(2025, 8, 1), "SELL", 50, "20000"),  # 당해 매도
    ]
    form = run_pipeline(txs, 2025)
    assert form.sale_count == 1
    # gain = 50 * (20000 - 8000) = 600_000
    assert form.total_realized_gain_krw == _D("600000")


# ---- JSON 직렬화 ----


def test_transactions_json_roundtrip():
    """AC7: to_json → from_json 동치 (Decimal·date 보존)."""
    txs = [
        _kr(date(2025, 1, 10), "BUY", 100, "12345.67"),
        _us(date(2025, 3, 20), "SELL", 5, "99.99", fx_rate="1320.50"),
    ]
    recovered = transactions_from_json(transactions_to_json(txs))
    assert recovered == list(txs)


def test_transactions_from_json_without_raw():
    """AC8: raw 필드 없는 JSON → raw=빈 dict."""
    data = [
        {
            "trade_date": "2025-01-10",
            "settle_date": None,
            "ticker": "005930",
            "market": "KR",
            "side": "BUY",
            "quantity": 10,
            "price": "10000",
            "currency": "KRW",
            "fee": "0",
            "tax": "0",
            "fx_rate": None,
            # 'raw' 생략
        }
    ]
    txs = transactions_from_json(json.dumps(data))
    assert len(txs) == 1
    assert txs[0].raw == {}


def test_json_preserves_decimal():
    """AC15: JSON 내 Decimal 값이 float repr (e+, e-) 없이 문자열 저장."""
    txs = [_kr(date(2025, 1, 1), "BUY", 1, "0.0001")]
    json_str = transactions_to_json(txs)
    assert "e-" not in json_str
    assert "e+" not in json_str
    assert '"0.0001"' in json_str


# ---- 리포트 기록 ----


def test_write_report_creates_two_csv(tmp_path):
    """AC9: write_report → summary·detail 2개 파일 생성."""
    form = run_pipeline([], 2025)
    summary_path, detail_path = write_report(form, tmp_path / "out")
    assert summary_path.exists()
    assert detail_path.exists()
    assert "summary" in summary_path.name
    assert "detail" in detail_path.name
    assert "2025" in summary_path.name


def test_write_report_content_matches_export(tmp_path):
    """write_report 내용이 export_*_csv 결과와 동일."""
    txs = [
        _kr(date(2025, 1, 10), "BUY", 100, "10000"),
        _kr(date(2025, 6, 15), "SELL", 100, "40000"),
    ]
    form = run_pipeline(txs, 2025)
    summary_path, detail_path = write_report(form, tmp_path / "out")
    # read back with newline="" to match csv.writer's \r\n
    with summary_path.open("r", encoding="utf-8", newline="") as fh:
        assert fh.read() == export_summary_csv(form)
    with detail_path.open("r", encoding="utf-8", newline="") as fh:
        assert fh.read() == export_detail_csv(form)


# ---- main() end-to-end ----


def test_main_from_json_exit_zero(tmp_path):
    """AC10: --from-json offline end-to-end → exit 0 + CSV 2개 파일."""
    txs = [
        _kr(date(2025, 1, 10), "BUY", 100, "10000"),
        _kr(date(2025, 6, 15), "SELL", 100, "40000"),
    ]
    json_path = _write_json_fixture(txs, tmp_path)
    out_dir = tmp_path / "out"
    exit_code = main(
        [
            "--from-json",
            str(json_path),
            "--tax-year",
            "2025",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 0
    assert (out_dir / "nts_summary_2025.csv").exists()
    assert (out_dir / "nts_detail_2025.csv").exists()


def test_main_missing_json_file_nonzero(tmp_path):
    """AC11: --from-json 없는 경로 → 비0 종료, traceback 미노출."""
    missing = tmp_path / "nonexistent.json"
    exit_code = main(
        [
            "--from-json",
            str(missing),
            "--tax-year",
            "2025",
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 5


def test_main_insufficient_lots_graceful(tmp_path, capsys):
    """AC12: lot 부족 → 명확 메시지 + 비0 종료 (exit 2), traceback 미노출."""
    sell_only = [_kr(date(2025, 6, 1), "SELL", 10, "20000")]
    json_path = _write_json_fixture(sell_only, tmp_path)
    exit_code = main(
        [
            "--from-json",
            str(json_path),
            "--tax-year",
            "2025",
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "start-date" in captured.err or "매수" in captured.err


def test_main_console_summary_has_numbers(tmp_path, capsys):
    """AC14: capsys로 콘솔 요약에 핵심 숫자 포함 확인."""
    txs = [
        _kr(date(2025, 1, 10), "BUY", 100, "10000"),
        _kr(date(2025, 6, 15), "SELL", 100, "40000"),
    ]
    json_path = _write_json_fixture(txs, tmp_path)
    out_dir = tmp_path / "out"
    main(
        [
            "--from-json",
            str(json_path),
            "--tax-year",
            "2025",
            "--out-dir",
            str(out_dir),
        ]
    )
    captured = capsys.readouterr()
    assert "3,000,000" in captured.out  # total_realized_gain_krw
    assert "500,000" in captured.out  # taxable_base_krw
    assert "100,000" in captured.out  # national_tax_krw


def test_main_tax_year_default(tmp_path, capsys):
    """--tax-year 미지정 시 직전 캘린더 연도 사용 (2026-05-15 → 2025)."""
    json_path = tmp_path / "empty.json"
    json_path.write_text("[]", encoding="utf-8")
    out_dir = tmp_path / "out"
    exit_code = main(
        [
            "--from-json",
            str(json_path),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "2025" in captured.out


def test_main_live_without_confirm_live(tmp_path, monkeypatch):
    """AC13: --env live + --confirm-live 누락 → fetch 거부, exit 4."""
    monkeypatch.delenv("SENTINELQ_LIVE_ALLOW", raising=False)
    exit_code = main(
        [
            "--env",
            "live",
            "--tax-year",
            "2025",
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 4


def test_main_dump_json(tmp_path):
    """--dump-json: fetch 결과(또는 --from-json 입력)를 JSON 파일로 저장."""
    txs = [_kr(date(2025, 1, 10), "BUY", 100, "10000")]
    json_path = _write_json_fixture(txs, tmp_path)
    dump_path = tmp_path / "dump.json"
    out_dir = tmp_path / "out"
    exit_code = main(
        [
            "--from-json",
            str(json_path),
            "--tax-year",
            "2025",
            "--out-dir",
            str(out_dir),
            "--dump-json",
            str(dump_path),
        ]
    )
    assert exit_code == 0
    assert dump_path.exists()
    recovered = transactions_from_json(dump_path.read_text(encoding="utf-8"))
    assert recovered == list(txs)


# ---- 견고성·정밀도 ----


def test_run_pipeline_sort_buy_before_sell_same_date():
    """E2: 동일 날짜 BUY가 SELL보다 먼저 정렬 → lot 소비 성공."""
    txs = [
        _kr(date(2025, 6, 1), "SELL", 10, "20000"),  # 입력 순서 SELL 먼저
        _kr(date(2025, 6, 1), "BUY", 10, "10000"),  # BUY 나중
    ]
    form = run_pipeline(txs, 2025)
    assert form.sale_count == 1
    assert form.total_realized_gain_krw == _D("100000")


def test_decimal_only_no_float():
    """run_pipeline 결과 금액 필드가 모두 Decimal 타입."""
    txs = [
        _kr(date(2025, 1, 10), "BUY", 100, "10000"),
        _kr(date(2025, 6, 15), "SELL", 100, "40000"),
    ]
    form = run_pipeline(txs, 2025)
    assert isinstance(form.total_realized_gain_krw, Decimal)
    assert isinstance(form.taxable_base_krw, Decimal)
    assert isinstance(form.national_tax_krw, Decimal)
    assert isinstance(form.local_tax_krw, Decimal)
    assert isinstance(form.total_tax_krw, Decimal)
