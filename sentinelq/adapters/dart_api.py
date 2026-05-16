"""DART OpenAPI 어댑터 (T020).

PREREG: PREREG-0011 §2.1-2.2
DART OpenAPI: https://opendart.fss.or.kr/guide/main.do

API 키: DART_API_KEY 환경변수 또는 secrets/dart_api_key.txt
법인코드 캐시: data/cache/dart/corp_code.json (dart_smoke.py로 생성)
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

_DART_BASE = "https://opendart.fss.or.kr/api"
_CORP_CACHE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "dart" / "corp_code.json"
)
_KEY_FILE = Path(__file__).resolve().parent.parent.parent / "secrets" / "dart_api_key.txt"

Importance = Literal["HIGH", "NORMAL"]

# 보고서명에 포함 시 HIGH로 분류하는 키워드
_HIGH_KEYWORDS: frozenset[str] = frozenset(
    {
        "유상증자",
        "무상증자",
        "감자",
        "합병",
        "분할",
        "인수합병",
        "공개매수",
        "최대주주",
        "전환사채",
        "신주인수권",
        "상장폐지",
        "관리종목",
        "영업정지",
        "파산",
        "기업회생",
        "횡령",
        "배임",
        "주요사항보고서",
    }
)


@dataclass(frozen=True)
class DisclosureRecord:
    """DART 공시 레코드."""

    corp_code: str
    corp_name: str
    stock_code: str
    report_name: str
    receipt_no: str  # 접수번호 14자리 (정렬·중복 기준)
    filer_name: str
    receipt_date: date
    importance: Importance
    url: str  # DART 공시 열람 URL


def load_api_key() -> str:
    """DART_API_KEY 환경변수 또는 secrets/dart_api_key.txt에서 로드."""
    key = os.environ.get("DART_API_KEY", "").strip()
    if key:
        return key
    if _KEY_FILE.exists():
        return _KEY_FILE.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        "DART API 키가 없습니다. DART_API_KEY 환경변수 또는 secrets/dart_api_key.txt를 설정하세요."
    )


def load_corp_code_map(cache_path: Path = _CORP_CACHE) -> dict[str, str]:
    """stock_code → corp_code 매핑 로드.

    캐시 파일 형식: {stock_code: {corp_code: ..., corp_name: ...}}
    캐시 없으면 빈 dict 반환. scripts/dart_smoke.py로 생성.
    """
    if not cache_path.exists():
        return {}
    with cache_path.open(encoding="utf-8") as f:
        raw = json.load(f)
    result: dict[str, str] = {}
    for stock_code, val in raw.items():
        if isinstance(val, dict):
            result[str(stock_code)] = val["corp_code"]
        else:
            result[str(stock_code)] = str(val)
    return result


def _classify(report_name: str) -> Importance:
    """보고서명 키워드 기반 중요도 분류."""
    if any(kw in report_name for kw in _HIGH_KEYWORDS):
        return "HIGH"
    return "NORMAL"


def _dart_url(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def fetch_disclosures(
    corp_code: str,
    start_date: date,
    end_date: date,
    *,
    api_key: str | None = None,
    page_count: int = 40,
) -> list[DisclosureRecord]:
    """단일 법인의 공시 목록 조회.

    Parameters
    ----------
    corp_code:
        DART 법인코드 (8자리)
    start_date, end_date:
        조회 기간
    api_key:
        None이면 load_api_key() 자동 호출
    page_count:
        페이지당 건수 (최대 100)
    """
    key = api_key if api_key is not None else load_api_key()
    params = {
        "crtfc_key": key,
        "corp_code": corp_code,
        "bgn_de": start_date.strftime("%Y%m%d"),
        "end_de": end_date.strftime("%Y%m%d"),
        "page_no": "1",
        "page_count": str(page_count),
    }
    url = f"{_DART_BASE}/list.json?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    status = data.get("status", "")
    if status == "013":  # 데이터 없음
        return []
    if status != "000":
        raise RuntimeError(f"DART API 오류: status={status}, message={data.get('message', '')}")

    records: list[DisclosureRecord] = []
    for item in data.get("list", []):
        rcept_dt = item.get("rcept_dt", "")
        try:
            rcept_date = date(int(rcept_dt[:4]), int(rcept_dt[4:6]), int(rcept_dt[6:8]))
        except (ValueError, IndexError):
            continue
        report_nm = item.get("report_nm", "")
        rcept_no = item.get("rcept_no", "")
        records.append(
            DisclosureRecord(
                corp_code=item.get("corp_code", ""),
                corp_name=item.get("corp_name", ""),
                stock_code=item.get("stock_code", ""),
                report_name=report_nm,
                receipt_no=rcept_no,
                filer_name=item.get("flr_nm", ""),
                receipt_date=rcept_date,
                importance=_classify(report_nm),
                url=_dart_url(rcept_no),
            )
        )
    return records


def fetch_holdings_disclosures(
    stock_codes: list[str],
    start_date: date,
    end_date: date,
    *,
    api_key: str | None = None,
    corp_map: dict[str, str] | None = None,
    importance_filter: Importance | None = None,
    rate_limit_sleep: float = 0.2,
) -> tuple[list[DisclosureRecord], list[str]]:
    """보유 종목 전체 공시 조회.

    Parameters
    ----------
    stock_codes:
        보유 종목 코드 리스트 (국내주식)
    start_date, end_date:
        조회 기간
    api_key:
        None이면 load_api_key() 자동 호출
    corp_map:
        None이면 load_corp_code_map() 자동 호출
    importance_filter:
        None이면 전체, "HIGH"이면 HIGH만 반환
    rate_limit_sleep:
        API 호출 간 대기 (초)

    Returns
    -------
    (records, skipped_codes)
        records: 공시 목록 (접수일 내림차순)
        skipped_codes: 법인코드 없어 건너뛴 종목 코드
    """
    if corp_map is None:
        corp_map = load_corp_code_map()
    key = api_key if api_key is not None else load_api_key()

    all_records: list[DisclosureRecord] = []
    seen: set[str] = set()
    skipped: list[str] = []

    for stock_code in stock_codes:
        corp_code = corp_map.get(stock_code)
        if not corp_code:
            skipped.append(stock_code)
            continue
        records = fetch_disclosures(corp_code, start_date, end_date, api_key=key)
        for r in records:
            if r.receipt_no not in seen:
                seen.add(r.receipt_no)
                if importance_filter is None or r.importance == importance_filter:
                    all_records.append(r)
        if rate_limit_sleep > 0:
            time.sleep(rate_limit_sleep)

    all_records.sort(key=lambda r: (r.receipt_date, r.receipt_no), reverse=True)
    return all_records, skipped
