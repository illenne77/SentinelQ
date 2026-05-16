"""DART 공시 모니터링 CLI (T023).

PREREG: PREREG-0011 §2.5
Usage:
  python scripts/run_dart_monitor.py --days 7
  python scripts/run_dart_monitor.py --tickers 005930 000660 --days 1 --notify
  python scripts/run_dart_monitor.py --env paper --importance ALL
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
except ImportError:
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DART 공시 모니터링")
    parser.add_argument(
        "--tickers",
        nargs="+",
        metavar="CODE",
        help="국내주식 종목코드 직접 지정 (예: --tickers 005930 000660)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="며칠 전부터 조회 (기본 7일)",
    )
    parser.add_argument(
        "--importance",
        choices=["HIGH", "ALL"],
        default="HIGH",
        help="공시 중요도 필터 (기본 HIGH만)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="텔레그램 알림 전송 (TELEGRAM_BOT_TOKEN·CHAT_ID 필요)",
    )
    parser.add_argument(
        "--env",
        choices=["paper", "live"],
        default="live",
        help="KIS API 환경 (--tickers 미지정 시 KIS 잔고 자동 조회)",
    )
    parser.add_argument("--account", default=None, help="계좌번호 (XXXXXXXX-YY)")
    args = parser.parse_args(argv)

    from sentinelq.adapters.dart_api import load_api_key, load_corp_code_map
    from sentinelq.monitoring.dart_monitor import run_monitor

    # 보유 종목 확보
    stock_codes: list[str] = []
    if args.tickers:
        stock_codes = [t.zfill(6) for t in args.tickers]
        print(f"종목 직접 지정: {stock_codes}")
    else:
        from sentinelq.adapters.kis_history import inquire_domestic_balance

        confirm_live = args.env == "live"
        print(f"[1/2] KIS 국내주식 잔고 조회 (env={args.env})...")
        try:
            holdings = inquire_domestic_balance(
                env=args.env, account=args.account, confirm_live=confirm_live
            )
            stock_codes = [h.ticker for h in holdings]
            print(f"      → {len(stock_codes)}개 종목")
        except Exception as exc:
            print(f"  ⚠ 잔고 조회 실패: {exc}")
            print("  --tickers 옵션으로 종목코드를 직접 지정하세요.")
            return 1

    if not stock_codes:
        print("조회할 종목이 없습니다.")
        return 0

    # API 키·법인코드 로드
    try:
        api_key = load_api_key()
    except RuntimeError as exc:
        print(f"오류: {exc}")
        return 1

    corp_map = load_corp_code_map()
    if not corp_map:
        print("경고: data/cache/dart/corp_code.json 없음. scripts/dart_smoke.py를 먼저 실행하세요.")

    importance_filter = None if args.importance == "ALL" else "HIGH"

    print(f"[2/2] DART 공시 조회 (최근 {args.days}일, 중요도={args.importance})...")
    result = run_monitor(
        stock_codes,
        days_back=args.days,
        importance_filter=importance_filter,
        api_key=api_key,
        corp_map=corp_map,
        rate_limit_sleep=0.2,
    )

    print(f"\n조회 기간: {result.checked_from} ~ {result.checked_to}")
    print(f"조회 종목: {len(result.stock_codes_checked)}개 (건너뜀: {len(result.skipped_codes)}개)")
    if result.skipped_codes:
        print(f"  건너뜀 (법인코드 없음): {result.skipped_codes}")
    print(
        f"발견 공시: {len(result.disclosures)}건 (HIGH {result.high_count}, NORMAL {result.normal_count})"
    )
    print()

    if not result.disclosures:
        print("신규 공시 없음.")
        return 0

    for d in result.disclosures:
        tag = "🔴" if d.importance == "HIGH" else "🔵"
        print(f"{tag} [{d.receipt_date}] {d.corp_name}({d.stock_code}) — {d.report_name}")
        print(f"   {d.url}")

    if args.notify:
        from sentinelq.notifications.telegram import send_disclosure_alert

        print("\n텔레그램 알림 전송 중...")
        try:
            ok = send_disclosure_alert(result.disclosures, as_of=date.today())
            print("  전송 완료." if ok else "  전송 실패 (응답 ok=False).")
        except Exception as exc:
            print(f"  ⚠ 전송 오류: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
