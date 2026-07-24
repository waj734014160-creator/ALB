"""Regression tests for mixed-bearing configuration ownership."""

from __future__ import annotations

import copy

import numpy as np

from ALB.config import HydConfig
from ALB.physics.bearing.solver import _DimensionalMixedFilmRuntime


def _small_config(**overrides) -> HydConfig:
    values = {
        "nx": 3,
        "nz": 3,
        "e": 0.2,
        "angle": 30.0,
        "freq": 50.0,
        "vf": 1.5,
    }
    values.update(overrides)
    return HydConfig(**values)


def test_default_mixed_bearings_do_not_share_configuration_state() -> None:
    first = _DimensionalMixedFilmRuntime()
    second = _DimensionalMixedFilmRuntime()

    first.input_args["vf"] = 7.0

    assert second.input_args["vf"] == 1.0
    assert first.input_args.data is not second.input_args.data


def test_constructor_does_not_modify_caller_hyd_config() -> None:
    config = _small_config(vib=True, dxt=None, dyt=None)
    before = copy.deepcopy(config.to_dict())

    bearing = _DimensionalMixedFilmRuntime(config)

    assert config.to_dict() == before
    assert bearing.input_args.data is not config
    assert bearing.input_args["dxt"] is not None
    assert bearing.input_args["dyt"] is not None


def test_reusing_original_config_after_enabling_vibration_recomputes_velocity() -> None:
    config = _small_config(vib=False, dxt=None, dyt=None)
    steady = _DimensionalMixedFilmRuntime(config)
    assert steady.input_args["dxt"] == 0.0
    assert steady.input_args["dyt"] == 0.0
    assert config.dxt is None
    assert config.dyt is None

    config.vib = True
    vibrating = _DimensionalMixedFilmRuntime(config)
    angular_speed = config.freq * 2.0 * np.pi
    expected_dxt = (
        -config.e
        * config.c
        * config.vf
        * angular_speed
        * np.cos(config.angle_rad)
    )
    expected_dyt = (
        -config.e
        * config.c
        * config.vf
        * angular_speed
        * np.sin(config.angle_rad)
    )

    assert vibrating.input_args["dxt"] == expected_dxt
    assert vibrating.input_args["dyt"] == expected_dyt
    assert config.dxt is None
    assert config.dyt is None
