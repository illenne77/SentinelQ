# OSS Algo-Trading Framework Architecture Patterns
**Target:** SentinelQ — KR Equity (KOSPI/KOSDAQ), KIS broker, Python, single-operator shop  
**Reviewed:** nautechsystems/nautilus_trader · edtechre/pybroker · QuantConnect/Lean  
**Date:** 2025-06  
**Sources:** GitHub API, direct file reads (no local clones)

---

## 1. Executive Summary

### nautechsystems/nautilus_trader
An institutional-grade, event-driven engine written in Rust (core) + Cython (Python bindings). Every order flows through a `RiskEngine → ExecutionEngine → Venue adapter` pipeline, with a `Portfolio` object maintaining authoritative real-time NAV, per-instrument realized/unrealized PnL, and margin state. The risk engine (`nautilus_trader/risk/engine.pyx`, ~50KB) enforces rate limits, per-instrument notional caps, and position limits before any order reaches the broker. The portfolio (`nautilus_trader/portfolio/portfolio.pyx`, ~115KB) is driven by fill events and quote-tick updates. **Steal:** the `RiskEngineConfig` schema (rate limits, `max_notional_per_order` dict), the `PortfolioFacade` read-only interface (7 query methods: `realized_pnl`, `unrealized_pnl`, `net_exposure`, `equity`, etc.), and the Clock+ExecutionClient swap pattern for backtest↔live unification. **Ignore:** Cython/Rust compilation (Windows build pain), the full actor-message-bus system, multi-venue/multi-currency support, L2/L3 order book machinery — all massively overengineered for a daily-frequency KIS REST shop.

### edtechre/pybroker
A Python-native ML-focused backtest framework with first-class walk-forward support, parquet-based indicator caching, and bootstrap-based confidence intervals on KPIs. The `Strategy.walkforward()` method is its crown jewel: it handles train/test window sequencing, per-window model fitting, OOS metric aggregation, and `bootstrap_sample_size` for significance testing. The `EvalMetrics` dataclass in `eval.py` provides ~20 KPIs (Sharpe, Sortino, Calmar, profit factor, win rate, IQR of returns). **Steal:** the `WalkforwardMixin` window-sequencing pattern, the `EvalMetrics` dataclass, and the `BarData` typed context object passed to each bar callback. **Ignore:** its `DataSource` adapters (Yahoo/Alpaca-centric), its Numba-accelerated `vect.py` (overkill for daily bars), and its live-trading stubs (essentially absent — pure backtest tool).

### QuantConnect/Lean
The canonical institutional framework with a mature 5-layer `QCAlgorithmFramework`: Universe Selection → Alpha → Portfolio Construction → Risk Management → Execution. Each layer is a stateless object with a single well-defined method (`update`, `determine_target_percent`, `manage_risk`, `execute`), passing a typed data contract (`Insight` → `PortfolioTarget`) between stages. Lean unifies backtest and live by swapping `SimulatedBrokerageModel` vs live broker model behind the same `QCAlgorithm` API. **Steal:** the 4-layer decomposition as an architectural contract, the `Insight(symbol, direction, period)` data structure between Alpha and Portfolio layers, and the `RiskManagementModel.manage_risk(algorithm, targets) → List[PortfolioTarget]` interface. **Ignore:** the entire C# runtime, QuantConnect cloud dependency, `AlgorithmImports` monolith, and 400+ brokerage connectors — none applicable to a Python/KIS shop.

---

## 2. The 4-Layer Algo Trading Pattern (Lean Canonical)

### 2.1 Layer Architecture

```
Data Feed
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  L1: ALPHA MODEL                                    │
│  Input:  new bar data + algorithm state             │
│  Output: List[Insight]                              │
│  Method: update(algorithm, data) → List[Insight]    │
└──────────────────────┬──────────────────────────────┘
                       │ Insight(symbol, direction, period, magnitude, confidence)
                       ▼
┌─────────────────────────────────────────────────────┐
│  L2: PORTFOLIO CONSTRUCTION MODEL (PCM)             │
│  Input:  active Insights                            │
│  Output: Dict[symbol, target_weight]                │
│  Method: determine_target_percent(insights)         │
└──────────────────────┬──────────────────────────────┘
                       │ PortfolioTarget(symbol, percent)
                       ▼
┌─────────────────────────────────────────────────────┐
│  L3: RISK MANAGEMENT MODEL                          │
│  Input:  portfolio targets + portfolio state        │
│  Output: risk-adjusted List[PortfolioTarget]        │
│  Method: manage_risk(algorithm, targets)            │
└──────────────────────┬──────────────────────────────┘
                       │ adjusted targets (may add zero-targets to force liquidation)
                       ▼
┌─────────────────────────────────────────────────────┐
│  L4: EXECUTION MODEL                                │
│  Input:  targets + order book / price state         │
│  Output: actual broker orders                       │
│  Method: execute(algorithm, targets)                │
└─────────────────────────────────────────────────────┘
```

### 2.2 Python Interface Signatures (from Lean source)

**Alpha Model** — `QuantConnect/Lean:Algorithm.Framework/Alphas/EmaCrossAlphaModel.py`
```python
class AlphaModel:
    def update(self, algorithm, data) -> List[Insight]:
        """Called each bar. Return Insight objects."""
        insights = []
        for symbol, symbol_data in self.symbol_data_by_symbol.items():
            if symbol_data.fast.is_ready and symbol_data.slow.is_ready:
                if symbol_data.fast > symbol_data.slow:
                    insights.append(
                        Insight.price(symbol, self.prediction_interval, InsightDirection.UP)
                    )
        return insights

    def on_securities_changed(self, algorithm, changes):
        """Called when universe membership changes — wire up new indicators."""
        for added in changes.added_securities:
            ...
        for removed in changes.removed_securities:
            ...

# Insight factory:
insight = Insight.price(
    symbol,
    prediction_interval,   # timedelta — how long the signal is valid
    InsightDirection.UP,   # UP / DOWN / FLAT
    magnitude=None,        # optional float: expected return magnitude
    confidence=None,       # optional float [0,1]
)
```

