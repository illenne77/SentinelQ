"""키움증권 영웅문 HTS 해외주식·국내주식 체결내역 CSV 파서 (T009).

PREREG: PREREG-0008-amendment-2 §2.1
Mandate: 다중 증권사 거래내역 통합 → TaxLotLedger 입력

지원 형식:
- 영웅문 HTS > 해외주식 > 체결내역조회 > 엑셀저장
- 영웅문 HTS > 국내주식 > 체결내역조회 > 엑셀저장

인코딩: UTF-8 BOM(utf-8-sig) 우선, EUC-KR 폴백.
컬럼 순서가 달라도 헤더명으로 자동 감지.
컬럼명이 다를 경우 ``col_map`` 인자로 재정의.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sentinelq.adapters.kis_history import Transaction

logger = logging.getLogger(__name__)

# ── 컬럼명 후보 (우선순위 순) ────────────────────────────────────

_COL_DATE = ["체결일자", "거래일자", "매매일자", "체결일"]
_COL_TICKER = ["종목코드", "ticker", "symbol"]
_COL_NAME = ["종목명", "종목", "name"]
_COL_SIDE = ["매매구분", "매도매수구분", "거래구분", "구분"]
_COL_QTY = ["체결수량", "수량", "거래수량", "체결수량(주)"]
_COL_PRICE = ["체결단가", "단가(외화)", "체결단가(외화)", "단가", "거래단가"]
_COL_AMOUNT_KRW = ["원화환산금액", "원화체결금액", "거래금액(원)", "체결금액(원화)"]
_COL_AMOUNT_FX = ["체결금액", "체결금액(외화)", "거래금액(외화)", "거래금액"]
_COL_CURRENCY = ["통화코드", "통화", "currency", "외화코드"]
_COL_FEE = ["수수료", "수수료(원)", "수수료(외화)", "거래수수료"]
_COL_TAX = ["세금", "제세금", "거래세"]
_COL_SETTLE = ["정산일", "결제일", "정산일자", "결제일자"]
_COL_MARKET = ["시장구분", "시장", "거래소"]

_BUY_MARKERS = {"매수", "buy", "b", "1"}
_SELL_MARKERS = {"매도", "sell", "s", "2"}

_OVERSEAS_CURRENCIES = {"USD", "HKD", "JPY", "EUR", "GBP", "CNH", "VND"}


class KiwoomParseError(Exception):
    """CSV 파싱 실패 상세 정보."""

    def __init__(self, path: str, row: int, message: str) -> None:
        self.path = path
        self.row = row
        self.message = message
        super().__init__(f"{path}:{row} — {message}")


# ── 내부 유틸 ─────────────────────────────────────────────────


def _open_csv(path: Path) -> list[dict[str, str]]:
    """인코딩 자동 감지(UTF-8 BOM → EUC-KR)로 CSV 읽기. 빈 파일은 빈 리스트."""
    for enc in ("utf-8-sig", "euc-kr", "cp949", "utf-8"):
        try:
            with path.open(encoding=enc, newline="") as fh:
                rows = list(csv.DictReader(fh))
            return rows  # 빈 파일이면 [] 반환 (오류 아님)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise KiwoomParseError(str(path), 0, f"파일 인코딩 감지 실패: {path.name}")


def _find_col(header: Sequence[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in header:
            return c
    return None


def _dec(value: str) -> Decimal:
    """쉼표·공백 제거 후 Decimal 변환."""
    cleaned = value.replace(",", "").replace(" ", "").strip()
    if not cleaned or cleaned == "-":
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"숫자 변환 실패: {value!r}") from exc


def _parse_date(value: str) -> date:
    """YYYYMMDD 또는 YYYY-MM-DD 또는 YYYY/MM/DD → date."""
    s = value.strip().replace("-", "").replace("/", "").replace(".", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"날짜 형식 불인식: {value!r}")
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _parse_side(value: str) -> str:
    v = value.strip().lower()
    if v in _BUY_MARKERS:
        return "BUY"
    if v in _SELL_MARKERS:
        return "SELL"
    raise ValueError(f"매매구분 불인식: {value!r} (매수/매도 중 하나여야 함)")


def _market_from_currency(currency: str) -> str:
    return "US" if currency in _OVERSEAS_CURRENCIES else "KR"


# ── 공개 API ──────────────────────────────────────────────────


def _resolve_col_map(col_map: dict[str, str] | None) -> dict[str, str]:
    return col_map or {}


def parse_kiwoom_csv(
    path: Path,
    *,
    col_map: dict[str, str] | None = None,
    col_map_file: Path | None = None,
) -> list[Transaction]:
    """키움증권 HTS 체결내역 CSV → Transaction 리스트.

    Parameters
    ----------
    path:
        CSV 파일 경로.
    col_map:
        컬럼명 재정의 dict. 예: ``{"체결일자": "거래일", "체결수량": "수량"}``.
        기본 후보 목록에 없는 컬럼명을 사용하는 경우에만 필요.
    col_map_file:
        JSON col_map 파일 경로 (``data/private/kiwoom_col_map.json`` 등).
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
        # col_map override 먼저 확인
        for c in candidates:
            if c in effective_map:
                return effective_map[c]
        found = _find_col(header, candidates)
        if found is None:
            raise KiwoomParseError(
                str(path),
                0,
                f"{label} 컬럼을 찾을 수 없음. 헤더: {header}. "
                f"col_map으로 재정의하거나 컬럼명 확인 필요.",
            )
        return found

    c_date = col(_COL_DATE, "체결일자")
    c_ticker = col(_COL_TICKER, "종목코드")
    c_side = col(_COL_SIDE, "매매구분")
    c_qty = col(_COL_QTY, "체결수량")
    c_currency = col(_COL_CURRENCY, "통화코드")

    # 선택 컬럼 (없어도 됨)
    c_name = _find_col(header, _COL_NAME)
    c_price = _find_col(header, _COL_PRICE)
    c_amount_krw = _find_col(header, _COL_AMOUNT_KRW)
    c_amount_fx = _find_col(header, _COL_AMOUNT_FX)
    c_fee = _find_col(header, _COL_FEE)
    c_tax = _find_col(header, _COL_TAX)
    c_settle = _find_col(header, _COL_SETTLE)

    transactions: list[Transaction] = []

    for i, row in enumerate(rows, start=2):  # row 1 = header
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

            # 가격: 외화 단가 → 없으면 원화환산금액 / qty
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

            # 결제일
            settle: date | None = None
            if c_settle and row.get(c_settle, "").strip():
                with _suppress_value_error():
                    settle = _parse_date(row[c_settle])

            # fx_rate: 원화환산금액 / 외화금액으로 역산 (선택)
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
        except KiwoomParseError:
            raise
        except Exception as exc:
            raise KiwoomParseError(str(path), i, str(exc)) from exc

    return transactions


class _suppress_value_error:
    """ValueError·decimal 오류 무시용 context manager."""

    def __enter__(self) -> _suppress_value_error:
        return self

    def __exit__(self, exc_type: Any, *_: Any) -> bool:
        return exc_type is not None and issubclass(exc_type, ValueError | InvalidOperation)
