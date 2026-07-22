"""Compatibility tests for ALB controller lifecycle integration points."""

from types import SimpleNamespace

import numpy as np
import pytest

from ALB.control.controllers import ALBLQGController, RCConfig, RepetitiveController
from ALB.systems.alb.assembly import ALB
from ALB.systems.alb.harmonic import ALBHarmonicLinear


class _LegacyController:
    """Historical controller whose output method owns calculation."""

    def __init__(self) -> None:
        self.error = np.zeros(2, dtype=float)
        self.time = 0.0
        self.output_calls = 0

    def input(self, time, error) -> None:
        self.time = float(time)
        self.error = np.asarray(error, dtype=float).reshape(2)

    def output(self) -> np.ndarray:
        self.output_calls += 1
        return self.error + self.time


class _ReadOnlyValve:
    """Small valve that exposes the command supplied by the harmonic path."""

    def __init__(self) -> None:
        self.command = 0.0
        self.input_calls = 0

    def input(self, time, command) -> None:
        del time
        self.command = float(command)
        self.input_calls += 1

    def output(self) -> float:
        return self.command


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


@pytest.mark.parametrize(
    "factory",
    [_LegacyController, _lqg_controller, _repetitive_controller],
    ids=["legacy", "lqg", "repetitive"],
)
def test_alb_control_process_accepts_strict_and_legacy_controllers(factory):
    controller = factory()
    alb = object.__new__(ALB)
    alb._gxy = np.eye(2)
    alb._gxyt = np.zeros((2, 2))
    alb.controller = controller

    command = ALB._control_process(
        alb,
        np.asarray([0.2, -0.3]),
        np.asarray([0.0, 0.0]),
        0.0,
    )

    assert np.asarray(command).shape == (2,)
    if isinstance(controller, _LegacyController):
        assert controller.output_calls == 1


@pytest.mark.parametrize(
    "factory",
    [_LegacyController, _lqg_controller, _repetitive_controller],
    ids=["legacy", "lqg", "repetitive"],
)
def test_harmonic_control_path_accepts_strict_and_legacy_controllers(factory):
    controller = factory()
    bearing = object.__new__(ALBHarmonicLinear)
    bearing.controller = controller
    bearing.coefficients = SimpleNamespace(clearance_m=2.0)
    bearing.servovalves = [_ReadOnlyValve(), _ReadOnlyValve()]

    ALBHarmonicLinear._advance_control(
        bearing,
        time_s=0.0,
        uxy=np.asarray([0.4, -0.6]),
    )

    assert bearing.spool_command.shape == (2,)
    np.testing.assert_array_equal(bearing.spool, bearing.spool_command)
    assert [valve.input_calls for valve in bearing.servovalves] == [1, 1]
    if isinstance(controller, _LegacyController):
        assert controller.output_calls == 1
