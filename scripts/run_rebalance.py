"""패시브 리밸런싱 실행 계획 CLI (T019).

PREREG: PREREG-0010 §2.6
Usage:
  python scripts/run_rebalance.py --target KR=30 US=70
  python scripts/run_rebalance.py --target-file targets.json --env live --threshold 5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
except ImportError:
    pass


def _parse_targets(items: list[str]) -> dict[str, Decimal]:
    """["KR=30", "US=70"] -> {"KR": Decimal("30"), "US": Decimal("70")}"""
    result: dict[str, Decimal] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"목표 배분 형식 오류: {item!r}  (예: KR=30)")
        market, pct = item.split("=", 1)
        result[market.strip().upper()] = Decimal(pct.strip())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="패시브 리밸런싱 실행 계획")
    parser.add_argument(
        "--target",
        nargs="+",
        metavar="MARKET=PCT",
        help="시장별 목표 비중 (예: --target KR=30 US=70)",
    )
    parser.add_argument(
        "--target-file",
        default=None,
        help='목표 배분 JSON 파일 (예: {"KR": 30, "US": 70})',
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="리밸런싱 발동 임계값 %% (기본 5)",
    )
    parser.add_argument(
        "--year", type=int, default=date.today().year, help="과세기간 (기본: 당해 연도)"
    )
    parser.add_argument("--env", choices=["paper", "live"], default="live")
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

    # 목표 배분 로드 (파일 우선, CLI 추가 override)
    target_weights: dict[str, Decimal] = {}
    if args.target_file:
        with open(args.target_file, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                target_weights[k.upper()] = Decimal(str(v))
    if args.target:
        try:
            target_weights.update(_parse_targets(args.target))
        except ValueError as exc:
            print(f"오류: {exc}")
            return 1

    if not target_weights:
        print("오류: --target 또는 --target-file 중 하나를 지정하세요.")
        print("예:  python scripts/run_rebalance.py --target KR=30 US=70")
        return 1

    from sentinelq.adapters.kis_history import (
        inquire_domestic_balance,
        inquire_overseas_balance,
        inquire_period_profit,
    )
    from sentinelq.portfolio.after_tax import calculate_after_tax
    from sentinelq.portfolio.rebalance import TargetAllocation, calculate_rebalance
    from sentinelq.reports.rebalance_report import export_rebalance_report

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

    print("[4/4] 리밸런싱 계획 생성...")
    portfolio = calculate_after_tax(all_holdings, realized_gain_ytd_krw=realized)

    try:
        targets = TargetAllocation(weights=target_weights)
    except ValueError as exc:
        print(f"오류: {exc}")
        return 1

    plan = calculate_rebalance(portfolio, targets, threshold_pct=Decimal(str(args.threshold)))

    stem = args.stem or str(args.year)
    txt, csv_path = export_rebalance_report(
        plan, Path(args.out), stem=stem, as_of=str(date.today())
    )

    print("\n출력 완료:")
    print(f"  리밸런싱 계획: {txt}")
    print(f"  CSV:          {csv_path}")
    print()
    sys.stdout.write(txt.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