**Portfolio Construction Model** — `QuantConnect/Lean:Algorithm.Framework/Portfolio/EqualWeightingPortfolioConstructionModel.py`
```python
class EqualWeightingPortfolioConstructionModel(PortfolioConstructionModel):
    def __init__(self, rebalance=Resolution.DAILY,
                 portfolio_bias=PortfolioBias.LONG_SHORT):
        super().__init__()
        if isinstance(rebalance, Resolution):
            rebalance = Extensions.to_time_span(rebalance)
        if isinstance(rebalance, timedelta):
            self.set_rebalancing_func(lambda dt: dt + rebalance)

    def determine_target_percent(self, active_insights) -> Dict[Insight, float]:
        """Map each insight to a target portfolio weight (-1 to +1)."""
        count = sum(1 for x in active_insights
                    if x.direction != InsightDirection.FLAT
                    and self.respect_portfolio_bias(x))
        percent = 0 if count == 0 else 1.0 / count
        return {
            insight: (insight.direction if self.respect_portfolio_bias(insight)
                      else InsightDirection.FLAT) * percent
            for insight in active_insights
        }
```

**Risk Management Model (Portfolio-level CB)** — `QuantConnect/Lean:Algorithm.Framework/Risk/MaximumDrawdownPercentPortfolio.py`
```python
class MaximumDrawdownPercentPortfolio(RiskManagementModel):
    def __init__(self, maximum_drawdown_percent=0.05, is_trailing=False):
        self.maximum_drawdown_percent = -abs(maximum_drawdown_percent)
        self.is_trailing = is_trailing
        self.initialised = False
        self.portfolio_high = 0

    def manage_risk(self, algorithm, targets) -> List[PortfolioTarget]:
        current_value = algorithm.portfolio.total_portfolio_value
        if not self.initialised:
            self.portfolio_high = current_value
            self.initialised = True
        if self.is_trailing and self.portfolio_high < current_value:
            self.portfolio_high = current_value
            return []
        pnl = (float(current_value) / float(self.portfolio_high)) - 1.0
        if pnl < self.maximum_drawdown_percent and targets:
            self.initialised = False    # reset after circuit break
            risk_adjusted = []
            for target in targets:
                algorithm.insights.cancel([target.symbol])
                risk_adjusted.append(PortfolioTarget(target.symbol, 0))  # liquidate
            return risk_adjusted
        return []
```

**Risk Management Model (Per-security stop)** — `QuantConnect/Lean:Algorithm.Framework/Risk/MaximumDrawdownPercentPerSecurity.py`
```python
class MaximumDrawdownPercentPerSecurity(RiskManagementModel):
    def __init__(self, maximum_drawdown_percent=0.05):
        self.maximum_drawdown_percent = -abs(maximum_drawdown_percent)

    def manage_risk(self, algorithm, targets):
        targets = []
        for kvp in algorithm.securities:
            security = kvp.value
            if not security.invested:
                continue
            pnl = security.holdings.unrealized_profit_percent
            if pnl < self.maximum_drawdown_percent:
                algorithm.insights.cancel([security.symbol])
                targets.append(PortfolioTarget(security.symbol, 0))
        return targets
```

**Execution Model** — `QuantConnect/Lean:Algorithm.Framework/Execution/SpreadExecutionModel.py`
```python
class SpreadExecutionModel(ExecutionModel):
    def __init__(self, accepting_spread_percent=0.005):
        self.accepting_spread_percent = abs(accepting_spread_percent)
        self.targets_collection = PortfolioTargetCollection()

    def execute(self, algorithm, targets):
        self.targets_collection.add_range(targets)
        if not self.targets_collection.is_empty:
            for target in self.targets_collection.order_by_margin_impact(algorithm):
                unordered_quantity = OrderSizing.get_unordered_quantity(algorithm, target)
                if unordered_quantity != 0:
                    security = algorithm.securities[target.symbol]
                    if self.spread_is_favorable(security):
                        algorithm.market_order(target.symbol, unordered_quantity)
            self.targets_collection.clear_fulfilled(algorithm)

    def spread_is_favorable(self, security):
        return (security.exchange.exchange_open
                and security.price > 0 and security.ask_price > 0
                and (security.ask_price - security.bid_price) / security.price
                    <= self.accepting_spread_percent)
```

### 2.3 Adopt vs. Adapt for SentinelQ

| Layer | Lean Interface | Our Context | Recommendation |
|---|---|---|---|
| Alpha | `AlphaModel.update(bars, date) → List[Insight]` | Inline in `run_backtest` | **BORROW verbatim** — wrap signal code in `update()` |
| PCM | `determine_target_percent(insights) → Dict[symbol, float]` | Ad-hoc `slot_notional = nav/slots` | **BORROW simplified** — accept `{ticker: direction}`, return `{ticker: weight}` |
| Risk | `manage_risk(portfolio_state, targets) → targets` | Inline stop/TP/drawdown in day loop | **BORROW_INTERFACE** — decouple as `RiskModel.check(portfolio, targets)` |
| Execution | `execute(targets) → orders` | Direct KIS API calls | **BORROW_INTERFACE** — `BrokerPort.buy/sell()` protocol |

**KIS-specific simplifications:**
- Drop `InsightDirection.DOWN` / short — KR retail shorting is restricted
- Drop `magnitude` and `confidence` until you have models that produce them
- `PortfolioTarget` for us = `(ticker: str, target_weight: float)` where weight ∈ [0, 1]
- No `order_by_margin_impact` needed — KIS has no margin for retail equities

---

## 3. Risk Engine Patterns (nautilus_trader Focus)

### 3.1 RiskEngineConfig Schema
Source: `nautechsystems/nautilus_trader:nautilus_trader/risk/config.py`

```python
class RiskEngineConfig(NautilusConfig, frozen=True):
    bypass: bool = False

    # Rate throttles: "N/HH:MM:SS" token-bucket syntax
    # "100/00:00:01" = max 100 submit commands per 1 second
    max_order_submit_rate: str = "100/00:00:01"
    max_order_modify_rate: str = "100/00:00:01"

    # Per-instrument notional caps (pre-trade hard limit)
    # {"005930.KRX": 5_000_000}  →  max 5M KRW per single order on Samsung
    max_notional_per_order: dict[str, int] = {}

    debug: bool = False
```

### 3.2 Risk Engine Pre-Trade Check Pipeline
Source: `nautechsystems/nautilus_trader:nautilus_trader/risk/engine.pyx` (key pattern, ~50KB Cython)

Every `SubmitOrder` command passes through this pipeline before reaching the broker adapter:

