"""DART 공시 모니터링 단위 테스트 (T021).

Coverage target: sentinelq/monitoring/dart_monitor.py >= 90%
PREREG: PREREG-0011 §2.3
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from sentinelq.adapters.dart_api import DisclosureRecord
from sentinelq.monitoring.dart_monitor import MonitorResult, run_monitor


def _disclosure(
    stock_code: str = "005930",
    report_name: str = "분기보고서",
    importance: str = "NORMAL",
    rcept_no: str = "20260514000111",
) -> DisclosureRecord:
    return DisclosureRecord(
        corp_code="00126380",
        corp_name="삼성전자",
        stock_code=stock_code,
        report_name=report_name,
        receipt_no=rcept_no,
        filer_name="삼성전자",
        receipt_date=date(2026, 5, 14),
        importance=importance,  # type: ignore[arg-type]
        url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
    )


class TestMonitorResult:
    def test_high_count(self):
        result = MonitorResult(
            checked_from=date(2026, 5, 7),
            checked_to=date(2026, 5, 14),
            stock_codes_checked=["005930"],
            disclosures=[
                _disclosure(importance="HIGH"),
                _disclosure(importance="NORMAL", rcept_no="AAA"),
                _disclosure(importance="HIGH", rcept_no="BBB"),
            ],
            skipped_codes=[],
        )
        assert result.high_count == 2
        assert result.normal_count == 1

    def test_empty_disclosures(self):
        result = MonitorResult(
            checked_from=date(2026, 5, 7),
            checked_to=date(2026, 5, 14),
            stock_codes_checked=[],
            disclosures=[],
            skipped_codes=[],
        )
        assert result.high_count == 0
        assert result.normal_count == 0


class TestRunMonitor:
    @patch("sentinelq.monitoring.dart_monitor.fetch_holdings_disclosures")
    @patch("sentinelq.monitoring.dart_monitor.load_corp_code_map")
    @patch("sentinelq.monitoring.dart_monitor.load_api_key")
    def test_returns_monitor_result(self, mock_key, mock_corp, mock_fetch):
        mock_key.return_value = "test_key"
        mock_corp.return_value = {"005930": "00126380"}
        mock_fetch.return_value = ([_disclosure()], [])
        result = run_monitor(["005930"])
        assert isinstance(result, MonitorResult)
        assert len(result.disclosures) == 1

    @patch("sentinelq.monitoring.dart_monitor.fetch_holdings_disclosures")
    @patch("sentinelq.monitoring.dart_monitor.load_corp_code_map")
    @patch("sentinelq.monitoring.dart_monitor.load_api_key")
    def test_empty_stock_codes(self, mock_key, mock_corp, mock_fetch):
        mock_key.return_value = "key"
        mock_corp.return_value = {}
        mock_fetch.return_value = ([], [])
        result = run_monitor([])
        assert result.disclosures == []
        assert result.stock_codes_checked == []

    @patch("sentinelq.monitoring.dart_monitor.fetch_holdings_disclosures")
    @patch("sentinelq.monitoring.dart_monitor.load_corp_code_map")
    @patch("sentinelq.monitoring.dart_monitor.load_api_key")
    def test_days_back_sets_date_range(self, mock_key, mock_corp, mock_fetch):
        mock_key.return_value = "key"
        mock_corp.return_value = {}
        mock_fetch.return_value = ([], [])
        end = date(2026, 5, 14)
        run_monitor(["005930"], days_back=7, end_date=end)
        call_kwargs = mock_fetch.call_args
        start_arg = call_kwargs[0][1]  # positional: stock_codes, start_date, end_date
        assert start_arg == date(2026, 5, 7)

    @patch("sentinelq.monitoring.dart_monitor.fetch_holdings_disclosures")
    @patch("sentinelq.monitoring.dart_monitor.load_corp_code_map")
    @patch("sentinelq.monitoring.dart_monitor.load_api_key")
    def test_skipped_codes_in_result(self, mock_key, mock_corp, mock_fetch):
        mock_key.return_value = "key"
        mock_corp.return_value = {}
        mock_fetch.return_value = ([], ["000660"])
        result = run_monitor(["005930", "000660"])
        assert "000660" in result.skipped_codes

    @patch("sentinelq.monitoring.dart_monitor.fetch_holdings_disclosures")
    @patch("sentinelq.monitoring.dart_monitor.load_corp_code_map")
    @patch("sentinelq.monitoring.dart_monitor.load_api_key")
    def test_custom_corp_map_used(self, mock_key, mock_corp, mock_fetch):
        mock_key.return_value = "key"
        mock_fetch.return_value = ([], [])
        custom_map = {"005930": "00126380"}
        run_monitor(["005930"], corp_map=custom_map)
        mock_corp.assert_not_called()  # 직접 전달 시 auto-load 안 함

    @patch("sentinelq.monitoring.dart_monitor.fetch_holdings_disclosures")
    @patch("sentinelq.monitoring.dart_monitor.load_corp_code_map")
    @patch("sentinelq.monitoring.dart_monitor.load_api_key")
    def test_custom_api_key_used(self, mock_key, mock_corp, mock_fetch):
        mock_corp.return_value = {}
        mock_fetch.return_value = ([], [])
        run_monitor(["005930"], api_key="custom_key")
        mock_key.assert_not_called()  # 직접 전달 시 auto-load 안 함
