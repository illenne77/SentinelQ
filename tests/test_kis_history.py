"""Unit tests for ``sentinelq.adapters.kis_history`` (Phase 3 T001).

spec: ``.claude/queue/spec-T001.md`` — Evaluator 체크리스트 §"테스트 8개+"
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from sentinelq.adapters import kis_history
from sentinelq.adapters.kis_history import (
    KisApiError,
    inquire_domestic_daily_trans,
    inquire_overseas_period_trans,
    inquire_period_profit,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ---- 공용 픽스처 ----


@pytest.fixture
def mock_token(monkeypatch):
    """`_load_token`을 stub 처리 — 만료되지 않은 paper 토큰."""
    fake = {
        "env": "paper",
        "base_url": "https://openapivts.koreainvestment.com:29443",
        "expires_at": "2099-12-31T23:59:59+00:00",
        "token_type": "Bearer",
        "access_token": "FAKE_TOKEN_TEST_ONLY",
    }
    monkeypatch.setattr(kis_history, "_load_token", lambda env: fake)


@pytest.fixture
def mock_account(monkeypatch):
    """계좌·인증 환경변수 stub."""
    monkeypatch.setenv("KIS_ACCOUNT", "12345678-01")
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "FAKE_KEY")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "FAKE_SECRET")


@pytest.fixture
def fast_sleep(monkeypatch):
    """`time.sleep`을 즉시 반환 — rate limit 백오프 테스트 가속."""
    monkeypatch.setattr(kis_history.time, "sleep", lambda *a, **k: None)


class _FakeResp:
    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._data


def _patch_urlopen(monkeypatch, responses):
    """`urllib.request.urlopen`을 mock — N개 응답을 순서대로 반환."""
    if isinstance(responses, bytes | bytearray):
        responses = [responses]
    iterator = iter(responses)

    def fake_urlopen(*args, **kwargs):
        return _FakeResp(next(iterator))

    monkeypatch.setattr(kis_history.urllib.request, "urlopen", fake_urlopen)
    return fake_urlopen


# ---- 해외주식 거래내역 ----


class TestInquireOverseasPeriodTrans:
    def test_empty_response_returns_empty_list(self, monkeypatch, mock_token, mock_account):
        _patch_urlopen(monkeypatch, _load_fixture("kis_empty_response.json"))
        result = inquire_overseas_period_trans(date(2024, 1, 1), date(2024, 12, 31))
        assert result == []

    def test_paginated_two_pages(self, monkeypatch, mock_token, mock_account):
        _patch_urlopen(
            monkeypatch,
            [
                _load_fixture("kis_overseas_trans_page1.json"),
                _load_fixture("kis_overseas_trans_page2.json"),
            ],
        )
        result = inquire_overseas_period_trans(date(2025, 12, 1), date(2025, 12, 31))
        assert len(result) == 3
        assert [r.ticker for r in result] == ["AAPL", "MSFT", "NVDA"]
        assert result[0].side == "BUY"
        assert result[0].market == "US"
        assert result[0].quantity == 10
        assert result[0].price == Decimal("175.50")
        assert result[0].currency == "USD"
        assert result[0].fx_rate == Decimal("1430.50")
        assert result[1].side == "SELL"

    def test_zero_quantity_rows_skipped(self, monkeypatch, mock_token, mock_account):
        """미체결·취소 주문(체결수량 0)은 Transaction으로 반환하지 않는다."""
        payload = {
            "rt_cd": "0",
            "ctx_area_fk200": "",
            "ctx_area_nk200": "",
            "output": [
                {
                    "ord_dt": "20250310",
                    "pdno": "AAPL",
                    "sll_buy_dvsn_cd": "02",
                    "ft_ccld_qty": "0",
                    "ft_ccld_unpr3": "180.00",
                    "erlm_exrt": "1400",
                },
                {
                    "ord_dt": "20250311",
                    "pdno": "MSFT",
                    "sll_buy_dvsn_cd": "02",
                    "ft_ccld_qty": "5",
                    "ft_ccld_unpr3": "400.00",
                    "erlm_exrt": "1400",
                },
            ],
        }
        _patch_urlopen(monkeypatch, json.dumps(payload).encode("utf-8"))
        result = inquire_overseas_period_trans(date(2025, 3, 1), date(2025, 3, 31))
        assert len(result) == 1
        assert result[0].ticker == "MSFT"
        assert result[0].quantity == 5


# ---- 국내주식 거래내역 ----


class TestInquireDomesticDailyTrans:
    def test_single_window_parses_fields(self, monkeypatch, mock_token, mock_account):
        _patch_urlopen(monkeypatch, _load_fixture("kis_domestic_trans.json"))
        result = inquire_domestic_daily_trans(date(2025, 10, 1), date(2025, 10, 31))
        assert len(result) == 2
        # Order is preserved from fixture
        assert result[0].ticker == "005930"
        assert result[0].market == "KR"
        assert result[0].side == "BUY"
        assert result[0].quantity == 100
        assert result[0].price == Decimal("78500")
        assert result[0].currency == "KRW"
        assert result[1].side == "SELL"
        assert result[1].tax == Decimal("21735")

    def test_auto_split_200d_calls_three_windows(self, monkeypatch, mock_token, mock_account):
        empty = _load_fixture("kis_empty_response.json")
        # 200 days range → 90+90+20 = 3 windows
        _patch_urlopen(monkeypatch, [empty, empty, empty])
        result = inquire_domestic_daily_trans(date(2024, 1, 1), date(2024, 7, 19))
        assert result == []

    def test_dedup_across_pagination(self, monkeypatch, mock_token, mock_account):
        # 동일 odno 가 두 번 등장하면 한 번만 카운트
        same = _load_fixture("kis_domestic_trans.json")
        _patch_urlopen(monkeypatch, [same, same])
        result = inquire_domestic_daily_trans(date(2025, 10, 1), date(2025, 10, 31))
        assert len(result) == 2  # 4건 입력이지만 odno 중복 제거 후 2건


# ---- 기간 손익 ----


class TestInquirePeriodProfit:
    def test_overseas_profit_parses(self, monkeypatch, mock_token, mock_account):
        _patch_urlopen(monkeypatch, _load_fixture("kis_period_profit.json"))
        result = inquire_period_profit(date(2025, 1, 1), date(2025, 12, 31), market="overseas")
        assert len(result) == 2
        assert result[0].ticker == "MSFT"
        assert result[0].realized_profit_krw == Decimal("215000")
        assert result[1].realized_profit_krw == Decimal("-120000")


# ---- paper/live 분리 ----


class TestPaperLiveSeparation:
    def test_paper_mode_default_works(self, monkeypatch, mock_token, mock_account):
        _patch_urlopen(monkeypatch, _load_fixture("kis_empty_response.json"))
        result = inquire_overseas_period_trans(date(2025, 1, 1), date(2025, 1, 31))
        assert result == []

    def test_live_blocked_without_env_var(self, monkeypatch, mock_token, mock_account):
        monkeypatch.delenv("SENTINELQ_LIVE_ALLOW", raising=False)
        with pytest.raises(PermissionError, match="Live API call blocked"):
            inquire_overseas_period_trans(
                date(2025, 1, 1), date(2025, 1, 31), env="live", confirm_live=True
            )

    def test_live_blocked_without_confirm(self, monkeypatch, mock_token, mock_account):
        monkeypatch.setenv("SENTINELQ_LIVE_ALLOW", "1")
        with pytest.raises(PermissionError, match="Live API call blocked"):
            inquire_overseas_period_trans(
                date(2025, 1, 1), date(2025, 1, 31), env="live", confirm_live=False
            )

    def test_live_allowed_with_both(self, monkeypatch, mock_token, mock_account):
        monkeypatch.setenv("SENTINELQ_LIVE_ALLOW", "1")
        # _load_token live 도 stub 처리 (mock_token은 env 무시함)
        _patch_urlopen(monkeypatch, _load_fixture("kis_empty_response.json"))
        # PermissionError raise 안 되어야 함
        result = inquire_overseas_period_trans(
            date(2025, 1, 1), date(2025, 1, 31), env="live", confirm_live=True
        )
        assert result == []


# ---- 에러 처리 ----


class TestErrorHandling:
    def test_kis_api_error_response_raises(self, monkeypatch, mock_token, mock_account):
        _patch_urlopen(monkeypatch, _load_fixture("kis_error_response.json"))
        with pytest.raises(KisApiError) as exc_info:
            inquire_overseas_period_trans(date(2025, 1, 1), date(2025, 1, 31))
        assert exc_info.value.code == "EGW00001"
        assert "계좌번호 오류" in exc_info.value.message

    def test_invalid_account_format_raises_value_error(self, monkeypatch, mock_token):
        monkeypatch.delenv("KIS_ACCOUNT", raising=False)
        with pytest.raises(ValueError, match="KIS_ACCOUNT"):
            inquire_overseas_period_trans(date(2025, 1, 1), date(2025, 1, 31))


# ---- Rate limit 백오프 ----


class TestRateLimitBackoff:
    def test_egw_retries_then_succeeds(self, monkeypatch, mock_token, mock_account, fast_sleep):
        rate_limit = json.dumps(
            {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수 초과"}
        ).encode("utf-8")
        success = _load_fixture("kis_empty_response.json")
        _patch_urlopen(monkeypatch, [rate_limit, rate_limit, success])
        result = inquire_overseas_period_trans(date(2025, 1, 1), date(2025, 1, 31))
        assert result == []

    def test_url_error_retries_then_succeeds(
        self, monkeypatch, mock_token, mock_account, fast_sleep
    ):
        """연결 오류(URLError)는 재시도하고 이후 성공 시 정상 반환."""
        success = _load_fixture("kis_empty_response.json")
        calls: list[int] = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise kis_history.urllib.error.URLError("timed out")
            return _FakeResp(success)

        monkeypatch.setattr(kis_history.urllib.request, "urlopen", flaky)
        result = inquire_overseas_period_trans(date(2025, 1, 1), date(2025, 1, 31))
        assert result == []

    def test_url_error_exhausted_raises_kis_api_error(
        self, monkeypatch, mock_token, mock_account, fast_sleep
    ):
        """연결 오류가 재시도 끝까지 지속되면 KisApiError(code=NETWORK)."""

        def always_timeout(*args, **kwargs):
            raise kis_history.urllib.error.URLError("timed out")

        monkeypatch.setattr(kis_history.urllib.request, "urlopen", always_timeout)
        with pytest.raises(KisApiError) as exc_info:
            inquire_overseas_period_trans(date(2025, 1, 1), date(2025, 1, 31))
        assert exc_info.value.code == "NETWORK"


# ---- 보안 (PREREG-0008 §3 보안 검사) ----


class TestSecurity:
    def test_app_key_and_secret_not_in_logs(self, monkeypatch, mock_token, mock_account, caplog):
        caplog.set_level(logging.DEBUG)
        _patch_urlopen(monkeypatch, _load_fixture("kis_empty_response.json"))
        inquire_overseas_period_trans(date(2025, 1, 1), date(2025, 1, 31))
        for record in caplog.records:
            msg = record.getMessage()
            assert "FAKE_KEY" not in msg
            assert "FAKE_SECRET" not in msg
            assert "FAKE_TOKEN_TEST_ONLY" not in msg
