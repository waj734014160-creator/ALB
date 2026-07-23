"""State-transition tests for native controller and servovalve runtimes."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from ALB.contracts import ControllerProtocol
from ALB.control.adapters import LegacyControllerAdapter
from ALB.control.controllers import ALBLQGController, RCConfig, RepetitiveController
from ALB.control import FuzzyPID, PID
from ALB.control.valve import moog_2nd_servovalve
from ALB.config import FuzzyPIDConfig, PIDConfig
from ALB.core import LifecycleState


def _lqg_controller() -> ALBLQGController:
    controller = ALBLQGController(SimpleNamespace(), dt=0.01, eso_enable=False)
    controller.active_ctrl_sys_d = SimpleNamespace(
        A=np.asarray([[0.8]], dtype=float),
        B=np.asarray([[0.2, -0.1]], dtype=float),
        C=np.asarray([[2.0], [-3.0]], dtype=float),
        D=np.zeros((2, 2), dtype=float),
    )
    controller._init_runtime_state()
    return controller


def _repetitive_controller() -> RepetitiveController:
    return RepetitiveController(
        RCConfig(
            dt=0.01,
            freq=10.0,
            k_rc=np.asarray([0.4, -0.2]),
            q_filter=0.95,
            m_lead=1,
        )
    )


@pytest.mark.parametrize("factory", [_lqg_controller, _repetitive_controller])
def test_native_controller_output_is_read_only(factory):
    controller = factory()
    assert isinstance(controller, ControllerProtocol)
    assert controller.lifecycle_state is LifecycleState.READY
    with pytest.raises(RuntimeError, match="unavailable"):
        controller.output()

    controller.input(0.0, [0.2, -0.3])
    assert controller.lifecycle_state is LifecycleState.RUNNING
    with pytest.raises(RuntimeError, match="unavailable"):
        controller.output()
    computed = controller.evaluate()
    first = controller.output()
    second = controller.output()

    assert controller.lifecycle_state is LifecycleState.READY
    np.testing.assert_array_equal(computed, first)
    np.testing.assert_array_equal(second, first)
    with pytest.raises(RuntimeError, match="new input"):
        controller.evaluate()


def test_legacy_controller_adapter_contains_calculation_in_evaluate():
    class LegacyController:
        def __init__(self):
            self.output_calls = 0

        def input(self, time, error):
            self.command = np.asarray(error, dtype=float) + float(time)

        def output(self):
            self.output_calls += 1
            return self.command

    legacy = LegacyController()
    controller = LegacyControllerAdapter(legacy)
    controller.input(0.25, [0.2, -0.3])
    assert legacy.output_calls == 0
    controller.evaluate()
    expected = np.asarray([0.2, -0.3], dtype=float) + 0.25
    np.testing.assert_array_equal(controller.output(), expected)
    np.testing.assert_array_equal(controller.output(), expected)
    assert legacy.output_calls == 1


def test_servovalve_input_does_not_advance_and_output_is_read_only():
    valve = moog_2nd_servovalve(dt=0.001)
    initial_history = (len(valve.xout), len(valve.yout))
    valve.input(0.0, 0.25)

    assert valve.lifecycle_state is LifecycleState.RUNNING
    assert (len(valve.xout), len(valve.yout)) == initial_history
    with pytest.raises(RuntimeError, match="unavailable"):
        valve.output()

    computed = valve.evaluate()
    history_after_evaluate = (len(valve.xout), len(valve.yout))
    np.testing.assert_array_equal(valve.output(), computed)
    np.testing.assert_array_equal(valve.output(), computed)
    assert (len(valve.xout), len(valve.yout)) == history_after_evaluate
    with pytest.raises(RuntimeError, match="new input"):
        valve.evaluate()


def test_pid_failure_is_terminal_until_explicit_init(monkeypatch):
    controller = PID(PIDConfig(kp=0.5, dt=0.01))
    controller.input(0.0, [0.2, -0.3])

    def fail(*args, **kwargs):
        del args, kwargs
        raise FloatingPointError("injected PID failure")

    monkeypatch.setattr(controller, "decrete_pid", fail)
    with pytest.raises(FloatingPointError, match="injected"):
        controller.evaluate()
    assert controller.lifecycle_state is LifecycleState.FAILED
    with pytest.raises(RuntimeError, match="init"):
        controller.output()
    with pytest.raises(RuntimeError, match="init"):
        controller.input(0.01, [0.0, 0.0])

    controller.init()
    assert controller.lifecycle_state is LifecycleState.READY
    with pytest.raises(RuntimeError, match="unavailable"):
        controller.output()


@pytest.mark.parametrize(
    "factory,input_args",
    [
        (lambda: PID(PIDConfig(kp=0.5, dt=0.01)), (0.0, [0.2, -0.3])),
        (_lqg_controller, (0.0, [0.2, -0.3])),
        (_repetitive_controller, (0.0, [0.2, -0.3])),
        (lambda: moog_2nd_servovalve(dt=0.001), (0.0, 0.2)),
    ],
    ids=["pid", "lqg", "repetitive", "servovalve"],
)
def test_completed_outputs_are_caller_owned_snapshots(factory, input_args):
    component = factory()
    component.input(*input_args)
    expected = component.evaluate()
    mutated = component.output()
    mutated[...] = 99.0

    np.testing.assert_array_equal(component.output(), expected)


@pytest.mark.parametrize(
    "invalid",
    [
        [1.0 + 1.0j, 0.0],
        [np.nan, 0.0],
        [np.inf, 0.0],
        [0.0],
    ],
)
def test_pid_shared_numeric_boundary_rejects_invalid_input_atomically(invalid):
    controller = PID(PIDConfig(kp=0.5, dt=0.01))

    with pytest.raises(ValueError):
        controller.input(0.0, invalid)

    assert controller.lifecycle_state is LifecycleState.READY
    with pytest.raises(RuntimeError, match="unavailable"):
        controller.output()


@pytest.mark.parametrize(
    "controller",
    [
        PID(
            PIDConfig(
                dt=0.01,
                kp=0.0,
                ki=0.0,
                kd=1.0,
                freq=5.0,
                sensor_angles=[0.0, 90.0],
            )
        ),
        FuzzyPID(
            FuzzyPIDConfig(
                dt=0.01,
                freq=5.0,
                rule_path=None,
                sensor_angles=[0.0, 90.0],
            )
        ),
    ],
    ids=["pid", "fuzzy-pid"],
)
def test_repeated_saturated_error_has_no_false_derivative(controller):
    controller.input(0.0, [1.2, -1.2])
    controller.evaluate()
    controller.input(0.01, [1.2, -1.2])
    controller.evaluate()

    np.testing.assert_array_equal(controller.delta_error, np.zeros(2))
    np.testing.assert_array_equal(controller.kd_calc, np.zeros(2))
