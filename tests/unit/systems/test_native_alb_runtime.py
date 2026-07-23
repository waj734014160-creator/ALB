"""Strict native lifecycle tests for nonlinear ALB runtime families."""

from __future__ import annotations

import numpy as np
import pytest

from ALB.contracts import (
    BearingInput,
    BearingRuntimeProtocol,
    DirectSpoolBearingInput,
    DirectSpoolBearingRuntimeProtocol,
    LifecycleState,
    ValveOutput,
)
from ALB.systems.alb.factories import alb2, nodim_alb
from ALB.systems.alb.harmonic import alb_harmonic_linear
from ALB.systems.alb.surrogate_runtime import ALBNNAgent
from tools.reference.generate_alb_runtime_families_reference_v1 import (
    _DeterministicNet,
    _dimensional_config,
    _nondimensional_config,
)


def _runtime(unit: str, kind: str):
    if unit == "dimensional":
        return alb2(_dimensional_config(kind))
    config = _nondimensional_config(kind, thermal=False)
    return nodim_alb(config, thermal_config=config.thermal_config)


def _input(unit: str, kind: str, time: float = 0.0):
    if unit == "dimensional":
        bearing = BearingInput(
            [1.0e-6, -2.0e-6],
            [1.0e-3, -2.0e-3],
            time,
            "dimensional",
        )
    else:
        bearing = BearingInput(
            [0.1, -0.2],
            [0.03, -0.04],
            time,
            "nondimensional",
        )
    if kind == "ALBSV":
        return DirectSpoolBearingInput(
            bearing,
            ValveOutput([0.2, -0.3], time, "nondimensional"),
        )
    return bearing


@pytest.mark.parametrize("unit", ["dimensional", "nondimensional"])
@pytest.mark.parametrize("kind", ["ALB", "ALBSV"])
def test_native_runtime_has_strict_read_only_output(unit: str, kind: str):
    runtime = _runtime(unit, kind)
    expected_protocol = (
        DirectSpoolBearingRuntimeProtocol
        if kind == "ALBSV"
        else BearingRuntimeProtocol
    )

    assert isinstance(runtime, expected_protocol)
    assert runtime.lifecycle_state is LifecycleState.READY
    with pytest.raises(RuntimeError, match="unavailable"):
        runtime.output()

    runtime.input(_input(unit, kind))
    assert runtime.lifecycle_state is LifecycleState.RUNNING
    with pytest.raises(RuntimeError, match="unavailable"):
        runtime.output()

    runtime.evaluate()
    output = runtime.output()
    result = runtime.result_snapshot()
    history_rows = len(runtime.results)

    assert runtime.lifecycle_state is LifecycleState.READY
    assert runtime.output() is output
    assert runtime.output() is output
    assert len(runtime.results) == history_rows == 0
    np.testing.assert_array_equal(result.values["force"], output.force)

    runtime.input(_input(unit, kind, 6.667e-4))
    with pytest.raises(RuntimeError, match="unavailable"):
        runtime.output()


def test_step_is_exactly_the_three_phase_native_lifecycle():
    stepped = _runtime("nondimensional", "ALBSV")
    phased = _runtime("nondimensional", "ALBSV")
    dto = _input("nondimensional", "ALBSV")

    step_output = stepped.step(dto)
    phased.input(dto)
    phased.evaluate()
    phased_output = phased.output()

    np.testing.assert_array_equal(step_output.force, phased_output.force)
    np.testing.assert_array_equal(
        stepped.result_snapshot().values["force"],
        phased.result_snapshot().values["force"],
    )


