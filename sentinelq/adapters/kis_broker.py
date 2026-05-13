"""KIS broker adapter — paper-mode default.

Implements ``BrokerPort`` over KIS REST. The class keeps phase as an
explicit attribute and refuses to construct in 'live' mode unless the
process env var ``SENTINELQ_LIVE_ALLOW=1`` AND the caller passes
``confirm_live=True``. This double-gate prevents accidental live trades
in a paper-trade harness.

Phase 0/2 NOTE: this adapter is currently a *stub* for paper mode that
fills market orders against the next available ``DataPort.latest_close``.
A real KIS REST submission path (``order-cash`` TR ``TTTC0011U``/
``VTTC0011U``) is sketched but disabled until we have a tested alpha to
deploy. Live trading is OUT OF SCOPE for this checkpoint.
"""

from __future__ import annotations

import os

import pandas as pd

from sentinelq.portfolio.portfolio import Fill
from sentinelq.ports.broker import OrderAck, OrderRequest, OrderStatus


class KisBroker:
    """BrokerPort over KIS. Paper mode default; simulates fills via DataPort."""

    def __init__(
        self,
        data_port,
        clock_port,
        commission_bps: float = 1.5,  # round-trip half = 7.5 bps + tax 23 bps -> set per side
        tax_bps: float = 23.0,  # KR sell-side tax 0.23%
        slippage_bps: float = 5.0,
        phase: str = "paper",
        kis_client=None,
        confirm_live: bool = False,
    ):
        if phase == "live":
            if os.environ.get("SENTINELQ_LIVE_ALLOW") != "1" or not confirm_live:
                raise PermissionError(
                    "Live mode blocked: set SENTINELQ_LIVE_ALLOW=1 AND pass confirm_live=True"
                )
            if kis_client is None:
                raise ValueError("Live mode requires kis_client")
        self.phase = phase
        self._data = data_port
        self._clock = clock_port
        self._commission_bps = commission_bps
        self._tax_bps = tax_bps
        self._slippage_bps = slippage_bps
        self._kis = kis_client
        self._fills: list[Fill] = []
        self._positions: dict[str, int] = {}
        self._next_order_id = 1
        self._seen_client_ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    def submit(self, order: OrderRequest) -> OrderAck:
        if order.client_order_id and order.client_order_id in self._seen_client_ids:
            return OrderAck(
                accepted=True,
                broker_order_id=self._seen_client_ids[order.client_order_id],
                status=OrderStatus.ACCEPTED,
                reason="idempotent-replay",
            )
        if self.phase == "paper":
            return self._submit_paper(order)
        return self._submit_live(order)

    def _submit_paper(self, order: OrderRequest) -> OrderAck:
        now = self._clock.now()
        ref_px = self._data.latest_close(order.ticker, now)
        if ref_px is None or ref_px <= 0:
            return OrderAck(
                False, None, OrderStatus.REJECTED, f"no price for {order.ticker} at {now}"
            )
        if order.order_type == "LIMIT":
            limit_px = float(order.limit_price)
            if order.side == "BUY" and ref_px > limit_px:
                return OrderAck(True, self._mk_id(order), OrderStatus.PENDING, "limit not crossed")
            if order.side == "SELL" and ref_px < limit_px:
                return OrderAck(True, self._mk_id(order), OrderStatus.PENDING, "limit not crossed")
            fill_px = limit_px
        else:
            slip = ref_px * (self._slippage_bps / 10000.0)
            fill_px = ref_px + slip if order.side == "BUY" else ref_px - slip

        commission = fill_px * order.qty * (self._commission_bps / 10000.0)
        if order.side == "SELL":
            commission += fill_px * order.qty * (self._tax_bps / 10000.0)

        bid = self._mk_id(order)
        fill = Fill(
            ticker=order.ticker,
            date=now,
            side=order.side,
            quantity=order.qty,
            price=float(fill_px),
            commission=float(commission),
        )
        self._fills.append(fill)
        delta = order.qty if order.side == "BUY" else -order.qty
        self._positions[order.ticker] = self._positions.get(order.ticker, 0) + delta
        if self._positions[order.ticker] == 0:
            del self._positions[order.ticker]
        return OrderAck(True, bid, OrderStatus.FILLED)

    def _submit_live(self, order: OrderRequest) -> OrderAck:
        # Disabled by design until a graduated alpha + risk sign-off exists.
        raise NotImplementedError(
            "Live KIS order submission is not enabled. Implement TR TTTC0011U "
            "after Risk Engine §Phase isolation sign-off."
        )

    def _mk_id(self, order: OrderRequest) -> str:
        bid = f"P{self._next_order_id:08d}"
        self._next_order_id += 1
        if order.client_order_id:
            self._seen_client_ids[order.client_order_id] = bid
        return bid

    # ------------------------------------------------------------------
    def cancel(self, broker_order_id: str) -> bool:
        if self.phase == "paper":
            return False  # paper fills are immediate; no resting orders
        raise NotImplementedError("live cancel not enabled")

    def fills_since(self, ts: pd.Timestamp) -> list[Fill]:
        cutoff = pd.Timestamp(ts)
        return [f for f in self._fills if pd.Timestamp(f.date) > cutoff]

    def positions(self) -> dict[str, int]:
        return dict(self._positions)
