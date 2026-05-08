"""
Risk gate application for daily-bar backtests.

Loads config/risk_limits.yaml and exposes filters compatible with daily OHLCV.

Gate coverage in v0 (daily-bar backtest):
  ✅ min_avg_daily_value_eokwon     — ADV × close
  ⚠️ min_market_cap_eokwon          — needs cap data (pykrx cap API broken);
                                       universe-implicit for KOSPI top-30 (all >> 1000억)
  ❌ block_if_managed_issue          — runtime-only (KIS live snapshot)
  ❌ block_if_warning / halted /
     settlement                      — runtime-only
  ❌ pause_if_vi_active              — intraday event, not modelable on daily bars

The runtime-only gates DO apply at order time (Risk Engine) — they just
cannot be retroactively backtested without a historical KIS field archive.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml


@dataclass(frozen=True)
class InstrumentGates:
    min_avg_daily_value_eokwon: float
    min_market_cap_eokwon: float
    min_price_krw: float
    max_price_krw: float
    block_if_managed_issue: bool
    block_if_investment_warning: bool
    block_if_market_warning_codes: tuple[str, ...]
    block_if_trading_halted: bool
    block_if_settlement_trade: bool
    pause_if_vi_active: bool


def load_gates(config_path: Optional[Path] = None) -> InstrumentGates:
    """Read instrument_gates from risk_limits.yaml."""
    if config_path is None:
        config_path = Path(__file__).resolve().parents[2] / "config" / "risk_limits.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    g = cfg["instrument_gates"]
    return InstrumentGates(
        min_avg_daily_value_eokwon=float(g["min_avg_daily_value_eokwon"]),
        min_market_cap_eokwon=float(g["min_market_cap_eokwon"]),
        min_price_krw=float(g["min_price_krw"]),
        max_price_krw=float(g["max_price_krw"]),
        block_if_managed_issue=bool(g["block_if_managed_issue"]),
        block_if_investment_warning=bool(g["block_if_investment_warning"]),
        block_if_market_warning_codes=tuple(g["block_if_market_warning_codes"]),
        block_if_trading_halted=bool(g["block_if_trading_halted"]),
        block_if_settlement_trade=bool(g["block_if_settlement_trade"]),
        pause_if_vi_active=bool(g["pause_if_vi_active"]),
    )


def apply_daily_gates(
    daily: pd.DataFrame,
    gates: InstrumentGates,
    lookback: int = 20,
) -> pd.Series:
    """Boolean Series indexed like `daily`: True if instrument passes the
    daily-data-modelable subset of gates on date t.

    Applied:
      * 20d avg daily value × close >= min_avg_daily_value_eokwon
      * close in [min_price_krw, max_price_krw]
    Window is left-closed (excludes day t itself).
    """
    close = daily["close"].astype(float)
    daily_value_eok = (daily["volume"].astype(float) * close) / 1e8
    adv_pass = daily_value_eok.rolling(lookback, closed="left").mean() >= gates.min_avg_daily_value_eokwon
    price_pass = (close >= gates.min_price_krw) & (close <= gates.max_price_krw)
    return adv_pass & price_pass


if __name__ == "__main__":
    g = load_gates()
    print("instrument_gates loaded:")
    for k, v in g.__dict__.items():
        print(f"  {k:35s} = {v}")
