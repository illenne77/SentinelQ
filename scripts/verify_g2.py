"""G2 게이트 검증 CLI 진입점 (thin shim).

실제 구현: sentinelq/reports/g2_verify.py
"""

import sys

from sentinelq.reports.g2_verify import main

if __name__ == "__main__":
    sys.exit(main())
