"""KIS 거래내역 → 양도세 NTS 신고 양식 CLI (T007, KPI Gate G1)."""

import sys

from sentinelq.reports.tax_report import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
