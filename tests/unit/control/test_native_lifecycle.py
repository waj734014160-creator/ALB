"""State-transition tests for native controller and servovalve runtimes."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from ALB.contracts import ControllerProtocol
from ALB.control.adapters import LegacyControllerAdapter
from ALB.control.controllers import ALBLQGController, RCConfig, RepetitiveController
from ALB.control.valve import moog_2nd_servovalve
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
