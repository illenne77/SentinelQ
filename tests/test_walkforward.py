"""Tests for sentinelq.research.walkforward."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from sentinelq.research.walkforward import (
    WalkForward,
    WFResult,
    WFWindow,
    compute_metrics,
)


def _drift_nav(
    start: str, end: str, daily: float = 0.0005, noise: float = 0.005, seed: int = 0
) -> pd.Series:
    """Synthetic NAV with constant drift plus small Gaussian noise.

    Noise is required so std-of-returns is non-zero and Sharpe is well defined.
    """
    idx = pd.date_range(start, end, freq="B")
    rng = np.random.default_rng(seed)
    rets = rng.normal(loc=daily, scale=noise, size=len(idx))
    nav = (1.0 + pd.Series(rets, index=idx)).cumprod()
    return nav


def test_compute_metrics_required_keys_present():
    nav = _drift_nav("2023-01-01", "2024-01-01")
    m = compute_metrics(nav, trades=[1, 2, 3])
    for key in ("cagr", "sharpe", "max_dd", "calmar", "hit_rate", "n_trades"):
        assert key in m, f"missing required KPI key: {key}"
    assert m["n_trades"] == 3
    assert "hit_month" in m


def test_compute_metrics_drift_is_positive_sharpe():
    nav = _drift_nav("2022-01-01", "2024-01-01", daily=0.001)
    m = compute_metrics(nav)
    assert m["cagr"] > 0
    assert m["sharpe"] > 0
    assert m["max_dd"] <= 0


def test_compute_metrics_empty_or_short_returns_defaults():
    out = compute_metrics(pd.Series(dtype=float))
    assert out["n_days"] == 0
    assert out["sharpe"] == 0.0
    assert out["n_trades"] == 0


def test_compute_metrics_with_benchmark_emits_alpha():
    strat = _drift_nav("2023-01-01", "2024-01-01", daily=0.001)
    bench = _drift_nav("2023-01-01", "2024-01-01", daily=0.0005)
    m = compute_metrics(strat, benchmark_nav=bench)
    assert m["alpha_ann"] is not None
    assert m["cagr_bench"] is not None
    assert m["alpha_ann"] == pytest.approx(m["cagr"] - m["cagr_bench"], rel=1e-9)
    assert m["alpha_ann"] > 0


def test_walkforward_runs_all_windows_and_picks_best_by_sharpe():
    windows = [
        WFWindow("W1", "2022-01-01", "2022-12-31", "2023-01-01", "2023-06-30"),
        WFWindow("W2", "2022-07-01", "2023-06-30", "2023-07-01", "2023-12-31"),
    ]

    def fake_strategy(bars: Any, params: dict[str, Any], start: str, end: str):
        return {
            "nav": _drift_nav(start, end, daily=params["daily"]),
            "trades": list(range(params.get("n_trades_seed", 5))),
        }

    wf = WalkForward(windows)
    results = wf.run(
        strategy_fn=fake_strategy,
        param_grid=[
            {"daily": 0.0001, "n_trades_seed": 4},
            {"daily": 0.001, "n_trades_seed": 7},
        ],
        bars=None,
        verbose=False,
    )

    assert len(results) == 2
    for r in results:
        assert isinstance(r, WFResult)
        assert r.params["daily"] == 0.001
        assert r.metrics["n_trades"] == 7
        assert r.metrics["sharpe"] > 0
        assert r.train_metrics

    summary = wf.summary(results)
    assert len(summary) == 2
    assert "param_daily" in summary.columns
    assert "oos_sharpe" in summary.columns
    assert "train_sharpe" in summary.columns


def test_walkforward_combined_nav_is_continuous():
    windows = [
        WFWindow("W1", "2022-01-01", "2022-06-30", "2022-07-01", "2022-12-31"),
        WFWindow("W2", "2022-07-01", "2022-12-31", "2023-01-01", "2023-06-30"),
    ]

    def fake_strategy(bars, params, start, end):
        return {"nav": _drift_nav(start, end, daily=0.0005), "trades": []}

    wf = WalkForward(windows)
    results = wf.run(
        strategy_fn=fake_strategy,
        param_grid=[{"daily": 0.0005}],
        bars=None,
        verbose=False,
    )
    combined = wf.combined_nav(results)
    assert len(combined) > 0
    # Drift dominates noise on average -> end > start.
    assert combined.iloc[-1] > combined.iloc[0]


def test_walkforward_empty_param_grid_raises():
    wf = WalkForward([WFWindow("W", "2022-01-01", "2022-06-30", "2022-07-01", "2022-12-31")])
    with pytest.raises(ValueError):
        wf.run(
            strategy_fn=lambda *a, **k: {"nav": pd.Series(dtype=float), "trades": []},
            param_grid=[],
            bars=None,
            verbose=False,
        )
