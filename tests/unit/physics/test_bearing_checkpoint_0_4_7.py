"""Checkpoint/restore contract of stateful bearing runtimes (ALB 0.4.7).

The predictor-corrector integrator trials stateful bearings through their
normal lifecycle and rolls each trial back. For every runtime family that
implements ``CheckpointableRuntimeProtocol`` these tests require:

* checkpoint -> three trials with different inputs (each rolled back) ->
  normal evaluation equals an undisturbed twin bit for bit, including the
  complete recursive state fingerprint (histories, controller memory and
  counters, thermal fields, restrictor buffers, lifecycle);
* a 20-step sequence with two rolled-back trials inserted before every
  committed evaluation (the 0.4.6 local check "A4") keeps every committed
  output, result snapshot, and the final state identical to the sequence
  without trials;
* after ``restore`` the lifecycle state and the readable output equal the
  state before the checkpoint, also after a trial that failed.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

import numpy as np
import pytest

import ALB
from ALB.api.building import build_runtime
from ALB.contracts import (
    BearingInput,
    CheckpointableRuntimeProtocol,
    DirectSpoolBearingInput,
    LifecycleState,
    UnitSystem,
    ValveOutput,
)
from ALB.core.checkpoint import RuntimeCheckpoint
from tests._support.dynamics.analytic_bearings import LinearSpoolProvider
from tests._support.dynamics.memory_bearings import (
    MemoryAnalyticBearing,
    SampledActiveAnalyticBearing,
)
from tests._support.state_fingerprint import fingerprint_diff, state_fingerprint
from tools.reference.generate_coupling_default_path_0_4_6_reference import (
    FUZZY_CONTROL,
    FUZZY_RULE_ROOT,
    PID_CONTROL,
    TIME_STEP,
    active_spec,
    liquid_film_spec,
)
from tools.reference.generate_coupling_staggered_pre_0_4_7_reference import (
    external_spool_spec,
    multi_pad_spec,
    thermal_active_spec,
    thermal_liquid_spec,
)


# Element and global matrices are solver scratch that every solve rebuilds.
SCRATCH = ("_matrixs", "_rights", "matrix_process", "elem_manager._right")
# Instrumentation counters of the analytic doubles survive rollbacks.
INSTRUMENTATION = ("lifecycle_evaluations", "controller_runs")


def _nondimensional_active_spec(mode: str, thermal: bool) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "family": "active_lubricated",
        "unit_system": "nondimensional",
        "time_step": 1.0e-3,
        "node": 0,
        "film": {
            "bearing_number": 1.0,
            "reference_bearing_number": 1.0,
            "length_ratio": 1.5,
            "arc_angle_deg": 80.0,
            "axial_length_ratio": 2.0,
            "circumferential_elements": 5,
            "axial_elements": 3,
            "solver_tolerance": 1.0e-7,
            "max_iterations": 100,
            "scale_viscosity": 0.0195,
            "scale_clearance": 1.2e-4,
            "scale_radius": 0.04,
            "scale_length": 0.06,
            "scale_pressure": 7.0e6,
            "scale_density": 872.0,
            "scale_speed_rpm": 3000.0,
        },
        "restrictors": {
            "positions": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            "base_flow_coefficient": 1.0,
            "spool_flow_coefficient": 1.0,
            "supply_pressure": 1.0,
            "tank_pressure": 0.0,
        },
        "tank": {"x_range": [0.49, 0.51], "z_range": [0.2, 0.8], "depth_ratio": 2.0},
        "valve": {"model": "second_order", "natural_frequency_hz": 166.0, "damping_ratio": 0.7},
        "control": (
            {"mode": "external_spool"}
            if mode == "external_spool"
            else {
                "mode": "pid",
                "frequency_hz": 50.0,
                "gains": {"kp": 1.0, "ki": 0.5, "kd": 0.01},
            }
        ),
        "transforms": {},
        "thermal": (
            {
                "t_in": 20.0,
                "miu0": 0.0195,
                "beta": 0.03,
                "tol": 1.0e-4,
                "transient_enabled": True,
            }
            if thermal
            else None
        ),
    }
    return spec


def _gas_spec() -> dict[str, Any]:
    return {
        "family": "gas_film",
        "unit_system": "dimensional",
        "time_step": TIME_STEP,
        "node": 0,
        "film": {"circumferential_elements": 8, "axial_elements": 3},
    }


class _StubSurrogateModel:
    """Stateless stand-in for a packaged ALBNN (no trained weights needed)."""

    def __init__(self) -> None:
        self._row: Any = None

    def input(self, displacement: Any, velocity: Any, spool: Any, *, nodim: bool) -> None:
        del nodim
        self._row = (
            np.asarray(displacement, dtype=float),
            np.asarray(velocity, dtype=float),
            np.asarray(spool, dtype=float),
        )

    def output(self, *, nodim: bool) -> np.ndarray:
        del nodim
        displacement, velocity, spool = self._row
        return -3.0e6 * displacement - 2.0e3 * velocity + 50.0 * spool


def _surrogate_runtime() -> Any:
    from ALB.surrogate.runtime import SurrogateBearingRuntime

    return SurrogateBearingRuntime(
        _StubSurrogateModel(),
        unit_system="dimensional",
        node_link=0,
        external_spool=False,
    )


def _config_runtime(spec: dict[str, Any], resource_root: Any = None) -> Callable[[], Any]:
    def build() -> Any:
        config = (
            ALB.BearingConfig(copy.deepcopy(spec))
            if resource_root is None
            else ALB.BearingConfig(copy.deepcopy(spec), resource_root=resource_root)
        )
        return build_runtime(config)

    return build


def _liquid_with_restrictors() -> dict[str, Any]:
    spec = liquid_film_spec()
    spec["restrictors"] = {"positions": [[0.5, 0.5]], "flow_coefficient": 0.05}
    return spec


def _liquid_with_save_histories() -> dict[str, Any]:
    spec = _liquid_with_restrictors()
    spec["film"] = {**spec["film"], "save_pressure": True, "save_thickness": True}
    return spec


def _pid_with_control_period() -> dict[str, Any]:
    # m = 3: the controller samples every third evaluation and holds the
    # command (``_held_command``) in between.
    return active_spec({**copy.deepcopy(PID_CONTROL), "control_period": 3 * TIME_STEP})


def _thermal_external_spool() -> dict[str, Any]:
    spec = external_spool_spec()
    spec["thermal"] = {"transient_enabled": True}
    return spec


FAMILIES: dict[str, tuple[Callable[[], Any], int]] = {
    # name: (factory, steps of the A4 sequence; 20 unless noted).
    "liquid_film": (_config_runtime(liquid_film_spec()), 20),
    "liquid_film_restrictors": (_config_runtime(_liquid_with_restrictors()), 20),
    "liquid_film_save_histories": (_config_runtime(_liquid_with_save_histories()), 20),
    "thermal_transient": (_config_runtime(thermal_liquid_spec(True)), 20),
    "thermal_steady": (_config_runtime(thermal_liquid_spec(False)), 20),
    "active_pid": (_config_runtime(active_spec(copy.deepcopy(PID_CONTROL))), 20),
    "active_pid_control_period": (_config_runtime(_pid_with_control_period()), 20),
    "active_fuzzy_pid": (
        _config_runtime(active_spec(copy.deepcopy(FUZZY_CONTROL)), FUZZY_RULE_ROOT),
        20,
    ),
    "active_uncontrolled": (_config_runtime(active_spec({"mode": "uncontrolled"})), 20),
    "active_pid_thermal": (_config_runtime(thermal_active_spec()), 20),
    "external_spool_thermal": (_config_runtime(_thermal_external_spool()), 20),
    "nondimensional_active_pid": (
        _config_runtime(_nondimensional_active_spec("pid", thermal=False)),
        20,
    ),
    "nondimensional_external_spool_thermal": (
        _config_runtime(_nondimensional_active_spec("external_spool", thermal=True)),
        # This small nondimensional transient thermal model stops converging
        # at the fifth input of ``_dto`` even without any trial, so its A4
        # sequence covers the first four steps.
        4,
    ),
    "multi_pad_children": (_config_runtime(multi_pad_spec()), 20),
    "gas_film": (_config_runtime(_gas_spec()), 20),
    "surrogate_fixed_spool": (_surrogate_runtime, 20),
    "memory_double": (
        lambda: MemoryAnalyticBearing(
            stiffness=3.0e4, damping=40.0, scale=6.0e-4, alpha=2.0, tau=5.0e-3
        ),
        20,
    ),
    "sampled_active_double": (
        lambda: SampledActiveAnalyticBearing(
            stiffness=3.0e4,
            damping=40.0,
            spool_gain=200.0,
            gain=500.0,
            tau=5.0e-3,
            control_steps=3,
        ),
        20,
    ),
}


def _ready(runtime: Any) -> Any:
    reset = getattr(runtime, "_reset_for_owner", None)
    if runtime.lifecycle_state is not LifecycleState.READY and callable(reset):
        reset()
    return runtime


def _dto(runtime: Any, step: int, scale: float = 1.0) -> Any:
    """Return a deterministic input for ``step``; ``scale`` perturbs trials."""

    unit = UnitSystem.coerce(runtime.unit_system)
    nondimensional = unit is UnitSystem.NONDIMENSIONAL
    length = 0.05 if nondimensional else 2.0e-6
    speed = 0.02 if nondimensional else 2.0e-4
    phase = 0.4 * step
    displacement = scale * length * np.array([np.cos(phase), -1.5 + np.sin(phase)])
    velocity = scale * speed * np.array([-np.sin(phase), np.cos(phase)])
    time = step * (1.0e-3 if nondimensional else TIME_STEP)
    bearing_input = BearingInput(displacement, velocity, time, unit)
    if runtime.input_dto_type is DirectSpoolBearingInput:
        spool = np.clip(np.array([0.2 * np.sin(phase), 0.1]) * scale, -1.0, 1.0)
        return DirectSpoolBearingInput(
            bearing_input,
            ValveOutput(spool, time, UnitSystem.NONDIMENSIONAL),
        )
    return bearing_input


def _build(name: str) -> Any:
    return _ready(FAMILIES[name][0]())


def _assert_same_result(left: Any, right: Any) -> None:
    assert left.values.keys() == right.values.keys()
    for key in left.values:
        a, b = left.values[key], right.values[key]
        try:
            np.testing.assert_array_equal(np.asarray(a, dtype=float), np.asarray(b, dtype=float), err_msg=key)
        except (TypeError, ValueError):
            assert repr(a) == repr(b), key
    assert repr(dict(left.metadata)) == repr(dict(right.metadata))


def _assert_same_state(left: Any, right: Any) -> None:
    difference = fingerprint_diff(
        state_fingerprint(left),
        state_fingerprint(right),
        ignore=INSTRUMENTATION,
    )
    assert difference == []


@pytest.mark.parametrize("name", tuple(FAMILIES))
def test_family_implements_checkpoint_protocol(name: str) -> None:
    runtime = _build(name)
    assert isinstance(runtime, CheckpointableRuntimeProtocol)


@pytest.mark.parametrize("name", tuple(FAMILIES))
def test_three_trials_then_restore_equal_an_undisturbed_twin(name: str) -> None:
    disturbed, twin = _build(name), _build(name)
    for runtime in (disturbed, twin):
        runtime.step(_dto(runtime, 0))
        runtime.step(_dto(runtime, 1))
    before = state_fingerprint(disturbed)
    token = disturbed.checkpoint()
    for scale in (1.6, 0.3, -0.8):
        try:
            disturbed.step(_dto(disturbed, 2, scale))
        finally:
            disturbed.restore(token)
    assert fingerprint_diff(
        before,
        state_fingerprint(disturbed),
        ignore=SCRATCH + INSTRUMENTATION,
    ) == []

    disturbed_output = disturbed.step(_dto(disturbed, 2))
    twin_output = twin.step(_dto(twin, 2))
    np.testing.assert_array_equal(disturbed_output.force, twin_output.force)
    assert disturbed_output.time == twin_output.time
    _assert_same_result(disturbed.result_snapshot(), twin.result_snapshot())
    _assert_same_state(disturbed, twin)


@pytest.mark.parametrize("name", tuple(FAMILIES))
def test_two_trials_per_step_keep_the_committed_sequence(name: str) -> None:
    steps = FAMILIES[name][1]
    disturbed, twin = _build(name), _build(name)
    for step in range(steps):
        if step > 0:
            token = disturbed.checkpoint()
            for scale in (1.3, 0.7):
                try:
                    disturbed.step(_dto(disturbed, step, scale))
                finally:
                    disturbed.restore(token)
        disturbed_output = disturbed.step(_dto(disturbed, step))
        twin_output = twin.step(_dto(twin, step))
        np.testing.assert_array_equal(
            disturbed_output.force,
            twin_output.force,
            err_msg=f"step {step}",
        )
        _assert_same_result(disturbed.result_snapshot(), twin.result_snapshot())
    _assert_same_state(disturbed, twin)


@pytest.mark.parametrize("name", tuple(FAMILIES))
def test_restore_returns_lifecycle_and_output_after_a_failed_trial(name: str) -> None:
    runtime = _build(name)
    runtime.step(_dto(runtime, 0))
    committed = runtime.output()
    state = runtime.lifecycle_state
    token = runtime.checkpoint()

    runtime.step(_dto(runtime, 1, 1.4))
    runtime.restore(token)
    assert runtime.lifecycle_state is state
    assert runtime.output() is committed

    # A trial that fails after latching its input leaves the runtime
    # RUNNING or FAILED; restore returns it to the committed state.
    runtime.input(_dto(runtime, 1))
    assert runtime.lifecycle_state is LifecycleState.RUNNING
    runtime.restore(token)
    assert runtime.lifecycle_state is state
    assert runtime.output() is committed


def test_failed_film_trial_is_rolled_back() -> None:
    runtime = _build("thermal_transient")
    twin = _build("thermal_transient")
    for item in (runtime, twin):
        item.step(_dto(item, 0))
    token = runtime.checkpoint()
    impossible = BearingInput(
        np.array([2.0e-3, 0.0]),  # eccentricity far above one clearance
        np.zeros(2),
        TIME_STEP,
        UnitSystem.DIMENSIONAL,
    )
    with pytest.raises(ValueError):
        try:
            runtime.step(impossible)
        finally:
            assert runtime.lifecycle_state is LifecycleState.FAILED
            runtime.restore(token)
    assert runtime.lifecycle_state is LifecycleState.READY
    np.testing.assert_array_equal(
        runtime.step(_dto(runtime, 1)).force,
        twin.step(_dto(twin, 1)).force,
    )
    _assert_same_state(runtime, twin)


def test_tokens_are_bound_to_their_runtime() -> None:
    first, second = _build("liquid_film"), _build("liquid_film")
    with pytest.raises(ValueError, match="another runtime"):
        second.restore(first.checkpoint())
    with pytest.raises(TypeError, match="checkpoint"):
        first.restore(object())
    assert isinstance(first.checkpoint(), RuntimeCheckpoint)


def test_thermal_wrapper_checkpoint_is_not_forwarded_to_its_film() -> None:
    runtime = _build("thermal_transient")
    token = runtime.checkpoint()
    assert token.owner is runtime
    with pytest.raises(ValueError, match="another runtime"):
        runtime.bearing.restore(token)


def test_spool_provider_double_rolls_back_samples() -> None:
    from ALB.contracts import StepContext

    provider = LinearSpoolProvider(gain=500.0)
    context = StepContext(0, 0.0, 1.0e-3, UnitSystem.DIMENSIONAL)
    state = BearingInput(np.array([1.0e-4, 0.0]), np.zeros(2), 0.0, UnitSystem.DIMENSIONAL)
    provider.input(context, state)
    provider.evaluate()
    committed = provider.output()
    token = provider.checkpoint()
    for _ in range(3):
        provider.input(
            StepContext(1, 1.0e-3, 1.0e-3, UnitSystem.DIMENSIONAL),
            BearingInput(np.array([3.0e-4, 0.0]), np.zeros(2), 1.0e-3, UnitSystem.DIMENSIONAL),
        )
        provider.evaluate()
        provider.restore(token)
    assert provider.samples == [0.0]
    assert provider.evaluations == 4
    assert provider.output() is committed


def test_spool_provider_double_matches_an_undisturbed_twin() -> None:
    """Three rolled-back trials per step keep a 20-step provider sequence."""

    from ALB.contracts import StepContext

    disturbed, twin = LinearSpoolProvider(gain=500.0), LinearSpoolProvider(gain=500.0)

    def sample(provider: LinearSpoolProvider, step: int, scale: float = 1.0) -> Any:
        time = step * 1.0e-3
        provider.input(
            StepContext(step, time, 1.0e-3, UnitSystem.DIMENSIONAL),
            BearingInput(
                scale * np.array([1.0e-4 * np.cos(0.4 * step), 2.0e-4]),
                np.zeros(2),
                time,
                UnitSystem.DIMENSIONAL,
            ),
        )
        provider.evaluate()
        return provider.output()

    for step in range(20):
        if step > 0:
            token = disturbed.checkpoint()
            for scale in (1.3, 0.7, -0.5):
                try:
                    sample(disturbed, step, scale)
                finally:
                    disturbed.restore(token)
        committed, reference = sample(disturbed, step), sample(twin, step)
        np.testing.assert_array_equal(committed.spool, reference.spool)
        assert committed.time == reference.time
    assert disturbed.samples == twin.samples
    assert disturbed.evaluations == twin.evaluations + 3 * 19


def test_multi_pad_rejects_children_without_checkpoint() -> None:
    from ALB.physics.bearing.solver import MultiPad
    from tests._support.dynamics.analytic_bearings import AnalyticBearing, linear_law

    child = AnalyticBearing(linear_law(1.0e4, 1.0))
    child._reset_for_owner()
    composite = MultiPad(child)
    with pytest.raises(TypeError, match="checkpoint"):
        composite.checkpoint()


def test_checkpoint_restores_nested_mappings_in_place() -> None:
    """Dictionaries of history lists and arrays are restored recursively."""

    from collections import defaultdict

    class Component:
        pass

    component = Component()
    history: dict[str, list[Any]] = {"t": [0.0], "x": [np.zeros(2)]}
    component._history = history
    component.arrays = {"state": np.ones(3)}
    component.channels = defaultdict(list)
    component.channels["u"].append(1.0)
    cyclic: dict[str, Any] = {}
    cyclic["self"] = cyclic
    component.cyclic = cyclic
    time_list = history["t"]
    token = RuntimeCheckpoint(component, [component])
    for _ in range(2):
        # Mutate like a controller trial, then roll back; tokens are reusable.
        history["t"].append(1.0)
        history["x"].append(np.ones(2))
        history["extra"] = [2.0]
        component.arrays["state"][0] = 5.0
        component.channels["u"].append(2.0)
        component.channels["v"].append(3.0)
        cyclic["key"] = 1
        token.restore(component)
        assert component._history is history
        assert history["t"] is time_list
        assert sorted(history) == ["t", "x"]
        assert history["t"] == [0.0]
        assert len(history["x"]) == 1
        np.testing.assert_array_equal(component.arrays["state"], np.ones(3))
        assert type(component.channels) is defaultdict
        assert dict(component.channels) == {"u": [1.0]}
        assert list(cyclic) == ["self"] and cyclic["self"] is cyclic


def test_active_bearing_delegates_to_a_checkpointable_controller() -> None:
    runtime = _build("active_pid")
    controller = runtime._controller
    calls: list[str] = []

    def checkpoint() -> RuntimeCheckpoint:
        calls.append("checkpoint")
        return RuntimeCheckpoint(controller, [controller, controller._lifecycle])

    def restore(token: object) -> None:
        calls.append("restore")
        assert isinstance(token, RuntimeCheckpoint)
        token.restore(controller)

    controller.checkpoint = checkpoint
    controller.restore = restore
    twin = _build("active_pid")
    for item in (runtime, twin):
        item.step(_dto(item, 0))
    token = runtime.checkpoint()
    runtime.step(_dto(runtime, 1, scale=1.7))
    runtime.restore(token)
    assert calls == ["checkpoint", "restore"]
    runtime.step(_dto(runtime, 1))
    twin.step(_dto(twin, 1))
    _assert_same_result(runtime.result_snapshot(), twin.result_snapshot())
