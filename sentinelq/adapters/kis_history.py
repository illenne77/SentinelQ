"""KIS Open API 거래내역 fetch 어댑터 (Phase 3 T001).

spec: ``.claude/queue/spec-T001.md``
PREREG: ``docs/preregistration/PREREG-0008-amendment-1.md``

본 모듈 책임:
- 해외주식 기간별 매매내역 조회 (TR_ID: VTTS3035R / TTTS3035R)
- 국내주식 일별 주문체결 조회 (TR_ID: VTTC8001R / TTTC8001R, 90일 한도 자동 분할)
- 기간 손익 조회 (TR_ID: VTRP6504R / CTRP6504R, VTSC9215R / CTSC9215R)

모의/실거래 분리:
- ``env="paper"`` 기본 — paper TR_ID 사용
- ``env="live"`` 호출 시 ``SENTINELQ_LIVE_ALLOW=1`` 환경변수 AND ``confirm_live=True`` 인자 둘 다 필요

Mandate 위반 금지 (ADR-0011·0012·0013):
- 실거래 매매 주문 호출 X (``kis_broker.py`` 영역)
- 시장 시세·차트 X (``kis_data.py`` 영역)
- 다른 증권사 X (PREREG-0008-amendment-1로 폐기)
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent.parent.parent
SECRETS_DIR = ROOT / "secrets"

Env = Literal["paper", "live"]
ENV_LIVE_ALLOW = "SENTINELQ_LIVE_ALLOW"

# ---- TR_ID·경로 (KIS Developers 포털 기준) ----
# paper 환경은 "V*", live 환경은 "T*"/"C*" 접두를 따른다.
TR_OVERSEAS_TRANS: dict[Env, str] = {"paper": "VTTS3035R", "live": "TTTS3035R"}
TR_DOMESTIC_TRANS: dict[Env, str] = {"paper": "VTTC8001R", "live": "TTTC8001R"}
TR_OVERSEAS_PROFIT: dict[Env, str] = {"paper": "VTRP6504R", "live": "CTRP6504R"}
TR_DOMESTIC_PROFIT: dict[Env, str] = {"paper": "VTSC9215R", "live": "CTSC9215R"}
TR_DOMESTIC_BALANCE: dict[Env, str] = {"paper": "VTTC8434R", "live": "TTTC8434R"}
TR_OVERSEAS_BALANCE: dict[Env, str] = {"paper": "VTTS3012R", "live": "TTTS3012R"}

PATH_OVERSEAS_TRANS = "/uapi/overseas-stock/v1/trading/inquire-ccnl"
PATH_DOMESTIC_TRANS = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
PATH_OVERSEAS_PROFIT = "/uapi/overseas-stock/v1/trading/inquire-period-profit"
PATH_DOMESTIC_PROFIT = "/uapi/domestic-stock/v1/trading/inquire-period-trade-profit"
PATH_DOMESTIC_BALANCE = "/uapi/domestic-stock/v1/trading/inquire-balance"
PATH_OVERSEAS_BALANCE = "/uapi/overseas-stock/v1/trading/inquire-balance"

DOMESTIC_WINDOW_DAYS = 90  # 국내 거래내역 endpoint 단일 호출 한도

# ---- 예외 ----


class KisApiError(RuntimeError):
    """KIS API 응답 ``rt_cd != "0"`` 또는 HTTP 오류 시 raise."""

    def __init__(self, code: str, message: str, *, tr_id: str | None = None) -> None:
        self.code = code
        self.message = message
        self.tr_id = tr_id
        super().__init__(f"[{code}] {message}" + (f" (tr_id={tr_id})" if tr_id else ""))


# ---- 데이터 모델 ----


@dataclass(frozen=True)
class Transaction:
    """단일 매매 체결 한 건. 양도세·손익통산 계산 입력."""

    trade_date: date
    settle_date: date | None
    ticker: str  # KR 6자리 또는 US 심볼
    market: Literal["KR", "US"]
    side: Literal["BUY", "SELL"]
    quantity: int
    price: Decimal
    currency: Literal["KRW", "USD"]
    fee: Decimal
    tax: Decimal
    fx_rate: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HoldingRecord:
    """잔고 한 종목. 포트폴리오 대시보드·세후 수익률 계산 입력 (T013)."""

    ticker: str
    name: str
    market: Literal["KR", "US"]
    quantity: int
    avg_price_krw: Decimal  # 매입 평균단가 (원화 환산)
    cost_basis_krw: Decimal  # 총 매입원가 (원화)
    current_price_krw: Decimal  # 현재가 (원화)
    current_value_krw: Decimal  # 현재 평가금액 (원화)
    unrealized_gain_krw: Decimal  # 미실현 손익 (원화)
    currency: Literal["KRW", "USD"]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfitRecord:
    """기간 손익 한 건. 12월 손실 인식 권장에 사용."""

    trade_date: date
    ticker: str
    realized_profit_krw: Decimal
    raw: dict[str, Any] = field(default_factory=dict)


# ---- 토큰 관리 ----


def _is_token_expired(token_data: dict[str, Any]) -> bool:
    exp = token_data.get("expires_at")
    if not exp:
        return True
    try:
        exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=UTC)
    return datetime.now(UTC) >= exp_dt - timedelta(minutes=5)


def _refresh_token(env: Env) -> None:
    """``scripts/kis_token.py``와 동일 로직으로 토큰 재발급."""
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env", override=True)
    prefix = "KIS_PAPER_" if env == "paper" else "KIS_LIVE_"
    base_url = os.environ[f"{prefix}BASE_URL"]
    app_key = os.environ[f"{prefix}APP_KEY"]
    app_secret = os.environ[f"{prefix}APP_SECRET"]
    body = json.dumps(
        {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/oauth2/tokenP",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "access_token" not in payload:
        raise KisApiError(
            str(payload.get("error_code", "?")),
            str(payload.get("error_description", "token refresh failed")),
        )
    cache = {
        "env": env,
        "base_url": base_url,
        "issued_at": datetime.now(UTC).isoformat(),
        "expires_at": payload.get("access_token_token_expired"),
        "expires_in": payload.get("expires_in"),
        "token_type": payload.get("token_type"),
        "access_token": payload["access_token"],
    }
    out = SECRETS_DIR / f"kis_token_{env}.json"
    out.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(out, 0o600)
    logger.info("token refreshed env=%s", env)


def _load_token(env: Env) -> dict[str, Any]:
    """``secrets/kis_token_<env>.json`` 로드 + 만료 자동 재발급."""
    path = SECRETS_DIR / f"kis_token_{env}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Token cache not found: {path}. Run: python scripts/kis_token.py {env}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if _is_token_expired(data):
        _refresh_token(env)
        data = json.loads(path.read_text(encoding="utf-8"))
    return data


# ---- HTTP 호출 ----


def _check_live_authorization(env: Env, confirm_live: bool) -> None:
    if env != "live":
        return
    if os.environ.get(ENV_LIVE_ALLOW) != "1" or not confirm_live:
        raise PermissionError(
            f"Live API call blocked: set {ENV_LIVE_ALLOW}=1 AND pass confirm_live=True"
        )


def _request(
    path: str,
    *,
    params: dict[str, str],
    tr_id: str,
    env: Env,
    confirm_live: bool = False,
    max_retries: int = 3,
) -> dict[str, Any]:
    """KIS REST GET 호출 + rate limit 백오프 + 토큰 자동 재발급.

    Raises:
        PermissionError: live 호출 시 인증 미통과
        KisApiError: ``rt_cd != "0"`` 또는 HTTP 오류
    """
    _check_live_authorization(env, confirm_live)
    token_data = _load_token(env)
    base_url = token_data["base_url"]
    url = f"{base_url}{path}?{urllib.parse.urlencode(params)}"
    key_var = "KIS_PAPER_APP_KEY" if env == "paper" else "KIS_LIVE_APP_KEY"
    sec_var = "KIS_PAPER_APP_SECRET" if env == "paper" else "KIS_LIVE_APP_SECRET"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"{token_data['token_type']} {token_data['access_token']}",
        "appkey": os.environ.get(key_var, ""),
        "appsecret": os.environ.get(sec_var, ""),
        "tr_id": tr_id,
    }
    backoff = 1.0
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            rt_cd = payload.get("rt_cd", "?")
            if rt_cd != "0":
                msg_code = str(payload.get("msg_cd", ""))
                msg_text = str(payload.get("msg1", ""))
                # 명확한 rate limit·timeout 시그널만 재시도. 그 외(인증·계좌·필드 오류)는 즉시 raise.
                is_transient = (
                    msg_code == "EGW00201"  # 초당 거래건수 초과
                    or "초당" in msg_text
                    or "OVER" in msg_text.upper()
                    or "TIMEOUT" in msg_text.upper()
                )
                if is_transient and attempt < max_retries - 1:
                    last_exc = KisApiError(msg_code, msg_text, tr_id=tr_id)
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise KisApiError(msg_code, msg_text, tr_id=tr_id)
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                last_exc = exc
                time.sleep(backoff)
                backoff *= 2
                continue
            raise KisApiError(str(exc.code), str(exc.reason), tr_id=tr_id) from exc
        except urllib.error.URLError as exc:
            # 연결 타임아웃·DNS·연결거부 — transient로 보고 재시도, 소진 시 KisApiError
            if attempt < max_retries - 1:
                last_exc = exc
                time.sleep(backoff)
                backoff *= 2
                continue
            raise KisApiError("NETWORK", f"KIS 연결 실패: {exc.reason}", tr_id=tr_id) from exc
    if isinstance(last_exc, Exception):
        raise last_exc
    raise KisApiError("?", "max_retries exhausted", tr_id=tr_id)


def _account_parts(account: str | None, env: Env = "paper") -> tuple[str, str]:
    """``"XXXXXXXX-YY"`` → ``("XXXXXXXX", "YY")``.

    우선순위:
      1. account 인수 (XXXXXXXX-YY 형식)
      2. KIS_ACCOUNT 환경변수 (XXXXXXXX-YY 형식)
      3. KIS_{LIVE|PAPER}_ACCOUNT_NO + KIS_{LIVE|PAPER}_ACCOUNT_PRDT 조합
    """
    raw = account or os.environ.get("KIS_ACCOUNT", "")
    if not raw:
        prefix = "KIS_LIVE_" if env == "live" else "KIS_PAPER_"
        no = os.environ.get(f"{prefix}ACCOUNT_NO", "")
        prdt = os.environ.get(f"{prefix}ACCOUNT_PRDT", "")
        if no and prdt:
            raw = f"{no}-{prdt}"
    if "-" not in raw:
        raise ValueError(
            f"계좌번호를 찾을 수 없습니다. "
            f".env에 KIS_ACCOUNT=XXXXXXXX-YY 또는 "
            f"KIS_LIVE_ACCOUNT_NO + KIS_LIVE_ACCOUNT_PRDT 를 설정하세요. got: {raw!r}"
        )
    cano, prdt_code = raw.split("-", 1)
    return cano, prdt_code


# ---- 공개 API: 거래내역 조회 ----


def inquire_overseas_period_trans(
    start: date,
    end: date,
    *,
    env: Env = "paper",
    account: str | None = None,
    exchange: Literal["NASD", "NYSE", "AMEX", "ALL"] = "ALL",
    confirm_live: bool = False,
) -> list[Transaction]:
    """해외주식 기간별 매매내역 조회 (페이지네이션 자동). 체결수량 0(미체결) 제외."""
    cano, prdt = _account_parts(account, env)
    tr_id = TR_OVERSEAS_TRANS[env]
    results: list[Transaction] = []
    ctx_fk = ""
    ctx_nk = ""
    while True:
        params: dict[str, str] = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt,
            "PDNO": "%",
            "ORD_STRT_DT": start.strftime("%Y%m%d"),
            "ORD_END_DT": end.strftime("%Y%m%d"),
            "SLL_BUY_DVSN": "00",
            "CCLD_NCCS_DVSN": "00",
            "OVRS_EXCG_CD": "" if exchange == "ALL" else exchange,
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_NK200": ctx_nk,
            "CTX_AREA_FK200": ctx_fk,
        }
        payload = _request(
            PATH_OVERSEAS_TRANS,
            params=params,
            tr_id=tr_id,
            env=env,
            confirm_live=confirm_live,
        )
        for row in payload.get("output", []) or []:
            tx = _parse_overseas_row(row)
            if tx.quantity <= 0:
                continue  # 미체결·취소 주문 (체결수량 0) — 양도세 대상 아님
            results.append(tx)
        ctx_fk = (payload.get("ctx_area_fk200") or "").strip()
        ctx_nk = (payload.get("ctx_area_nk200") or "").strip()
        if not ctx_nk:
            break
    return results


def _parse_overseas_row(row: dict[str, Any]) -> Transaction:
    trade_date = datetime.strptime(row["ord_dt"], "%Y%m%d").date()
    settle_raw = row.get("dmst_ord_dt") or row.get("rvsn_ord_rmn_qty_dt")
    settle_date = datetime.strptime(str(settle_raw), "%Y%m%d").date() if settle_raw else None
    side: Literal["BUY", "SELL"] = "BUY" if row.get("sll_buy_dvsn_cd") == "02" else "SELL"
    fx_raw = row.get("erlm_exrt") or "0"
    fx = Decimal(str(fx_raw))
    return Transaction(
        trade_date=trade_date,
        settle_date=settle_date,
        ticker=str(row.get("pdno", "")).strip(),
        market="US",
        side=side,
        quantity=int(str(row.get("ft_ccld_qty", "0") or "0")),
        price=Decimal(str(row.get("ft_ccld_unpr3", "0") or "0")),
        currency="USD",
        fee=Decimal(str(row.get("frcr_cmsn_amt", "0") or "0")),
        tax=Decimal("0"),
        fx_rate=fx if fx > 0 else None,
        raw=row,
    )


def inquire_domestic_daily_trans(
    start: date,
    end: date,
    *,
    env: Env = "paper",
    account: str | None = None,
    confirm_live: bool = False,
) -> list[Transaction]:
    """국내주식 일별 주문체결 조회 (90일 한도 자동 분할 + 중복 제거). 체결수량 0 제외."""
    cano, prdt = _account_parts(account, env)
    tr_id = TR_DOMESTIC_TRANS[env]
    results: list[Transaction] = []
    seen_ids: set[str] = set()
    cur_start = start
    while cur_start <= end:
        cur_end = min(cur_start + timedelta(days=DOMESTIC_WINDOW_DAYS - 1), end)
        ctx_fk = ""
        ctx_nk = ""
        while True:
            params: dict[str, str] = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "INQR_STRT_DT": cur_start.strftime("%Y%m%d"),
                "INQR_END_DT": cur_end.strftime("%Y%m%d"),
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": ctx_fk,
                "CTX_AREA_NK100": ctx_nk,
            }
            payload = _request(
                PATH_DOMESTIC_TRANS,
                params=params,
                tr_id=tr_id,
                env=env,
                confirm_live=confirm_live,
            )
            for row in payload.get("output1", []) or []:
                odno = str(row.get("odno", ""))
                ord_dt = str(row.get("ord_dt", ""))
                key = f"{ord_dt}-{odno}-{row.get('pdno', '')}"
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                tx = _parse_domestic_row(row)
                if tx.quantity <= 0:
                    continue  # 미체결·취소 주문 (체결수량 0) — 양도세 대상 아님
                results.append(tx)
            ctx_fk = (payload.get("ctx_area_fk100") or "").strip()
            ctx_nk = (payload.get("ctx_area_nk100") or "").strip()
            if not ctx_nk:
                break
        cur_start = cur_end + timedelta(days=1)
    return results


def _parse_domestic_row(row: dict[str, Any]) -> Transaction:
    trade_date = datetime.strptime(str(row["ord_dt"]), "%Y%m%d").date()
    side: Literal["BUY", "SELL"] = "BUY" if row.get("sll_buy_dvsn_cd") == "02" else "SELL"
    return Transaction(
        trade_date=trade_date,
        settle_date=None,  # 국내 D+2이지만 응답에 직접 포함 X (별도 계산)
        ticker=str(row.get("pdno", "")).strip().zfill(6),
        market="KR",
        side=side,
        quantity=int(str(row.get("tot_ccld_qty", "0") or "0")),
        price=Decimal(str(row.get("avg_prvs", "0") or "0")),
        currency="KRW",
        fee=Decimal(str(row.get("cmsn_amt", "0") or "0")),
        tax=Decimal(str(row.get("ord_tax_amt", "0") or "0")),
        fx_rate=None,
        raw=row,
    )


def inquire_period_profit(
    start: date,
    end: date,
    *,
    env: Env = "paper",
    account: str | None = None,
    market: Literal["domestic", "overseas"] = "overseas",
    confirm_live: bool = False,
) -> list[ProfitRecord]:
    """기간 손익 조회 (양도세 손익통산·12월 손실 인식 권장에 사용)."""
    cano, prdt = _account_parts(account, env)
    if market == "overseas":
        tr_id = TR_OVERSEAS_PROFIT[env]
        path = PATH_OVERSEAS_PROFIT
    else:
        tr_id = TR_DOMESTIC_PROFIT[env]
        path = PATH_DOMESTIC_PROFIT
    results: list[ProfitRecord] = []
    ctx_fk = ""
    ctx_nk = ""
    while True:
        params: dict[str, str] = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt,
            "INQR_STRT_DT": start.strftime("%Y%m%d"),
            "INQR_END_DT": end.strftime("%Y%m%d"),
            "PDNO": "",
            "SORT_DVSN": "00",
            "CTX_AREA_FK200": ctx_fk,
            "CTX_AREA_NK200": ctx_nk,
        }
        payload = _request(path, params=params, tr_id=tr_id, env=env, confirm_live=confirm_live)
        for row in payload.get("output1", []) or []:
            ticker = str(row.get("pdno", "")).strip()
            profit_raw = row.get("rlzt_pfls") or row.get("evlu_pfls_amt") or "0"
            profit = Decimal(str(profit_raw))
            tdate_raw = row.get("trad_dt") or row.get("ord_dt") or start.strftime("%Y%m%d")
            try:
                tdate = datetime.strptime(str(tdate_raw), "%Y%m%d").date()
            except ValueError:
                tdate = start
            results.append(
                ProfitRecord(
                    trade_date=tdate,
                    ticker=ticker,
                    realized_profit_krw=profit,
                    raw=row,
                )
            )
        ctx_fk = (payload.get("ctx_area_fk200") or "").strip()
        ctx_nk = (payload.get("ctx_area_nk200") or "").strip()
        if not ctx_nk:
            break
    return results


def inquire_domestic_balance(
    *,
    env: Env = "paper",
    account: str | None = None,
    confirm_live: bool = False,
) -> list[HoldingRecord]:
    """국내주식 잔고 조회 (VTTC8434R / TTTC8434R). 수량 0 종목 제외.

    PREREG: PREREG-0009 §2.1 T013
    """
    cano, prdt = _account_parts(account, env)
    tr_id = TR_DOMESTIC_BALANCE[env]
    results: list[HoldingRecord] = []
    ctx_fk = ""
    ctx_nk = ""
    while True:
        params: dict[str, str] = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": ctx_fk,
            "CTX_AREA_NK100": ctx_nk,
        }
        payload = _request(
            PATH_DOMESTIC_BALANCE, params=params, tr_id=tr_id, env=env, confirm_live=confirm_live
        )
        for row in payload.get("output1", []) or []:
            qty = int(str(row.get("hldg_qty", "0") or "0"))
            if qty <= 0:
                continue
            avg = Decimal(str(row.get("pchs_avg_pric", "0") or "0"))
            cost = Decimal(str(row.get("pchs_amt", "0") or "0"))
            evlu = Decimal(str(row.get("evlu_amt", "0") or "0"))
            pfls = Decimal(str(row.get("evlu_pfls_amt", "0") or "0"))
            prpr = Decimal(str(row.get("prpr", "0") or "0"))
            results.append(
                HoldingRecord(
                    ticker=str(row.get("pdno", "")).strip().zfill(6),
                    name=str(row.get("prdt_name", "")).strip(),
                    market="KR",
                    quantity=qty,
                    avg_price_krw=avg,
                    cost_basis_krw=cost if cost else avg * qty,
                    current_price_krw=prpr,
                    current_value_krw=evlu,
                    unrealized_gain_krw=pfls,
                    currency="KRW",
                    raw=row,
                )
            )
        ctx_fk = (payload.get("ctx_area_fk100") or "").strip()
        ctx_nk = (payload.get("ctx_area_nk100") or "").strip()
        if not ctx_nk:
            break
    return results


def inquire_overseas_balance(
    *,
    env: Env = "paper",
    account: str | None = None,
    exchanges: list[str] | None = None,
    confirm_live: bool = False,
) -> list[HoldingRecord]:
    """해외주식 잔고 조회 (VTTS3012R / TTTS3012R). 수량 0 종목 제외.

    exchanges: 조회할 거래소 코드 리스트. 기본값: ["NASD", "NYSE", "AMEX"].
    PREREG: PREREG-0009 §2.1 T013
    """
    if exchanges is None:
        exchanges = ["NASD", "NYSE", "AMEX"]
    cano, prdt = _account_parts(account, env)
    tr_id = TR_OVERSEAS_BALANCE[env]
    seen: set[str] = set()
    results: list[HoldingRecord] = []

    for excg in exchanges:
        ctx_fk = ""
        ctx_nk = ""
        while True:
            params: dict[str, str] = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": excg,
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": ctx_fk,
                "CTX_AREA_NK200": ctx_nk,
            }
            payload = _request(
                PATH_OVERSEAS_BALANCE,
                params=params,
                tr_id=tr_id,
                env=env,
                confirm_live=confirm_live,
            )
            for row in payload.get("output1", []) or []:
                qty = int(str(row.get("ovrs_cblc_qty", "0") or "0"))
                if qty <= 0:
                    continue
                ticker = str(row.get("ovrs_pdno", "")).strip().upper()
                if ticker in seen:
                    continue
                seen.add(ticker)
                avg_krw = Decimal(str(row.get("pchs_avg_pric", "0") or "0"))
                cost_krw = Decimal(str(row.get("pchs_amt", "0") or "0"))
                evlu_krw = Decimal(str(row.get("ovrs_stck_evlu_amt", "0") or "0"))
                pfls_krw = Decimal(str(row.get("evlu_pfls_amt", "0") or "0"))
                cur_price_krw = Decimal(str(row.get("now_pric2", "0") or "0"))
                results.append(
                    HoldingRecord(
                        ticker=ticker,
                        name=str(row.get("ovrs_item_name", "")).strip(),
                        market="US",
                        quantity=qty,
                        avg_price_krw=avg_krw,
                        cost_basis_krw=cost_krw if cost_krw else avg_krw * qty,
                        current_price_krw=cur_price_krw,
                        current_value_krw=evlu_krw,
                        unrealized_gain_krw=pfls_krw,
                        currency="USD",
                        raw=row,
                    )
                )
            ctx_fk = (payload.get("ctx_area_fk200") or "").strip()
            ctx_nk = (payload.get("ctx_area_nk200") or "").strip()
            if not ctx_nk:
                break
    return results


def fetch_balance(
    *,
    env: Env = "live",
    account: str | None = None,
    confirm_live: bool = False,
) -> list[HoldingRecord]:
    """국내·해외 잔고 통합 조회 (포트폴리오 대시보드용)."""
    kr = inquire_domestic_balance(env=env, account=account, confirm_live=confirm_live)
    us = inquire_overseas_balance(env=env, account=account, confirm_live=confirm_live)
    return kr + us


__all__ = [
    "SECRETS_DIR",
    "Env",
    "HoldingRecord",
    "KisApiError",
    "ProfitRecord",
    "Transaction",
    "fetch_balance",
    "inquire_domestic_balance",
    "inquire_domestic_daily_trans",
    "inquire_overseas_balance",
    "inquire_overseas_period_trans",
    "inquire_period_profit",
]
