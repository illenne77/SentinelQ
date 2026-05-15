"""KIS API 거래내역 fetch 기간 한도 실측 probe (Phase 3 G1·G2 실증 1단계).

decisions: .claude/decisions/T001-kis-api-period-limit.md
PREREG: PREREG-0008-amendment-1 §"Amendment-2 트리거"

본인 live 계정에서 과거 어느 기간까지 거래내역 fetch가 가능한지 측정한다.
- 거래 데이터 자체는 출력하지 않고 건수만 보고한다 (개인정보 보호).
- 거래내역 조회(read-only)만 호출 — 자동매매 주문 경로와 무관.

사용 (PowerShell):
    cd D:\\GitLabProjects\\SentinelQ
    . .venv\\Scripts\\Activate.ps1
    $env:SENTINELQ_LIVE_ALLOW = "1"
    python scripts\\kis_fetch_limit_probe.py --account XXXXXXXX-YY

`--account` 미지정 시 환경변수 KIS_ACCOUNT 사용.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]

from sentinelq.adapters.kis_history import (
    KisApiError,
    inquire_domestic_daily_trans,
    inquire_overseas_period_trans,
)

ROOT = Path(__file__).resolve().parent.parent

# (라벨, 종료일로부터 거슬러 올라갈 일수)
WINDOWS: list[tuple[str, int]] = [
    ("최근 1개월", 30),
    ("최근 3개월", 91),
    ("최근 1년", 365),
    ("최근 2년", 730),
    ("최근 3년", 1095),
    ("최근 4년", 1460),
]


def _probe(fn, start: date, end: date, account: str | None) -> str:
    """단일 endpoint 측정. OK(건수) / ERROR(API 거부) / FAIL(기타)."""
    try:
        rows = fn(start, end, env="live", account=account, confirm_live=True)
        return f"OK ({len(rows)}건)"
    except KisApiError as exc:
        return f"ERROR [{exc.code}] {exc.message}"
    except Exception as exc:  # probe는 어떤 오류에도 다음 기간 측정을 계속한다
        return f"FAIL {type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KIS 거래내역 fetch 기간 한도 실측")
    parser.add_argument("--account", default=None, help="XXXXXXXX-YY (기본: KIS_ACCOUNT 환경변수)")
    parser.add_argument("--end-date", default=None, help="측정 종료일 YYYY-MM-DD (기본: 오늘)")
    args = parser.parse_args(argv)

    if load_dotenv is not None:
        load_dotenv(ROOT / ".env", override=True)

    if os.environ.get("SENTINELQ_LIVE_ALLOW") != "1":
        print("ERROR: 환경변수 SENTINELQ_LIVE_ALLOW=1 이 필요합니다.", file=sys.stderr)
        print('  PowerShell: $env:SENTINELQ_LIVE_ALLOW = "1"', file=sys.stderr)
        return 1

    end = date.fromisoformat(args.end_date) if args.end_date else date.today()

    print(f"KIS 거래내역 fetch 기간 한도 실측 — env=live, 종료일={end}")
    print("=" * 60)
    for label, days in WINDOWS:
        start = end - timedelta(days=days)
        overseas = _probe(inquire_overseas_period_trans, start, end, args.account)
        domestic = _probe(inquire_domestic_daily_trans, start, end, args.account)
        print(f"[{label}]  {start} ~ {end}")
        print(f"  해외 거래내역: {overseas}")
        print(f"  국내 거래내역: {domestic}")
    print("=" * 60)
    print("OK=정상 fetch / ERROR=API 거부(기간 한도 등) / FAIL=기타 오류")
    print("→ 결과를 .claude/decisions/T001-kis-api-period-limit.md 표에 기록하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
