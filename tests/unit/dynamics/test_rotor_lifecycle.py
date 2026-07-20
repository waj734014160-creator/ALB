"""Lifecycle regression tests for explicit rotor advancement."""

from types import SimpleNamespace

import numpy as np
import pytest

from ALB.dynamics.rotor import RossRotor


class _LinearRotorPlant:
    ndof = 1
    number_dof = 1

    def _lti(self, speed):
        del speed
        return SimpleNamespace(
            A=np.array([[-1.5, 0.25], [-0.5, -0.75]], dtype=float),
            B=np.array([[1.0], [0.2]], dtype=float),
            C=np.eye(2, dtype=float),
            D=np.zeros((2, 1), dtype=float),
        )


def test_rotor_output_never_hides_state_advancement():
    rotor = RossRotor(_LinearRotorPlant(), speed=1.0, dt=1.0e-3)
    initial = rotor.output()
    np.testing.assert_array_equal(initial, np.zeros(2))

    rotor.input_force(0.0, np.array([1.0]))
    with pytest.raises(RuntimeError, match="stale"):
        rotor.output()

    rotor.advance()
    first = rotor.output()
    np.testing.assert_array_equal(rotor.current_state(), first)
    np.testing.assert_array_equal(rotor.output(), first)
    with pytest.raises(RuntimeError, match="new rotor load"):
        rotor.advance()
