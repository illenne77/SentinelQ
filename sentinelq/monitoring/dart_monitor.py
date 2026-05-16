"""DART 공시 모니터링 (T021).

PREREG: PREREG-0011 §2.3
보유 종목의 최근 N일 공시를 일괄 조회하고 중요도 분류 결과를 반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sentinelq.adapters.dart_api import (
    DisclosureRecord,
    Importance,
    fetch_holdings_disclosures,
    load_api_key,
    load_corp_code_map,
)


@dataclass
class MonitorResult:
    """공시 모니터링 결과."""

    checked_from: date
    checked_to: date
    stock_codes_checked: list[str]
    disclosures: list[DisclosureRecord]
    skipped_codes: list[str]  # 법인코드 없어 건너뛴 종목 (주로 해외주식)

    @property
    def high_count(self) -> int:
        return sum(1 for d in self.disclosures if d.importance == "HIGH")

    @property
    def normal_count(self) -> int:
        return sum(1 for d in self.disclosures if d.importance == "NORMAL")


def run_monitor(
    stock_codes: list[str],
    *,
    days_back: int = 7,
    end_date: date | None = None,
    importance_filter: Importance | None = "HIGH",
    api_key: str | None = None,
    corp_map: dict[str, str] | None = None,
    rate_limit_sleep: float = 0.2,
) -> MonitorResult:
    """보유 종목 공시 모니터링.

    Parameters
    ----------
    stock_codes:
        보유 종목 코드 리스트 (국내주식 코드)
    days_back:
        며칠 전부터 조회 (기본 7일)
    end_date:
        조회 종료일 (None이면 오늘)
    importance_filter:
        "HIGH"이면 중요 공시만, None이면 전체
    api_key:
        None이면 load_api_key() 자동 호출
    corp_map:
        None이면 load_corp_code_map() 자동 호출
    rate_limit_sleep:
        DART API 호출 간 대기 (초)
    """
    today = end_date or date.today()
    start = today - timedelta(days=days_back)

    if corp_map is None:
        corp_map = load_corp_code_map()
    if api_key is None:
        api_key = load_api_key()

    disclosures, skipped = fetch_holdings_disclosures(
        stock_codes,
        start,
        today,
        api_key=api_key,
        corp_map=corp_map,
        importance_filter=importance_filter,
        rate_limit_sleep=rate_limit_sleep,
    )

    return MonitorResult(
        checked_from=start,
        checked_to=today,
        stock_codes_checked=list(stock_codes),
        disclosures=disclosures,
        skipped_codes=skipped,
    )
