"""미래에셋증권 HTS 해외주식·국내주식 체결내역 CSV 파서 (T010).

PREREG: PREREG-0008-amendment-2 §2.1
Mandate: 다중 증권사 거래내역 통합 → TaxLotLedger 입력

지원 형식:
- 미래에셋증권 HTS > 해외주식 > 체결내역 > 저장
- 미래에셋증권 HTS > 국내주식 > 체결내역 > 저장

인코딩: UTF-8 BOM(utf-8-sig) 우선, EUC-KR 폴백.
공통 유틸(_dec, _parse_date, _parse_side, _open_csv)은 kiwoom_csv에서 재사용.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sentinelq.adapters.kis_history import Transaction
from sentinelq.adapters.kiwoom_csv import (
    _OVERSEAS_CURRENCIES,
    _dec,
    _market_from_currency,
    _open_csv,
    _parse_date,
    _parse_side,
    _suppress_value_error,
)

logger = logging.getLogger(__name__)

# ── 미래에셋 컬럼명 후보 (우선순위 순) ────────────────────────────
# 미래에셋 HTS는 키움과 컬럼명이 일부 다름 — 미래에셋 명칭을 앞에 배치

_COL_DATE = ["거래일자", "체결일자", "매매일자", "거래일"]
_COL_TICKER = ["종목코드", "ticker", "symbol", "종목번호"]
_COL_NAME = ["종목명", "종목", "name"]
_COL_SIDE = ["매도매수구분", "매매구분", "거래구분", "구분"]
_COL_QTY = ["거래수량", "체결수량", "수량", "거래수량(주)"]
_COL_PRICE = ["거래단가(외화)", "체결단가(외화)", "거래단가", "단가(외화)", "체결단가"]
_COL_AMOUNT_KRW = ["거래금액(원화)", "원화거래금액", "원화환산금액", "체결금액(원화)"]
_COL_AMOUNT_FX = ["거래금액(외화)", "체결금액(외화)", "거래금액", "체결금액"]
_COL_CURRENCY = ["통화", "통화코드", "currency", "외화코드"]
_COL_FEE = ["수수료(원화)", "수수료", "거래수수료", "수수료(원)"]
_COL_TAX = ["거래세", "세금", "제세금"]
_COL_SETTLE = ["결제일자", "결제일", "정산일", "정산일자"]

_BUY_MARKERS = {"매수", "buy", "b", "1"}
_SELL_MARKERS = {"매도", "sell", "s", "2"}


class MiraeAssetParseError(Exception):
    """미래에셋 CSV 파싱 실패 상세 정보."""

    def __init__(self, path: str, row: int, message: str) -> None:
        self.path = path
        self.row = row
        self.message = message
        super().__init__(f"{path}:{row} — {message}")


def _find_col(header: Sequence[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in header:
            return c
    return None


def parse_miraeasset_csv(
    path: Path,
    *,
    col_map: dict[str, str] | None = None,
    col_map_file: Path | None = None,
) -> list[Transaction]:
    """미래에셋증권 HTS 체결내역 CSV → Transaction 리스트.

    Parameters
    ----------
    path:
        CSV 파일 경로.
    col_map:
        컬럼명 재정의 dict. 기본 후보 목록에 없는 컬럼명인 경우에만 필요.
    col_map_file:
        JSON col_map 파일 경로 (``data/private/miraeasset_col_map.json`` 등).
        ``col_map`` 인자보다 우선순위 낮음.
    """
    effective_map: dict[str, str] = {}
    if col_map_file and col_map_file.exists():
        effective_map.update(json.loads(col_map_file.read_text(encoding="utf-8")))
    if col_map:
        effective_map.update(col_map)

    rows = _open_csv(path)
    if not rows:
        return []

    header = list(rows[0].keys())

    def col(candidates: list[str], label: str) -> str:
        for c in candidates:
            if c in effective_map:
                return effective_map[c]
        found = _find_col(header, candidates)
        if found is None:
            raise MiraeAssetParseError(
                str(path),
                0,
                f"{label} 컬럼을 찾을 수 없음. 헤더: {header}. "
                f"col_map으로 재정의하거나 컬럼명 확인 필요.",
            )
        return found

    c_date = col(_COL_DATE, "거래일자")
    c_ticker = col(_COL_TICKER, "종목코드")
    c_side = col(_COL_SIDE, "매도매수구분")
    c_qty = col(_COL_QTY, "거래수량")
    c_currency = col(_COL_CURRENCY, "통화")

    c_name = _find_col(header, _COL_NAME)
    c_price = _find_col(header, _COL_PRICE)
    c_amount_krw = _find_col(header, _COL_AMOUNT_KRW)
    c_amount_fx = _find_col(header, _COL_AMOUNT_FX)
    c_fee = _find_col(header, _COL_FEE)
    c_tax = _find_col(header, _COL_TAX)
    c_settle = _find_col(header, _COL_SETTLE)

    transactions: list[Transaction] = []

    for i, row in enumerate(rows, start=2):
        try:
            trade_date = _parse_date(row[c_date])
            ticker = row[c_ticker].strip().upper()
            side = _parse_side(row[c_side])
            qty = int(_dec(row[c_qty]))
            currency_raw = row[c_currency].strip().upper()
            currency: Any = (
                currency_raw if currency_raw in ("KRW", *_OVERSEAS_CURRENCIES) else "USD"
            )
            market: Any = _market_from_currency(currency)

            if c_price and row.get(c_price, "").strip():
                price = _dec(row[c_price])
            elif c_amount_krw and row.get(c_amount_krw, "").strip() and qty:
                price = _dec(row[c_amount_krw]) / qty
                currency = "KRW"
                market = "KR"
            else:
                price = Decimal("0")

            fee = _dec(row[c_fee]) if c_fee and row.get(c_fee) else Decimal("0")
            tax = _dec(row[c_tax]) if c_tax and row.get(c_tax) else Decimal("0")

            settle: date | None = None
            if c_settle and row.get(c_settle, "").strip():
                with _suppress_value_error():
                    settle = _parse_date(row[c_settle])

            fx_rate: Decimal | None = None
            if (
                currency != "KRW"
                and c_amount_krw
                and c_amount_fx
                and row.get(c_amount_krw, "").strip()
                and row.get(c_amount_fx, "").strip()
            ):
                fx_amount = _dec(row[c_amount_fx])
                krw_amount = _dec(row[c_amount_krw])
                if fx_amount:
                    fx_rate = krw_amount / fx_amount

            raw: dict[str, Any] = dict(row)
            if c_name:
                raw["name"] = row.get(c_name, "")

            if qty <= 0:
                logger.debug("수량=0 행 건너뜀: row %d ticker=%s", i, ticker)
                continue

            transactions.append(
                Transaction(
                    trade_date=trade_date,
                    settle_date=settle,
                    ticker=ticker,
                    market=market,
                    side=side,
                    quantity=qty,
                    price=price,
                    currency=currency,
                    fee=fee,
                    tax=tax,
                    fx_rate=fx_rate,
                    raw=raw,
                )
            )
        except MiraeAssetParseError:
            raise
        except Exception as exc:
            raise MiraeAssetParseError(str(path), i, str(exc)) from exc

    return transactions
