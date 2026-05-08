# ============================================================================
# SentinelQ — A4 Liquidity Surge — Backtest Skeleton (QuantConnect Lean / Python)
# ----------------------------------------------------------------------------
# Hypothesis (from plan v2.2 §7.6 Alpha Catalog A4):
#   When a KOSPI/KOSDAQ name's intraday cumulative volume by 10:30 KST is
#   significantly above its same-time-of-day median over the prior 20 trading
#   days, AND the move is not driven by a known scheduled event (earnings,
#   dividend, halt-resume), the next 1–3 day forward return is positive
#   in expectation.
#
# Why this alpha first:
#   * Inputs are derivable from a single KIS field (prdy_vrss_vol_rate) plus
#     standard OHLCV — minimal data dependency.
#   * Risk gates (managed/warn/VI) are already in market_quote_snapshot.
#   * Effect is well-documented in microstructure literature; KR-specific
#     foreign/program flow (A6) can be layered later as a confirming factor.
#
# Bias prevention (plan v2.2 §7.4.2 — every box MUST be checked before promotion):
#   [ ] Lookahead bias .... entry computed on data ≤ 10:30 KST, executed at 10:31 open
#   [ ] Survivorship ...... universe includes delisted / suspended names
#   [ ] Leakage ........... earnings calendar fetched as of T-1 only
#   [ ] Hindsight ......... thresholds frozen before OOS window
#   [ ] Selection ......... no per-symbol parameter tuning
#   [ ] p-hacking ......... ≤ 1 grid sweep before lock; record full grid
#   [ ] Walk-forward OOS .. 70/15/15 train/val/test, expanding window
#   [ ] Slippage modeled .. 8 bps + half-spread
#   [ ] Borrow / short .... LONG ONLY (per plan §1A.2 OOS)
#
# Skeleton status:
#   - Strategy logic .................. TODO  (entry/exit rules below)
#   - Universe + delisted handling .... TODO  (Lean Map/Factor files)
#   - Forward returns / labels ........ TODO  (use OnEndOfDay close)
#   - Slippage + commission ........... DONE  (Lean built-in models)
#   - Walk-forward harness ............ TODO  (run multiple Lean periods)
#   - Metrics export .................. DONE  (CSV emitter at end)
# ============================================================================

from AlgorithmImports import *
from datetime import time
import pandas as pd


# ----------------------------------------------------------------------------
# Risk gate proxy — mirrors risk_limits.yaml > instrument_gates
# In Phase 0 backtest, KIS snapshot fields are not historically available, so
# we approximate gates with what Lean offers + curated event lists.
# Phase 0.5+ will replace this with the actual market_quote_snapshot reader.
# ----------------------------------------------------------------------------
class RiskGateProxy:
    def __init__(self, algorithm: QCAlgorithm):
        self.algo = algorithm
        # TODO: load curated lists for the KOSPI/KOSDAQ test window
        self.managed_issues: set[str] = set()      # 관리종목
        self.investment_warnings: set[str] = set() # 투자경고/위험
        self.halt_dates: dict[str, set] = {}       # ticker -> set of halted dates

    def is_blocked(self, symbol: Symbol, asof) -> tuple[bool, str | None]:
        t = symbol.Value
        d = asof.date()
        if t in self.managed_issues:        return True, "GATE_MANAGED"
        if t in self.investment_warnings:   return True, "GATE_WARNED"
        if d in self.halt_dates.get(t, set()): return True, "GATE_HALTED"
        # Liquidity / size floors
        sec = self.algo.Securities[symbol]
        if sec.Price < 1000:                return True, "GATE_PENNY"
        if sec.Price > 1_000_000:           return True, "GATE_TOO_PRICEY"
        return False, None


