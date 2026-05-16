"""키움증권 HTS CSV 파서 단위 테스트 (T009).

Coverage target: sentinelq/adapters/kiwoom_csv.py >= 90%
PREREG: PREREG-0008-amendment-2 §2.1
"""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from sentinelq.adapters.kiwoom_csv import (
    KiwoomParseError,
    _dec,
    _parse_date,
    _parse_side,
    parse_kiwoom_csv,
)

# ── 픽스처 헬퍼 ─────────────────────────────────────────────────


def _write_csv(path: Path, rows: list[dict], encoding: str = "utf-8-sig") -> None:
    if not rows:
        path.write_text("", encoding=encoding)
        return
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# 키움증권 해외주식 체결내역 표준 컬럼
_BASE_ROW: dict = {
    "체결일자": "20250612",
    "종목코드": "NVDA",
    "종목명": "NVIDIA",
    "매매구분": "매도",
    "체결수량": "80",
    "체결단가": "196.87",
    "체결금액": "15,749.60",
    "원화환산금액": "21,387,637",
    "수수료": "15,750",
    "세금": "0",
    "통화코드": "USD",
    "정산일": "20250615",
}

_BUY_ROW: dict = {
    **_BASE_ROW,
    "체결일자": "20250303",
    "종목코드": "NVDA",
    "매매구분": "매수",
    "체결수량": "80",
    "체결단가": "113.44",
    "체결금액": "9,075.20",
    "원화환산금액": "13,259,917",
    "수수료": "9,075",
    "정산일": "20250306",
}


# ── _dec ────────────────────────────────────────────────────────


class TestDec:
    def test_plain(self):
        assert _dec("1234") == Decimal("1234")

    def test_comma(self):
        assert _dec("1,234.56") == Decimal("1234.56")

    def test_empty(self):
        assert _dec("") == Decimal("0")

    def test_dash(self):
        assert _dec("-") == Decimal("0")

    def test_invalid(self):
        with pytest.raises(ValueError):
            _dec("abc")


# ── _parse_date ─────────────────────────────────────────────────


class TestParseDate:
    def test_yyyymmdd(self):
        assert _parse_date("20250612") == date(2025, 6, 12)

    def test_dash_separated(self):
        assert _parse_date("2025-06-12") == date(2025, 6, 12)

    def test_slash_separated(self):
        assert _parse_date("2025/06/12") == date(2025, 6, 12)

    def test_invalid(self):
        with pytest.raises(ValueError):
            _parse_date("not-a-date")


# ── _parse_side ─────────────────────────────────────────────────


class TestParseSide:
    def test_sell_korean(self):
        assert _parse_side("매도") == "SELL"

    def test_buy_korean(self):
        assert _parse_side("매수") == "BUY"

    def test_sell_english(self):
        assert _parse_side("sell") == "SELL"

    def test_buy_english(self):
        assert _parse_side("buy") == "BUY"

    def test_unknown(self):
        with pytest.raises(ValueError):
            _parse_side("unknown")


# ── parse_kiwoom_csv — 정상 케이스 ─────────────────────────────


