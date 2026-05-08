"""DART quarterly equity backfill for SentinelQ alpha A-F01 (Book-to-Market).

For each ticker in the existing 136-ticker universe:
1. Look up corp_code from cached corpCode map
2. Fetch quarterly reports for years YEAR_START..YEAR_END (4 quarters per year)
3. Extract '지배기업 소유주지분' (ifrs-full_EquityAttributableToOwnersOfParent)
4. Save to data/cache/dart/equity_quarterly.parquet  (long format)

Reporting calendar (DART reprt_code):
  11013 = 1Q (release ~mid May)
  11012 = 반기 (release ~mid Aug)
  11014 = 3Q (release ~mid Nov)
  11011 = 사업보고서/Annual (release ~mid Mar of next year)

Rate: ~10 req/sec is safe.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = ROOT / "secrets" / "dart_api_key.txt"
CACHE_DIR = ROOT / "data" / "cache" / "dart"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CORP_MAP_PATH = CACHE_DIR / "corp_code.json"
OUT_PATH = CACHE_DIR / "equity_quarterly.parquet"
LOG_PATH = ROOT / "research" / "a_f01_value" / "dart_backfill_log.txt"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

UNIVERSE_CSV = ROOT / "research" / "a2_sector_rotation" / "sector_map.csv"

YEAR_START = 2020
YEAR_END = 2024
REPRT_CODES = {
    "11013": "1Q",
    "11012": "2Q",
    "11014": "3Q",
    "11011": "Annual",
}
BASE = "https://opendart.fss.or.kr/api"

# Quarterly fiscal-period end dates (used to assign a "filing window" report date).
# DART reports become public ~45 days after period end (Q1/Q2/Q3) or ~90 days (Annual).
QUARTER_END = {
    "11013": ("03-31", 45),  # Q1 ends 3/31, public ~mid May
    "11012": ("06-30", 45),  # Q2 ends 6/30, public ~mid Aug
    "11014": ("09-30", 45),  # Q3 ends 9/30, public ~mid Nov
    "11011": ("12-31", 90),  # Annual ends 12/31, public ~mid Mar
}

EQUITY_CONTROLLING = "ifrs-full_EquityAttributableToOwnersOfParent"
EQUITY_TOTAL = "ifrs-full_Equity"


def load_key() -> str:
    return KEY_PATH.read_text().strip()


def load_corp_map() -> Dict[str, dict]:
    if not CORP_MAP_PATH.exists():
        sys.exit(f"ERROR: missing {CORP_MAP_PATH}. Run scripts/dart_smoke.py first.")
    with CORP_MAP_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_universe() -> List[str]:
    if not UNIVERSE_CSV.exists():
        sys.exit(f"ERROR: missing {UNIVERSE_CSV}")
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    return df["ticker"].tolist()


def fetch_one(api_key: str, corp_code: str, year: int, reprt_code: str) -> Optional[dict]:
    """Return the controlling-interest equity in KRW for one (corp, year, quarter), or None."""
    url = f"{BASE}/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": reprt_code,
        "fs_div": "CFS",  # Consolidated
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        js = r.json()
    except Exception as e:
        return {"error": str(e)}
    status = js.get("status")
    if status != "000":
        return {"status": status, "message": js.get("message")}
    items = js.get("list", [])

    eq_ctrl = None
    eq_total = None
    for it in items:
        if it.get("sj_div") != "BS":
            continue
        aid = it.get("account_id", "")
        if aid == EQUITY_CONTROLLING:
            try:
                eq_ctrl = int(it.get("thstrm_amount", "").replace(",", ""))
            except (ValueError, AttributeError):
                pass
        elif aid == EQUITY_TOTAL:
            try:
                eq_total = int(it.get("thstrm_amount", "").replace(",", ""))
            except (ValueError, AttributeError):
                pass
    if eq_ctrl is None and eq_total is None:
        return {"status": "no_equity_line", "items": len(items)}

    period_end_md, lag_days = QUARTER_END[reprt_code]
    period_end = pd.Timestamp(f"{year}-{period_end_md}")
    available_from = period_end + pd.Timedelta(days=lag_days)
    return {
        "status": "ok",
        "equity_controlling": eq_ctrl,
        "equity_total": eq_total,
        "period_end": period_end,
        "available_from": available_from,
    }


def main() -> int:
    api_key = load_key()
    corp_map = load_corp_map()
    universe = load_universe()
    print(f"Universe: {len(universe)} tickers")
    print(f"Years: {YEAR_START}-{YEAR_END}, quarters: {list(REPRT_CODES.values())}")

    # Resolve corp_codes
    resolved = []
    missing = []
    for tk in universe:
        info = corp_map.get(tk)
        if info:
            resolved.append((tk, info["corp_code"], info["corp_name"]))
        else:
            missing.append(tk)
    print(f"Resolved {len(resolved)} / {len(universe)} (missing: {len(missing)})")
    if missing:
        print(f"  Missing tickers: {missing[:10]}{'...' if len(missing) > 10 else ''}")

    rows = []
    errors = []
    log_lines = []
    log_lines.append(f"DART backfill log\n{'=' * 60}\n")
    log_lines.append(f"Universe: {len(universe)}, resolved: {len(resolved)}, missing: {len(missing)}\n")
    log_lines.append(f"Years: {YEAR_START}-{YEAR_END}\n\n")

    n_calls = 0
    n_ok = 0
    n_fail = 0
    n_total = len(resolved) * (YEAR_END - YEAR_START + 1) * len(REPRT_CODES)
    print(f"Total calls planned: {n_total}")

    t0 = time.time()
    for ticker, corp_code, name in resolved:
        ok_count = 0
        for year in range(YEAR_START, YEAR_END + 1):
            for reprt_code, qname in REPRT_CODES.items():
                res = fetch_one(api_key, corp_code, year, reprt_code)
                n_calls += 1
                time.sleep(0.105)  # ~9.5/sec
                if res is None or res.get("status") != "ok":
                    n_fail += 1
                    msg = (res or {}).get("message") or (res or {}).get("status") or "unknown"
                    errors.append((ticker, year, qname, msg))
                    continue
                rows.append({
                    "ticker": ticker,
                    "name": name,
                    "year": year,
                    "quarter": qname,
                    "reprt_code": reprt_code,
                    "period_end": res["period_end"],
                    "available_from": res["available_from"],
                    "equity_controlling_krw": res.get("equity_controlling"),
                    "equity_total_krw": res.get("equity_total"),
                })
                n_ok += 1
                ok_count += 1
        if n_calls % 500 == 0:
            elapsed = time.time() - t0
            rate = n_calls / max(elapsed, 1)
            eta = (n_total - n_calls) / max(rate, 0.1)
            print(f"  [{n_calls}/{n_total}] ok={n_ok} fail={n_fail} rate={rate:.1f}/s eta={eta/60:.1f}min")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed/60:.1f} min. ok={n_ok} fail={n_fail}")

    df = pd.DataFrame(rows)
    print(f"Output rows: {len(df)}")
    if not df.empty:
        df.to_parquet(OUT_PATH, index=False)
        print(f"Saved to {OUT_PATH}")
        # Coverage by ticker
        cov = df.groupby("ticker").size().describe()
        print(f"Coverage per ticker stats:\n{cov}")

    # Write log
    log_lines.append(f"Calls: {n_calls}, ok: {n_ok}, fail: {n_fail}\n")
    log_lines.append(f"Elapsed: {elapsed/60:.1f} min\n\n")
    if errors:
        log_lines.append(f"ERRORS ({len(errors)}):\n")
        for ticker, year, qname, msg in errors[:50]:
            log_lines.append(f"  {ticker} {year} {qname}: {msg}\n")
        if len(errors) > 50:
            log_lines.append(f"  ... +{len(errors) - 50} more\n")
    LOG_PATH.write_text("".join(log_lines), encoding="utf-8")
    print(f"Log: {LOG_PATH}")

    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
