"""포트폴리오 세후 수익률 대시보드 CLI (T016).

PREREG: PREREG-0009 §2.4
Usage:
  python scripts/run_portfolio.py --year 2025
  python scripts/run_portfolio.py --year 2025 --out data/output/ --env live
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
except ImportError:
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="포트폴리오 세후 수익률 대시보드")
    parser.add_argument(
        "--year", type=int, default=date.today().year, help="과세기간 (기본: 당해 연도)"
    )
    parser.add_argument("--env", choices=["paper", "live"], default="live", help="KIS API 환경")
    parser.add_argument("--account", default=None, help="계좌번호 (XXXXXXXX-YY)")
    parser.add_argument(
        "--realized-gain",
        type=int,
        default=None,
        help="당해 실현 손익 수동 입력 (원). 미입력 시 KIS 기간손익 조회",
    )
    parser.add_argument("--out", default="data/output", help="출력 디렉토리")
    parser.add_argument("--stem", default="", help="출력 파일명 접두사")
    args = parser.parse_args(argv)

    from sentinelq.adapters.kis_history import (
        inquire_domestic_balance,
        inquire_overseas_balance,
        inquire_period_profit,
    )
    from sentinelq.portfolio.after_tax import calculate_after_tax
    from sentinelq.reports.portfolio_report import export_portfolio_report

    confirm_live = args.env == "live"
    api_kw: dict = {"env": args.env, "account": args.account, "confirm_live": confirm_live}

    print(f"[1/4] KIS 국내주식 잔고 조회 (env={args.env})...")
    try:
        kr_holdings = inquire_domestic_balance(**api_kw)
    except Exception as exc:
        print(f"  ⚠ 국내주식 잔고 조회 실패 (계속): {exc}")
        kr_holdings = []

    print(f"[2/4] KIS 해외주식 잔고 조회 (env={args.env})...")
    try:
        us_holdings = inquire_overseas_balance(**api_kw)
    except Exception as exc:
        print(f"  ⚠ 해외주식 잔고 조회 실패 (계속): {exc}")
        us_holdings = []

    all_holdings = kr_holdings + us_holdings
    print(f"      → 총 {len(all_holdings)}개 종목")

    print("[3/4] 당해 실현 손익 조회...")
    if args.realized_gain is not None:
        realized = Decimal(args.realized_gain)
        print(f"      → 수동 입력: {realized:,}원")
    else:
        try:
            profits = inquire_period_profit(
                date(args.year, 1, 1),
                date(args.year, 12, 31),
                **api_kw,
            )
            realized = sum((p.realized_profit_krw for p in profits), Decimal("0"))
            print(f"      → KIS 조회: {realized:,}원")
        except Exception as exc:
            print(f"  ⚠ 기간손익 조회 실패 → 0원으로 처리: {exc}")
            realized = Decimal("0")

    print("[4/4] 세후 수익률 계산 및 리포트 생성...")
    portfolio = calculate_after_tax(all_holdings, realized_gain_ytd_krw=realized)

    stem = args.stem or str(args.year)
    txt, csv_path = export_portfolio_report(
        portfolio,
        Path(args.out),
        stem=stem,
        as_of=str(date.today()),
    )

    print("\n출력 완료:")
    print(f"  텍스트 대시보드: {txt}")
    print(f"  CSV:            {csv_path}")
    print()
    sys.stdout.write(txt.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
