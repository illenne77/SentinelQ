"""DART annual income-statement + total-assets backfill for A-F03 GP/A.

Annual reports only (reprt_code=11011), fs_div=CFS.
Years 2019..2024 (6 annual reports per ticker; 2025 not yet filed).

Extracts:
    ifrs-full_Revenue       (영업수익/매출액)
    ifrs-full_CostOfSales   (매출원가)
    ifrs-full_GrossProfit   (매출총이익)  -- preferred when present
    ifrs-full_Assets        (자산총계)

Output: data/cache/dart/income_assets_annual.parquet
    columns: ticker, name, year, period_end, available_from,
             revenue_krw, cogs_krw, gross_profit_krw, assets_krw

available_from = (year-end + 90 days) per K-IFRS annual filing window.
Errors logged to research/a_f03_quality/dart_income_assets_log.txt.

Rate: ~10 req/sec (0.105s sleep). ~136 × 6 = 816 calls; ~2 min.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "secrets"
KEY_FILE = SECRETS / "dart_api_key.txt"
CORP_MAP = ROOT / "data" / "cache" / "dart" / "corp_code.json"
UNIVERSE_CSV = ROOT / "research" / "a2_sector_rotation" / "sector_map.csv"
OUT_PATH = ROOT / "data" / "cache" / "dart" / "income_assets_annual.parquet"
LOG_PATH = ROOT / "research" / "a_f03_quality" / "dart_income_assets_log.txt"

YEARS = [2019, 2020, 2021, 2022, 2023, 2024]
REPRT_CODE = "11011"  # Annual

ACCOUNTS = {
    "revenue_krw": "ifrs-full_Revenue",
    "cogs_krw": "ifrs-full_CostOfSales",
    "gross_profit_krw": "ifrs-full_GrossProfit",
    "assets_krw": "ifrs-full_Assets",
}


def fetch_one(api_key: str, corp_code: str, year: int):
    qs = urllib.parse.urlencode({
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": REPRT_CODE,
        "fs_div": "CFS",
    })
    url = f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json?{qs}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_payload(payload: dict):
    if payload.get("status") != "000":
        return None, payload.get("status"), payload.get("message", "")
    items = payload.get("list", [])
    extracted = {}
    for item in items:
        aid = item.get("account_id", "")
        for col, target_id in ACCOUNTS.items():
            if aid == target_id and col not in extracted:
                v = item.get("thstrm_amount", "")
                try:
                    extracted[col] = float(str(v).replace(",", ""))
                except (ValueError, TypeError):
                    pass
    if "revenue_krw" not in extracted and "gross_profit_krw" not in extracted:
        return None, "missing", "no revenue/gp lines"
    # Fallback: if GP missing but Rev+COGS present
    if "gross_profit_krw" not in extracted and "revenue_krw" in extracted and "cogs_krw" in extracted:
        extracted["gross_profit_krw"] = extracted["revenue_krw"] - extracted["cogs_krw"]
    return extracted, "000", "ok"


def main():
    api_key = KEY_FILE.read_text().strip()
    corp_map = json.loads(CORP_MAP.read_text(encoding="utf-8"))
    universe = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_lines = []

    rows = []
    total_calls = 0
    ok_count = 0
    fail_count = 0

    print(f"Backfilling {len(universe)} tickers × {len(YEARS)} annual reports...")
    for i, urow in universe.iterrows():
        ticker = urow["ticker"].zfill(6)
        name = urow.get("name", "")
        cmap = corp_map.get(ticker)
        if not cmap:
            log_lines.append(f"{ticker}\tno_corp_code")
            continue
        corp_code = cmap["corp_code"] if isinstance(cmap, dict) else cmap
        for year in YEARS:
            total_calls += 1
            try:
                payload = fetch_one(api_key, corp_code, year)
            except Exception as e:
                log_lines.append(f"{ticker}\t{year}\thttp\t{e}")
                fail_count += 1
                time.sleep(0.105)
                continue
            extracted, status, msg = parse_payload(payload)
            if extracted is None:
                log_lines.append(f"{ticker}\t{year}\t{status}\t{msg}")
                fail_count += 1
            else:
                period_end = date(year, 12, 31)
                row = {
                    "ticker": ticker,
                    "name": name,
                    "year": year,
                    "period_end": pd.Timestamp(period_end),
                    "available_from": pd.Timestamp(period_end + timedelta(days=90)),
                    "revenue_krw": extracted.get("revenue_krw"),
                    "cogs_krw": extracted.get("cogs_krw"),
                    "gross_profit_krw": extracted.get("gross_profit_krw"),
                    "assets_krw": extracted.get("assets_krw"),
                }
                rows.append(row)
                ok_count += 1
            time.sleep(0.105)
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(universe)}] calls={total_calls} ok={ok_count} fail={fail_count}")

    df = pd.DataFrame(rows)
    df.to_parquet(OUT_PATH, index=False)
    LOG_PATH.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\nDone. {total_calls} calls, ok={ok_count}, fail={fail_count}")
    print(f"Wrote {len(df)} rows to {OUT_PATH}")
    print(f"Tickers covered: {df['ticker'].nunique()}")
    print(f"Year coverage:")
    print(df.groupby("year").size())


if __name__ == "__main__":
    sys.exit(main() or 0)
