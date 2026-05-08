"""Build sector mapping for the 136-ticker universe.

Source:
  * KOSPI top-80: inline KRX 업종 comments in universe_kospi_top80.txt
  * KOSDAQ mid-cap: hand-curated below from public knowledge

KRX raw 업종 (15 buckets) consolidated to 8 working sectors:
  IT_HW       전기·전자
  HEALTH      의약품
  AUTO_HEAVY  운수장비, 기계
  CHEM        화학
  STEEL       철강금속
  FIN         금융업, 보험
  CONS        음식료품, 유통업
  UTIL_SVC    전기가스업, 통신업, 운수창고업, 건설업
  SVC         서비스업

Output: sector_map.csv with columns ticker,sector,raw,name (raw/name optional).

Bias notes:
- KOSDAQ classifications are best-effort from public knowledge as of 2026 Q1.
- Tickers we are not confident about are tagged 'OTHER' and excluded from
  sector ranking. PREREG-0004 must declare this.
- Mapping is *static* — same as universe; sector membership changes over
  time but constituent turnover is small over 5y.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
A4 = ROOT / "research" / "a4_liquidity_surge"
OUT = ROOT / "research" / "a2_sector_rotation" / "sector_map.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

# KRX raw 업종 -> consolidated 8-sector code
RAW_TO_SECTOR = {
    "전기·전자": "IT_HW",
    "전기전자":   "IT_HW",
    "의약품":     "HEALTH",
    "운수장비":   "AUTO_HEAVY",
    "기계":       "AUTO_HEAVY",
    "화학":       "CHEM",
    "철강금속":   "STEEL",
    "금융업":     "FIN",
    "보험":       "FIN",
    "음식료품":   "CONS",
    "유통업":     "CONS",
    "전기가스업": "UTIL_SVC",
    "통신업":     "UTIL_SVC",
    "운수창고업": "UTIL_SVC",
    "건설업":     "UTIL_SVC",
    "서비스업":   "SVC",
}

# KOSDAQ hand-curated map (ticker -> raw 업종). Only confident entries.
KOSDAQ_RAW = {
    "247540": "화학",       # 에코프로비엠 (2차전지 소재)
    "086520": "화학",       # 에코프로
    "196170": "의약품",     # 알테오젠
    "145020": "의약품",     # 휴젤
    "214150": "의약품",     # 클래시스 (의료기기, bucket as 의약품 for our purposes)
    "086900": "의약품",     # 메디톡스
    "240810": "전기·전자", # 원익IPS (반도체 장비)
    "058470": "전기·전자", # 리노공업
    "357780": "화학",       # 솔브레인 (반도체 소재)
    "213420": "화학",       # 덕산네오룩스
    "095340": "전기·전자", # ISC
    "005290": "화학",       # 동진쎄미켐
    "046890": "전기·전자", # 서울반도체
    "263750": "서비스업",   # 펄어비스 (게임)
    "293490": "서비스업",   # 카카오게임즈
    "112040": "서비스업",   # 위메이드
    "095660": "서비스업",   # 네오위즈
    "192080": "서비스업",   # 더블유게임즈 (also in KOSPI list)
    "035760": "서비스업",   # CJ ENM
    "053800": "서비스업",   # 안랩
    "067310": "전기·전자", # 하나마이크론
    "039030": "기계",       # 이오테크닉스
    "067160": "서비스업",   # SOOP (구 아프리카TV)
    "035900": "서비스업",   # JYP Ent
    "122870": "서비스업",   # 와이지엔터테인먼트
    "041510": "서비스업",   # SM
    "064760": "전기·전자", # 티씨케이
    "121600": "화학",       # 나노신소재
    "137400": "기계",       # 피엔티
    "328130": "의약품",     # 루닛 (의료 AI)
    "095700": "의약품",     # 제넥신
    "036570": "서비스업",   # 엔씨소프트 (also in KOSPI; dedup later)
    "036930": "전기·전자", # 주성엔지니어링
    "036540": "의약품",     # SFA반도체? no — 036540 is SFA반도체 actually? unknown -> OTHER
    "039200": "전기·전자", # 오스코텍? unsure -> OTHER
    "178320": "전기·전자", # 서진시스템
    "036830": "전기·전자", # 솔브레인홀딩스 (지주) -- treat as 화학 actually
    "253450": "서비스업",   # 스튜디오드래곤
    "066970": "전기·전자", # 엘앤에프 — actually 2차전지 소재, 화학? -> 화학
    "032500": "전기·전자", # 케이엠더블유
    "033640": "전기·전자", # 네패스
    "064290": "전기·전자", # 인탑스
    "091700": "전기·전자", # 파트론
    "092870": "전기·전자", # 엑사이엔씨
    "089030": "전기·전자", # 테크윙
    "047310": "전기·전자", # 파워로직스
    "060280": "전기·전자", # 큐렉소? 의료기기? -> OTHER
    "178920": "화학",       # PI첨단소재
    "058820": "전기·전자", # CMG제약? -> 의약품 actually CMG제약 is 058820 -> 의약품
    "060720": "서비스업",   # KH바텍? -> 전기·전자 actually
    "277810": "기계",       # 레인보우로보틱스
    "078340": "서비스업",   # 컴투스
    "357550": "화학",       # 석경에이티
    "263770": "서비스업",   # 유엔젤 (uncertain) -> OTHER
    "007390": "의약품",     # 네이처셀
    "141080": "의약품",     # 리가켐바이오
    "083310": "전기·전자", # 엘오티베큠
    "080530": "전기·전자", # 코디
}

# Manual overrides where my initial map was wrong:
KOSDAQ_RAW["036540"] = None       # SFA반도체 — uncertain, mark OTHER
KOSDAQ_RAW["039200"] = None       # 오스코텍 — uncertain
KOSDAQ_RAW["060280"] = None       # 큐렉소 — uncertain
KOSDAQ_RAW["263770"] = None       # 유엔젤 — uncertain
KOSDAQ_RAW["058820"] = "의약품"  # CMG제약
KOSDAQ_RAW["060720"] = "전기·전자"  # KH바텍
KOSDAQ_RAW["066970"] = "화학"     # 엘앤에프 (2차전지 소재)
KOSDAQ_RAW["036830"] = "화학"     # 솔브레인홀딩스


def parse_kospi_file(p: Path) -> list[tuple[str, str, str]]:
    """Returns list of (ticker, raw_sector, name)."""
    out = []
    pat = re.compile(r"^(\d{6})\s*#\s*([^\s—-]+)\s*[—-]\s*(.+)$")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = pat.match(line)
        if not m:
            # Has a ticker but no sector annotation
            tm = re.match(r"^(\d{6})", line)
            if tm:
                out.append((tm.group(1), "", ""))
            continue
        ticker, name, raw = m.groups()
        out.append((ticker, raw.strip(), name.strip()))
    return out


def parse_kosdaq_file(p: Path) -> list[tuple[str, str, str]]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip().split("#", 1)[0].strip()
        if not line:
            continue
        if line.isdigit() and len(line) == 6:
            raw = KOSDAQ_RAW.get(line)
            out.append((line, raw or "", ""))
    return out


def main():
    kospi = parse_kospi_file(A4 / "universe_kospi_top80.txt")
    kosdaq = parse_kosdaq_file(A4 / "universe_kosdaq_midcap.txt")

    seen = set()
    rows = []
    for ticker, raw, name in kospi + kosdaq:
        if ticker in seen:
            continue
        seen.add(ticker)
        sector = RAW_TO_SECTOR.get(raw, "OTHER") if raw else "OTHER"
        rows.append((ticker, sector, raw, name))

    rows.sort(key=lambda r: (r[1], r[0]))

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "sector", "raw_krx", "name"])
        for r in rows:
            w.writerow(r)

    # Summary
    from collections import Counter
    cnt = Counter(r[1] for r in rows)
    print(f"wrote {OUT}")
    print(f"total tickers: {len(rows)}")
    for s in sorted(cnt, key=lambda k: (-cnt[k], k)):
        print(f"  {s:12s}: {cnt[s]}")


if __name__ == "__main__":
    main()