```
SubmitOrder command received
    │
    ├── 1. Duplicate order ID check       (always, even in bypass=True)
    ├── 2. Order rate-limit check         (token bucket, max_order_submit_rate)
    ├── 3. Notional cap check             (qty × last_price ≤ max_notional_per_order[id])
    ├── 4. Net position limit check       (sum of open orders + fills)
    └── 5. Venue-level gross exposure     (total notional across all instruments)
         │
    PASS → forward to ExecutionEngine → Venue adapter
    FAIL → emit OrderDenied event (logged, never reaches broker)
```

The crucial design: **the risk engine is a separate object that receives commands via message bus, not a function call**. This means risk checks happen asynchronously between strategy signal and broker API call — there's always a "firewall."

### 3.3 Position Sizer
Source: `nautechsystems/nautilus_trader:nautilus_trader/risk/sizing.pyx`

```python
class FixedRiskSizer:
    """Size position by fixed % risk of equity per trade."""
    
    def calculate(
        self,
        instrument,       # holds tick_size, lot_size, etc.
        equity: Money,    # total portfolio equity
        risk_percent: float,  # e.g. 0.01 = risk 1% of equity
        price: Price,     # entry price
        stop_loss: Price, # stop price
        exchange_rate: float = 1.0
    ) -> Quantity:
        risk_points = abs(float(price) - float(stop_loss))
        if risk_points == 0:
            return instrument.make_qty(0)
        risk_amount = float(equity) * risk_percent / exchange_rate
        quantity = risk_amount / risk_points
        return instrument.make_qty(quantity)  # rounds to lot size
```

### 3.4 Minimal Python RiskEngine for KIS

```python
# sentinelq/risk/engine.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol
import time


@dataclass
class RiskConfig:
    # Per-ticker notional cap in KRW (empty = no cap)
    max_notional_per_order: dict[str, float] = field(default_factory=dict)
    # Portfolio-level limits
    max_position_count: int = 10
    max_gross_exposure_pct: float = 1.0      # 1.0 = fully invested
    max_single_position_pct: float = 0.20    # 20% of NAV per position
    max_drawdown_pct: float = 0.15           # circuit breaker at -15% from peak
    # KIS API rate guard
    order_submit_cooldown_sec: float = 0.5


@dataclass
class OrderRequest:
    ticker: str
    side: str           # "BUY" | "SELL"
    quantity: int
    price: float

    @property
    def notional(self) -> float:
        return self.price * self.quantity


class PortfolioState(Protocol):
    """Read-only snapshot passed to risk checks."""
    def nav(self) -> float: ...
    def cash(self) -> float: ...
    def position_count(self) -> int: ...
    def gross_exposure(self) -> float: ...
    def peak_nav(self) -> float: ...
    def drawdown(self) -> float: ...          # negative number, e.g. -0.05


class RiskEngine:
    def __init__(self, config: RiskConfig):
        self.cfg = config
        self._last_submit_ts: float = 0.0

    def check(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
    ) -> tuple[bool, str]:
        """
        Returns (approved: bool, reason: str).
        All checks must pass for order to be submitted.
        """
        nav = portfolio.nav()

        # 0. Rate limit guard (KIS allows ~2 req/sec on order endpoint)
        elapsed = time.monotonic() - self._last_submit_ts
        if elapsed < self.cfg.order_submit_cooldown_sec:
            return False, f"rate limit: {elapsed:.2f}s since last order"

        # 1. Per-ticker notional cap
        cap = self.cfg.max_notional_per_order.get(order.ticker)
        if cap and order.notional > cap:
            return False, f"{order.ticker}: notional {order.notional:,.0f} > cap {cap:,.0f}"

        # 2. Position count cap (only on new BUY into flat position)
        if order.side == "BUY" and portfolio.position_count() >= self.cfg.max_position_count:
            return False, f"position count {portfolio.position_count()} at maximum {self.cfg.max_position_count}"

        # 3. Single-position size cap
        if order.notional > nav * self.cfg.max_single_position_pct:
            return False, (
                f"single position {order.notional/nav:.1%} exceeds "
                f"limit {self.cfg.max_single_position_pct:.1%}"
            )

        # 4. Gross exposure cap
        if order.side == "BUY":
            projected_exposure = portfolio.gross_exposure() + order.notional
            if projected_exposure > nav * self.cfg.max_gross_exposure_pct:
                return False, (
                    f"projected exposure {projected_exposure/nav:.1%} exceeds "
                    f"limit {self.cfg.max_gross_exposure_pct:.0%}"
                )

        # 5. Portfolio drawdown circuit breaker
        dd = portfolio.drawdown()
        if dd < -self.cfg.max_drawdown_pct:
            return False, (
                f"portfolio drawdown {dd:.1%} exceeds circuit breaker "
                f"-{self.cfg.max_drawdown_pct:.0%} — all new orders blocked"
            )

        return True, ""

    def record_submit(self) -> None:
        """Call this immediately after a successful order submission."""
        self._last_submit_ts = time.monotonic()
```

**Key principle from nautilus:** the risk engine is **always separate from strategy logic**. Strategy code produces `OrderRequest`; risk engine approves or rejects; execution adapter calls KIS. This separation means you can unit-test the risk engine without a broker connection, and you can tighten/loosen limits without touching alpha code.

---

## 4. Portfolio NAV Bookkeeping (nautilus_trader Portfolio)

### 4.1 nautilus_trader PortfolioFacade Interface
Source: `nautechsystems/nautilus_trader:nautilus_trader/portfolio/base.pyx`

```python
class PortfolioFacade:
    """Read-only interface to the Portfolio (strategy code uses this view)."""

    # ── per-instrument queries ────────────────────────────────────────
    def realized_pnl(self, instrument_id, target_currency=None) -> Money: ...
    def unrealized_pnl(self, instrument_id, price=None, target_currency=None) -> Money: ...
    def total_pnl(self, instrument_id, price=None, target_currency=None) -> Money: ...
    def net_exposure(self, instrument_id, price=None, target_currency=None) -> Money: ...
    def net_position(self, instrument_id) -> Decimal: ...   # shares held (signed)

    # ── portfolio-wide queries ────────────────────────────────────────
    def realized_pnls(self, target_currency=None) -> dict: ...   # by instrument
    def unrealized_pnls(self, target_currency=None) -> dict: ...
    def net_exposures(self, target_currency=None) -> dict: ...
    def mark_values(self) -> dict: ...    # current market value per instrument
    def equity(self) -> dict: ...         # cash_balance + sum(unrealized_pnl)
    def balances_locked(self) -> dict: ... # reserved margin (zero for KR retail)

    # ── boolean state ─────────────────────────────────────────────────
    def is_net_long(self, instrument_id) -> bool: ...
    def is_flat(self, instrument_id) -> bool: ...
    def is_completely_flat(self) -> bool: ...
    def missing_price_instruments(self, venue) -> list: ...
```