# ----------------------------------------------------------------------------
# A4 Liquidity Surge strategy
# ----------------------------------------------------------------------------
class A4LiquiditySurge(QCAlgorithm):

    # --- Hyperparameters (FROZEN before OOS window) -------------------------
    LOOKBACK_DAYS         = 20            # rolling baseline window
    SURGE_THRESHOLD       = 2.0           # cum_vol / median(cum_vol, 20d) ≥ 2.0
    OBSERVE_TIME_KST      = time(10, 30)  # decision cut-off
    EXECUTE_TIME_KST      = time(10, 31)  # 1-min lag, no same-bar fill
    HOLD_DAYS             = 2             # forward holding period
    PER_TRADE_STOPLOSS    = -0.03         # mirrors risk_limits.yaml
    MAX_CONCURRENT        = 3
    POSITION_PCT          = 0.05

    # --- Universe ----------------------------------------------------------
    UNIVERSE_SIZE         = 100           # top-N by ADV
    MIN_MARKET_CAP        = 100_000_000_000  # 1000억 KRW

    def Initialize(self):
        # ====== Backtest window =====================================
        # NOTE: Walk-forward harness overrides these dates per fold.
        # Defaults shown are the IN-SAMPLE training fold only.
        self.SetStartDate(2023, 1, 1)
        self.SetEndDate(2024, 6, 30)
        self.SetCash(10_000_000)            # KRW (matches capital base)
        self.SetTimeZone("Asia/Seoul")

        # ====== Brokerage / fees / slippage ==========================
        # Conservative model — mirrors plan v2.2 §7.4.1 simulation realism.
        self.SetBrokerageModel(
            BrokerageName.InteractiveBrokersBrokerage,  # placeholder — KR broker model TBD
            AccountType.Cash,
        )
        self.Settings.FreePortfolioValuePercentage = 0.02  # buffer

        # Per-share or % commission — KIS retail typical: 0.015% + tax 0.20% on sells
        # Implement custom fee model:
        # self.SetSecurityInitializer(self._init_security)

        # ====== Universe (dynamic top-N by ADV, refreshed weekly) =====
        self.UniverseSettings.Resolution = Resolution.Minute
        self.AddUniverse(self._coarse_filter)

        # ====== Risk gates ==========================================
        self.gates = RiskGateProxy(self)

        # ====== Bookkeeping =========================================
        self.surge_history: dict[Symbol, list] = {}  # ticker -> rolling cum_vol@1030
        self.entries: dict[Symbol, dict] = {}        # open position metadata

        # ====== Schedules ============================================
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(self.OBSERVE_TIME_KST.hour,
                              self.OBSERVE_TIME_KST.minute),
            self._observe_and_signal,
        )
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(self.EXECUTE_TIME_KST.hour,
                              self.EXECUTE_TIME_KST.minute),
            self._execute_signals,
        )

        # ====== Output =============================================
        self.signal_log: list[dict] = []   # for post-run metrics emission

    # ------------------------------------------------------------------
    def _coarse_filter(self, coarse):
        """Top-N by ADV, with size floor. Survivorship-safe via Lean Map files."""
        filtered = [
            x for x in coarse
            if x.HasFundamentalData
            and x.Price >= 1000
            and x.DollarVolume * 1300 >= 5_000_000_000  # ~50억 KRW ADV
        ]
        filtered.sort(key=lambda x: x.DollarVolume, reverse=True)
        return [x.Symbol for x in filtered[: self.UNIVERSE_SIZE]]

    # ------------------------------------------------------------------
    def _observe_and_signal(self):
        """At 10:30 KST: compute cum-volume-by-1030 vs 20d median; flag surge."""
        candidates = []
        for symbol in self.ActiveSecurities.Keys:
            blocked, reason = self.gates.is_blocked(symbol, self.Time)
            if blocked:
                continue

            # TODO: read cum-volume-by-1030 from minute history
            # hist = self.History(symbol, self.LOOKBACK_DAYS + 1, Resolution.Minute)
            # cv_today = hist.between(today_open, 10:30).volume.sum()
            # baseline = median([cv_at_1030 for each of last 20 sessions])
            # ratio = cv_today / baseline
            ratio = 0.0  # placeholder

            if ratio >= self.SURGE_THRESHOLD:
                candidates.append((symbol, ratio))

        candidates.sort(key=lambda x: -x[1])
        self._pending_signals = candidates[: self.MAX_CONCURRENT - len(self.entries)]

    # ------------------------------------------------------------------
    def _execute_signals(self):
        """At 10:31 KST: execute pending entries at next-bar open."""
        for symbol, ratio in getattr(self, "_pending_signals", []):
            if symbol in self.entries:
                continue
            qty = self.CalculateOrderQuantity(symbol, self.POSITION_PCT)
            if qty <= 0:
                continue
            ticket = self.MarketOrder(symbol, qty)
            self.entries[symbol] = {
                "entry_time": self.Time,
                "entry_price": self.Securities[symbol].Price,
                "ratio": ratio,
                "exit_due": self.Time + timedelta(days=self.HOLD_DAYS),
            }
            self.signal_log.append({
                "ticker": symbol.Value,
                "entry_time": self.Time,
                "entry_price": self.Securities[symbol].Price,
                "surge_ratio": ratio,
            })

    # ------------------------------------------------------------------
    def OnData(self, data: Slice):
        # Time-based exit + per-trade stoploss
        for symbol in list(self.entries.keys()):
            if symbol not in data.Bars:
                continue
            entry = self.entries[symbol]
            price = data.Bars[symbol].Close
            ret = price / entry["entry_price"] - 1.0

            if ret <= self.PER_TRADE_STOPLOSS or self.Time >= entry["exit_due"]:
                self.Liquidate(symbol)
                # backfill log
                for row in reversed(self.signal_log):
                    if row["ticker"] == symbol.Value and "exit_time" not in row:
                        row["exit_time"]  = self.Time
                        row["exit_price"] = price
                        row["return"]     = ret
                        row["exit_reason"] = "STOP" if ret <= self.PER_TRADE_STOPLOSS else "TIME"
                        break
                del self.entries[symbol]

    # ------------------------------------------------------------------
    def OnEndOfAlgorithm(self):
        df = pd.DataFrame(self.signal_log)
        if df.empty:
            self.Log("[A4] No signals fired.")
            return
        closed = df.dropna(subset=["return"])
        if closed.empty:
            return

        hit_rate = (closed["return"] > 0).mean()
        avg_ret  = closed["return"].mean()
        std_ret  = closed["return"].std()
        sharpe   = (avg_ret / std_ret) * (252 ** 0.5) if std_ret else 0.0

        equity_curve = (1 + closed.sort_values("exit_time")["return"]).cumprod()
        peak = equity_curve.cummax()
        mdd = ((equity_curve - peak) / peak).min()

        self.Log(f"[A4] trades={len(closed)} hit_rate={hit_rate:.2%} "
                 f"avg_ret={avg_ret:.4f} sharpe={sharpe:.2f} mdd={mdd:.2%}")

        # Persist for walk-forward harness aggregation
        self.ObjectStore.Save("a4_signals.csv", df.to_csv(index=False))


# ============================================================================
# TODO — companion artifacts (not part of this Lean file)
#   * walk_forward.py    — runs Lean across folds, aggregates metrics
#   * grid_search.yaml   — frozen hyperparam grid (record ALL runs)
#   * report.ipynb       — by-regime breakdown, cost sensitivity
# ============================================================================
