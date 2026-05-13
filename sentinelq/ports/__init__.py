"""Hexagonal ports for SentinelQ Phase 2.

These are Protocol-based interfaces (no runtime base class). Adapters in
``sentinelq/adapters/`` implement them; the paper-trade harness
(``scripts/paper_trade.py``) and future strategy code depend on these
protocols, NOT on concrete adapters.

Contract guarantees:

* All timestamps are tz-naive ``pd.Timestamp`` in KST (Asia/Seoul).
* All prices are KRW (no FX).
* All quantities are integer shares.
* Methods that touch network MUST raise ``IOError`` on transport failure
  (do not swallow). Adapters MAY add their own retry layer beneath that.

See ``research/oss_review/architecture_patterns.md`` §2 for rationale.
"""

from .broker import BrokerPort, OrderAck, OrderRequest, OrderStatus
from .clock import ClockPort
from .data import DataPort

__all__ = [
    "BrokerPort",
    "ClockPort",
    "DataPort",
    "OrderAck",
    "OrderRequest",
    "OrderStatus",
]
