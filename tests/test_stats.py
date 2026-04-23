"""Wilson score interval + cost-per-success regression tests."""
from __future__ import annotations

import math

import pandas as pd

from harness_eng.analysis import aggregate, wilson_ci


def test_wilson_ci_7_of_10():
    """Reference value: Wilson 95% CI for 7/10 at z=1.96 ≈ (0.3968, 0.8922)."""
    low, high = wilson_ci(7, 10)
    assert math.isclose(low, 0.3968, abs_tol=1e-3), low
    assert math.isclose(high, 0.8922, abs_tol=1e-3), high


def test_wilson_ci_extremes_bounded():
    low, high = wilson_ci(0, 10)
    assert low == 0.0
    assert 0.0 < high < 1.0

    low, high = wilson_ci(10, 10)
    assert high == 1.0
    assert 0.0 < low < 1.0


def test_wilson_ci_zero_trials_uninformative():
    low, high = wilson_ci(0, 0)
    assert low == 0.0
    assert high == 1.0


def test_aggregate_includes_ci_and_cost_per_success():
    """aggregate() emits ci_low, ci_high, cost_per_success_usd columns."""
    rows = [
        {
            "harness": "single_shot", "task_id": "t1", "success": True,
            "field_accuracy": 1.0, "input_tokens": 100, "output_tokens": 50,
            "tool_calls": 1, "wall_clock_s": 0.5, "cost_usd": 0.001,
            "per_field": {"a": True},
        },
        {
            "harness": "single_shot", "task_id": "t2", "success": False,
            "field_accuracy": 0.5, "input_tokens": 120, "output_tokens": 60,
            "tool_calls": 1, "wall_clock_s": 0.6, "cost_usd": 0.0012,
            "per_field": {"a": False},
        },
    ]
    df = pd.DataFrame(rows)
    agg = aggregate(df)
    h = agg.df_harness.iloc[0]
    assert "ci_low" in agg.df_harness.columns
    assert "ci_high" in agg.df_harness.columns
    assert "cost_per_success_usd" in agg.df_harness.columns
    assert h["trials"] == 2
    assert h["successes"] == 1
    assert math.isclose(h["cost_per_success_usd"], 0.0022, abs_tol=1e-9)
    assert 0.0 <= h["ci_low"] <= h["success_rate"] <= h["ci_high"] <= 1.0


def test_aggregate_zero_successes_cost_per_success_nan():
    rows = [
        {
            "harness": "h", "task_id": "t1", "success": False,
            "field_accuracy": 0.0, "input_tokens": 10, "output_tokens": 5,
            "tool_calls": 0, "wall_clock_s": 0.1, "cost_usd": 0.0005,
            "per_field": {"a": False},
        },
    ]
    df = pd.DataFrame(rows)
    agg = aggregate(df)
    h = agg.df_harness.iloc[0]
    assert math.isnan(h["cost_per_success_usd"])
