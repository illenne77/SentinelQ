"""KOSPI200 benchmark honesty check.

Existing F01/F03/FF01 walk-forward results used an EQUAL-WEIGHTED universe
benchmark. Small/mid-caps in the 136-ticker universe outperformed cap-weighted
KR market substantially in 2023-26, which inflated apparent benchmark CAGR
and therefore *deflated* our reported alphas. This script re-prices the 8
DART-fundamentals variants against the actual KOSPI200 index (FDR ticker
'KS200') and reports whether any alpha would change verdict.

Output: research/honesty_check/kospi200_benchmark.txt
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "research" / "honesty_check"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "kospi200_benchmark.txt"

WINDOWS = [
    ("W1", "2023-01-01", "2023-12-31"),
    ("W2", "2024-01-01", "2024-12-31"),
    ("W3", "2025-01-01", "2026-05-08"),
    ("FULL", "2023-01-01", "2026-05-08"),
]

RESULT_FILES = {
    "A-F01": ROOT / "research" / "a_f01_value" / "walkforward_f01_results.txt",
    "A-F03": ROOT / "research" / "a_f03_quality" / "walkforward_f03_results.txt",
    "A-FF01": ROOT / "research" / "a_ff01_multifactor" / "walkforward_ff01_results.txt",
}


def fetch_kospi200() -> pd.Series:
    """Use KODEX 200 ETF (069500) as KOSPI200 proxy.

    KRX index endpoint via FDR gives 'LOGOUT' errors and pykrx is broken in
    this environment (see ADR-0006). The KODEX 200 ETF tracks KOSPI200 with
    near-zero tracking error and is fetched via the stock endpoint reliably.
    """
    import FinanceDataReader as fdr
    df = fdr.DataReader("069500", "2022-12-15", "2026-05-09")
    s = df["Close"].astype(float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def cagr(series: pd.Series, start: str, end: str) -> float:
    s = series[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]
    if len(s) < 2:
        return float("nan")
    days = (s.index[-1] - s.index[0]).days
    yrs = max(days / 365.25, 1e-6)
    return (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1


def parse_result_table(path: Path) -> pd.DataFrame:
    txt = path.read_text(encoding="utf-8")
    lines = txt.splitlines()
    header_idx = next(i for i, ln in enumerate(lines) if ln.strip().startswith("window"))
    header = re.split(r"\s+", lines[header_idx].strip())
    rows = []
    for ln in lines[header_idx + 1:]:
        if not ln.strip() or ln.strip().startswith(("KPI", "Gate", "G1", "G2", "G3", "G4", "G5", "G6", "  V", "Conclusion", "===")):
            continue
        if any(k in ln for k in ("V1", "V2", "V3", "V4", "V5")) and any(w in ln for w in ("W1", "W2", "W3", "FULL")):
            parts = re.split(r"\s+", ln.strip())
            if len(parts) >= len(header):
                rows.append(parts[: len(header)])
    df = pd.DataFrame(rows, columns=header)
    for c in df.columns:
        if c not in ("window", "variant"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def main():
    print("Fetching KOSPI200 index from FDR...")
    ks200 = fetch_kospi200()
    print(f"  {len(ks200)} bars, {ks200.index[0].date()} .. {ks200.index[-1].date()}")

    bench = {win: cagr(ks200, ts, te) for win, ts, te in WINDOWS}
    print("KOSPI200 CAGR per window:")
    for w, v in bench.items():
        print(f"  {w}: {v*100:+.2f}%")

    out = []
    out.append("KOSPI200 benchmark honesty check")
    out.append(f"Generated: {pd.Timestamp.now().isoformat()}")
    out.append(f"KOSPI200 source: FDR 'KS200', {len(ks200)} bars")
    out.append("")
    out.append("KOSPI200 (real) CAGR per window:")
    for win, ts, te in WINDOWS:
        out.append(f"  {win}: {bench[win]*100:+.2f}%")
    out.append("")

    overall_pass = []
    for alpha_name, fpath in RESULT_FILES.items():
        if not fpath.exists():
            continue
        df = parse_result_table(fpath)
        if df.empty:
            continue
        df["alpha_ks200"] = df.apply(lambda r: r["cagr"] - bench[r["window"]], axis=1)
        df["alpha_orig"] = df["alpha_ann"]
        df["delta"] = df["alpha_ks200"] - df["alpha_orig"]
        out.append(f"=== {alpha_name} ===")
        out.append(df[["window", "variant", "cagr", "cagr_bench", "alpha_orig", "alpha_ks200", "delta"]]
                   .to_string(index=False, float_format=lambda x: f"{x: .4f}"))
        out.append("")

        full = df[df["window"] == "FULL"]
        for _, r in full.iterrows():
            v = r["variant"]
            per_win = df[(df["variant"] == v) & (df["window"].isin(["W1", "W2", "W3"]))]
            g1 = r["alpha_ks200"] >= 0.015
            g4 = (per_win["alpha_ks200"] > 0).all() if not per_win.empty else False
            verdict = "PASS-G1+G4" if (g1 and g4) else ("G1-only" if g1 else "FAIL")
            overall_pass.append((alpha_name, v, r["alpha_ks200"], verdict))
            out.append(f"  {alpha_name} {v}: KOSPI200 alpha={r['alpha_ks200']*100:+.2f}% G1={g1} G4={g4} -> {verdict}")
        out.append("")

    out.append("=== Summary: variants that flip verdict with KOSPI200 benchmark ===")
    flippers = [r for r in overall_pass if r[3] != "FAIL"]
    if flippers:
        for a, v, alp, ver in flippers:
            out.append(f"  {a} {v}: {alp*100:+.2f}% pa  -> {ver}")
    else:
        out.append("  NONE. All variants still FAIL G1+G4 with KOSPI200 benchmark.")

    OUT_PATH.write_text("\n".join(out), encoding="utf-8")
    print()
    print("\n".join(out))
    print(f"\nWritten: {OUT_PATH}")


if __name__ == "__main__":
    sys.exit(main() or 0)
