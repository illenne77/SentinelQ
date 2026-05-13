"""Walk-forward harness for SentinelQ strategy research.

Implements the recommended walk-forward design from
``research/oss_review/architecture_patterns.md`` §5.3, with metric
keys aligned to the PREREG-0004 KPI gate vocabulary used in
``research/a2_sector_rotation`` (``cagr``, ``sharpe``, ``max_dd``,
``calmar``, ``hit_rate``, ``alpha_ann``, ``hit_month``, ``n_trades``).

Strategy callable contract
--------------------------
``strategy_fn(bars, params, start, end) -> Dict[str, Any]`` must
return a mapping with at minimum:

- ``"nav"``: ``pd.Series`` of NAV levels indexed by date over the
  backtest window.
- ``"trades"``: list of trade records (any objects); only its length
  is consumed by :func:`compute_metrics` to populate ``n_trades``.

Optional keys (``"benchmark_nav"`` etc.) are forwarded to
:func:`compute_metrics` when present.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class WFWindow:
    """Single walk-forward window: a (train, test) date pair."""

    name: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str


@dataclass
class WFResult:
    """Result of one walk-forward step (the OOS test side, plus train ref)."""

    window: WFWindow
    params: dict[str, Any]
    nav: pd.Series
    trades: list[Any]
    metrics: dict[str, Any]
    train_metrics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_metrics(
    nav: pd.Series,
    trades: list[Any] | None = None,
    benchmark_nav: pd.Series | None = None,
    ann: int = 252,
) -> dict[str, Any]:
    """Compute annualised KPIs from a NAV series.

    Output keys (always present, matching the PREREG-0004 / A2 vocabulary):

    - ``n_days``: number of return observations
    - ``cagr``: compound annual growth rate
    - ``vol``: annualised volatility of daily returns
    - ``sharpe``: ``cagr / vol`` (zero-rf simple Sharpe)
    - ``max_dd``: maximum drawdown (non-positive number)
    - ``calmar``: ``cagr / |max_dd|`` (``None`` if no drawdown observed)
    - ``hit_rate``: fraction of months with positive return
    - ``hit_month``: alias of ``hit_rate`` for backward compatibility with
      existing A2 walkforward outputs
    - ``n_trades``: ``len(trades)`` if provided, else ``0``
    - ``alpha_ann``: ``cagr - cagr_bench`` (``None`` if no benchmark passed)
    - ``cagr_bench``: benchmark CAGR (``None`` if no benchmark passed)

    Parameters
    ----------
    nav:
        NAV time series indexed by date.
    trades:
        Optional iterable of trade records; only ``len(trades)`` is used.
    benchmark_nav:
        Optional benchmark NAV series; if provided the function emits
        ``alpha_ann`` and ``cagr_bench`` over the intersection of dates.
    ann:
        Annualisation factor (``252`` for daily KR equity bars).
    """
    empty: dict[str, Any] = {
        "n_days": 0,
        "cagr": 0.0,
        "vol": 0.0,
        "sharpe": 0.0,
        "max_dd": 0.0,
        "calmar": None,
        "hit_rate": 0.0,
        "hit_month": 0.0,
        "n_trades": len(trades) if trades is not None else 0,
        "alpha_ann": None,
        "cagr_bench": None,
    }
    if nav is None or len(nav) < 2:
        return empty

    nav = nav.astype(float).sort_index()
    rets = nav.pct_change().dropna()
    n = len(rets)
    if n == 0:
        return empty

    years = n / float(ann)
    cum = float((1.0 + rets).prod() - 1.0)
    cagr = (1.0 + cum) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    vol = float(rets.std() * np.sqrt(ann))
    sharpe = cagr / vol if vol > 1e-9 else 0.0

    peak = nav.cummax()
    max_dd = float((nav / peak - 1.0).min())
    calmar = cagr / abs(max_dd) if max_dd < 0 else None

    # Monthly hit rate (matches A2 ``hit_month`` semantics).
    try:
        monthly = nav.resample("ME").last().pct_change().dropna()
    except ValueError:
        monthly = nav.resample("M").last().pct_change().dropna()
    hit_rate = float((monthly > 0).mean()) if len(monthly) > 0 else 0.0

    out: dict[str, Any] = {
        "n_days": n,
        "cagr": float(cagr),
        "vol": float(vol),
        "sharpe": float(sharpe),
        "max_dd": float(max_dd),
        "calmar": float(calmar) if calmar is not None else None,
        "hit_rate": hit_rate,
        "hit_month": hit_rate,
        "n_trades": len(trades) if trades is not None else 0,
        "alpha_ann": None,
        "cagr_bench": None,
    }

    if benchmark_nav is not None and len(benchmark_nav) >= 2:
        b = benchmark_nav.astype(float).sort_index()
        b = b.reindex(nav.index).dropna()
        if len(b) >= 2:
            b_rets = b.pct_change().dropna()
            b_years = len(b_rets) / float(ann)
            b_cum = float((1.0 + b_rets).prod() - 1.0)
            cagr_b = (1.0 + b_cum) ** (1.0 / b_years) - 1.0 if b_years > 0 else 0.0
            out["cagr_bench"] = float(cagr_b)
            out["alpha_ann"] = float(cagr - cagr_b)

    return out


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class WalkForward:
    """Universal walk-forward harness.

    For each :class:`WFWindow`:

    1. Run ``strategy_fn`` on the train period for every param set.
    2. Select best params (default: max train Sharpe).
    3. Run ``strategy_fn`` on the test period with the selected params.
    4. Collect a :class:`WFResult` per window.

    The harness is intentionally agnostic about what a "strategy" is:
    any callable obeying the ``(bars, params, start, end) -> dict``
    contract is supported.
    """

    def __init__(self, windows: list[WFWindow]):
        self.windows = list(windows)

    def run(
        self,
        strategy_fn: Callable[..., dict[str, Any]],
        param_grid: list[dict[str, Any]],
        bars: Any,
        select_params_fn: Callable[[list[WFResult]], dict[str, Any]] | None = None,
        verbose: bool = False,
    ) -> list[WFResult]:
        """Execute walk-forward over all configured windows.

        Parameters
        ----------
        strategy_fn:
            Callable returning ``{"nav": pd.Series, "trades": list, ...}``.
        param_grid:
            List of parameter dicts to evaluate on each train period.
        bars:
            Input bar data passed through to ``strategy_fn`` unchanged
            (typically a ``Dict[str, DataFrame]``).
        select_params_fn:
            Optional custom selector. Defaults to maximum train Sharpe.
        verbose:
            Library code is silent by default; set ``True`` only in
            interactive scripts (no print is emitted regardless — flag
            is reserved for future structured logging).
        """
        if not param_grid:
            raise ValueError("param_grid must contain at least one config")

        oos_results: list[WFResult] = []

        for window in self.windows:
            train_results: list[WFResult] = []
            for params in param_grid:
                r = strategy_fn(bars, params, window.train_start, window.train_end)
                metrics = compute_metrics(
                    r.get("nav", pd.Series(dtype=float)),
                    trades=r.get("trades", []),
                    benchmark_nav=r.get("benchmark_nav"),
                )
                train_results.append(
                    WFResult(
                        window=window,
                        params=params,
                        nav=r.get("nav", pd.Series(dtype=float)),
                        trades=list(r.get("trades", [])),
                        metrics=metrics,
                        train_metrics={},
                    )
                )

            if select_params_fn is not None:
                best_params = select_params_fn(train_results)
                best = next(
                    (x for x in train_results if x.params == best_params),
                    train_results[0],
                )
            else:
                best = max(
                    train_results,
                    key=lambda x: (
                        x.metrics.get("sharpe", float("-inf")) if x.metrics else float("-inf")
                    ),
                )
                best_params = best.params

            r = strategy_fn(bars, best_params, window.test_start, window.test_end)
            test_metrics = compute_metrics(
                r.get("nav", pd.Series(dtype=float)),
                trades=r.get("trades", []),
                benchmark_nav=r.get("benchmark_nav"),
            )

            oos_results.append(
                WFResult(
                    window=window,
                    params=best_params,
                    nav=r.get("nav", pd.Series(dtype=float)),
                    trades=list(r.get("trades", [])),
                    metrics=test_metrics,
                    train_metrics=best.metrics,
                )
            )

        return oos_results

    def summary(self, results: list[WFResult]) -> pd.DataFrame:
        """One-row-per-window summary DataFrame for quick inspection."""
        rows: list[dict[str, Any]] = []
        for r in results:
            row: dict[str, Any] = {
                "window": r.window.name,
                "test_start": r.window.test_start,
                "test_end": r.window.test_end,
            }
            for k, v in r.params.items():
                row[f"param_{k}"] = v
            for k, v in r.metrics.items():
                row[f"oos_{k}"] = v
            for k, v in r.train_metrics.items():
                row[f"train_{k}"] = v
            rows.append(row)
        return pd.DataFrame(rows)

    def combined_nav(self, results: list[WFResult]) -> pd.Series:
        """Stitch OOS NAV segments into a single continuous curve.

        Each subsequent segment is rescaled so it begins at the previous
        segment's last value, producing a synthetic "live equivalent"
        OOS curve for plotting and aggregate metric computation.
        """
        pieces = [r.nav for r in results if r.nav is not None and not r.nav.empty]
        if not pieces:
            return pd.Series(dtype=float)
        combined = pieces[0].astype(float).copy()
        for seg in pieces[1:]:
            seg = seg.astype(float)
            if seg.iloc[0] == 0:
                continue
            scale = combined.iloc[-1] / seg.iloc[0]
            combined = pd.concat([combined, seg * scale])
        combined = combined[~combined.index.duplicated(keep="first")]
        return combined.sort_index()
