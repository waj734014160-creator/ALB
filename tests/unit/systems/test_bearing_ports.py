"""Shared strict bearing-port tests for nonlinear and harmonic implementations."""

import numpy as np
import pytest

from ALB.contracts import (
    BearingCoefficientProtocol,
    BearingInput,
    BearingProtocol,
    ValveOutput,
)
from ALB.systems.alb import (
    BearingBlock,
    DirectSpoolBearingBlock,
    DirectSpoolBearingInput,
    HarmonicBearingBlock,
)


class _BearingImplementation:
    unit_system = "dimensional"
    node_link = 4

    def input(self, displacement, velocity, time):
        self.force = np.asarray(displacement) + 2.0 * np.asarray(velocity) + time

    def output(self):
        return {"force": self.force}


class _HarmonicImplementation(_BearingImplementation):
    K = np.array([[1.0, 2.0], [3.0, 4.0]])
    C = np.array([[5.0, 6.0], [7.0, 8.0]])
    G_xv = np.array([[1.0 + 2.0j, 0.0], [0.0, 3.0 - 4.0j]])


class _DirectSpoolImplementation:
    unit_system = "nondimensional"
    node_link = 6

    def __init__(self):
        self.calls = {"input": 0, "output": 0, "finished": 0}

    def input(self, displacement, velocity, time, *, sv, nodim):
        self.calls["input"] += 1
        assert nodim is True
        self.force = np.asarray(displacement) + np.asarray(velocity) + sv + time

    def output(self, *, nodim):
        self.calls["output"] += 1
        assert nodim is True
        return {"force": self.force}

    def calc_is_finished(self):
        self.calls["finished"] += 1
        return True


def test_nonlinear_bearing_adapter_uses_standard_dto_lifecycle():
    block = BearingBlock(_BearingImplementation())
    assert isinstance(block, BearingProtocol)
    dto = BearingInput([1.0, 2.0], [0.5, -0.5], 0.25, "dimensional")
    block.input(dto)
    with pytest.raises(RuntimeError):
        block.output()
    block.evaluate()
    np.testing.assert_array_equal(block.output().force, [2.25, 1.25])


def test_harmonic_adapter_exposes_formal_coefficient_capability():
    block = HarmonicBearingBlock(_HarmonicImplementation())
    assert isinstance(block, BearingProtocol)
    assert isinstance(block, BearingCoefficientProtocol)
    np.testing.assert_array_equal(block.K, _HarmonicImplementation.K)
    np.testing.assert_array_equal(block.C, _HarmonicImplementation.C)
    np.testing.assert_array_equal(block.G_xv, _HarmonicImplementation.G_xv)


def test_direct_spool_adapter_evaluates_once_and_keeps_output_read_only():
    implementation = _DirectSpoolImplementation()
    block = DirectSpoolBearingBlock(implementation)
    dto = DirectSpoolBearingInput(
        BearingInput([0.1, -0.2], [0.03, -0.04], 0.25, "nondimensional"),
        ValveOutput([0.2, -0.3], 0.25, "nondimensional"),
    )

    result = block.step(dto)
    np.testing.assert_array_equal(
        result.force,
        dto.bearing.displacement
        + dto.bearing.velocity
        + dto.spool.spool
        + dto.bearing.time,
    )
    assert block.convergence_status.converged is True
    assert implementation.calls == {"input": 1, "output": 1, "finished": 1}

    assert block.output() is result
    assert block.convergence_status.converged is True
    assert implementation.calls == {"input": 1, "output": 1, "finished": 1}


def test_direct_spool_input_rejects_mismatched_time_and_dimensional_spool():
    bearing = BearingInput([0.0, 0.0], [0.0, 0.0], 0.25, "dimensional")
    with pytest.raises(ValueError, match="timestamps"):
        DirectSpoolBearingInput(
            bearing, ValveOutput([0.0, 0.0], 0.5, "nondimensional")
        )
    with pytest.raises(ValueError, match="nondimensional"):
        DirectSpoolBearingInput(
            bearing, ValveOutput([0.0, 0.0], 0.25, "dimensional")
        )
