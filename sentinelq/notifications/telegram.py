"""텔레그램 공시 알림 모듈 (T022).

PREREG: PREREG-0011 §2.4
환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date

from sentinelq.adapters.dart_api import DisclosureRecord

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _load_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
    return token


def _load_chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID 환경변수가 설정되지 않았습니다.")
    return chat_id


def format_disclosure_message(
    disclosures: list[DisclosureRecord],
    *,
    as_of: date | None = None,
) -> str:
    """공시 목록 → 텔레그램 메시지 텍스트."""
    today_str = str(as_of or date.today())
    lines = [f"*[DART 공시 알림]* 보유 종목 신규 공시 ({today_str})\n"]
    for d in disclosures:
        tag = "🔴" if d.importance == "HIGH" else "🔵"
        lines.append(
            f"{tag} *{d.corp_name}* ({d.stock_code})\n"
            f"   {d.report_name}\n"
            f"   접수일: {d.receipt_date}\n"
            f"   → {d.url}"
        )
    return "\n\n".join(lines)


def send_disclosure_alert(
    disclosures: list[DisclosureRecord],
    *,
    bot_token: str | None = None,
    chat_id: str | None = None,
    as_of: date | None = None,
) -> bool:
    """공시 알림 텔레그램 전송.

    Parameters
    ----------
    disclosures:
        전송할 공시 레코드 목록
    bot_token:
        None이면 TELEGRAM_BOT_TOKEN 환경변수 사용
    chat_id:
        None이면 TELEGRAM_CHAT_ID 환경변수 사용
    as_of:
        메시지 날짜 (None이면 오늘)

    Returns
    -------
    bool
        전송 성공 여부 (비어있으면 False)
    """
    if not disclosures:
        return False

    token = bot_token if bot_token is not None else _load_token()
    cid = chat_id if chat_id is not None else _load_chat_id()

    text = format_disclosure_message(disclosures, as_of=as_of)
    payload = json.dumps({"chat_id": cid, "text": text, "parse_mode": "Markdown"}).encode("utf-8")

    url = _TELEGRAM_API.format(token=token)
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    return bool(result.get("ok", False))
