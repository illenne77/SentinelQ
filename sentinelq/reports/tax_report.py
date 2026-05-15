"""오케스트레이션 파이프라인 — KIS 거래내역 → NTS 양도세 신고 양식 (Phase 3 T007).

Spec: .claude/queue/spec-T007.md
PREREG: PREREG-0008 §2.5 + §4.1 + amendment-1 §6
ADR: ADR-0013 Phase 3 KR Investor Tools
KPI Gate: G1 — 본인 KIS 계정 → fetch → 양도세 신고 양식 자동 출력 (15분 이내)
OUT: csv_importer/타 증권사, PDF 렌더링, deduction/loss_harvesting 자동 통합,
     다년 리포트, ports 인터페이스, 자동매매·주문·알파·시그널 (ADR-0011·0012·0013).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sentinelq.adapters.kis_history import (
    KisApiError,
    Transaction,
    inquire_domestic_daily_trans,
    inquire_overseas_period_trans,
)
from sentinelq.portfolio.tax_lots import InsufficientLotsError, TaxLotLedger
from sentinelq.reports.nts_form import (
    NTSCapitalGainsForm,
    build_nts_form,
    export_detail_csv,
    export_summary_csv,
)
from sentinelq.tax.capital_gains import calculate_year


def run_pipeline(
    transactions: Iterable[Transaction],
    tax_year: int,
) -> NTSCapitalGainsForm:
    """T002→T003→T006 순수 오케스트레이션. 네트워크 無.

    거래를 trade_date 오름차순(동일자 BUY 우선)으로 정렬 후
    TaxLotLedger 적용 → calculate_year → build_nts_form.
    빈 입력은 영 폼 반환 (예외 없음).
    """
    txs = sorted(
        transactions,
        key=lambda t: (t.trade_date, 0 if t.side == "BUY" else 1),
    )
    ledger = TaxLotLedger()
    realizations = ledger.apply_all(txs)
    summary = calculate_year(realizations, tax_year)
    return build_nts_form(summary, realizations)


def fetch_transactions(
    tax_year: int,
    *,
    start_date: date | None = None,
    env: str = "paper",
    account: str | None = None,
    confirm_live: bool = False,
) -> list[Transaction]:
    """KIS 해외 + 국내 거래내역 fetch + 합본 (T001 함수 호출).

    start_date None → date(tax_year, 1, 1).
    """
    if start_date is None:
        start_date = date(tax_year, 1, 1)
    end_date = date(tax_year, 12, 31)
    overseas = inquire_overseas_period_trans(
        start_date,
        end_date,
        env=env,  # type: ignore[arg-type]
        account=account,
        confirm_live=confirm_live,
    )
    domestic = inquire_domestic_daily_trans(
        start_date,
        end_date,
        env=env,  # type: ignore[arg-type]
        account=account,
        confirm_live=confirm_live,
    )
    return overseas + domestic


def _tx_to_dict(tx: Transaction) -> dict[str, Any]:
    return {
        "trade_date": tx.trade_date.isoformat(),
        "settle_date": tx.settle_date.isoformat() if tx.settle_date is not None else None,
        "ticker": tx.ticker,
        "market": tx.market,
        "side": tx.side,
        "quantity": tx.quantity,
        "price": str(tx.price),
        "currency": tx.currency,
        "fee": str(tx.fee),
        "tax": str(tx.tax),
        "fx_rate": str(tx.fx_rate) if tx.fx_rate is not None else None,
        "raw": tx.raw,
    }


def transactions_to_json(transactions: Iterable[Transaction]) -> str:
    """Transaction 시퀀스를 JSON 배열 문자열로. Decimal→str, date→ISO."""
    return json.dumps([_tx_to_dict(tx) for tx in transactions], ensure_ascii=False)


def _dict_to_tx(d: dict[str, Any]) -> Transaction:
    settle_raw = d.get("settle_date")
    fx_raw = d.get("fx_rate")
    return Transaction(
        trade_date=date.fromisoformat(d["trade_date"]),
        settle_date=date.fromisoformat(settle_raw) if settle_raw else None,
        ticker=d["ticker"],
        market=d["market"],
        side=d["side"],
        quantity=int(d["quantity"]),
        price=Decimal(str(d["price"])),
        currency=d["currency"],
        fee=Decimal(str(d["fee"])),
        tax=Decimal(str(d["tax"])),
        fx_rate=Decimal(str(fx_raw)) if fx_raw is not None else None,
        raw=d.get("raw", {}),
    )


def transactions_from_json(text: str) -> list[Transaction]:
    """JSON 배열 → list[Transaction]. raw 누락 시 빈 dict."""
    return [_dict_to_tx(d) for d in json.loads(text)]


def write_report(form: NTSCapitalGainsForm, out_dir: Path) -> tuple[Path, Path]:
    """summary·detail CSV 2개 파일 기록. (summary_path, detail_path) 반환.

    out_dir 미존재 시 생성. 파일명에 tax_year 포함.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / f"nts_summary_{form.tax_year}.csv"
    detail_path = out_dir / f"nts_detail_{form.tax_year}.csv"
    # newline="" preserves csv.writer's \r\n without Windows double-translation
    with summary_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(export_summary_csv(form))
    with detail_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(export_detail_csv(form))
    return summary_path, detail_path


