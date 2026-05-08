"""Pre-trade risk engine.

Implements the minimal Python ``RiskEngine`` from
``research/oss_review/architecture_patterns.md`` §3.4.

The engine is deliberately broker-agnostic: it inspects an
:class:`OrderRequest` against a :class:`PortfolioState` snapshot and
returns approve/reject. KIS-specific concerns (HTTP transport, idempotency
tokens, etc.) are layered on top in the Phase 3 broker adapter.

Pre-trade checks executed (short-circuit on first failure):

1. Order-submission cooldown (``order_submit_cooldown_sec``) — a
   defensive rate guard for KIS REST limits.
2. Per-ticker notional cap (``max_notional_per_order``).
3. Position-count cap on new BUY orders (``max_position_count``).
4. Single-position size cap (``max_single_position_pct`` of NAV).
5. Sector exposure caps (``max_sector_pct``) when a sector mapping is
   supplied with the order.
6. Gross-exposure cap on BUY orders (``max_gross_exposure_pct``).
7. Daily drawdown circuit breaker (``max_drawdown_pct``).

The :class:`RiskCheckResult` dataclass carries both the boolean
decision and a human-readable reason for audit logging.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover - 3.7 fallback only
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


@dataclass
class RiskConfig:
    """Configuration container for :class:`RiskEngine`.

    All percentage fields are expressed as fractions
    (``0.20`` = 20%).
    """

    # Per-ticker notional cap in KRW (empty mapping = no per-ticker cap).
    max_notional_per_order: Dict[str, float] = field(default_factory=dict)

    # Portfolio-level limits.
    max_position_count: int = 10
    max_gross_exposure_pct: float = 1.0       # 1.0 = fully invested
    max_single_position_pct: float = 0.20     # 20% of NAV per position
    max_drawdown_pct: float = 0.15            # circuit breaker at -15% from peak

    # Sector exposure caps (keyed by sector code). Empty mapping disables
    # the check. The order-side caller is responsible for tagging orders
    # with a sector via ``OrderRequest.sector`` for the cap to apply.
    max_sector_pct: Dict[str, float] = field(default_factory=dict)

    # KIS API rate guard (seconds between successive submit acks).
    order_submit_cooldown_sec: float = 0.5


@dataclass
class OrderRequest:
    """A trade intent produced by strategy code, evaluated by the risk engine."""

    ticker: str
    side: str            # "BUY" | "SELL"
    quantity: int
    price: float
    sector: Optional[str] = None  # optional sector tag for sector caps

    @property
    def notional(self) -> float:
        """Order notional in KRW (price * quantity, unsigned)."""
        return float(self.price) * int(self.quantity)


@dataclass
class RiskCheckResult:
    """Outcome of a :meth:`RiskEngine.check` call.

    ``approved`` is the decision; ``reason`` is empty on approval and
    carries a human-readable rejection reason otherwise. ``code`` is a
    short stable identifier suitable for metrics/labels.
    """

    approved: bool
    reason: str = ""
    code: str = ""

    # Tuple-unpacking convenience: ``approved, reason = result``.
    def __iter__(self):
        yield self.approved
        yield self.reason

    def __bool__(self) -> bool:
        return self.approved


@runtime_checkable
class PortfolioState(Protocol):
    """Read-only snapshot interface consumed by the risk engine.

    The :class:`sentinelq.portfolio.Portfolio` class implements all of
    these methods, but any duck-typed object works for unit testing.
    """

    def nav(self) -> float: ...
    def cash(self) -> float: ...
    def position_count(self) -> int: ...
    def gross_exposure(self) -> float: ...
    def peak_nav(self) -> float: ...
    def drawdown(self) -> float: ...


class RiskEngine:
    """Stateless pre-trade risk gate (with a tiny rate-limit cursor).

    A single instance can be reused across many orders. Call
    :meth:`record_submit` immediately after each successful broker
    submission so the cooldown guard advances.
    """

    def __init__(self, config: RiskConfig):
        self.cfg = config
        self._last_submit_ts: float = 0.0

    def check(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        sector_exposures: Optional[Dict[str, float]] = None,
    ) -> RiskCheckResult:
        """Evaluate ``order`` against ``portfolio`` state.

        Parameters
        ----------
        order:
            Trade intent to validate.
        portfolio:
            Read-only state snapshot (anything implementing
            :class:`PortfolioState`).
        sector_exposures:
            Optional mapping of ``sector_code -> current_exposure_KRW``
            used together with :attr:`RiskConfig.max_sector_pct` to
            enforce sector concentration limits.

        Returns
        -------
        RiskCheckResult
            ``approved=True`` with empty reason on pass; otherwise the
            first failing check's reason and a stable failure code.
        """
        nav = float(portfolio.nav())

        # 1. Rate-limit guard.
        if self._last_submit_ts > 0.0:
            elapsed = time.monotonic() - self._last_submit_ts
            if elapsed < self.cfg.order_submit_cooldown_sec:
                return RiskCheckResult(
                    False,
                    "rate limit: {:.2f}s since last order".format(elapsed),
                    code="rate_limit",
                )

        # 2. Per-ticker notional cap.
        cap = self.cfg.max_notional_per_order.get(order.ticker)
        if cap is not None and order.notional > cap:
            return RiskCheckResult(
                False,
                "{}: notional {:,.0f} > cap {:,.0f}".format(
                    order.ticker, order.notional, cap
                ),
                code="ticker_notional",
            )

        # 3. Position-count cap on new BUY into a flat portfolio slot.
        if (
            order.side == "BUY"
            and portfolio.position_count() >= self.cfg.max_position_count
        ):
            return RiskCheckResult(
                False,
                "position count {} at maximum {}".format(
                    portfolio.position_count(), self.cfg.max_position_count
                ),
                code="position_count",
            )

        # 4. Single-position size cap (relative to NAV). BUY-only.
        if (
            order.side == "BUY"
            and nav > 0
            and order.notional > nav * self.cfg.max_single_position_pct
        ):
            return RiskCheckResult(
                False,
                "single position {:.1%} exceeds limit {:.1%}".format(
                    order.notional / nav, self.cfg.max_single_position_pct
                ),
                code="position_pct",
            )

        # 5. Sector exposure cap.
        if (
            order.side == "BUY"
            and order.sector is not None
            and self.cfg.max_sector_pct
            and order.sector in self.cfg.max_sector_pct
            and nav > 0
        ):
            current = 0.0
            if sector_exposures is not None:
                current = float(sector_exposures.get(order.sector, 0.0))
            projected = current + order.notional
            cap_pct = self.cfg.max_sector_pct[order.sector]
            if projected > nav * cap_pct:
                return RiskCheckResult(
                    False,
                    "sector {} exposure {:.1%} exceeds cap {:.1%}".format(
                        order.sector, projected / nav, cap_pct
                    ),
                    code="sector_pct",
                )

        # 6. Gross exposure cap on BUY.
        if order.side == "BUY" and nav > 0:
            projected_exposure = portfolio.gross_exposure() + order.notional
            if projected_exposure > nav * self.cfg.max_gross_exposure_pct:
                return RiskCheckResult(
                    False,
                    "projected exposure {:.1%} exceeds limit {:.0%}".format(
                        projected_exposure / nav,
                        self.cfg.max_gross_exposure_pct,
                    ),
                    code="gross_exposure",
                )

        # 7. Daily drawdown circuit breaker.
        dd = float(portfolio.drawdown())
        if dd < -self.cfg.max_drawdown_pct:
            return RiskCheckResult(
                False,
                (
                    "portfolio drawdown {:.1%} exceeds circuit breaker "
                    "-{:.0%} - all new orders blocked"
                ).format(dd, self.cfg.max_drawdown_pct),
                code="drawdown",
            )

        return RiskCheckResult(True, "", code="ok")

    def record_submit(self) -> None:
        """Mark the moment a successful broker submission occurred.

        Subsequent :meth:`check` calls within
        :attr:`RiskConfig.order_submit_cooldown_sec` will be rejected
        with code ``rate_limit``.
        """
        self._last_submit_ts = time.monotonic()
