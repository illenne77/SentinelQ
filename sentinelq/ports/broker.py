"""BrokerPort — abstraction for order submission and fill polling.

Adapters MUST default to phase='paper'. Live adapters require
explicit opt-in (see ``sentinelq/adapters/kis_broker.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import pandas as pd

from sentinelq.portfolio.portfolio import Fill


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class OrderRequest:
    ticker: str
    side: str  # "BUY" | "SELL"
    qty: int
    order_type: str = "MARKET"  # "MARKET" | "LIMIT"
    limit_price: float | None = None
    client_order_id: str | None = None  # idempotency key

    def __post_init__(self):
        if self.side not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY/SELL, got {self.side!r}")
        if self.qty <= 0:
            raise ValueError(f"qty must be positive, got {self.qty}")
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")
        if self.order_type not in ("MARKET", "LIMIT"):
            raise ValueError(f"order_type must be MARKET/LIMIT, got {self.order_type!r}")


@dataclass(frozen=True)
class OrderAck:
    accepted: bool
    broker_order_id: str | None
    status: OrderStatus
    reason: str | None = None


class BrokerPort(Protocol):
    phase: str  # "paper" | "live"

    def submit(self, order: OrderRequest) -> OrderAck:
        """Submit order. Idempotent on client_order_id."""
        ...

    def cancel(self, broker_order_id: str) -> bool:
        """Best-effort cancel."""
        ...

    def fills_since(self, ts: pd.Timestamp) -> list[Fill]:
        """Chronological fills with ts > ``ts``. Empty if none."""
        ...

    def positions(self) -> dict[str, int]:
        """Authoritative broker positions (ticker -> qty)."""
        ...
