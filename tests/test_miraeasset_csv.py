"""미래에셋증권 HTS CSV 파서 단위 테스트 (T010).

Coverage target: sentinelq/adapters/miraeasset_csv.py >= 90%
PREREG: PREREG-0008-amendment-2 §2.1
"""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from sentinelq.adapters.miraeasset_csv import (
    MiraeAssetParseError,
    parse_miraeasset_csv,
)


def _write_csv(path: Path, rows: list[dict], encoding: str = "utf-8-sig") -> None:
    if not rows:
        path.write_text("", encoding=encoding)
        return
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# 미래에셋증권 HTS 해외주식 체결내역 표준 컬럼
_BASE_ROW: dict = {
    "거래일자": "20250612",
    "종목코드": "NVDA",
    "종목명": "NVIDIA",
    "매도매수구분": "매도",
    "거래수량": "80",
    "거래단가(외화)": "196.87",
    "거래금액(외화)": "15,749.60",
    "거래금액(원화)": "21,387,637",
    "수수료(원화)": "15,750",
    "거래세": "0",
    "통화": "USD",
    "결제일자": "20250615",
}

_BUY_ROW: dict = {
    **_BASE_ROW,
    "거래일자": "20250303",
    "매도매수구분": "매수",
    "거래수량": "80",
    "거래단가(외화)": "113.44",
    "거래금액(외화)": "9,075.20",
    "거래금액(원화)": "13,259,917",
    "수수료(원화)": "9,075",
    "결제일자": "20250306",
}


class TestParseMiraeAssetCsv:
    def test_single_sell_row(self, tmp_path):
        p = tmp_path / "mirae.csv"
        _write_csv(p, [_BASE_ROW])
        result = parse_miraeasset_csv(p)
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
        p = tmp_path / "mirae.csv"
        _write_csv(p, [_BUY_ROW, _BASE_ROW])
        result = parse_miraeasset_csv(p)
        assert len(result) == 2
        assert result[0].side == "BUY"
        assert result[1].side == "SELL"

    def test_fx_rate_derived(self, tmp_path):
        p = tmp_path / "mirae.csv"
        _write_csv(p, [_BASE_ROW])
        result = parse_miraeasset_csv(p)
        t = result[0]
        expected = Decimal("21387637") / Decimal("15749.60")
        assert t.fx_rate is not None
        assert abs(t.fx_rate - expected) < Decimal("0.01")

    def test_domestic_stock(self, tmp_path):
        kr_row = {
            "거래일자": "20251106",
            "종목코드": "005930",
            "종목명": "삼성전자",
            "매도매수구분": "매도",
            "거래수량": "10",
            "거래단가(외화)": "58500",
            "거래금액(외화)": "585000",
            "거래금액(원화)": "585000",
            "수수료(원화)": "350",
            "거래세": "880",
            "통화": "KRW",
            "결제일자": "20251108",
        }
        p = tmp_path / "mirae_kr.csv"
        _write_csv(p, [kr_row])
        result = parse_miraeasset_csv(p)
        assert len(result) == 1
        t = result[0]
        assert t.market == "KR"
        assert t.currency == "KRW"
        assert t.ticker == "005930"

    def test_skips_zero_quantity(self, tmp_path):
        row = {**_BASE_ROW, "거래수량": "0"}
        p = tmp_path / "mirae.csv"
        _write_csv(p, [row])
        result = parse_miraeasset_csv(p)
        assert result == []

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.csv"
        _write_csv(p, [])
        result = parse_miraeasset_csv(p)
        assert result == []

    def test_euc_kr_encoding(self, tmp_path):
        p = tmp_path / "mirae_euckr.csv"
        _write_csv(p, [_BASE_ROW], encoding="euc-kr")
        result = parse_miraeasset_csv(p)
        assert len(result) == 1
        assert result[0].ticker == "NVDA"

    def test_missing_required_column_raises(self, tmp_path):
        bad_row = {k: v for k, v in _BASE_ROW.items() if k != "종목코드"}
        p = tmp_path / "bad.csv"
        _write_csv(p, [bad_row])
        with pytest.raises(MiraeAssetParseError, match="종목코드"):
            parse_miraeasset_csv(p)

    def test_col_map_override(self, tmp_path):
        renamed = {
            "날짜": "20250612",
            "코드": "AAPL",
            "매도매수구분": "매도",
            "거래수량": "30",
            "거래단가(외화)": "227.50",
            "거래금액(외화)": "6825.00",
            "거래금액(원화)": "9893475",
            "수수료(원화)": "6825",
            "거래세": "0",
            "통화": "USD",
        }
        p = tmp_path / "renamed.csv"
        _write_csv(p, [renamed])
        result = parse_miraeasset_csv(
            p,
            col_map={"거래일자": "날짜", "종목코드": "코드"},
        )
        assert len(result) == 1
        assert result[0].ticker == "AAPL"

    def test_col_map_file_override(self, tmp_path):
        renamed = {
            "날짜": "20250612",
            "코드": "TSLA",
            "매도매수구분": "매수",
            "거래수량": "5",
            "거래단가(외화)": "280.00",
            "거래금액(외화)": "1400.00",
            "거래금액(원화)": "2030000",
            "수수료(원화)": "1400",
            "거래세": "0",
            "통화": "USD",
        }
        csv_path = tmp_path / "renamed.csv"
        _write_csv(csv_path, [renamed])
        map_path = tmp_path / "col_map.json"
        map_path.write_text(json.dumps({"거래일자": "날짜", "종목코드": "코드"}), encoding="utf-8")
        result = parse_miraeasset_csv(csv_path, col_map_file=map_path)
        assert result[0].ticker == "TSLA"

    def test_multiple_tickers(self, tmp_path):
        aapl_buy = {
            **_BUY_ROW,
            "종목코드": "AAPL",
            "종목명": "Apple",
            "거래일자": "20250101",
        }
        p = tmp_path / "multi.csv"
        _write_csv(p, [aapl_buy, _BUY_ROW, _BASE_ROW])
        result = parse_miraeasset_csv(p)
        assert len(result) == 3
        assert {t.ticker for t in result} == {"AAPL", "NVDA"}

    def test_invalid_date_raises(self, tmp_path):
        bad = {**_BASE_ROW, "거래일자": "not-a-date"}
        p = tmp_path / "bad.csv"
        _write_csv(p, [bad])
        with pytest.raises(MiraeAssetParseError):
            parse_miraeasset_csv(p)