def main(argv: list[str] | None = None) -> int:
    """argparse CLI 엔트리. 성공 0, 오류 비0."""
    parser = argparse.ArgumentParser(
        prog="run_tax_report",
        description="KIS 거래내역 → NTS 양도세 신고 양식 자동 생성 (T007, KPI Gate G1)",
    )
    parser.add_argument(
        "--tax-year",
        type=int,
        default=None,
        help="과세연도 YYYY (기본: 직전 캘린더 연도)",
    )
    parser.add_argument(
        "--from-json",
        default=None,
        help="거래내역 JSON 파일 경로 (지정 시 네트워크 fetch 건너뜀)",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="fetch 시작일 YYYY-MM-DD (FIFO 정확성용, 기본: tax_year-01-01)",
    )
    parser.add_argument(
        "--env",
        choices=["paper", "live"],
        default="paper",
        help="KIS 환경 (기본: paper)",
    )
    parser.add_argument(
        "--account",
        default=None,
        help="계좌번호 (기본: KIS_ACCOUNT 환경변수)",
    )
    parser.add_argument(
        "--out-dir",
        default="data/private",
        help="출력 디렉터리 (기본: data/private, gitignored)",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="실거래 fetch 명시 동의 (--env live 필수)",
    )
    parser.add_argument(
        "--dump-json",
        default=None,
        help="fetch 결과 JSON 저장 경로 (재실행 캐시용)",
    )

    args = parser.parse_args(argv)
    tax_year = args.tax_year if args.tax_year is not None else (date.today().year - 1)

    if args.from_json is not None:
        json_path = Path(args.from_json)
        try:
            text = json_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"입력 파일 오류: {exc}", file=sys.stderr)
            return 5
        transactions: list[Transaction] = transactions_from_json(text)
    else:
        if args.env == "live":
            live_allow = os.environ.get("SENTINELQ_LIVE_ALLOW", "") == "1"
            if not args.confirm_live or not live_allow:
                print(
                    "실거래 호출 거부: --confirm-live 플래그와 "
                    "환경변수 SENTINELQ_LIVE_ALLOW=1 모두 필요합니다.",
                    file=sys.stderr,
                )
                return 4
        start_date: date | None = None
        if args.start_date:
            start_date = date.fromisoformat(args.start_date)
        try:
            transactions = fetch_transactions(
                tax_year,
                start_date=start_date,
                env=args.env,
                account=args.account,
                confirm_live=args.confirm_live,
            )
        except KisApiError as exc:
            print(f"KIS API 오류: {exc}", file=sys.stderr)
            return 3

    if args.dump_json is not None:
        Path(args.dump_json).write_text(transactions_to_json(transactions), encoding="utf-8")

    try:
        form = run_pipeline(transactions, tax_year)
    except InsufficientLotsError as exc:
        print(
            "매도 종목의 매수 기록이 fetch 범위 밖입니다 "
            "— --start-date 를 더 이른 날짜로 지정하세요. "
            f"({exc})",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out_dir)
    summary_path, detail_path = write_report(form, out_dir)

    print(f"과세연도: {form.tax_year}")
    print(f"매도 건수: {form.sale_count}")
    print(f"총 양도차익: {form.total_realized_gain_krw:,} 원")
    print(f"과세표준: {form.taxable_base_krw:,} 원")
    print(f"산출세액(국세): {form.national_tax_krw:,} 원")
    print(f"지방소득세: {form.local_tax_krw:,} 원")
    print(f"총 세액: {form.total_tax_krw:,} 원")
    print(f"신고기간: {form.filing_period_start} ~ {form.filing_period_end}")
    print(f"요약 CSV: {summary_path}")
    print(f"상세 CSV: {detail_path}")

    return 0
