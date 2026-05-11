"""Adapter package — concrete implementations of ``sentinelq.ports`` + Phase 3 tools.

Naming convention: ``<source>_<port>.py``

Phase 0~2 (alpha trading, archived mandate):
- ``kis_broker.py`` — BrokerPort over KIS REST
- ``kis_data.py``   — DataPort over KIS daily cache + live REST
- ``clock.py``      — ClockPort

Phase 3 (KR Investor Tools, ADR-0013 / PREREG-0008 mandate):
- ``kis_history.py`` — KIS 거래내역·기간손익 조회 (T001)
"""

from sentinelq.adapters.kis_history import (
    KisApiError,
    ProfitRecord,
    Transaction,
    inquire_domestic_daily_trans,
    inquire_overseas_period_trans,
    inquire_period_profit,
)

__all__ = [
    "KisApiError",
    "ProfitRecord",
    "Transaction",
    "inquire_domestic_daily_trans",
    "inquire_overseas_period_trans",
    "inquire_period_profit",
]
