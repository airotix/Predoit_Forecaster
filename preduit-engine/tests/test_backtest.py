"""Unit tests for backtest metric functions."""

import numpy as np
import pytest

from preduit_engine.backtest import (
    compute_bias,
    compute_interval_coverage,
    compute_wmape,
    format_accuracy_api_payload,
)


def test_compute_wmape_perfect():
    actuals = np.array([100.0, 200.0])
    forecasts = np.array([100.0, 200.0])
    assert compute_wmape(actuals, forecasts) == 0.0


def test_compute_wmape_known_value():
    actuals = np.array([100.0, 100.0])
    forecasts = np.array([90.0, 110.0])
    assert compute_wmape(actuals, forecasts) == 10.0


def test_compute_bias_over_forecast():
    actuals = np.array([100.0, 100.0])
    forecasts = np.array([110.0, 110.0])
    assert compute_bias(actuals, forecasts) == 10.0


def test_compute_interval_coverage():
    actuals = np.array([5.0, 15.0, 25.0])
    lower = np.array([0.0, 10.0, 20.0])
    upper = np.array([10.0, 20.0, 30.0])
    assert compute_interval_coverage(actuals, lower, upper) == 100.0


def test_format_accuracy_api_payload_empty():
    payload = format_accuracy_api_payload(None)
    assert payload["headline"]["wmape"] is None
    assert payload["byModelType"] == []


def test_format_accuracy_api_payload_with_data():
    latest = {
        "completedAt": "2025-01-01T00:00:00",
        "summary": {"wmape": 12.5, "bias": -2.0, "coverage80": 78.0, "skuCount": 100},
        "folds": [{"foldMonth": "2024-12", "wmape": 12.5, "bias": -2.0, "coverage80": 78.0}],
        "breakdown": [
            {
                "dimension": "model_type",
                "dimensionValue": "SARIMA_M",
                "wmape": 10.0,
                "bias": -1.0,
                "coverage80": 80.0,
                "skuCount": 50,
            },
            {
                "dimension": "famille",
                "dimensionValue": "SHIRTS",
                "wmape": 15.0,
                "bias": 0.0,
                "coverage80": 75.0,
                "skuCount": 30,
            },
        ],
    }
    payload = format_accuracy_api_payload(latest)
    assert payload["headline"]["wmape"] == 12.5
    assert len(payload["byModelType"]) == 1
    assert payload["byModelType"][0]["modelType"] == "SARIMA_M"
    assert len(payload["byCategory"]) == 1
