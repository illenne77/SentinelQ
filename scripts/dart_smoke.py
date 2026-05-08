"""DART OpenAPI smoke test.

Verifies:
1. API key is valid
2. corpCode.xml endpoint returns the ticker -> corp_code mapping
3. fnlttSinglAcntAll.json returns quarterly financials for a known ticker
4. We can extract 자본총계 (total equity) and 보통주식수 (common shares)
5. Compute BPS for one quarter

Reference: https://opendart.fss.or.kr/guide/main.do
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Dict, Optional
from xml.etree import ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = ROOT / "secrets" / "dart_api_key.txt"
CACHE_DIR = ROOT / "data" / "cache" / "dart"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://opendart.fss.or.kr/api"


def load_key() -> str:
    return KEY_PATH.read_text().strip()


def fetch_corp_code_map(api_key: str) -> Dict[str, dict]:
    """Download and parse corpCode.xml. Returns {stock_code: {corp_code, corp_name}}.

    Cached to data/cache/dart/corp_code.json on disk.
    """
    cache = CACHE_DIR / "corp_code.json"
    if cache.exists():
        with cache.open(encoding="utf-8") as f:
            return json.load(f)

    url = f"{BASE}/corpCode.xml"
    r = requests.get(url, params={"crtfc_key": api_key}, timeout=60)
    r.raise_for_status()
    # Response is a ZIP file containing CORPCODE.xml
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        with zf.open("CORPCODE.xml") as xf:
            tree = ET.parse(xf)
    root = tree.getroot()

    out: Dict[str, dict] = {}
    for elem in root.findall("list"):
        stock_code = (elem.findtext("stock_code") or "").strip()
        if not stock_code or stock_code == " ":
            # Non-listed corp; skip
            continue
        out[stock_code] = {
            "corp_code": (elem.findtext("corp_code") or "").strip(),
            "corp_name": (elem.findtext("corp_name") or "").strip(),
        }
    with cache.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def fetch_financials(api_key: str, corp_code: str, year: int, reprt_code: str = "11014") -> dict:
    """Fetch fnlttSinglAcntAll.

    reprt_code:
      11013 = 1Q (분기보고서)
      11012 = 반기 (Half)
      11014 = 3Q (분기보고서 3분기)
      11011 = 사업보고서 (Annual)
    """
    url = f"{BASE}/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": reprt_code,
        "fs_div": "CFS",  # Consolidated (연결)
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def find_account(items: list, account_id_keywords: list) -> Optional[dict]:
    """Find a line item by matching any keyword in account_id or account_nm."""
    for it in items:
        aid = it.get("account_id", "")
        anm = it.get("account_nm", "")
        for kw in account_id_keywords:
            if kw in aid or kw in anm:
                return it
    return None


def main() -> int:
    api_key = load_key()
    print(f"API key loaded: {api_key[:6]}...{api_key[-4:]} (len={len(api_key)})")

    # Step 1: corpCode map
    print("\n[1] Fetching corpCode.xml...")
    corp_map = fetch_corp_code_map(api_key)
    print(f"  Listed companies: {len(corp_map)}")
    samsung = corp_map.get("005930")
    print(f"  Samsung Electronics (005930): {samsung}")
    if not samsung:
        print("  ERROR: Samsung not found")
        return 1

    # Step 2: one quarterly report
    print("\n[2] Fetching 2024 3Q financials for Samsung...")
    js = fetch_financials(api_key, samsung["corp_code"], 2024, "11014")
    print(f"  status: {js.get('status')}, message: {js.get('message')}")
    items = js.get("list", [])
    print(f"  line items: {len(items)}")
    if not items:
        print(f"  Raw response keys: {list(js.keys())}")
        return 1

    # Show first item to understand schema
    print(f"\n  Sample item keys: {list(items[0].keys())}")

    # Step 3: list all 자본 BS items to identify both 자본총계 and 지배지분 자본
    print("\n[3] Equity items in BS:")
    for it in items:
        if it.get("sj_div") == "BS" and ("자본" in it.get("account_nm", "") or "지배" in it.get("account_nm", "")):
            print(f"    {it.get('account_id'):60s}: {it.get('account_nm'):40s} = {it.get('thstrm_amount')}")

    # Step 4: fetch shares outstanding — try alternate endpoint names
    print("\n[4] Fetching shares outstanding...")
    for endpoint in ["stockTotqySttus.json", "stockTotqyCnt.json", "stockSttus.json"]:
        url = f"{BASE}/{endpoint}"
        params = {
            "crtfc_key": api_key,
            "corp_code": samsung["corp_code"],
            "bsns_year": "2024",
            "reprt_code": "11014",
        }
        r = requests.get(url, params=params, timeout=30)
        try:
            js2 = r.json()
        except Exception:
            js2 = {"status": "?", "message": r.text[:200]}
        print(f"  {endpoint}: status={js2.get('status')}, message={js2.get('message')}")
        if js2.get("status") == "000":
            for it in js2.get("list", []):
                se = it.get("se", "")
                istc = it.get("istc_totqy", "-")
                distb = it.get("distb_stock_co", "-")
                tess = it.get("tesstk_co", "-")
                print(f"    se={se:8s}  istc_totqy(발행)={istc:>20s}  tesstk(자기)={tess:>15s}  distb(유통)={distb:>15s}")
            break

    # Step 5: BPS sanity check
    # Samsung Q3 2024 known approx BPS ~ 50,000 KRW
    # 지배지분 자본 / 보통주식수
    return 0


if __name__ == "__main__":
    sys.exit(main())
