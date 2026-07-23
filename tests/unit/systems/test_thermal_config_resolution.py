"""Regression tests for shared ALB thermal configuration materialization."""

from __future__ import annotations

import warnings

import pytest

from ALB.config import (
    ALBConfig,
    FPBConfig,
    NodimALBConfig,
    ThermalConfig,
    build_thermal_config,
)
from ALB.systems.alb.builder import ALBBuilder
from ALB.systems.alb.factories import _nodim_thermal_config


@pytest.mark.parametrize("enabled", [False, True])
def test_dimensional_and_nondimensional_resolvers_preserve_explicit_mode(
    enabled,
) -> None:
    servo = "static" if not enabled else "moog_2nd"
    thermal = ThermalConfig(transient_enabled=enabled)
    dimensional = ALBConfig(
        servo=servo,
        pad_config=FPBConfig(thermal_config=thermal),
    )
    nondimensional = NodimALBConfig(servo=servo)

    dimensional_resolved = ALBBuilder(dimensional)._create_thermal_config()
    nondimensional_resolved = _nodim_thermal_config(
        nondimensional,
        thermal,
    )

    assert dimensional_resolved.transient_enabled is enabled
    assert dimensional_resolved.args_nodim is False
    assert dimensional_resolved.dt == dimensional.dt
    assert nondimensional_resolved.transient_enabled is enabled
    assert nondimensional_resolved.args_nodim is True
    assert nondimensional_resolved.dt == nondimensional.dt


def test_steady_newton_thermal_mode_is_not_forced_to_transient() -> None:
    config = ALBConfig(
        servo="moog_2nd",
        pad_config=FPBConfig(
            thermal_config=ThermalConfig(
                transient_enabled=False,
                iter_method="newton",
            )
        ),
    )

    with pytest.warns(RuntimeWarning, match="dynamic servo"):
        resolved = ALBBuilder(config)._create_thermal_config()

    assert resolved.transient_enabled is False
    assert resolved.iter_method == "newton"


def test_fluent_pad_override_is_the_dimensional_thermal_source() -> None:
    original = FPBConfig(
        thermal_config=ThermalConfig(t_in=35.0, transient_enabled=False)
    )
    override = FPBConfig(
        thermal_config=ThermalConfig(t_in=52.0, transient_enabled=False)
    )
    builder = ALBBuilder(ALBConfig(servo="static", pad_config=original))
    builder.set_pads_config(override)

    resolved = builder._create_thermal_config()

    assert resolved.t_in == 52.0
    assert resolved is not override.thermal_config


@pytest.mark.parametrize(
    ("servo", "transient_enabled", "message"),
    [
        ("moog_2nd", False, "dynamic servo"),
        ("static", True, "static servo"),
    ],
)
def test_mixed_fidelity_thermal_modes_warn_once(
    servo,
    transient_enabled,
    message,
) -> None:
    config = ALBConfig(
        servo=servo,
        pad_config=FPBConfig(
            thermal_config=ThermalConfig(
                transient_enabled=transient_enabled
            )
        ),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ALBBuilder(config)._create_thermal_config()

    matching = [
        item
        for item in caught
        if issubclass(item.category, RuntimeWarning)
        and message in str(item.message)
    ]
    assert len(matching) == 1


@pytest.mark.parametrize(
    ("servo", "transient_enabled"),
    [("static", False), ("moog_2nd", True)],
)
def test_consistent_thermal_modes_do_not_warn(
    servo,
    transient_enabled,
) -> None:
    config = ALBConfig(
        servo=servo,
        pad_config=FPBConfig(
            thermal_config=ThermalConfig(
                transient_enabled=transient_enabled
            )
        ),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ALBBuilder(config)._create_thermal_config()

    assert caught == []


def test_typed_none_is_rejected_but_legacy_none_migrates_to_false() -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        ThermalConfig(transient_enabled=None)

    migrated = build_thermal_config(
        True,
        {"transient_enabled": None},
    )
    assert migrated.transient_enabled is False
