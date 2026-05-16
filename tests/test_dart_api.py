"""DART OpenAPI 어댑터 단위 테스트 (T020).

Coverage target: sentinelq/adapters/dart_api.py >= 90%
PREREG: PREREG-0011 §2.1-2.2
실제 DART API 미호출 — urllib.request.urlopen을 monkeypatch로 대체.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from sentinelq.adapters.dart_api import (
    DisclosureRecord,
    _classify,
    fetch_disclosures,
    fetch_holdings_disclosures,
    load_corp_code_map,
)

# ── 헬퍼 ──────────────────────────────────────────────────────


def _mock_urlopen(payload: dict):
    """urllib.request.urlopen을 모의하는 context manager mock."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(payload).encode("utf-8")
    return mock


_BASE_ITEM = {
    "corp_code": "00126380",
    "corp_name": "삼성전자",
    "stock_code": "005930",
    "corp_cls": "Y",
    "report_nm": "분기보고서",
    "rcept_no": "20260514000111",
    "flr_nm": "삼성전자",
    "rcept_dt": "20260514",
    "rm": "",
}

_HIGH_ITEM = {
    **_BASE_ITEM,
    "report_nm": "유상증자결정",
    "rcept_no": "20260513000222",
}


def _ok_payload(items: list[dict]) -> dict:
    return {"status": "000", "message": "OK", "total_count": len(items), "list": items}


# ── _classify ─────────────────────────────────────────────────


class TestClassify:
    def test_quarterly_report_is_normal(self):
        assert _classify("분기보고서") == "NORMAL"

    def test_annual_report_is_normal(self):
        assert _classify("사업보고서") == "NORMAL"

    def test_capital_increase_is_high(self):
        assert _classify("유상증자결정") == "HIGH"

    def test_merger_is_high(self):
        assert _classify("합병결정") == "HIGH"

    def test_delisting_is_high(self):
        assert _classify("상장폐지") == "HIGH"

    def test_major_report_is_high(self):
        assert _classify("주요사항보고서(유상증자)") == "HIGH"

    def test_unknown_is_normal(self):
        assert _classify("임원변경") == "NORMAL"


# ── load_corp_code_map ────────────────────────────────────────


class TestLoadCorpCodeMap:
    def test_loads_dict_format(self, tmp_path):
        cache = tmp_path / "corp_code.json"
        cache.write_text(
            json.dumps({"005930": {"corp_code": "00126380", "corp_name": "삼성전자"}}),
            encoding="utf-8",
        )
        result = load_corp_code_map(cache)
        assert result["005930"] == "00126380"

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_corp_code_map(tmp_path / "nonexistent.json")
        assert result == {}

    def test_multiple_entries(self, tmp_path):
        cache = tmp_path / "corp_code.json"
        data = {
            "005930": {"corp_code": "00126380", "corp_name": "삼성전자"},
            "000660": {"corp_code": "00164779", "corp_name": "SK하이닉스"},
        }
        cache.write_text(json.dumps(data), encoding="utf-8")
        result = load_corp_code_map(cache)
        assert len(result) == 2
        assert result["000660"] == "00164779"


# ── fetch_disclosures ─────────────────────────────────────────


