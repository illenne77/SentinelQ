"""
KIS price inquiry smoke test — paper or live.

Reads the token from secrets/kis_token_<env>.json and queries the
'inquire-price' endpoint for a given ticker (default 005930 Samsung).

Usage:
    python scripts/kis_inquire_price.py            # paper, 005930
    python scripts/kis_inquire_price.py 035720     # paper, Kakao
    python scripts/kis_inquire_price.py 005930 live

Hard rules:
  * Refuses to call live without explicit 'live' arg.
  * Loads only the env-matched token cache; never mixes envs.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("ERROR: pip install python-dotenv")

ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = ROOT / "secrets"


def _resolve_args() -> tuple[str, str]:
    args = sys.argv[1:]
    ticker = "005930"
    env = (os.getenv("KIS_ENV") or "paper").strip().lower()

    for a in args:
        a = a.strip().lower()
        if a in {"paper", "live"}:
            env = a
        elif a.isdigit() and len(a) == 6:
            ticker = a
        else:
            sys.exit(f"ERROR: bad arg {a!r}")
    if env == "live" and "live" not in [a.lower() for a in args]:
        sys.exit("ERROR: 'live' must be passed explicitly as a CLI arg.")
    return ticker, env


def _load_token(env: str) -> tuple[str, str, str, str]:
    cache = SECRETS_DIR / f"kis_token_{env}.json"
    if not cache.exists():
        sys.exit(f"ERROR: no token cache at {cache}. Run scripts/kis_token.py first.")
    data = json.loads(cache.read_text(encoding="utf-8"))
    base_url = data["base_url"]
    token = data["access_token"]
    prefix = "KIS_PAPER_" if env == "paper" else "KIS_LIVE_"
    app_key = os.getenv(f"{prefix}APP_KEY")
    app_secret = os.getenv(f"{prefix}APP_SECRET")
    if not app_key or not app_secret:
        sys.exit(f"ERROR: missing {prefix}APP_KEY / APP_SECRET in .env")
    return base_url, token, app_key, app_secret


def main() -> int:
    load_dotenv(ROOT / ".env", override=True)
    ticker, env = _resolve_args()
    base_url, token, app_key, app_secret = _load_token(env)

    qs = urllib.parse.urlencode({
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
    })
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
        payload = json.loads(resp.read().decode("utf-8"))

    out = payload.get("output", {})
    if payload.get("rt_cd") != "0" or not out:
        print("[inquire-price] FAILED:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2

    # Print a tight summary; full payload is one-line at the end.
    print(f"[inquire-price] env={env} ticker={ticker} ({out.get('bstp_kor_isnm','')})")
    print(f"  price        = {out.get('stck_prpr')} ({out.get('prdy_ctrt')}%)")
    print(f"  range        = {out.get('stck_lwpr')} – {out.get('stck_hgpr')}")
    print(f"  cum_vol      = {out.get('acml_vol')}")
    print(f"  vol_vs_prev  = {out.get('prdy_vrss_vol_rate')}%")
    print(f"  per/pbr      = {out.get('per')} / {out.get('pbr')}")
    print(f"  mkt_cap_eok  = {out.get('hts_avls')}")
    print(f"  vi_active    = {out.get('vi_cls_code')}   (N=normal)")
    print(f"  managed/warn = {out.get('mang_issu_cls_code')} / {out.get('mrkt_warn_cls_code')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