**Key design choices in nautilus:**
- No scalar "NAV" property — it's computed as `equity = cash + unrealized_pnl_sum`
- Realized vs. unrealized are **strictly separate**: realized accumulates on `OrderFilled` events; unrealized is recomputed from last tick price on demand
- FX handled via `target_currency` + `ExchangeRateCalculator` → **for KRW-only KIS: ignore entirely**
- Dividends: not in Portfolio — treated as account cash adjustments from broker reconciliation feed
- Mark-to-market: driven by streaming `QuoteTick` events; portfolio subscribes to price feed

### 4.2 Critique of Current A2 Implementation

Source: `research/a2_sector_rotation/exp_walkforward_a2.py:360–476`

**Current approach:**
```python
cash = 1.0
open_positions: list[Position] = []

# NAV recomputed as scalar every bar (lines 462-472):
mtm = sum(p.notional * (bar[3] / p.entry_price) for p in open_positions)
nav = cash + mtm * (1 - ROUND_TRIP_COST / 2)  # heuristic half-cost

# Cash updated on close (lines 402-404):
gross = pos.notional * (exit_at / pos.entry_price)
cash += gross * (1 - ROUND_TRIP_COST)
```

**Problems:**
1. `nav` is a local float — no `peak_nav` tracking → can't compute portfolio drawdown during the run
2. No separation of realized vs. unrealized — `cash` absorbs closes but daily MTM is folded into `nav` without logging per-position unrealized PnL
3. Transaction cost split heuristically (half at open, half at close) — less accurate than applying per-side commission
4. Position `notional` is **initial investment** frozen at entry — `mtm = notional × (close/entry)` is a ratio calculation, not actual share-count × price
5. No `Portfolio` object — risk checks (stop/TP) are inline in the day loop, untestable in isolation
6. No `Fill` events — position state is mutated directly, making it impossible to replay fills for reconciliation

### 4.3 Recommended Clean Portfolio Interface

```python
# sentinelq/portfolio/portfolio.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class Fill:
    """Atomic fill event — single source of truth for position changes."""
    ticker: str
    date: pd.Timestamp
    side: str           # "BUY" | "SELL"
    quantity: int       # shares
    price: float        # fill price in KRW
    commission: float   # KRW commission amount


@dataclass
class PositionState:
    ticker: str
    quantity: int           # shares held
    avg_cost: float         # volume-weighted average cost per share
    realized_pnl: float = 0.0

    def unrealized_pnl(self, current_price: float) -> float:
        return self.quantity * (current_price - self.avg_cost)

    def market_value(self, current_price: float) -> float:
        return self.quantity * current_price


class Portfolio:
    """
    Single-currency (KRW) portfolio bookkeeper.
    
    Usage pattern:
        portfolio = Portfolio(initial_cash=10_000_000)
        
        # On each fill (from paper broker or KIS webhook):
        portfolio.on_fill(Fill(ticker, date, side, qty, price, commission))
        
        # End of each day:
        nav = portfolio.mark(date, {ticker: close_price, ...})
    """

    def __init__(self, initial_cash: float):
        self._cash: float = initial_cash
        self._positions: dict[str, PositionState] = {}
        self._peak_nav: float = initial_cash
        self._nav_series: list[tuple[pd.Timestamp, float]] = []
        self._total_commission: float = 0.0
        self._last_prices: dict[str, float] = {}

    # ── event handlers ───────────────────────────────────────────────

    def on_fill(self, fill: Fill) -> None:
        """Apply a fill to cash and position state. Call this for every trade."""
        self._total_commission += fill.commission
        pos = self._positions.get(fill.ticker)

        if fill.side == "BUY":
            cost = fill.quantity * fill.price + fill.commission
            self._cash -= cost
            if pos is None:
                self._positions[fill.ticker] = PositionState(
                    ticker=fill.ticker,
                    quantity=fill.quantity,
                    avg_cost=fill.price,
                )
            else:
                # volume-weighted average cost
                total_qty = pos.quantity + fill.quantity
                pos.avg_cost = (
                    pos.quantity * pos.avg_cost + fill.quantity * fill.price
                ) / total_qty
                pos.quantity = total_qty

        elif fill.side == "SELL":
            proceeds = fill.quantity * fill.price - fill.commission
            self._cash += proceeds
            if pos is not None:
                realized = (fill.quantity * (fill.price - pos.avg_cost)
                            - fill.commission)
                pos.realized_pnl += realized
                pos.quantity -= fill.quantity
                if pos.quantity <= 0:
                    del self._positions[fill.ticker]

    def mark(self, date: pd.Timestamp, prices: dict[str, float]) -> float:
        """
        End-of-day mark-to-market.
        Updates peak NAV and appends to NAV series.
        Returns current NAV.
        """
        self._last_prices.update(prices)
        nav = self.nav()
        self._peak_nav = max(self._peak_nav, nav)
        self._nav_series.append((date, nav))
        return nav

    # ── queries ──────────────────────────────────────────────────────

    def nav(self) -> float:
        """Total portfolio value = cash + market value of all positions."""
        return self._cash + self.gross_exposure()

    def cash(self) -> float:
        return self._cash

    def gross_exposure(self) -> float:
        """Total market value of open positions at last known prices."""
        return sum(
            pos.market_value(self._last_prices.get(t, pos.avg_cost))
            for t, pos in self._positions.items()
        )

    def unrealized_pnl(self, ticker: Optional[str] = None) -> float:
        if ticker:
            pos = self._positions.get(ticker)
            if pos is None:
                return 0.0
            price = self._last_prices.get(ticker, pos.avg_cost)
            return pos.unrealized_pnl(price)
        return sum(
            pos.unrealized_pnl(self._last_prices.get(t, pos.avg_cost))
            for t, pos in self._positions.items()
        )

    def realized_pnl(self, ticker: Optional[str] = None) -> float:
        if ticker:
            pos = self._positions.get(ticker)
            return pos.realized_pnl if pos else 0.0
        return sum(p.realized_pnl for p in self._positions.values())

    def peak_nav(self) -> float:
        return self._peak_nav

    def drawdown(self) -> float:
        """Current drawdown from peak NAV (negative number, e.g. -0.05 = -5%)."""
        if self._peak_nav == 0:
            return 0.0
        return (self.nav() / self._peak_nav) - 1.0

    def position_count(self) -> int:
        return len(self._positions)

    def positions(self) -> dict[str, PositionState]:
        return dict(self._positions)

    def nav_series(self) -> pd.Series:
        return pd.Series(
            {d: v for d, v in self._nav_series},
            dtype=float
        ).sort_index()
```

