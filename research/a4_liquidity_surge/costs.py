"""
Transaction cost model for KR equity backtests.

Configurable per-side:
  * commission_bps  — brokerage commission (default 1.5 bp = 0.015%)
  * slippage_bps    — execution slippage (default 5 bp; assumes market order on liquid name)
  * sell_tax_bps    — securities transaction tax + agri-fishery special tax,
                      applied ONLY on the sell side
                      (KOSPI/KOSDAQ as of 2025: 0.15% 거래세 + 0.03% 농특세 = 0.18%
                       Use 18 bp default. ETF/ETN/futures excluded.)

Conventions:
  * All bps are *per side* unless noted.
  * Round-trip cost (BPS) = buy + sell + tax = 1.5 + 1.5 + 5 + 5 + 18 = 31 bps
  * Net return = gross_return - round_trip_cost / 10000

Limitations (NOT modeled in v0):
  * Market impact (size-dependent)
  * Limit-order improvement
  * Crossing spread asymmetry on volatile names
  * VAT on commission (negligible at retail scale)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    commission_bps: float = 1.5      # per side
    slippage_bps: float = 5.0        # per side
    sell_tax_bps: float = 18.0       # sell only

    def buy_cost_bps(self) -> float:
        return self.commission_bps + self.slippage_bps

    def sell_cost_bps(self) -> float:
        return self.commission_bps + self.slippage_bps + self.sell_tax_bps

    def round_trip_bps(self) -> float:
        return self.buy_cost_bps() + self.sell_cost_bps()

    def net_return(self, gross_return: float) -> float:
        """Apply round-trip cost to a gross return.

        For long-only strategy: net = (1 + gross) * (1 - buy) * (1 - sell) - 1
        Approximation (small-cost): net ≈ gross - round_trip_bps / 10000
        We use the exact form for accuracy.
        """
        buy_factor = 1.0 - self.buy_cost_bps() / 10000.0
        sell_factor = 1.0 - self.sell_cost_bps() / 10000.0
        return (1.0 + gross_return) * buy_factor * sell_factor - 1.0


# Pre-configured profiles
CHEAP = CostModel(commission_bps=1.5, slippage_bps=3.0)            # generous limit-order fills
DEFAULT = CostModel()                                              # market order, retail
CONSERVATIVE = CostModel(commission_bps=2.5, slippage_bps=10.0)    # adverse selection / wider spreads


if __name__ == "__main__":
    for name, cm in [("CHEAP", CHEAP), ("DEFAULT", DEFAULT), ("CONSERVATIVE", CONSERVATIVE)]:
        print(f"{name:13s}  RT={cm.round_trip_bps():.1f} bps   "
              f"net(+1%)  = {cm.net_return(0.01):+.5f}")
