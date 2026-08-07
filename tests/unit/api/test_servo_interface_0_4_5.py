"""Strict public configuration tests for the 0.4.5 servovalve interface."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

import ALB
from ALB.api.building import _active_config
from ALB.config import (
    SecondOrderServoConfig,
    StaticServoConfig,
    TransferFunctionServoConfig,
)


EXAMPLE = Path("docs/api/examples/active_lubricated_pid.json5")


def _active_spec() -> dict:
    """Return a mutable copy of the documented active-bearing specification."""

    return deepcopy(ALB.load_bearing_config(EXAMPLE).to_dict()["spec"])


def test_second_order_json_uses_frequency_damping_and_optional_delay() -> None:
    spec = _active_spec()
    spec["valve"] = {
        "model": "second_order",
        "natural_frequency_hz": 80.0,
        "damping_ratio": 0.6,
        "delay": 0.002,
    }

    config = ALB.BearingConfig(spec)
    resolved = _active_config(config)

    assert isinstance(resolved.servo_config, SecondOrderServoConfig)
    assert resolved.servo_config.natural_frequency_hz == 80.0
    assert resolved.servo_config.damping_ratio == 0.6
    assert resolved.servo_config.delay == 0.002
    assert resolved.valve_model == "second_order"


def test_transfer_function_json_passes_complete_polynomials() -> None:
    spec = _active_spec()
    spec["valve"] = {
        "model": "transfer_function",
        "numerator": [2.0, 1.0],
        "denominator": [1.0, 3.0, 2.0],
    }

    config = ALB.BearingConfig(spec)
    resolved = _active_config(config)

    assert isinstance(resolved.servo_config, TransferFunctionServoConfig)
    assert resolved.servo_config.numerator == (2.0, 1.0)
    assert resolved.servo_config.denominator == (1.0, 3.0, 2.0)
    assert resolved.valve_model == "transfer_function"


def test_transfer_function_public_config_builds_and_calculates() -> None:
    spec = _active_spec()
    spec["valve"] = {
        "model": "transfer_function",
        "numerator": [1.0],
        "denominator": [1.0e-9, 2.0e-6, 1.0e-3, 1.0],
    }

    bearing = ALB.build_bearing(ALB.BearingConfig(spec))
    result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)

    assert result.force.shape == (2,)
    assert np.all(np.isfinite(result.force))


def test_static_json_builds_memoryless_unity_gain_valves() -> None:
    spec = _active_spec()
    spec["valve"] = {"model": "static"}

    config = ALB.BearingConfig(spec)
    resolved = _active_config(config)
    bearing = ALB.build_bearing(config)
    result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)

    assert isinstance(resolved.servo_config, StaticServoConfig)
    assert resolved.valve_model == "static"
    assert result.force.shape == (2,)
    assert np.all(np.isfinite(result.force))


@pytest.mark.parametrize(
    "valve",
    [
        {"model": "second_order", "damping_ratio": 0.7},
        {"model": "second_order", "natural_frequency_hz": 166.0},
        {
            "model": "second_order",
            "natural_frequency_hz": 166.0,
            "damping_ratio": 0.7,
            "response_time": 0.01,
        },
        {
            "model": "transfer_function",
            "numerator": [1.0],
        },
        {"model": "static", "delay": 0.0},
        {
            "model": "transfer_function",
            "numerator": [1.0, 0.0],
            "denominator": [1.0],
        },
        {
            "model": "transfer_function",
            "numerator": [1.0],
            "denominator": [1.0, 1.0],
            "delay": 0.001,
        },
        {
            "model": "second_order",
            "natural_frequency_hz": 166.0,
            "damping_ratio": 0.7,
            "numerator": [1.0],
        },
        {
            "model": "transfer_function",
            "numerator": [0.0],
            "denominator": [1.0],
        },
        {"model": "third_order"},
    ],
)
def test_invalid_or_removed_valve_contracts_are_rejected(valve: dict) -> None:
    spec = _active_spec()
    spec["valve"] = valve

    with pytest.raises(ALB.ConfigurationError):
        ALB.BearingConfig(spec)