**Compared to A2:**

| Aspect | A2 `_run_v2` | New `Portfolio` |
|---|---|---|
| NAV storage | local float, lost after run | persistent `_nav_series` list |
| Peak NAV | not tracked | `_peak_nav` updated on `mark()` |
| Realized PnL | merged into `cash` | per-position `realized_pnl` |
| Unrealized PnL | ratio calc, not query | `unrealized_pnl(ticker)` query |
| Cost model | heuristic half at entry/half at exit | full commission per side in `Fill` |
| Risk checks | inline in day loop | via `Portfolio.drawdown()` → `RiskEngine.check()` |
| Testability | none (requires full bars run) | `on_fill()` is unit-testable |

---

## 5. Walk-Forward Harness (pybroker Focus)

### 5.1 How pybroker Structures Walk-Forward
Source: `edtechre/pybroker:src/pybroker/strategy.py`

```python
class Strategy:
    def walkforward(
        self,
        windows: int,                  # number of train+test folds
        train_size: float = 0.5,       # fraction of each window for training
        shuffle: bool = False,         # shuffle train bars (useful for ML)
        warmup: Optional[int] = None,  # warm-up bars before test period
        calc_bootstrap: bool = True,
        bootstrap_sample_size: int = 100,   # size of each bootstrap resample
        bootstrap_samples: int = 10_000,    # number of bootstrap iterations
        train_only: bool = False,      # if True, skip test evaluation
    ) -> TestResult:
        """
        Internally:
        1. Split [start_date, end_date] into `windows` equal chunks
        2. Per chunk: first train_size fraction = train, remainder = test
        3. For each window: call model.fit(train_data) → fitted model stored in StaticScope
        4. Run vectorized bar callback on test period using fitted model
        5. Concatenate all test-period results into one TestResult
        6. If calc_bootstrap: resample returns → CI on Sharpe, Calmar, profit_factor
        """
```

**KPI output** (`EvalMetrics` from `edtechre/pybroker:src/pybroker/eval.py`):
```python
@dataclass
class EvalMetrics:
    trade_count: int
    win_rate: Decimal              # fraction of winning trades
    initial_market_val: Decimal
    end_market_val: Decimal
    total_pnl: Decimal
    unrealized_pnl: Decimal
    total_return_pct: Decimal
    annual_return_pct: Decimal
    sharpe: Decimal
    sortino: Decimal
    profit_factor: Decimal        # gross_profit / gross_loss
    calmar: Decimal               # annual_return / max_drawdown
    max_drawdown: Decimal         # absolute
    max_drawdown_pct: Decimal
    max_drawdown_start: datetime
    max_drawdown_end: datetime
    ulcer_index: Decimal          # RMS of drawdown depths
    upi: Decimal                  # Ulcer Performance Index (Sharpe using ulcer_index)
    equity_r2: Decimal            # R² of equity curve (linearity)
    std_error: Decimal
```

**Model integration protocol:**
```python
# pybroker model registration pattern
def train_fn(symbol, train_data, target_data, *args) -> any_model:
    """Fit and return a model object."""
    model = MyMLModel()
    model.fit(train_data[["rsi", "macd"]], target_data["forward_return"])
    return model

my_model = pybroker.model(
    name='my_model',
    model_fn=train_fn,
    indicators=[rsi_indicator, macd_indicator],  # pre-computed indicators
)

strategy = pybroker.Strategy(data_source, start, end)
strategy.add_execution(exec_fn, symbols=['005930', '000660'], models=[my_model])
result = strategy.walkforward(windows=3, train_size=0.5)
```

### 5.2 Current A2 Pattern (Baseline to Replace)
Source: `research/a2_sector_rotation/exp_walkforward_a2.py:44-58`

```python
# Current: hardcoded window dict, manual nested loop
WINDOWS = {
    "W1": ("2023-01-01", "2023-12-31"),
    "W2": ("2024-01-01", "2024-12-31"),
    "W3": ("2025-01-01", "2026-05-08"),
    "FULL": ("2023-01-01", "2026-05-08"),
}
VARIANTS = {
    "V1": dict(L=20, K=3, picks=1, stop=0.03, tp=0.12, max_hold=20, rebal="M"),
    "V2": dict(L=60, K=3, picks=1, stop=0.03, tp=0.12, max_hold=20, rebal="M"),
    ...
}
# driver (main): for w in WINDOWS: for v in VARIANTS: run_backtest(...)
```

**Missing:** no train/test split, no parameter selection on train, no model fitting, no CI on metrics, no result object (just text to file).

### 5.3 Recommended Walk-Forward Harness for SentinelQ

