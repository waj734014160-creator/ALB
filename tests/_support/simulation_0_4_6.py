"""Shared inputs for the ALB 0.4.6 control-period and ROS2 API tests.

The physical one-node plant, the small bearing specifications, the controller
sections, and the loads are reused from the frozen 0.4.6 default-path
reference generator. With ``TIME_STEP = 2e-5`` s these configurations run
stably in a fraction of a second per step, so the API tests can exercise real
coupled simulations instead of mocks.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
import copy
from typing import Any
import warnings

import numpy as np

import ALB
from ALB.contracts import LifecycleState, UnitSystem
from ALB.dynamics.rotor import RossRotor
from tools.reference.generate_coupling_default_path_0_4_6_reference import (
    FUZZY_CONTROL,
    FUZZY_RULE_ROOT,
    LOADS,
    PID_CONTROL,
    TIME_STEP,
    SinglePlant,
    active_spec,
    liquid_film_spec,
)


SPEED = 2.0 * np.pi * 50.0
"""Rotor speed in rad/s used by every RossRotor built here."""

NEW_METADATA_KEYS = frozenset(
    {
        "integrator",
        "time_step",
        "control_periods",
        "time_step_adjustment",
        "ros2_options",
        "initial_rotor_state",
    }
)
"""Result metadata keys that 0.4.6 adds only for non-default runs."""


def ross_rotor(time_step: float = TIME_STEP) -> RossRotor:
    """Return a continuous RossRotor around the physical one-node plant."""

    return RossRotor(SinglePlant(), speed=SPEED, dt=time_step)


def pid_spec(
    control_period: float | None,
    time_step: float = TIME_STEP,
) -> dict[str, Any]:
    """Return the active PID bearing spec with an optional ``control_period``."""

    control = copy.deepcopy(PID_CONTROL)
    if control_period is not None:
        control["control_period"] = control_period
    return active_spec(control, time_step)


def inherited_pid_child(control_period: float | None) -> dict[str, Any]:
    """Return an inline multi-pad PID child that inherits step, node, units."""

    spec = pid_spec(control_period)
    for key in ("time_step", "node", "unit_system"):
        spec.pop(key)
    return spec


def pid_config(
    control_period: float | None,
    time_step: float = TIME_STEP,
) -> ALB.BearingConfig:
    """Return a validated active PID bearing configuration."""

    return ALB.BearingConfig(pid_spec(control_period, time_step))


def fuzzy_config(
    control_period: float | None,
    time_step: float = TIME_STEP,
) -> ALB.BearingConfig:
    """Return a validated active fuzzy-PID configuration with its rule file."""

    control = copy.deepcopy(FUZZY_CONTROL)
    if control_period is not None:
        control["control_period"] = control_period
    return ALB.BearingConfig(
        active_spec(control, time_step),
        resource_root=FUZZY_RULE_ROOT,
    )


def liquid_config(time_step: float = TIME_STEP, **overrides: Any) -> ALB.BearingConfig:
    """Return the small dimensional liquid-film configuration."""

    spec = liquid_film_spec(time_step)
    spec.update(overrides)
    return ALB.BearingConfig(spec)


def simulation_config(
    *bearings: ALB.BearingConfig,
    steps: int,
    time_step: float = TIME_STEP,
    rotor: Any = None,
    loads: Sequence[Mapping[str, Any]] = LOADS,
    **kwargs: Any,
) -> ALB.SimulationConfig:
    """Return a SimulationConfig mounting each bearing at nodes 0, 1, ..."""

    return ALB.SimulationConfig(
        rotor=ross_rotor(time_step) if rotor is None else rotor,
        mounts=tuple(
            ALB.BearingMount(bearing, node)
            for node, bearing in enumerate(bearings)
        ),
        time_step=time_step,
        steps=steps,
        loads=tuple(loads),
        **kwargs,
    )


@contextmanager
def recorded_warnings() -> Iterator[list[warnings.WarningMessage]]:
    """Record every warning raised in the block, ignoring global filters."""

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield caught


def adjustment_warnings(
    caught: Sequence[warnings.WarningMessage],
) -> list[warnings.WarningMessage]:
    """Return only the recorded ``TimeStepAdjustedWarning`` entries."""

    return [
        item
        for item in caught
        if issubclass(item.category, ALB.TimeStepAdjustedWarning)
    ]


def active_runtime(simulation: ALB.RotorBearingSimulation, index: int = 0) -> Any:
    """Return the native active-bearing runtime of one simulation mount."""

    return simulation._coupling.bindings[index].bearing


class ProtocolRotor:
    """Minimal ``RotorProtocol`` double without any owner-only hooks.

    It has no ``_retime_for_owner`` and no continuous-system hooks, so it
    cannot be retimed by a control-period adjustment or integrated by ROS2.
    """

    unit_system = UnitSystem.DIMENSIONAL
    lifecycle_state = LifecycleState.READY

    def __init__(self, dt: float) -> None:
        self.dt = dt

    def _reset_for_owner(self, initial_state: Any = None) -> None:
        del initial_state

    def input_force2node(
        self,
        time: Any,
        force: Any,
        node: Any,
        initial_state: Any = None,
        *,
        force0: Any = None,
    ) -> None:
        del time, force, node, initial_state, force0

    def input_load(self, value: Any) -> None:
        del value

    def advance(self) -> np.ndarray:
        return np.zeros(4)

    def current_state(self, node: Any = None) -> np.ndarray:
        del node
        return np.zeros(4)

    def output(self, node: Any = None) -> object:
        count = 1 if node is None else len(np.atleast_1d(node))
        return {
            "uxy": np.zeros((count, 2)),
            "uxyt": np.zeros((count, 2)),
        }


__all__ = [
    "FUZZY_RULE_ROOT",
    "LOADS",
    "NEW_METADATA_KEYS",
    "ProtocolRotor",
    "SPEED",
    "TIME_STEP",
    "active_runtime",
    "adjustment_warnings",
    "fuzzy_config",
    "inherited_pid_child",
    "liquid_config",
    "pid_config",
    "pid_spec",
    "recorded_warnings",
    "ross_rotor",
    "simulation_config",
]