def test_evaluation_failure_seals_normal_state_until_reinitialization(
    monkeypatch,
):
    runtime = _runtime("nondimensional", "ALBSV")
    runtime.input(_input("nondimensional", "ALBSV"))
    original_output = runtime.pads[1].output

    def fail_output(*args, **kwargs):
        raise RuntimeError("injected pad failure")

    monkeypatch.setattr(runtime.pads[1], "output", fail_output)
    with pytest.raises(RuntimeError, match="injected pad failure"):
        runtime.evaluate()

    assert runtime.lifecycle_state is LifecycleState.FAILED
    assert runtime.failure_snapshot().metadata["phase"] == "evaluate"
    for action in (
        runtime.output,
        runtime.result_snapshot,
        lambda: runtime.input(_input("nondimensional", "ALBSV")),
        lambda: runtime.save(False, "failed", "alb"),
        lambda: runtime.results,
    ):
        with pytest.raises(RuntimeError, match="failed"):
            action()

    monkeypatch.setattr(runtime.pads[1], "output", original_output)
    runtime.init()
    recovered = runtime.step(_input("nondimensional", "ALBSV"))
    assert np.all(np.isfinite(recovered.force))


def test_convergence_queries_do_not_reenter_children(monkeypatch):
    runtime = _runtime("nondimensional", "ALBSV")
    runtime.step(_input("nondimensional", "ALBSV"))
    expected = runtime.convergence_status

    def fail_query():
        raise AssertionError("child convergence was queried twice")

    monkeypatch.setattr(runtime.pads[0], "calc_is_finished", fail_query)
    assert runtime.convergence_status is expected
    assert runtime.calc_is_finished() is expected.converged


def test_reinitialization_invalidates_a_completed_output():
    runtime = _runtime("nondimensional", "ALB")
    runtime.step(_input("nondimensional", "ALB"))
    runtime.init()

    assert runtime.lifecycle_state is LifecycleState.READY
    with pytest.raises(RuntimeError, match="unavailable"):
        runtime.output()


def test_albnn_shell_is_a_native_read_only_bearing_runtime():
    runtime = ALBNNAgent(
        _DeterministicNet(),
        unit_system="nondimensional",
        node_link=5,
    )
    assert runtime.lifecycle_state is LifecycleState.READY
    runtime.of[0].xv = 0.1
    runtime.of[1].xv = -0.2
    dto = BearingInput(
        [0.1, -0.2],
        [0.03, -0.04],
        0.0,
        "nondimensional",
    )
    output = runtime.step(dto)
    history_rows = len(runtime.results)

    assert isinstance(runtime, BearingRuntimeProtocol)
    assert runtime.node_link == 5
    assert runtime.output() is output
    assert len(runtime.results) == history_rows == 0
    np.testing.assert_array_equal(
        runtime.result_snapshot().values["force"],
        output.force,
    )


def test_albnn_inference_failure_is_sealed_until_init():
    class _FailingNet(_DeterministicNet):
        def output(self, *, nodim: bool) -> np.ndarray:
            del nodim
            return np.asarray([np.nan, 0.0])

    runtime = ALBNNAgent(
        _FailingNet(),
        unit_system="nondimensional",
    )
    runtime.input(
        BearingInput(
            [0.1, -0.2],
            [0.03, -0.04],
            0.0,
            "nondimensional",
        )
    )
    with pytest.raises(ValueError, match="finite"):
        runtime.evaluate()

    assert runtime.lifecycle_state is LifecycleState.FAILED
    with pytest.raises(RuntimeError, match="failed"):
        runtime.output()
    assert runtime.failure_snapshot().metadata["phase"] == "evaluate"


def test_harmonic_runtime_latches_before_control_and_publishes_dto():
    runtime = alb_harmonic_linear(node_link=12)
    assert runtime.lifecycle_state is LifecycleState.READY
    dto = BearingInput(
        runtime.uxy0,
        [0.0, 0.0],
        0.0,
        "dimensional",
    )
    command_before = runtime.spool_command.copy()
    runtime.input(dto)

    np.testing.assert_array_equal(runtime.spool_command, command_before)
    with pytest.raises(RuntimeError, match="unavailable"):
        runtime.output()

    runtime.evaluate()
    output = runtime.output()
    assert isinstance(runtime, BearingRuntimeProtocol)
    assert runtime.output() is output
    np.testing.assert_array_equal(
        runtime.result_snapshot().values["force"],
        output.force,
    )