```python
# sentinelq/research/walkforward.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any
import pandas as pd
import numpy as np


@dataclass
class WFWindow:
    name: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str


@dataclass
class WFResult:
    window: WFWindow
    params: dict
    nav: pd.Series      # date → NAV level (OOS test period)
    trades: list
    metrics: dict       # sharpe, cagr, max_dd, calmar, etc.
    train_metrics: dict # same keys but from train period (for overfitting check)


def compute_metrics(nav: pd.Series, ann: int = 252) -> dict:
    """Annualized KPIs from a NAV series."""
    rets = nav.pct_change().dropna()
    if len(rets) < 10:
        return {}
    years = len(rets) / ann
    cum = (1 + rets).prod() - 1
    cagr = (1 + cum) ** (1 / years) - 1 if years > 0 else 0.0
    vol = rets.std() * np.sqrt(ann)
    sharpe = cagr / vol if vol > 1e-9 else 0.0
    peak = nav.cummax()
    max_dd = float((nav / peak - 1).min())
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan
    # Win rate at monthly frequency
    monthly = nav.resample("ME").last().pct_change().dropna()
    win_rate = float((monthly > 0).mean()) if len(monthly) > 0 else 0.0
    return {
        "n_days": len(rets),
        "cagr": round(cagr, 4),
        "vol": round(vol, 4),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 4),
        "calmar": round(calmar, 3) if not np.isnan(calmar) else None,
        "win_rate_monthly": round(win_rate, 3),
    }


class WalkForward:
    """
    Universal walk-forward harness for SentinelQ strategies.

    Example — replacing the A2 ad-hoc loop:

        wf = WalkForward(windows=[
            WFWindow("W1", "2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
            WFWindow("W2", "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
            WFWindow("W3", "2023-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
        ])

        def a5_strategy(bars, params, start, end):
            # returns {"nav": pd.Series, "trades": list}
            return run_backtest(bars, params, start, end)

        results = wf.run(
            strategy_fn=a5_strategy,
            param_grid=[
                {"L": 20, "K": 3, "stop": 0.03},
                {"L": 60, "K": 3, "stop": 0.03},
                {"L": 20, "K": 5, "stop": 0.02},
            ],
            bars=bars,
        )
        print(wf.summary(results).to_string())
    """

    def __init__(self, windows: list[WFWindow]):
        self.windows = windows

    def run(
        self,
        strategy_fn: Callable,          # (bars, params, start, end) → {"nav": Series, "trades": list}
        param_grid: list[dict],
        bars: dict,
        select_params_fn: Callable = None,  # (train_results: list[WFResult]) → dict
        verbose: bool = True,
    ) -> list[WFResult]:
        """
        For each window:
          1. Run strategy_fn on TRAIN period for every param set
          2. Select best params (default: max Sharpe on train)
          3. Run strategy_fn on TEST period with best params
          4. Collect OOS WFResult
        """
        oos_results: list[WFResult] = []

        for window in self.windows:
            if verbose:
                print(f"\n=== Window: {window.name} "
                      f"(train {window.train_start}→{window.train_end}, "
                      f"test {window.test_start}→{window.test_end}) ===")

            # ── Train phase ──────────────────────────────────────────
            train_results: list[WFResult] = []
            for params in param_grid:
                r = strategy_fn(bars, params, window.train_start, window.train_end)
                metrics = compute_metrics(r["nav"])
                train_results.append(WFResult(
                    window=window, params=params,
                    nav=r["nav"], trades=r["trades"],
                    metrics=metrics, train_metrics={},
                ))
                if verbose:
                    sh = metrics.get("sharpe", "N/A")
                    print(f"  train {params} → Sharpe={sh}")

            # ── Parameter selection ──────────────────────────────────
            if select_params_fn:
                best_params = select_params_fn(train_results)
            else:
                # Default: maximize Sharpe on train period
                best = max(
                    train_results,
                    key=lambda x: x.metrics.get("sharpe", -np.inf),
                )
                best_params = best.params
                if verbose:
                    print(f"  → selected params: {best_params}")

            # ── Test phase (OOS) ─────────────────────────────────────
            r = strategy_fn(bars, best_params, window.test_start, window.test_end)
            test_metrics = compute_metrics(r["nav"])
            train_metrics = best.metrics

            if verbose:
                print(f"  OOS Sharpe={test_metrics.get('sharpe', 'N/A')}, "
                      f"CAGR={test_metrics.get('cagr', 'N/A'):.1%}, "
                      f"MaxDD={test_metrics.get('max_dd', 'N/A'):.1%}")

            oos_results.append(WFResult(
                window=window,
                params=best_params,
                nav=r["nav"],
                trades=r["trades"],
                metrics=test_metrics,
                train_metrics=train_metrics,
            ))

        return oos_results

    def summary(self, results: list[WFResult]) -> pd.DataFrame:
        """Return a DataFrame with one row per test window."""
        rows = []
        for r in results:
            row = {
                "window": r.window.name,
                "test_start": r.window.test_start,
                "test_end": r.window.test_end,
                **{f"param_{k}": v for k, v in r.params.items()},
                **{f"oos_{k}": v for k, v in r.metrics.items()},
                **{f"train_{k}": v for k, v in r.train_metrics.items()},
            }
            rows.append(row)
        return pd.DataFrame(rows)

    def combined_nav(self, results: list[WFResult]) -> pd.Series:
        """Stitch OOS NAV series into one continuous curve."""
        pieces = [r.nav for r in results if not r.nav.empty]
        if not pieces:
            return pd.Series(dtype=float)
        # Scale each segment to start from previous end value
        combined = pieces[0]
        for seg in pieces[1:]:
            scale = combined.iloc[-1] / seg.iloc[0]
            combined = pd.concat([combined, seg * scale])
        return combined.sort_index()
```

---

## 6. Backtest ↔ Live Unification

### 6.1 How Each Framework Achieves It

#### nautilus_trader: Clock + ExecutionClient Abstraction
Source: `nautechsystems/nautilus_trader:nautilus_trader/backtest/` + `nautilus_trader/live/node.py`

The strategy class uses only:
- `self.clock.utc_now()` — never `datetime.utcnow()` directly
- `self.cache.bar(instrument_id)` — never a direct file read
- `self.submit_order(order)` — never a direct HTTP call

The engine wires the correct implementations at startup:
```
Backtest:  BacktestEngine  ──► SimulatedClock   +  BacktestExecutionClient
Live:      TradingNode     ──► LiveClock         +  LiveExecutionClient (REST/WS)
```

Same `Strategy` class runs in both modes — zero code changes.

#### Lean: BrokerageModel Injection
Source: `QuantConnect/Lean:Algorithm.Framework/`

`QCAlgorithm.SetBrokerageModel(brokerage, account_type)` swaps in a different fill/fee model:
```python
# Backtest
self.set_brokerage_model(BrokerageName.DEFAULT, AccountType.CASH)
# Live
self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS, AccountType.MARGIN)
```

Strategy code uses `self.portfolio.total_portfolio_value`, `self.market_order()` etc. — same API both modes.

#### pybroker: No Live Support
pybroker is backtest-only. `Strategy.run()` and `walkforward()` operate exclusively on historical data. No live stubs. This is honest — better than pretending unification that hasn't been built.

### 6.2 The Minimal Abstraction: 3 Ports

For a KIS-only Python shop, you need exactly **3 swappable port objects**:

