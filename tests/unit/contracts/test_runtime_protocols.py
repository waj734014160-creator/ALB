"""Interface and state-transition tests for strict runtime protocols."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from ALB.contracts import (
    ControllerProtocol,
    ResultSnapshotProtocol,
    RuntimeLifecycleProtocol,
    ServoValveProtocol,
)
from ALB.control.controllers import ALBLQGController
from ALB.control.valve import moog_2nd_servovalve
from ALB.core import LifecycleState, RuntimeLifecycle, TimeIterDt
from ALB.dynamics.coupling import RsRotorBearingCouple


def _controller() -> ALBLQGController:
    controller = ALBLQGController(SimpleNamespace(), dt=0.01, eso_enable=False)
    controller.active_ctrl_sys_d = SimpleNamespace(
        A=np.asarray([[0.8]], dtype=float),
        B=np.asarray([[0.2, -0.1]], dtype=float),
        C=np.asarray([[2.0], [-3.0]], dtype=float),
        D=np.zeros((2, 2), dtype=float),
    )
    controller._init_runtime_state()
    return controller


def test_controller_and_valve_implement_formal_runtime_protocols():
    controller = _controller()
    valve = moog_2nd_servovalve(dt=0.001)

    assert isinstance(controller, ControllerProtocol)
    assert isinstance(controller, RuntimeLifecycleProtocol)
    assert isinstance(valve, ServoValveProtocol)
    assert isinstance(valve, RuntimeLifecycleProtocol)


def test_runtime_lifecycle_has_one_output_generation_per_evaluation():
    lifecycle = RuntimeLifecycle("test component")
    assert lifecycle.state is LifecycleState.NEW
    with pytest.raises(RuntimeError, match="initialized"):
        lifecycle.require_input_slot()

    lifecycle.reset()
    lifecycle.latch()
    assert lifecycle.state is LifecycleState.RUNNING
    with lifecycle.evaluation():
        pass
    assert lifecycle.state is LifecycleState.READY
    lifecycle.require_output()
    lifecycle.require_output()

    lifecycle.latch()
    with pytest.raises(RuntimeError, match="unavailable"):
        lifecycle.require_output()
    with pytest.raises(RuntimeError, match="injected"):
        with lifecycle.evaluation():
            raise RuntimeError("injected failure")
    assert lifecycle.state is LifecycleState.FAILED
    with pytest.raises(RuntimeError, match="init"):
        lifecycle.require_input_slot()


def test_coupling_exposes_result_snapshot_protocol():
    class Bearing:
        node_link = 0
        unit_system = "dimensional"

        def __init__(self):
            from ALB.core import Signal

            self.signal = Signal(sys=self)

        def init(self):
            return None

        def input(self, uxy, uxyt, t):
            del uxy, uxyt, t

        def output(self):
            return {"force": np.zeros(2)}

        def finish_signal(self):
            return None

        def save(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("not used")

    class Rotor:
        def __init__(self):
            from ALB.core import Signal

            self.signal = Signal(sys=self)

        def init(self):
            return None

        def output(self, nodes):
            count = len(np.asarray(nodes).reshape(-1))
            return {"uxy": np.zeros((count, 2)), "uxyt": np.zeros((count, 2))}

        def finish_signal(self):
            return None

    coupling = RsRotorBearingCouple(Rotor(), TimeIterDt(0.01, 1), Bearing())
    coupling.init()

    assert isinstance(coupling, ResultSnapshotProtocol)
    assert isinstance(coupling, RuntimeLifecycleProtocol)
    assert coupling.lifecycle_state is LifecycleState.READY
    assert coupling.result_snapshot() is coupling.output()