class TestParseKiwoomCsv:
    def test_single_sell_row(self, tmp_path):
        p = tmp_path / "kiwoom.csv"
        _write_csv(p, [_BASE_ROW])
        result = parse_kiwoom_csv(p)
        assert len(result) == 1
        t = result[0]
        assert t.ticker == "NVDA"
        assert t.side == "SELL"
        assert t.quantity == 80
        assert t.trade_date == date(2025, 6, 12)
        assert t.settle_date == date(2025, 6, 15)
        assert t.currency == "USD"
        assert t.market == "US"
        assert t.price == Decimal("196.87")
        assert t.fee == Decimal("15750")

    def test_buy_and_sell_rows(self, tmp_path):
        p = tmp_path / "kiwoom.csv"
        _write_csv(p, [_BUY_ROW, _BASE_ROW])
        result = parse_kiwoom_csv(p)
        assert len(result) == 2
        assert result[0].side == "BUY"
        assert result[1].side == "SELL"

    def test_fx_rate_derived(self, tmp_path):
        p = tmp_path / "kiwoom.csv"
        _write_csv(p, [_BASE_ROW])
        result = parse_kiwoom_csv(p)
        t = result[0]
        # 원화환산금액 / 체결금액 = 21387637 / 15749.60
        expected = Decimal("21387637") / Decimal("15749.60")
        assert t.fx_rate is not None
        assert abs(t.fx_rate - expected) < Decimal("0.01")

    def test_domestic_stock(self, tmp_path):
        kr_row = {
            "체결일자": "20251106",
            "종목코드": "005930",
            "종목명": "삼성전자",
            "매매구분": "매도",
            "체결수량": "10",
            "체결단가": "58500",
            "체결금액": "585000",
            "원화환산금액": "585000",
            "수수료": "350",
            "세금": "880",
            "통화코드": "KRW",
            "정산일": "20251108",
        }
        p = tmp_path / "kiwoom_kr.csv"
        _write_csv(p, [kr_row])
        result = parse_kiwoom_csv(p)
        assert len(result) == 1
        t = result[0]
        assert t.market == "KR"
        assert t.currency == "KRW"
        assert t.ticker == "005930"

    def test_skips_zero_quantity(self, tmp_path):
        zero_row = {**_BASE_ROW, "체결수량": "0"}
        p = tmp_path / "kiwoom.csv"
        _write_csv(p, [zero_row])
        result = parse_kiwoom_csv(p)
        assert result == []

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.csv"
        _write_csv(p, [])
        result = parse_kiwoom_csv(p)
        assert result == []

    def test_euc_kr_encoding(self, tmp_path):
        p = tmp_path / "kiwoom_euckr.csv"
        _write_csv(p, [_BASE_ROW], encoding="euc-kr")
        result = parse_kiwoom_csv(p)
        assert len(result) == 1
        assert result[0].ticker == "NVDA"

    def test_missing_required_column_raises(self, tmp_path):
        bad_row = {k: v for k, v in _BASE_ROW.items() if k != "종목코드"}
        p = tmp_path / "bad.csv"
        _write_csv(p, [bad_row])
        with pytest.raises(KiwoomParseError, match="종목코드"):
            parse_kiwoom_csv(p)

    def test_col_map_override(self, tmp_path):
        renamed = {
            "거래일": "20250612",
            "코드": "AAPL",
            "매매구분": "매도",
            "체결수량": "30",
            "체결단가": "227.50",
            "체결금액": "6825.00",
            "원화환산금액": "9893475",
            "수수료": "6825",
            "세금": "0",
            "통화코드": "USD",
        }
        p = tmp_path / "renamed.csv"
        _write_csv(p, [renamed])
        result = parse_kiwoom_csv(
            p,
            col_map={"체결일자": "거래일", "종목코드": "코드"},
        )
        assert len(result) == 1
        assert result[0].ticker == "AAPL"

    def test_col_map_file_override(self, tmp_path):
        renamed = {
            "날짜": "20250612",
            "코드": "TSLA",
            "매매구분": "매수",
            "체결수량": "5",
            "체결단가": "280.00",
            "체결금액": "1400.00",
            "원화환산금액": "2030000",
            "수수료": "1400",
            "세금": "0",
            "통화코드": "USD",
        }
        csv_path = tmp_path / "renamed.csv"
        _write_csv(csv_path, [renamed])
        map_path = tmp_path / "col_map.json"
        map_path.write_text(json.dumps({"체결일자": "날짜", "종목코드": "코드"}), encoding="utf-8")
        result = parse_kiwoom_csv(csv_path, col_map_file=map_path)
        assert result[0].ticker == "TSLA"

    def test_missing_currency_defaults_to_usd(self, tmp_path):
        row = {**_BASE_ROW, "통화코드": "XYZ"}
        p = tmp_path / "kiwoom.csv"
        _write_csv(p, [row])
        result = parse_kiwoom_csv(p)
        assert result[0].currency == "USD"

    def test_invalid_date_raises(self, tmp_path):
        bad = {**_BASE_ROW, "체결일자": "not-a-date"}
        p = tmp_path / "bad.csv"
        _write_csv(p, [bad])
        with pytest.raises(KiwoomParseError):
            parse_kiwoom_csv(p)

    def test_multiple_tickers(self, tmp_path):
        aapl_buy = {
            **_BUY_ROW,
            "종목코드": "AAPL",
            "종목명": "Apple",
            "체결일자": "20250101",
        }
        rows = [aapl_buy, _BUY_ROW, _BASE_ROW]
        p = tmp_path / "multi.csv"
        _write_csv(p, rows)
        result = parse_kiwoom_csv(p)
        assert len(result) == 3
        tickers = {t.ticker for t in result}
        assert tickers == {"AAPL", "NVDA"}