class TestFetchDisclosures:
    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_basic_record_parsed(self, mock_open):
        mock_open.return_value = _mock_urlopen(_ok_payload([_BASE_ITEM]))
        records = fetch_disclosures(
            "00126380",
            date(2026, 5, 1),
            date(2026, 5, 14),
            api_key="test_key",
        )
        assert len(records) == 1
        r = records[0]
        assert r.corp_code == "00126380"
        assert r.corp_name == "삼성전자"
        assert r.stock_code == "005930"
        assert r.report_name == "분기보고서"
        assert r.receipt_no == "20260514000111"
        assert r.receipt_date == date(2026, 5, 14)
        assert r.importance == "NORMAL"

    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_high_importance_classified(self, mock_open):
        mock_open.return_value = _mock_urlopen(_ok_payload([_HIGH_ITEM]))
        records = fetch_disclosures("00126380", date(2026, 5, 1), date(2026, 5, 14), api_key="key")
        assert records[0].importance == "HIGH"

    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_status_013_returns_empty(self, mock_open):
        mock_open.return_value = _mock_urlopen(
            {"status": "013", "message": "데이터 없음", "list": []}
        )
        records = fetch_disclosures("00126380", date(2026, 5, 1), date(2026, 5, 14), api_key="key")
        assert records == []

    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_error_status_raises(self, mock_open):
        mock_open.return_value = _mock_urlopen({"status": "999", "message": "서버 오류"})
        with pytest.raises(RuntimeError, match="DART API 오류"):
            fetch_disclosures("00126380", date(2026, 5, 1), date(2026, 5, 14), api_key="key")

    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_url_constructed_correctly(self, mock_open):
        mock_open.return_value = _mock_urlopen(_ok_payload([]))
        fetch_disclosures("00126380", date(2026, 5, 1), date(2026, 5, 14), api_key="mykey")
        call_url = mock_open.call_args[0][0]
        assert "corp_code=00126380" in call_url
        assert "bgn_de=20260501" in call_url
        assert "end_de=20260514" in call_url
        assert "crtfc_key=mykey" in call_url

    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_dart_url_in_record(self, mock_open):
        mock_open.return_value = _mock_urlopen(_ok_payload([_BASE_ITEM]))
        records = fetch_disclosures("00126380", date(2026, 5, 1), date(2026, 5, 14), api_key="key")
        assert "20260514000111" in records[0].url
        assert "dart.fss.or.kr" in records[0].url

    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_invalid_date_row_skipped(self, mock_open):
        bad_item = {**_BASE_ITEM, "rcept_dt": "INVALID"}
        mock_open.return_value = _mock_urlopen(_ok_payload([bad_item, _BASE_ITEM]))
        records = fetch_disclosures("00126380", date(2026, 5, 1), date(2026, 5, 14), api_key="key")
        assert len(records) == 1  # bad_item 건너뜀


# ── fetch_holdings_disclosures ────────────────────────────────


class TestFetchHoldingsDisclosures:
    @patch("sentinelq.adapters.dart_api.time.sleep")
    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_basic_two_stocks(self, mock_open, mock_sleep):
        mock_open.return_value = _mock_urlopen(_ok_payload([_BASE_ITEM]))
        corp_map = {"005930": "00126380", "000660": "00164779"}
        _records, skipped = fetch_holdings_disclosures(
            ["005930", "000660"],
            date(2026, 5, 1),
            date(2026, 5, 14),
            api_key="key",
            corp_map=corp_map,
        )
        assert mock_open.call_count == 2
        assert skipped == []

    @patch("sentinelq.adapters.dart_api.time.sleep")
    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_skips_missing_corp_code(self, mock_open, mock_sleep):
        mock_open.return_value = _mock_urlopen(_ok_payload([_BASE_ITEM]))
        corp_map = {"005930": "00126380"}  # 000660 없음
        _records, skipped = fetch_holdings_disclosures(
            ["005930", "000660"],
            date(2026, 5, 1),
            date(2026, 5, 14),
            api_key="key",
            corp_map=corp_map,
        )
        assert "000660" in skipped
        assert mock_open.call_count == 1

    @patch("sentinelq.adapters.dart_api.time.sleep")
    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_deduplicates_by_receipt_no(self, mock_open, mock_sleep):
        # 같은 접수번호가 두 번 나와도 1건만 포함
        mock_open.return_value = _mock_urlopen(_ok_payload([_BASE_ITEM, _BASE_ITEM]))
        corp_map = {"005930": "00126380"}
        records, _ = fetch_holdings_disclosures(
            ["005930"],
            date(2026, 5, 1),
            date(2026, 5, 14),
            api_key="key",
            corp_map=corp_map,
        )
        assert len(records) == 1

    @patch("sentinelq.adapters.dart_api.time.sleep")
    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_importance_filter_high_only(self, mock_open, mock_sleep):
        mock_open.return_value = _mock_urlopen(_ok_payload([_BASE_ITEM, _HIGH_ITEM]))
        corp_map = {"005930": "00126380"}
        records, _ = fetch_holdings_disclosures(
            ["005930"],
            date(2026, 5, 1),
            date(2026, 5, 14),
            api_key="key",
            corp_map=corp_map,
            importance_filter="HIGH",
        )
        assert all(r.importance == "HIGH" for r in records)

    @patch("sentinelq.adapters.dart_api.time.sleep")
    @patch("sentinelq.adapters.dart_api.urllib.request.urlopen")
    def test_returns_disclosure_record_type(self, mock_open, mock_sleep):
        mock_open.return_value = _mock_urlopen(_ok_payload([_BASE_ITEM]))
        corp_map = {"005930": "00126380"}
        records, _ = fetch_holdings_disclosures(
            ["005930"],
            date(2026, 5, 1),
            date(2026, 5, 14),
            api_key="key",
            corp_map=corp_map,
        )
        assert isinstance(records[0], DisclosureRecord)
