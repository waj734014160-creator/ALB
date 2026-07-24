"""Port lifecycle tests for controller and valve adapters."""

import numpy as np
import pytest

from ALB.contracts import ControlInput, LifecycleState, UnitSystem, ValveInput
from ALB.control.blocks import ControllerBlock, ValveBlock
from ALB.control.valve import moog_2nd_servovalve


class _Controller:
    @property
    def lifecycle_state(self):
        return LifecycleState.READY

    def input(self, time, error):
        self.command = np.asarray(error) * 2.0 + time

    def evaluate(self):
        return self.command

    def output(self):
        return self.command


class _Valve:
    @property
    def lifecycle_state(self):
        return LifecycleState.READY

    def input(self, time, command):
        self.spool = np.asarray(command) - time

    def evaluate(self):
        return self.spool

    def output(self):
        return self.spool


def test_controller_block_uses_explicit_compute_command():
    block = ControllerBlock(_Controller(), UnitSystem.NONDIMENSIONAL)
    dto = ControlInput([0.2, -0.1], 0.5, "nondimensional")
    block.input(dto)
    with pytest.raises(RuntimeError):
        block.output()
    block.compute_command()
    np.testing.assert_array_equal(block.output().command, [0.9, 0.3])


def test_valve_block_uses_explicit_evaluate():
    block = ValveBlock(_Valve(), "nondimensional")
    result = block.step(ValveInput([0.4, -0.2], 0.1, "nondimensional"))
    np.testing.assert_allclose(result.spool, [0.3, -0.3], rtol=0.0, atol=1e-15)


def test_servo_valve_requires_evaluate_and_repeated_reads_do_not_advance():
    valve = moog_2nd_servovalve(dt=0.001)
    valve.input(0.0, 0.25)
    with pytest.raises(RuntimeError, match="unavailable"):
        valve.output()
    expected = np.asarray(valve.evaluate(), dtype=float).copy()
    history_lengths = (len(valve.ts), len(valve.xout), len(valve.yout))

    np.testing.assert_array_equal(valve.output(), expected)
    assert (len(valve.ts), len(valve.xout), len(valve.yout)) == history_lengths
