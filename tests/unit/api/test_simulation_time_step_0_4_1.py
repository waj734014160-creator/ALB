"""Time-step and removed-capability gates introduced in ALB 0.4.1."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import ALB
from ALB.api.building import _active_config, _thermal_config
from ALB.api.config import SCHEMA_VERSION
from ALB.contracts import LifecycleState, UnitSystem


class _Rotor:
    """Minimal rotor protocol used for construction-time validation."""

    unit_system = UnitSystem.DIMENSIONAL
    lifecycle_state = LifecycleState.READY

    def __init__(self, dt: float) -> None:
        self.dt = dt

    def _reset_for_owner(self, initial_state=None) -> None:
        del initial_state

    def input_force2node(
        self,
        time,
        force,
        node,
        initial_state=None,
        *,
        force0=None,
    ) -> None:
        del time, force, node, initial_state, force0

    def input_load(self, value) -> None:
        del value

    def advance(self) -> np.ndarray:
        return np.zeros(4)

    def current_state(self, node=None) -> np.ndarray:
        del node
        return np.zeros(4)

    def output(self, node=None) -> object:
        count = 1 if node is None else len(np.atleast_1d(node))
        return {
            "uxy": np.zeros((count, 2)),
            "uxyt": np.zeros((count, 2)),
        }


def _liquid_spec(time_step: float) -> dict[str, object]:
    return {
        "family": "liquid_film",
        "unit_system": "dimensional",
        "time_step": time_step,
        "node": 0,
        "film": {},
        "restrictors": None,
        "thermal": None,
    }


def _mount(config: ALB.BearingConfig) -> tuple[ALB.BearingMount, ...]:
    return (ALB.BearingMount(config, 0),)


def test_patch_release_keeps_the_0_4_configuration_schema() -> None:
    assert ALB.__version__ == "0.4.4"
    assert SCHEMA_VERSION == "0.4.0"


def test_simulation_rejects_rotor_time_step_mismatch_with_path() -> None:
    config = ALB.BearingConfig(_liquid_spec(1.0e-3))

    with pytest.raises(ALB.ConfigurationError, match=r"rotor\.dt"):
        ALB.SimulationConfig(
            rotor=_Rotor(2.0e-3),
            mounts=_mount(config),
            time_step=1.0e-3,
            steps=1,
        )


def test_simulation_rejects_mount_time_step_mismatch_with_path() -> None:
    config = ALB.BearingConfig(_liquid_spec(2.0e-3))

    with pytest.raises(
        ALB.ConfigurationError,
        match=r"mounts\[0\]\.config\.time_step",
    ):
        ALB.SimulationConfig(
            rotor=_Rotor(1.0e-3),
            mounts=_mount(config),
            time_step=1.0e-3,
            steps=1,
        )


def test_simulation_rejects_nested_multi_pad_time_step_mismatch() -> None:
    multi_pad = ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "pads": [
                _liquid_spec(1.0e-3),
                {
                    "family": "multi_pad",
                    "pads": [
                        _liquid_spec(2.0e-3),
                    ],
                },
            ],
        }
    )

    with pytest.raises(
        ALB.ConfigurationError,
        match=r"mounts\[0\]\.config\.pads\[1\]\.pads\[0\]\.time_step",
    ):
        ALB.SimulationConfig(
            rotor=_Rotor(1.0e-3),
            mounts=_mount(multi_pad),
            time_step=1.0e-3,
            steps=1,
        )


def test_materialized_controller_valve_and_thermal_share_bearing_step() -> None:
    time_step = 1.25e-3
    config = ALB.BearingConfig(
        {
            "family": "active_lubricated",
            "unit_system": "dimensional",
            "time_step": time_step,
            "node": 0,
            "film": {},
            "restrictors": {
                "positions": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            },
            "tank": {},
            "valve": {"model": "second_order"},
            "control": {
                "mode": "pid",
                "gains": {"kp": 1.0, "ki": 0.0, "kd": 0.0},
            },
            "thermal": {"transient_enabled": False},
            "transforms": {},
        }
    )

    materialized = _active_config(config)

    assert materialized.dt == time_step
    assert materialized.servo_config.dt == time_step
    assert materialized.controller_config is not None
    assert materialized.controller_config.dt == time_step
    assert materialized.thermal_config is not None
    assert materialized.thermal_config.dt == time_step
    assert _thermal_config(config).dt == time_step


def test_tilting_pad_implementation_is_absent_from_active_package_source() -> None:
    package_root = Path(ALB.__file__).resolve().parent
    forbidden = (
        "TiltingPadHydrodynamicPad",
        "tilting_pads_bearing",
        "tilting_pads_bearings",
        "solve_tilting_pad_equilibrium",
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in package_root.rglob("*.py")
    )

    for name in forbidden:
        assert name not in source
