"""
KIS OAuth token issuance — paper or live.

Usage (PowerShell):
    cd D:\\GitLabProjects\\SentinelQ
    python scripts\\kis_token.py            # uses KIS_ENV from .env
    python scripts\\kis_token.py paper      # force paper
    python scripts\\kis_token.py live       # force live  (requires confirmation)

Output: prints redacted token info. Token is also cached at
    secrets/kis_token_<env>.json   (gitignored)

Hard rules:
  * Never prints app_key or app_secret.
  * Refuses to issue a `live` token unless the script is given `live`
    AS AN EXPLICIT CLI ARG — prevents accidental issuance from a paper-default .env.
  * Refuses if app_secret looks like the well-known leaked paper secret.

This script intentionally has zero third-party deps beyond `python-dotenv`
and stdlib. Install once:
    pip install python-dotenv
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("ERROR: pip install python-dotenv  (one-time)")

ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = ROOT / "secrets"
SECRETS_DIR.mkdir(exist_ok=True)

# ---- Known-leaked secrets — refuse to issue tokens for these ----
LEAKED_PAPER_APP_KEYS = {
    "PS79nLHuwOJVexe9HxmHa62OlGa5DxwJ30rn",   # exposed in chat 2026-05-08
}


def _redact(s: str, keep: int = 4) -> str:
    if not s:
        return "<empty>"
    if len(s) <= keep * 2:
        return "*" * len(s)
    return f"{s[:keep]}…{s[-keep:]} (len={len(s)})"


def _resolve_env(arg: str | None) -> str:
    env = (arg or os.getenv("KIS_ENV") or "").strip().lower()
    if env not in {"paper", "live"}:
        sys.exit(f"ERROR: KIS_ENV must be 'paper' or 'live', got: {env!r}")
    if env == "live" and arg != "live":
        sys.exit(
            "ERROR: 'live' token issuance requires explicit CLI argument:\n"
            "  python scripts/kis_token.py live"
        )
    return env


def _load_creds(env: str) -> tuple[str, str, str]:
    prefix = "KIS_PAPER_" if env == "paper" else "KIS_LIVE_"
    base_url = os.getenv(f"{prefix}BASE_URL")
    app_key = os.getenv(f"{prefix}APP_KEY")
    app_secret = os.getenv(f"{prefix}APP_SECRET")
    missing = [n for n, v in [
        (f"{prefix}BASE_URL", base_url),
        (f"{prefix}APP_KEY", app_key),
        (f"{prefix}APP_SECRET", app_secret),
    ] if not v]
    if missing:
        sys.exit(f"ERROR: missing in .env: {', '.join(missing)}")
    if app_key in LEAKED_PAPER_APP_KEYS:
        sys.exit(
            f"REFUSED: app_key {_redact(app_key)} is a known LEAKED key.\n"
            "Re-issue a fresh key from the KIS portal before using this tool."
        )
    return base_url, app_key, app_secret


def _issue(base_url: str, app_key: str, app_secret: str) -> dict:
    body = json.dumps({
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/oauth2/tokenP",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    load_dotenv(ROOT / ".env", override=True)
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else None
    env = _resolve_env(arg)

    base_url, app_key, app_secret = _load_creds(env)
    print(f"[kis_token] env={env}")
    print(f"[kis_token] base_url={base_url}")
    print(f"[kis_token] app_key={_redact(app_key)}")
    print(f"[kis_token] app_secret={_redact(app_secret)}")

    if env == "live":
        ans = input("LIVE token will be issued. Type 'YES' to continue: ")
        if ans.strip() != "YES":
            print("aborted.")
            return 1

    print("[kis_token] requesting token …")
    payload = _issue(base_url, app_key, app_secret)

    if "access_token" not in payload:
        print("[kis_token] FAILED:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2

    cache = {
        "env": env,
        "base_url": base_url,
        "issued_at": datetime.utcnow().isoformat() + "Z",
        "expires_at": payload.get("access_token_token_expired"),
        "expires_in": payload.get("expires_in"),
        "token_type": payload.get("token_type"),
        "access_token": payload["access_token"],
    }
    out = SECRETS_DIR / f"kis_token_{env}.json"
    out.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass

    print("[kis_token] OK")
    print(f"           expires_at  = {cache['expires_at']}")
    print(f"           expires_in  = {cache['expires_in']}s")
    print(f"           token       = {_redact(payload['access_token'], 8)}")
    print(f"           cached at   = {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