```python
# sentinelq/ports.py
"""
The three port interfaces that enable backtest ↔ live unification.
Strategy code ONLY calls these interfaces — never pandas read_parquet(),
never datetime.now(), never requests.post() directly.
"""
from typing import Protocol
import pandas as pd


class DataPort(Protocol):
    """Supply OHLCV bars — from parquet cache (backtest) or KIS API (live)."""

    def get_bars(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """Return DataFrame with columns: open, high, low, close, volume; index: date."""
        ...

    def get_latest_price(self, ticker: str) -> float:
        """Return the most recent close/last price."""
        ...


class ClockPort(Protocol):
    """Supply current time — simulated (backtest) or wall clock (live)."""

    def today(self) -> pd.Timestamp:
        """Current trading date (date only, no time)."""
        ...

    def now(self) -> pd.Timestamp:
        """Current datetime (UTC)."""
        ...

    def is_market_open(self) -> bool:
        """True if KRX is currently in trading hours."""
        ...


class BrokerPort(Protocol):
    """Submit and query orders — paper broker (backtest) or KIS REST (live)."""

    def buy(
        self,
        ticker: str,
        quantity: int,
        price: float = None,    # None = market order
    ) -> str:
        """Submit buy order. Returns order_id."""
        ...

    def sell(
        self,
        ticker: str,
        quantity: int,
        price: float = None,
    ) -> str:
        """Submit sell order. Returns order_id."""
        ...

    def get_positions(self) -> dict[str, int]:
        """Return {ticker: shares_held} for all open positions."""
        ...

    def get_cash(self) -> float:
        """Return available cash in KRW."""
        ...


# ── BACKTEST IMPLEMENTATIONS ─────────────────────────────────────────

class ParquetDataPort:
    """Read from existing data/cache/kis_daily/*.parquet files."""

    def __init__(self, cache_dir: str):
        import pathlib
        self._cache = pathlib.Path(cache_dir)

    def get_bars(self, ticker, start, end):
        import pandas as pd
        path = self._cache / f"{ticker}.parquet"
        df = pd.read_parquet(path)
        return df.loc[start:end]

    def get_latest_price(self, ticker):
        path = self._cache / f"{ticker}.parquet"
        import pandas as pd
        df = pd.read_parquet(path)
        return float(df["close"].iloc[-1])


class SimulatedClock:
    """Replay a list of trading dates."""

    def __init__(self, dates: list[pd.Timestamp]):
        self._dates = dates
        self._idx = 0

    @property
    def _current(self) -> pd.Timestamp:
        return self._dates[self._idx]

    def today(self) -> pd.Timestamp:
        return self._current.normalize()

    def now(self) -> pd.Timestamp:
        return self._current

    def is_market_open(self) -> bool:
        return True  # always "open" in simulation

    def advance(self) -> bool:
        """Step to next date. Returns False if exhausted."""
        self._idx += 1
        return self._idx < len(self._dates)


class PaperBroker:
    """
    Simulated broker for backtesting and paper trading.
    Fills immediately at the provided price (or last known price).
    Commission rate defaults to KIS retail: 0.015% buy + 0.3% sell (tax included ≈ 0.30% round-trip).
    """

    def __init__(
        self,
        portfolio: "Portfolio",       # Portfolio instance to record fills
        data_port: DataPort,
        buy_commission_rate: float = 0.00015,   # 0.015% brokerage + 0.003% tax
        sell_commission_rate: float = 0.00315,  # 0.015% brokerage + 0.30% tax
    ):
        from sentinelq.portfolio.portfolio import Fill
        self._portfolio = portfolio
        self._data = data_port
        self._buy_rate = buy_commission_rate
        self._sell_rate = sell_commission_rate
        self._Fill = Fill
        self._order_counter = 0

    def buy(self, ticker, quantity, price=None):
        fill_price = price or self._data.get_latest_price(ticker)
        commission = fill_price * quantity * self._buy_rate
        import pandas as pd
        self._portfolio.on_fill(self._Fill(
            ticker=ticker, date=pd.Timestamp.now(), side="BUY",
            quantity=quantity, price=fill_price, commission=commission,
        ))
        self._order_counter += 1
        return f"paper-{self._order_counter}"

    def sell(self, ticker, quantity, price=None):
        fill_price = price or self._data.get_latest_price(ticker)
        commission = fill_price * quantity * self._sell_rate
        import pandas as pd
        self._portfolio.on_fill(self._Fill(
            ticker=ticker, date=pd.Timestamp.now(), side="SELL",
            quantity=quantity, price=fill_price, commission=commission,
        ))
        self._order_counter += 1
        return f"paper-{self._order_counter}"

    def get_positions(self):
        return {t: p.quantity for t, p in self._portfolio.positions().items()}

    def get_cash(self):
        return self._portfolio.cash()


# ── LIVE IMPLEMENTATIONS ─────────────────────────────────────────────

class LiveClock:
    """Real wall-clock time."""
    def today(self):
        import pandas as pd
        return pd.Timestamp.today().normalize()

    def now(self):
        import pandas as pd
        return pd.Timestamp.now()

    def is_market_open(self):
        """KRX hours: 09:00–15:30 KST on weekdays."""
        import pytz
        kst = pytz.timezone("Asia/Seoul")
        now = pd.Timestamp.now(tz=kst)
        if now.weekday() >= 5:
            return False
        return (now.hour, now.minute) >= (9, 0) and (now.hour, now.minute) < (15, 30)


class KISBroker:
    """Wraps existing KIS REST API client."""

    def __init__(self, api_client, portfolio: "Portfolio"):
        self._api = api_client
        self._portfolio = portfolio

    def buy(self, ticker, quantity, price=None):
        order_id = self._api.place_order(ticker, "BUY", quantity, price)
        # Fill recorded asynchronously via order status polling or webhook
        return order_id

    def sell(self, ticker, quantity, price=None):
        return self._api.place_order(ticker, "SELL", quantity, price)

    def get_positions(self):
        return self._api.get_holdings()

    def get_cash(self):
        return self._api.get_available_cash()
```

### 6.3 The One Rule That Makes It Work

All three frameworks converge on the same foundational insight: **inject time, don't read it**.

```python
# ❌ BAD — untestable in backtest (always reads wall clock)
import datetime
if datetime.date.today().weekday() == 0:  # is it Monday?
    rebalance()

# ✅ GOOD — testable (clock can be simulated)
if clock.today().weekday() == 0:
    rebalance()
```

The secondary insight: **inject the broker, don't call it directly**.

```python
# ❌ BAD — coupled to KIS REST, can't backtest
import requests
requests.post("https://openapi.koreainvestment.com/orders", ...)

# ✅ GOOD — swappable
broker.buy(ticker="005930", quantity=10)  # same call in backtest and live
```

