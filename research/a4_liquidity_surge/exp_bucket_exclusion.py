"""Quick bucket-exclusion experiment (read-only on cached triggers)."""
import sys
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from costs import DEFAULT  # noqa: E402

df = pd.read_parquet(Path(__file__).parent / "_cache" / "backtest_20250101_20260508_t1.5_h5.parquet")
df = df.dropna(subset=["ret_fwd"])
df = df[df["gate_pass"]]
df["net"] = df["ret_fwd"].apply(DEFAULT.net_return)

experiments = [
    ("keep 1.5-2.0 only",      (df["surge_ratio"] >= 1.5) & (df["surge_ratio"] < 2.0)),
    ("keep 1.5-2.0 + 3.0-5.0", ((df["surge_ratio"] >= 1.5) & (df["surge_ratio"] < 2.0)) |
                               ((df["surge_ratio"] >= 3.0) & (df["surge_ratio"] < 5.0))),
    ("keep 3.0-5.0 only",      (df["surge_ratio"] >= 3.0) & (df["surge_ratio"] < 5.0)),
    ("drop 2.0-3.0 only",      ~((df["surge_ratio"] >= 2.0) & (df["surge_ratio"] < 3.0))),
    ("drop 5.0+ only",          df["surge_ratio"] < 5.0),
    ("baseline (no exclude)",   pd.Series(True, index=df.index)),
]

hdr = f'{"label":<28} {"n":>5} {"mean":>8} {"hit":>7}'
print(hdr)
print("-" * len(hdr))
for label, mask in experiments:
    s = df[mask]
    if len(s):
        kpi_m = "M" if s["net"].mean() >= 0.012 else "."
        kpi_h = "H" if (s["net"] > 0).mean() >= 0.58 else "."
        print(f'{label:<28} {len(s):>5} {s["net"].mean():>+8.4f} {(s["net"]>0).mean():>7.4f}  {kpi_m}{kpi_h}')
