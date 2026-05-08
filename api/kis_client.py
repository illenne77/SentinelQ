"""
KIS HTTP client — token + rate-limited GET.

Wraps stdlib urllib so the rest of the codebase does not depend on requests.
Rate limit policy is conservative-by-default and configurable via env var
KIS_RATE_PER_SEC (float). Default 10/sec per PREREG-0001 §10.

Public API:
    KisClient.from_env(env="paper")        -> client
    client.get(path, params, tr_id)        -> dict (parsed json)

The client transparently retries on rt_cd in {"1", "EGW00201"} (busy/throttle)
with exponential backoff up to 5 attempts.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

try:
    from dotenv import load_dotenv
except ImportError:
    raise SystemExit("ERROR: pip install python-dotenv")

ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = ROOT / "secrets"


@dataclass
class _RateLimiter:
    per_sec: float
    _last: float = 0.0
    _lock: Lock = None  # type: ignore

    def __post_init__(self):
        self._lock = Lock()

    def wait(self):
        min_gap = 1.0 / self.per_sec
        with self._lock:
            now = time.monotonic()
            gap = now - self._last
            if gap < min_gap:
                time.sleep(min_gap - gap)
            self._last = time.monotonic()


class KisClient:
    def __init__(self, env: str, base_url: str, token: str,
                 app_key: str, app_secret: str, rate_per_sec: float = 10.0):
        self.env = env
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.app_key = app_key
        self.app_secret = app_secret
        self.limiter = _RateLimiter(rate_per_sec)

    @classmethod
    def from_env(cls, env: str = "paper") -> "KisClient":
        load_dotenv(ROOT / ".env", override=True)
        cache = SECRETS_DIR / f"kis_token_{env}.json"
        if not cache.exists():
            raise SystemExit(
                f"ERROR: no token cache at {cache}. "
                f"Run: python scripts/kis_token.py {env}"
            )
        data = json.loads(cache.read_text(encoding="utf-8"))
        prefix = "KIS_PAPER_" if env == "paper" else "KIS_LIVE_"
        app_key = os.getenv(f"{prefix}APP_KEY")
        app_secret = os.getenv(f"{prefix}APP_SECRET")
        if not app_key or not app_secret:
            raise SystemExit(f"ERROR: missing {prefix}APP_KEY / APP_SECRET in .env")
        rate = float(os.getenv("KIS_RATE_PER_SEC", "10"))
        return cls(env, data["base_url"], data["access_token"],
                   app_key, app_secret, rate_per_sec=rate)

    def get(self, path: str, params: dict, tr_id: str,
            *, max_retries: int = 5, timeout: int = 15) -> dict:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        backoff = 0.5
        last_payload = None
        for attempt in range(max_retries):
            self.limiter.wait()
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                time.sleep(backoff)
                backoff *= 2
                continue

            last_payload = payload
            rt = payload.get("rt_cd")
            msg_cd = payload.get("msg_cd", "")
            if rt == "0":
                return payload
            # Throttle / busy → retry
            if msg_cd in ("EGW00201", "EGW00121") or rt == "1":
                time.sleep(backoff)
                backoff *= 2
                continue
            # Other failure → fail fast
            return payload

        return last_payload or {"rt_cd": "?", "msg1": "no payload"}
