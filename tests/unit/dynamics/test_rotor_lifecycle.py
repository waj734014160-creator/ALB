"""Lifecycle regression tests for explicit rotor advancement."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ALB.dynamics.rotor import RotorDofLayout, RossRotor, location_mapping_matrix
from ALB.contracts import RotorProtocol
from ALB.contracts.result_tree import SaveTreeNode


ROOT = Path(__file__).resolve().parents[3]
TIME_REFERENCE = ROOT / "refs" / "ross_rotor_time_validation_reference_v2.npz"


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


class _NodeRotorPlant:
    ndof = 4
    number_dof = 4

    def _lti(self, speed):
        del speed
        state_count = 2 * self.ndof
        return SimpleNamespace(
            A=-0.5 * np.eye(state_count, dtype=float),
            B=np.vstack(
                (
                    np.eye(self.ndof, dtype=float),
                    0.25 * np.eye(self.ndof, dtype=float),
                )
            ),
            C=np.eye(state_count, dtype=float),
            D=np.zeros((state_count, self.ndof), dtype=float),
        )


class _SixDofNodeRotorPlant:
    ndof = 12
    number_dof = 6

    def _lti(self, speed):
        del speed
        state_count = 2 * self.ndof
        return SimpleNamespace(
            A=-0.5 * np.eye(state_count, dtype=float),
            B=np.vstack(
                (
                    np.eye(self.ndof, dtype=float),
                    0.25 * np.eye(self.ndof, dtype=float),
                )
            ),
            C=np.eye(state_count, dtype=float),
            D=np.zeros((state_count, self.ndof), dtype=float),
        )


def test_rotor_output_never_hides_state_advancement():
    rotor = RossRotor(_LinearRotorPlant(), speed=1.0, dt=1.0e-3)
    initial = rotor.output()
    np.testing.assert_array_equal(initial, np.zeros(2))

    rotor.input_force(0.0, np.array([1.0]))
    with pytest.raises(RuntimeError, match="unavailable"):
        rotor.output()

    rotor.advance()
    first = rotor.output()
    np.testing.assert_array_equal(rotor.current_state(), first)
    np.testing.assert_array_equal(rotor.output(), first)
    with pytest.raises(RuntimeError, match="new rotor load"):
        rotor.advance()


def test_rotor_advance_failure_requires_successful_reinitialization(monkeypatch):
    rotor = RossRotor(_LinearRotorPlant(), speed=1.0, dt=1.0e-3)
    rotor.input_force(0.0, np.array([1.0]))

    def fail():
        raise FloatingPointError("injected rotor propagation failure")

    monkeypatch.setattr(rotor, "_propagate", fail)
    with pytest.raises(FloatingPointError, match="injected"):
        rotor.advance()
    assert rotor.lifecycle_state.value == "failed"
    with pytest.raises(RuntimeError, match="init"):
        rotor.output()
    with pytest.raises(RuntimeError, match="init"):
        rotor.input_force(0.0, np.array([1.0]))

    rotor._reset_for_owner()
    assert rotor.lifecycle_state.value == "ready"
    np.testing.assert_array_equal(rotor.output(), np.zeros(2))


def test_rotor_results_and_persistence_are_read_only_after_advance():
    rotor = RossRotor(_LinearRotorPlant(), speed=1.0, dt=1.0e-3)
    rotor.input_force(0.0, np.array([1.0]))
    rotor.advance()

    response = rotor.results()
    save_tree = rotor.save(tofile=False)

    assert isinstance(save_tree, SaveTreeNode)
    assert type(response) is type(save_tree.data.rotor_result)
    assert rotor.lifecycle_state.value == "ready"


def test_rotor_valid_time_trajectories_match_v2_reference_exactly():
    with np.load(TIME_REFERENCE) as reference:
        global_rotor = RossRotor(
            _LinearRotorPlant(), speed=2.0 * np.pi * 50.0, dt=1.0e-3
        )
        assert isinstance(global_rotor, RotorProtocol)
        global_states = []
        for time_value, force in zip(
            reference["global.times"], reference["global.forces"]
        ):
            global_rotor.input_force(time_value, force)
            global_states.append(global_rotor.advance().copy())

        node_rotor = RossRotor(_NodeRotorPlant(), speed=10.0, dt=2.0e-3)
        node_global_forces = []
        node_states = []
        for time_value, force in zip(
            reference["node.times"], reference["node.input_forces"]
        ):
            node_rotor.input_force2node(time_value, force, node=[0])
            node_global_forces.append(node_rotor._force1.copy())
            node_states.append(node_rotor.advance().copy())

        actual = {
            "global.times": np.asarray(global_rotor._t, dtype=float),
            "global.forces": reference["global.forces"],
            "global.states": np.vstack(global_states),
            "global.time_history": np.asarray(global_rotor._t, dtype=float),
            "global.state_history": np.asarray(global_rotor._xouts, dtype=float),
            "global.output_history": np.asarray(global_rotor._youts, dtype=float),
            "global.Ad": np.asarray(global_rotor._a, dtype=float),
            "global.Bd0": np.asarray(global_rotor._Bd0, dtype=float),
            "global.Bd1": np.asarray(global_rotor._Bd1, dtype=float),
            "node.times": np.asarray(node_rotor._t, dtype=float),
            "node.input_forces": reference["node.input_forces"],
            "node.global_forces": np.vstack(node_global_forces),
            "node.states": np.vstack(node_states),
            "node.time_history": np.asarray(node_rotor._t, dtype=float),
        }
        assert set(actual) == set(reference.files)
        for name, value in actual.items():
            np.testing.assert_array_equal(value, reference[name], err_msg=name)


def test_input_force_rejects_invalid_time_without_mutating_state():
    dt = 1.0e-3
    fresh_rotor = RossRotor(_LinearRotorPlant(), speed=1.0, dt=dt)
    with pytest.raises(ValueError, match="finite"):
        fresh_rotor.input_force(np.nan, np.array([1.0]))
    assert fresh_rotor._t == []

    for invalid_time in (0.0, 0.5 * dt, 1.5 * dt, np.nan, np.inf, -np.inf):
        rotor = RossRotor(_LinearRotorPlant(), speed=1.0, dt=dt)
        rotor.input_force(0.0, np.array([1.0]))
        rotor.advance()
        before = {
            "time": list(rotor._t),
            "force0": rotor._force0.copy(),
            "force1": rotor._force1.copy(),
            "state": rotor._xk0.copy(),
            "state_ready": rotor._state_ready,
        }

        with pytest.raises(ValueError):
            rotor.input_force(
                invalid_time,
                np.array([9.0]),
                x0=np.full(2, 8.0),
                force0=np.array([7.0]),
            )

        assert rotor._t == before["time"]
        np.testing.assert_array_equal(rotor._force0, before["force0"])
        np.testing.assert_array_equal(rotor._force1, before["force1"])
        np.testing.assert_array_equal(rotor._xk0, before["state"])
        assert rotor._state_ready is before["state_ready"]


def test_input_force2node_rejects_invalid_time_without_mutating_state():
    dt = 1.0e-3
    rotor = RossRotor(_NodeRotorPlant(), speed=1.0, dt=dt)
    rotor.input_force2node(0.0, np.array([1.0, -1.0]), node=[0])
    rotor.advance()
    before = {
        "time": list(rotor._t),
        "force0": rotor._force0.copy(),
        "force1": rotor._force1.copy(),
        "state": rotor._xk0.copy(),
        "state_ready": rotor._state_ready,
    }

    with pytest.raises(ValueError, match="time step"):
        rotor.input_force2node(
            1.5 * dt,
            np.array([9.0, -9.0]),
            node=[0],
            x0=np.full(8, 8.0),
            force0=np.array([7.0, -7.0]),
        )

    assert rotor._t == before["time"]
    np.testing.assert_array_equal(rotor._force0, before["force0"])
    np.testing.assert_array_equal(rotor._force1, before["force1"])
    np.testing.assert_array_equal(rotor._xk0, before["state"])
    assert rotor._state_ready is before["state_ready"]


def test_node_force_mapping_uses_actual_six_dof_stride():
    rotor = RossRotor(_SixDofNodeRotorPlant(), speed=1.0, dt=1.0e-3)

    rotor.input_force2node(0.0, [[3.0, -4.0]], node=[1])

    expected = np.zeros(12)
    expected[6:8] = [3.0, -4.0]
    np.testing.assert_array_equal(rotor._force1, expected)


def test_six_dof_result_and_mapping_use_ross_local_layout():
    rotor = RossRotor(_SixDofNodeRotorPlant(), speed=1.0, dt=1.0e-3)
    yout = np.arange(24, dtype=float)
    rotor._youts = [yout]

    np.testing.assert_array_equal(rotor.result_uxy(1), [[6.0, 7.0]])
    layout = RotorDofLayout.from_dof_per_node(6)
    mapping = location_mapping_matrix(
        12,
        [(1, "x"), (1, "y"), (1, "alpha"), (1, "beta")],
        layout=layout,
    )
    expected = np.zeros((12, 4))
    expected[[6, 7, 9, 10], np.arange(4)] = 1.0
    np.testing.assert_array_equal(mapping, expected)


@pytest.mark.parametrize("node", [0.9, -0.1, True, np.bool_(False)])
def test_current_state_rejects_non_integer_node_indices_without_truncation(node):
    rotor = RossRotor(_SixDofNodeRotorPlant(), speed=1.0, dt=1.0e-3)
    rotor._xk0 = np.arange(24, dtype=float)
    rotor._state_ready = True

    with pytest.raises(TypeError, match="integers"):
        rotor.current_state(node)


@pytest.mark.parametrize("node", [-1, 2])
def test_current_state_rejects_out_of_range_node_indices(node):
    rotor = RossRotor(_SixDofNodeRotorPlant(), speed=1.0, dt=1.0e-3)
    rotor._xk0 = np.arange(24, dtype=float)
    rotor._state_ready = True

    with pytest.raises(ValueError):
        rotor.current_state(node)


@pytest.mark.parametrize(
    ("force", "node", "error"),
    [
        ([[1.0, 2.0], [3.0, 4.0]], [0], "node count"),
        ([[1.0, 2.0]], [-1], "nonnegative"),
        ([[1.0, 2.0]], [2], "exceeds"),
        ([[1.0, 2.0]], [0.5], "integers"),
        ([[1.0, np.nan]], [0], "finite"),
    ],
)
def test_invalid_node_force_mapping_is_atomic(force, node, error):
    rotor = RossRotor(_SixDofNodeRotorPlant(), speed=1.0, dt=1.0e-3)
    before_time = list(rotor._t)
    before_force = rotor._force1.copy()

    with pytest.raises((TypeError, ValueError), match=error):
        rotor.input_force2node(0.0, force, node=node)

    assert rotor._t == before_time
    np.testing.assert_array_equal(rotor._force1, before_force)
