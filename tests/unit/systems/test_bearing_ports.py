"""Shared strict bearing-port tests for nonlinear and harmonic implementations."""

import numpy as np
import pytest

from ALB.contracts import (
    BearingCoefficientProtocol,
    BearingInput,
    BearingProtocol,
)
from ALB.systems.alb import BearingBlock, HarmonicBearingBlock


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
