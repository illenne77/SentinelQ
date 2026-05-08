"""KIS chart smoke test — fetch 6 months of Samsung daily bars."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.kis_client import KisClient
from api.kis_chart import fetch_daily

env = sys.argv[1] if len(sys.argv) > 1 else "paper"
ticker = sys.argv[2] if len(sys.argv) > 2 else "005930"
start = sys.argv[3] if len(sys.argv) > 3 else "20251101"
end = sys.argv[4] if len(sys.argv) > 4 else "20260508"

client = KisClient.from_env(env=env)
print(f"[smoke] env={env} ticker={ticker} {start}..{end}")
df = fetch_daily(client, ticker, start, end, use_cache=False, verbose=True)
print(f"[smoke] returned {len(df)} bars")
if not df.empty:
    print(df.head(3))
    print("...")
    print(df.tail(3))
