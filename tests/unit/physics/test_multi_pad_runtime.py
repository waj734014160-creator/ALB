"""Unit tests for the formal MultiPad composite bearing runtime."""

from __future__ import annotations

import numpy as np
import pytest

from ALB.contracts import BearingInput, BearingRuntimeProtocol, UnitSystem
from ALB.core import LifecycleState
from ALB.physics.bearing import MultiPad


class _LeafPad:
    """Small legacy-shaped film solver used only as a MultiPad child."""

    unit_system = UnitSystem.DIMENSIONAL
    node_link = 2

    def __init__(self, force, friction, *, fail=False, converged=True):
        self.args = {"c": 1.0e-4}
        self.force = np.asarray(force, dtype=float)
        self.friction = float(friction)
        self.fail = fail
        self.converged = converged
        self.init_calls = 0
        self.input_calls = 0
        self.output_calls = 0

    def init(self):
        self.init_calls += 1

    def input(self, *, uxy, uxyt, t, nodim):
        self.input_calls += 1
        self.last_input = (
            np.asarray(uxy, dtype=float),
            np.asarray(uxyt, dtype=float),
            float(t),
            bool(nodim),
        )

    def output(self, *, nodim):
        self.output_calls += 1
        if self.fail:
            raise FloatingPointError("injected child failure")
        return {
            "force": self.force.copy(),
            "friction": self.friction,
            "nodim": nodim,
        }

    def calc_is_finished(self):
        return self.converged

    def calc_capacity(self, **kwargs):
        del kwargs
        return self.force.copy()

    def calc_friction(self, **kwargs):
        del kwargs
        return self.friction

    def set_thickness(self, method, **kwargs):
        self.thickness = (method, kwargs)


def _input(time=0.2):
    return BearingInput(
        displacement=[0.01, -0.02],
        velocity=[0.03, -0.04],
        time=time,
        unit_system=UnitSystem.DIMENSIONAL,
    )


def test_multipad_auto_ready_three_phase_and_exact_read_only_sum() -> None:
    first = _LeafPad([1.25, -2.5], 0.75)
    second = _LeafPad([-0.5, 4.0], 1.25)
    runtime = MultiPad(first, second)

    assert isinstance(runtime, BearingRuntimeProtocol)
    assert runtime.lifecycle_state is LifecycleState.READY
    assert first.init_calls == second.init_calls == 1
    with pytest.raises(RuntimeError, match="unavailable"):
        runtime.output()

    runtime.input(_input())
    assert runtime.lifecycle_state is LifecycleState.RUNNING
    assert first.input_calls == second.input_calls == 0
    runtime.evaluate()
    assert runtime.lifecycle_state is LifecycleState.READY

    output = runtime.output()
    np.testing.assert_array_equal(output.force, [0.75, 1.5])
    assert output.time == 0.2
    assert output.unit_system is UnitSystem.DIMENSIONAL
    assert first.input_calls == second.input_calls == 1
    assert first.output_calls == second.output_calls == 1
    with pytest.raises(ValueError):
        output.force[0] = 99.0

    repeated = runtime.output()
    np.testing.assert_array_equal(repeated.force, output.force)
    assert first.output_calls == second.output_calls == 1
    snapshot = runtime.result_snapshot()
    np.testing.assert_array_equal(snapshot.values["force"], [0.75, 1.5])
    assert snapshot.values["friction"] == 2.0
    assert snapshot.metadata["pad_count"] == 2
    assert snapshot.metadata["converged"] is True
    assert runtime.results.shape == (1, 3)


def test_multipad_analysis_methods_preserve_exact_aggregation() -> None:
    first = _LeafPad([1.25, -2.5], 0.75)
    second = _LeafPad([-0.5, 4.0], 1.25)
    runtime = MultiPad(first, second)

    np.testing.assert_array_equal(runtime.calc_capacity(), [0.75, 1.5])
    assert runtime.calc_friction() == 2.0


def test_multipad_child_failure_seals_runtime_and_snapshot() -> None:
    first = _LeafPad([1.0, 2.0], 0.0)
    second = _LeafPad([3.0, 4.0], 0.0, fail=True)
    runtime = MultiPad(first, second)
    runtime.input(_input())

    with pytest.raises(FloatingPointError, match="injected child"):
        runtime.evaluate()

    assert runtime.lifecycle_state is LifecycleState.FAILED
    with pytest.raises(RuntimeError, match="init"):
        runtime.output()
    failure = runtime.failure_snapshot()
    assert failure.metadata["schema"] == "alb.multi-pad-failure.v1"
    assert failure.metadata["phase"] == "evaluate"
    assert failure.metadata["error_type"] == "FloatingPointError"
    assert failure.metadata["message"].startswith(
        "component arithmetic failed; detail_fingerprint="
    )
    diagnostic = runtime.diagnostic_snapshot()
    assert diagnostic.metadata["has_failure"] is True
