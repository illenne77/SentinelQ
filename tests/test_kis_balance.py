"""KIS 잔고 조회 어댑터 단위 테스트 (T013).

실제 KIS API는 호출하지 않음 — _request를 monkeypatch로 대체.
Coverage target: inquire_domestic_balance, inquire_overseas_balance >= 90%
PREREG: PREREG-0009 §2.1
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from sentinelq.adapters.kis_history import (
    HoldingRecord,
    inquire_domestic_balance,
    inquire_overseas_balance,
)

# ── mock 응답 헬퍼 ──────────────────────────────────────────────


def _kr_payload(rows: list[dict], ctx_nk: str = "") -> dict:
    return {
        "rt_cd": "0",
        "output1": rows,
        "output2": [{"tot_evlu_amt": "10000000"}],
        "ctx_area_fk100": "",
        "ctx_area_nk100": ctx_nk,
    }


def _us_payload(rows: list[dict], ctx_nk: str = "") -> dict:
    return {
        "rt_cd": "0",
        "output1": rows,
        "output2": [{}],
        "ctx_area_fk200": "",
        "ctx_area_nk200": ctx_nk,
    }


_KR_ROW = {
    "pdno": "005930",
    "prdt_name": "삼성전자",
    "hldg_qty": "100",
    "pchs_avg_pric": "58500",
    "pchs_amt": "5850000",
    "evlu_amt": "6000000",
    "evlu_pfls_amt": "150000",
    "prpr": "60000",
}

_US_ROW = {
    "ovrs_pdno": "NVDA",
    "ovrs_item_name": "NVIDIA",
    "ovrs_cblc_qty": "80",
    "pchs_avg_pric": "165250",
    "pchs_amt": "13220000",
    "ovrs_stck_evlu_amt": "15600000",
    "evlu_pfls_amt": "2380000",
    "now_pric2": "195000",
}


# ── inquire_domestic_balance ───────────────────────────────────


class TestInquireDomesticBalance:
    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_basic_holding(self, mock_req, mock_acct):
        mock_req.return_value = _kr_payload([_KR_ROW])
        result = inquire_domestic_balance(env="paper")
        assert len(result) == 1
        h = result[0]
        assert h.ticker == "005930"
        assert h.name == "삼성전자"
        assert h.market == "KR"
        assert h.quantity == 100
        assert h.avg_price_krw == Decimal("58500")
        assert h.cost_basis_krw == Decimal("5850000")
        assert h.current_value_krw == Decimal("6000000")
        assert h.unrealized_gain_krw == Decimal("150000")
        assert h.currency == "KRW"

    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_skips_zero_quantity(self, mock_req, mock_acct):
        row = {**_KR_ROW, "hldg_qty": "0"}
        mock_req.return_value = _kr_payload([row])
        result = inquire_domestic_balance(env="paper")
        assert result == []

    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_empty_response(self, mock_req, mock_acct):
        mock_req.return_value = _kr_payload([])
        result = inquire_domestic_balance(env="paper")
        assert result == []

    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_pagination_stops_on_empty_ctx_nk(self, mock_req, mock_acct):
        mock_req.side_effect = [
            _kr_payload([_KR_ROW], ctx_nk="NEXT"),
            _kr_payload([{**_KR_ROW, "pdno": "000660"}]),  # ctx_nk="" → stop
        ]
        result = inquire_domestic_balance(env="paper")
        assert len(result) == 2

    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_cost_basis_fallback_avg_times_qty(self, mock_req, mock_acct):
        row = {**_KR_ROW, "pchs_amt": "0"}  # pchs_amt 없을 때 avg x qty 사용
        mock_req.return_value = _kr_payload([row])
        result = inquire_domestic_balance(env="paper")
        assert result[0].cost_basis_krw == Decimal("58500") * 100


# ── inquire_overseas_balance ───────────────────────────────────


class TestInquireOverseasBalance:
    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_basic_holding(self, mock_req, mock_acct):
        # 3 exchanges but only NASD returns data
        mock_req.side_effect = [
            _us_payload([_US_ROW]),  # NASD
            _us_payload([]),  # NYSE
            _us_payload([]),  # AMEX
        ]
        result = inquire_overseas_balance(env="paper")
        assert len(result) == 1
        h = result[0]
        assert h.ticker == "NVDA"
        assert h.market == "US"
        assert h.quantity == 80
        assert h.currency == "USD"
        assert h.current_value_krw == Decimal("15600000")
        assert h.unrealized_gain_krw == Decimal("2380000")

    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_deduplicates_ticker_across_exchanges(self, mock_req, mock_acct):
        # NVDA appears in both NASD and NYSE (edge case) → deduplicated
        mock_req.side_effect = [
            _us_payload([_US_ROW]),  # NASD → NVDA
            _us_payload([_US_ROW]),  # NYSE → NVDA duplicate → skip
            _us_payload([]),
        ]
        result = inquire_overseas_balance(env="paper")
        assert len(result) == 1

    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_custom_exchanges(self, mock_req, mock_acct):
        mock_req.return_value = _us_payload([])
        result = inquire_overseas_balance(env="paper", exchanges=["HKEX"])
        assert mock_req.call_count == 1
        assert result == []

    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_skips_zero_quantity(self, mock_req, mock_acct):
        row = {**_US_ROW, "ovrs_cblc_qty": "0"}
        mock_req.side_effect = [_us_payload([row]), _us_payload([]), _us_payload([])]
        result = inquire_overseas_balance(env="paper")
        assert result == []

    @patch("sentinelq.adapters.kis_history._account_parts", return_value=("12345678", "01"))
    @patch("sentinelq.adapters.kis_history._request")
    def test_holding_record_fields(self, mock_req, mock_acct):
        mock_req.side_effect = [_us_payload([_US_ROW]), _us_payload([]), _us_payload([])]
        result = inquire_overseas_balance(env="paper")
        h = result[0]
        assert isinstance(h, HoldingRecord)
        assert h.ticker == "NVDA"
        assert h.name == "NVIDIA"
        assert h.avg_price_krw == Decimal("165250")
