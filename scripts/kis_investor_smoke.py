"""KIS investor flow endpoint smoke test.

Goal: determine maximum historical depth available from
/uapi/domestic-stock/v1/quotations/inquire-investor (TR FHKST01010900).

Hypothesis: KIS returns only ~30 days. If true, A6 needs forward-collect
or alternative endpoint.

Also tries inquire-daily-trade-investor (FHKST01010900 alt? -> actually
inquire-investor returns intraday-by-day, while there is also
inquire-daily-foreign-institution / inquire-investor period variants).

We probe several candidate endpoints/params and report what data comes back.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.kis_client import KisClient


PROBES = [
    # (label, path, params, tr_id)
    (
        "inquire-investor (default, no date)",
        "/uapi/domestic-stock/v1/quotations/inquire-investor",
        {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"},
        "FHKST01010900",
    ),
    (
        "inquire-daily-trade-investor (with date range 1y)",
        "/uapi/domestic-stock/v1/quotations/inquire-daily-investor",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": "005930",
            "FID_INPUT_DATE_1": "20250101",
            "FID_INPUT_DATE_2": "20250508",
        },
        "FHKST01010900",
    ),
    (
        "investor-program-trade-today (program flow)",
        "/uapi/domestic-stock/v1/quotations/program-trade-by-stock",
        {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"},
        "FHPPG04650100",
    ),
    (
        "frgnmem-pchs-trend (foreign member trend)",
        "/uapi/domestic-stock/v1/quotations/frgnmem-pchs-trend",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": "005930",
            "FID_INPUT_ISCD_2": "0000",
        },
        "FHKST644100C0",
    ),
    (
        "investor-trend-estimate (당일 추정)",
        "/uapi/domestic-stock/v1/quotations/investor-trend-estimate",
        {"MKSC_SHRN_ISCD": "005930"},
        "HHPTJ04160200",
    ),
]


def main():
    client = KisClient.from_env(env="paper")
    print(f"base={client.base_url}")
    print(f"today={date.today()}\n")

    for label, path, params, tr_id in PROBES:
        print(f"=== {label}")
        print(f"   path={path}")
        print(f"   tr_id={tr_id} params={params}")
        try:
            payload = client.get(path, params, tr_id)
        except Exception as e:
            print(f"   EXCEPTION: {e}\n")
            continue

        rt = payload.get("rt_cd")
        msg = payload.get("msg1", "")[:80]
        print(f"   rt_cd={rt} msg={msg}")

        if rt != "0":
            print()
            continue

        # Find date-bearing list
        for key in ("output", "output1", "output2"):
            v = payload.get(key)
            if isinstance(v, list) and v:
                print(f"   {key}: {len(v)} rows")
                first = v[0]
                last = v[-1]
                # Find a date-like field
                date_keys = [k for k in first if "date" in k.lower() or "ymd" in k.lower() or k in ("stck_bsop_date",)]
                print(f"   keys (first 12): {list(first.keys())[:12]}")
                if date_keys:
                    dk = date_keys[0]
                    print(f"   date span: {first.get(dk)} .. {last.get(dk)}  via key={dk}")
                # Print first row sample
                sample = {k: first[k] for k in list(first)[:8]}
                print(f"   first row sample: {sample}")
            elif isinstance(v, dict) and v:
                print(f"   {key}: dict with keys {list(v.keys())[:10]}")
        print()


if __name__ == "__main__":
    main()
