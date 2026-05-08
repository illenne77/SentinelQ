"""
A4 exit-rule simulator — applies plan v2.2 §7.5 exit rules to triggers.

Inputs:
  * entry_close   : float, entry price (day-of-trigger close)
  * future_bars   : pd.DataFrame with daily OHLC indexed by date,
                    starting on day t+1 (the day AFTER trigger).
  * horizon       : int, time-exit deadline in trading days.

Returns:
  ExitResult: dict with realized return (weighted across legs), exit reason,
  exit day index. Costs are NOT applied here — apply via costs.net_return().

Approximations (daily-bar simulation, no intraday tape):
  * If day's Low <= stop_price AND High >= tp1_price → assume stop fires
    first (worst-case ordering for the trader).
  * Trailing stop tracks daily High AFTER tp1 fire; triggers if next day's
    Low <= peak_high * (1 - 0.015).
  * Same-day tp1 + tp2 both possible (high enough range); both fire that day.
  * Same-day tp1 + trailing stop: tp1 fires; trailing arms; cannot fire same
    day (no peak yet), evaluated next day onward.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


STOP_PCT = -0.02
TP1_PCT = 0.03
TP2_PCT = 0.05
TRAIL_PCT = -0.015
TP1_SHARE = 0.50
TP2_SHARE = 0.30
TRAIL_SHARE = 0.20


@dataclass
class ExitResult:
    realized_return: float
    exit_reason: str       # 'stop' | 'tp_full' | 'trail' | 'time' | 'mixed'
    exit_day: int          # index into future_bars (0-based, day t+1)
    legs: dict             # diagnostic breakdown


def simulate_exit(entry_close: float, future_bars: pd.DataFrame,
                  horizon: int = 5) -> ExitResult:
    """Simulate the §7.5 exit ladder on daily OHLC bars."""
    if future_bars.empty:
        return ExitResult(0.0, "no_data", -1, {})

    stop_px = entry_close * (1 + STOP_PCT)
    tp1_px = entry_close * (1 + TP1_PCT)
    tp2_px = entry_close * (1 + TP2_PCT)

    pos_tp1 = TP1_SHARE       # 50% leg, stops out via main stop OR fires at tp1
    pos_tp2 = TP2_SHARE       # 30% leg, stops out via main stop OR fires at tp2
    pos_trail = TRAIL_SHARE   # 20% leg, stops out via main stop until tp1 fires; then trailing

    # leg states: 'open' | 'stopped' | 'tp1' | 'tp2' | 'trail' | 'time'
    leg_state = {"tp1": "open", "tp2": "open", "trail": "open"}
    leg_return = {"tp1": 0.0, "tp2": 0.0, "trail": 0.0}

    trail_armed = False
    trail_peak = entry_close   # peak high since arming

    bars = future_bars.head(horizon)
    last_close = entry_close
    exit_day = -1
    reasons: list[str] = []

    for i, (date, row) in enumerate(bars.iterrows()):
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        last_close = close

        # 1) Stop check first (worst-case ordering): any open leg, low <= stop_px
        if low <= stop_px:
            for leg in ("tp1", "tp2", "trail"):
                if leg_state[leg] == "open":
                    leg_state[leg] = "stopped"
                    leg_return[leg] = STOP_PCT
            reasons.append("stop")
            exit_day = i
            break

        # 2) tp1 fires this day (50% leg out at +3%)
        if leg_state["tp1"] == "open" and high >= tp1_px:
            leg_state["tp1"] = "tp1"
            leg_return["tp1"] = TP1_PCT
            trail_armed = True
            trail_peak = max(trail_peak, high)
            reasons.append("tp1")

        # 3) tp2 fires this day (30% leg out at +5%)
        if leg_state["tp2"] == "open" and high >= tp2_px:
            leg_state["tp2"] = "tp2"
            leg_return["tp2"] = TP2_PCT
            reasons.append("tp2")

        # 4) trailing stop (only if armed AND open AND peak set on a PRIOR or current day)
        if trail_armed and leg_state["trail"] == "open":
            # Update peak using today's high (we already passed stop check)
            trail_peak = max(trail_peak, high)
            trail_stop_px = trail_peak * (1 + TRAIL_PCT)
            # Same-day arming: tp1 fired today; trail can't fire today (need a
            # later bar where low pierces a peak set by an earlier bar). But if
            # trail was armed BEFORE today, today's low can pierce.
            if "tp1" not in reasons or i > 0:  # not the same bar that armed
                if low <= trail_stop_px:
                    leg_state["trail"] = "trail"
                    leg_return["trail"] = (trail_stop_px / entry_close) - 1.0
                    reasons.append("trail")

        # If all three legs closed, we're done
        if all(s != "open" for s in leg_state.values()):
            exit_day = i
            break

    # 5) Time exit: any leg still open closes at last_close (horizon-end)
    time_ret = (last_close / entry_close) - 1.0
    if any(s == "open" for s in leg_state.values()):
        for leg in ("tp1", "tp2", "trail"):
            if leg_state[leg] == "open":
                leg_state[leg] = "time"
                leg_return[leg] = time_ret
        reasons.append("time")
        if exit_day < 0:
            exit_day = len(bars) - 1

    realized = (leg_return["tp1"] * TP1_SHARE
                + leg_return["tp2"] * TP2_SHARE
                + leg_return["trail"] * TRAIL_SHARE)

    if len(set(reasons)) == 1:
        reason = reasons[0]
    elif "stop" in reasons:
        reason = "stop"
    elif set(reasons) <= {"tp1", "tp2"} and len(reasons) >= 2:
        reason = "tp_full"
    else:
        reason = "mixed"

    return ExitResult(
        realized_return=realized,
        exit_reason=reason,
        exit_day=exit_day,
        legs={"state": leg_state, "ret": leg_return},
    )