---

## 7. Recommended Adoption Plan for SentinelQ

| Component | Decision | Rationale |
|---|---|---|
| **4-layer Alpha/PCM/Risk/Exec split** | `BORROW_INTERFACE` | Copy Lean's layer interfaces in pure Python; `AlphaModel`, `RiskManagementModel`, `ExecutionModel` are simple ABCs. Do not import Lean (C# runtime, cloud lock-in). |
| **Risk Engine** | `BORROW_INTERFACE` | Copy `RiskEngineConfig` + pre-trade check pipeline from nautilus; reimplement as ~150 lines pure Python (see §3.4). The config schema alone is worth stealing. |
| **Portfolio NAV Bookkeeper** | `BORROW_INTERFACE` | Copy `PortfolioFacade` interface; reimplement `Portfolio` using `Fill` events (see §4.3). Drop FX/margin/multi-venue — not needed for KIS. |
| **Walk-Forward Harness** | `BORROW_INTERFACE` | Copy pybroker's window-sequencing pattern; do NOT pip-install pybroker for this (its `Strategy.run()` requires its own `DataSource`). Use `WalkForward` class from §5.3. |
| **KPI Metrics (Sharpe, Calmar, etc.)** | `ADOPT_DIRECTLY` | `pip install pybroker` — the `EvalMetrics` / `BootstrapResult` classes are pure Python (numpy/pandas only) and immediately usable. Or copy `eval.py` (38KB). |
| **Backtest Engine** | `INSPIRE_ONLY` | Our existing `_run_v2` loop in A2 is adequate if refactored to use `Portfolio` + `RiskEngine` objects. No need to adopt nautilus BacktestEngine (Rust/Cython build pain on Windows). |
| **Execution Layer (live)** | `BORROW_INTERFACE` | Build `KISBroker(BrokerPort)` wrapping existing KIS REST client. Nautilus `LiveExecutionClient` pattern (retry logic, order state reconciliation) is worth reading. |
| **Data Layer** | `INSPIRE_ONLY` | Keep existing parquet cache under `data/cache/`. Wrap in `ParquetDataPort(DataPort)` for testability. Both pybroker `DataSource` and nautilus `DataCatalog` are far too complex for a single-broker setup. |
| **Paper Trading** | `BORROW_INTERFACE` | Build `PaperBroker(BrokerPort)` using pybroker + nautilus patterns (§6.2). This is the **critical missing piece** between backtest and live. |
| **nautilus_trader (pip install)** | `SKIP` | Requires Rust toolchain + Cython compilation; Windows builds routinely break. All value is in design patterns — study the source, do not run it. |
| **QuantConnect/Lean (pip install)** | `SKIP` | C# runtime; QuantConnect cloud dependency; no native KIS adapter. Steal the framework pattern, not the code. |
| **pybroker (pip install)** | `ADOPT_DIRECTLY` | Pure Python, pip-installable, Windows-compatible (`pip install pybroker`). Use for `EvalMetrics` and bootstrap confidence intervals on returns. Do NOT use its `Strategy.run()` with KIS data. |

### Priority Build Order

```
Phase 1 — Foundation (build now, ~1 week):
  ├── sentinelq/portfolio/portfolio.py   (Portfolio, Fill, PositionState)
  ├── sentinelq/risk/engine.py           (RiskEngine, RiskConfig)
  └── sentinelq/research/walkforward.py (WalkForward, WFWindow, compute_metrics)
  
  → Refactor A5/A6 hypothesis code to use these instead of ad-hoc loops

Phase 2 — Paper Trading (~1 week):
  ├── sentinelq/ports.py                 (DataPort, ClockPort, BrokerPort protocols)
  ├── sentinelq/ports.py                 (ParquetDataPort, SimulatedClock, PaperBroker)
  └── sentinelq/strategy/base.py         (AlphaModel ABC, 4-layer runner)
  
  → Run DART fundamental hypothesis in paper mode before committing capital

Phase 3 — Live (~2 weeks, after Phase 2 validates):
  └── sentinelq/ports.py                 (KISBroker wrapping existing KIS client)
  
  → Swap PaperBroker → KISBroker; no strategy code changes
```

---

## Appendix: Key File References

| Framework | File | Key Content |
|---|---|---|
| nautilus | `nautilus_trader/risk/config.py` | `RiskEngineConfig` — rate limits, notional caps |
| nautilus | `nautilus_trader/risk/engine.pyx` | Full pre-trade check pipeline (~50KB Cython) |
| nautilus | `nautilus_trader/risk/sizing.pyx` | `FixedRiskSizer` — size by % equity risk |
| nautilus | `nautilus_trader/portfolio/base.pyx` | `PortfolioFacade` — complete read-only interface |
| nautilus | `nautilus_trader/portfolio/portfolio.pyx` | Concrete impl — fill events, MTM, PnL (~115KB) |
| nautilus | `nautilus_trader/backtest/engine.pyx` | Backtest engine wiring (~340KB — reference only) |
| nautilus | `nautilus_trader/live/node.py` | `TradingNode` — live wiring pattern |
| Lean | `Algorithm.Framework/Alphas/EmaCrossAlphaModel.py` | Concrete `AlphaModel.update()` |
| Lean | `Algorithm.Framework/Portfolio/EqualWeightingPortfolioConstructionModel.py` | `determine_target_percent()` |
| Lean | `Algorithm.Framework/Risk/MaximumDrawdownPercentPortfolio.py` | Portfolio circuit breaker |
| Lean | `Algorithm.Framework/Risk/MaximumDrawdownPercentPerSecurity.py` | Per-security trailing stop |
| Lean | `Algorithm.Framework/Execution/SpreadExecutionModel.py` | Execution model pattern |
| pybroker | `src/pybroker/strategy.py` | `Strategy.walkforward()` + `WalkforwardMixin` (~63KB) |
| pybroker | `src/pybroker/eval.py` | `EvalMetrics` dataclass + all KPI computations (~38KB) |
| pybroker | `src/pybroker/portfolio.py` | Portfolio bookkeeping pattern (~44KB) |
| pybroker | `src/pybroker/context.py` | `BarData` typed context for bar callbacks (~52KB) |
| SentinelQ | `research/a2_sector_rotation/exp_walkforward_a2.py` | Current ad-hoc baseline to refactor |
