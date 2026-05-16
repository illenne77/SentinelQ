"""텔레그램 공시 알림 단위 테스트 (T022).

Coverage target: sentinelq/notifications/telegram.py >= 90%
PREREG: PREREG-0011 §2.4
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from sentinelq.adapters.dart_api import DisclosureRecord
from sentinelq.notifications.telegram import (
    format_disclosure_message,
    send_disclosure_alert,
)


def _disclosure(
    corp_name: str = "삼성전자",
    stock_code: str = "005930",
    report_name: str = "유상증자결정",
    importance: str = "HIGH",
) -> DisclosureRecord:
    return DisclosureRecord(
        corp_code="00126380",
        corp_name=corp_name,
        stock_code=stock_code,
        report_name=report_name,
        receipt_no="20260514000111",
        filer_name=corp_name,
        receipt_date=date(2026, 5, 14),
        importance=importance,  # type: ignore[arg-type]
        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260514000111",
    )


def _mock_urlopen(ok: bool = True):
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps({"ok": ok}).encode("utf-8")
    return mock


# ── format_disclosure_message ─────────────────────────────────


class TestFormatMessage:
    def test_contains_corp_name(self):
        text = format_disclosure_message([_disclosure()])
        assert "삼성전자" in text

    def test_contains_report_name(self):
        text = format_disclosure_message([_disclosure(report_name="유상증자결정")])
        assert "유상증자결정" in text

    def test_contains_dart_url(self):
        text = format_disclosure_message([_disclosure()])
        assert "dart.fss.or.kr" in text

    def test_high_importance_marked(self):
        text = format_disclosure_message([_disclosure(importance="HIGH")])
        assert "🔴" in text

    def test_normal_importance_marked(self):
        text = format_disclosure_message([_disclosure(importance="NORMAL")])
        assert "🔵" in text

    def test_as_of_date_shown(self):
        text = format_disclosure_message([_disclosure()], as_of=date(2026, 5, 16))
        assert "2026-05-16" in text

    def test_multiple_disclosures(self):
        disclosures = [
            _disclosure(corp_name="삼성전자"),
            _disclosure(corp_name="SK하이닉스", stock_code="000660"),
        ]
        text = format_disclosure_message(disclosures)
        assert "삼성전자" in text
        assert "SK하이닉스" in text


# ── send_disclosure_alert ─────────────────────────────────────


class TestSendDisclosureAlert:
    @patch("sentinelq.notifications.telegram.urllib.request.urlopen")
    def test_successful_send(self, mock_open):
        mock_open.return_value = _mock_urlopen(ok=True)
        ok = send_disclosure_alert(
            [_disclosure()],
            bot_token="test_token",
            chat_id="12345",
        )
        assert ok is True

    @patch("sentinelq.notifications.telegram.urllib.request.urlopen")
    def test_empty_list_returns_false_no_call(self, mock_open):
        ok = send_disclosure_alert([], bot_token="token", chat_id="123")
        assert ok is False
        mock_open.assert_not_called()

    @patch("sentinelq.notifications.telegram.urllib.request.urlopen")
    def test_api_returns_ok_false(self, mock_open):
        mock_open.return_value = _mock_urlopen(ok=False)
        ok = send_disclosure_alert([_disclosure()], bot_token="token", chat_id="123")
        assert ok is False

    def test_missing_token_raises(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"),
        ):
            send_disclosure_alert([_disclosure()])

    def test_missing_chat_id_raises(self):
        with (
            patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "tok"}, clear=True),
            pytest.raises(RuntimeError, match="TELEGRAM_CHAT_ID"),
        ):
            send_disclosure_alert([_disclosure()])

    @patch("sentinelq.notifications.telegram.urllib.request.urlopen")
    def test_sends_to_correct_api(self, mock_open):
        mock_open.return_value = _mock_urlopen()
        send_disclosure_alert([_disclosure()], bot_token="mytoken", chat_id="999")
        req = mock_open.call_args[0][0]
        assert "mytoken" in req.full_url
        assert "sendMessage" in req.full_url
