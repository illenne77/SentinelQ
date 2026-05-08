"""Fetch current shares outstanding per ticker via KIS inquire-price.

Uses hts_avls (시가총액 in 억) and stck_prpr (current price) to back out:
    shares = hts_avls * 1e8 / stck_prpr

Output: data/cache/dart/shares_snapshot.csv
    columns: ticker, name, close, mkt_cap_eok, shares

This is a SNAPSHOT (today). Used as approximate constant shares for the
A-F01 B/M backtest. See PREREG-0005 §13 for the approximation caveat.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("ERROR: pip install python-dotenv")

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "secrets"
UNIVERSE_CSV = ROOT / "research" / "a2_sector_rotation" / "sector_map.csv"
OUT_PATH = ROOT / "data" / "cache" / "dart" / "shares_snapshot.csv"


def load_token(env: str = "live"):
    cache = SECRETS / f"kis_token_{env}.json"
    data = json.loads(cache.read_text(encoding="utf-8"))
    prefix = "KIS_LIVE_" if env == "live" else "KIS_PAPER_"
    app_key = os.environ[f"{prefix}APP_KEY"]
    app_secret = os.environ[f"{prefix}APP_SECRET"]
    return data["base_url"], data["access_token"], app_key, app_secret


def fetch_price(base_url: str, token: str, app_key: str, app_secret: str, ticker: str):
    qs = urllib.parse.urlencode({"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker})
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price?{qs}"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01010100",
        "custtype": "P",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    load_dotenv(ROOT / ".env", override=True)
    base_url, token, app_key, app_secret = load_token("live")

    universe = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    print(f"Fetching shares for {len(universe)} tickers...")

    rows = []
    for i, row in universe.iterrows():
        ticker = row["ticker"]
        try:
            payload = fetch_price(base_url, token, app_key, app_secret, ticker)
        except Exception as e:
            print(f"  [{i+1}] {ticker} ERROR: {e}")
            continue
        if payload.get("rt_cd") != "0":
            print(f"  [{i+1}] {ticker} rt_cd={payload.get('rt_cd')} msg={payload.get('msg1')}")
            continue
        out = payload.get("output", {})
        try:
            close = float(out.get("stck_prpr", "0"))
            mkt_cap_eok = float(out.get("hts_avls", "0"))
        except (ValueError, TypeError):
            print(f"  [{i+1}] {ticker} parse error")
            continue
        if close <= 0 or mkt_cap_eok <= 0:
            print(f"  [{i+1}] {ticker} zero close/mcap (delisted?)")
            continue
        shares = mkt_cap_eok * 1e8 / close
        rows.append({
            "ticker": ticker,
            "name": out.get("bstp_kor_isnm", ""),
            "close": close,
            "mkt_cap_eok": mkt_cap_eok,
            "shares": shares,
            "per": out.get("per"),
            "pbr": out.get("pbr"),
        })
        if (i + 1) % 30 == 0:
            print(f"  [{i+1}/{len(universe)}] ok={len(rows)}")
        time.sleep(0.105)  # ~9.5/sec

    df = pd.DataFrame(rows)
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\nSaved {len(df)} rows to {OUT_PATH}")
    print(df.head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
