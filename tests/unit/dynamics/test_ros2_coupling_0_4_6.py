"""ROS2 coupled integration added in ALB 0.4.6.

The tests use analytic bearings only (no trained surrogate package):

* a constant-coefficient bearing compared with the matrix-exponential solution
  of the closed-loop linear system, including a harmonic unbalance;
* a hardening bearing (stiffness grows with eccentricity) checked by
  self-convergence at h, h/2, h/4;
* the staggered scheme converging to the same solution with first order.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.linalg import expm

from ALB.contracts import StepContext, UnitSystem
from ALB.core.time import TimeIterDt
from ALB.dynamics.bindings import CoupledBearingBinding, CouplingRuntimeDependencies
from ALB.dynamics.coupling import _RotorBearingStepRuntime
from ALB.dynamics.ros2 import (
    ROS2_GAMMA,
    Ros2Options,
    Ros2StageError,
    Ros2Stepper,
    ros2_stability_function,
)
from ALB.dynamics.rotor import RossRotor
from ALB.infrastructure.recording import InMemoryResultRecorder
from tests._support.dynamics.analytic_bearings import (
    ActuatedAnalyticBearing,
    AnalyticBearing,
    DirectSpoolAnalyticBearing,
    LinearSpoolProvider,
    SinglePlant,
    hardening_law,
    hardening_torch_law,
    linear_law,
    spool_law,
)


STATIC_FORCE = np.array([3.0, -20.0])
UNBALANCE = {"phase": 0.3, "m": 2.0e-3, "freq": 12.0, "e": 1.0e-2}
# The analytic plant has its first modes near 25 Hz with about 9 % damping.
# Step sizes below are inside the asymptotic range of both schemes; coarser
# steps are dominated by ROS2 numerical damping of the free vibration excited
# by the suddenly applied static load, or by the staggered k*h instability.


def _run(
    bearing,
    *,
    time_step: float,
    end_time: float,
    integrator: str,
    options: Ros2Options | None = None,
    plant: SinglePlant | None = None,
    unbalance: bool = True,
    dependencies: CouplingRuntimeDependencies | None = None,
    spool_provider=None,
) -> tuple[_RotorBearingStepRuntime, list]:
    """Run one coupled simulation and return the runtime and snapshots."""

    steps = int(round(end_time / time_step))
    rotor = RossRotor(plant or SinglePlant(), speed=1.0, dt=time_step)
    kwargs = {"integrator": integrator}
    if options is not None:
        kwargs["ros2_options"] = options
    if dependencies is not None:
        kwargs["dependencies"] = dependencies
    runtime = _RotorBearingStepRuntime(
        rotor,
        TimeIterDt(time_step, steps),
        CoupledBearingBinding(bearing, node_link=0, spool_provider=spool_provider),
        **kwargs,
    )
    runtime.add_static_force(STATIC_FORCE, 0)
    if unbalance:
        runtime.add_unbalance(node_link=0, **UNBALANCE)
    runtime._reset_for_owner()
    snapshots = [runtime.output()]
    for index in range(1, steps + 1):
        snapshots.append(
            runtime.advance(
                StepContext(
                    index,
                    time_step * index,
                    time_step,
                    UnitSystem.DIMENSIONAL,
                )
            )
        )
    return runtime, snapshots


def _exact_linear_state(
    stiffness: float,
    damping: float,
    end_time: float,
    plant: SinglePlant,
) -> np.ndarray:
    """Return the closed-loop state at ``end_time`` from an augmented expm."""

    system = plant._lti(0.0)
    a, b = system.A, system.B
    n = a.shape[0]
    selector_x = np.zeros((2, n))
    selector_v = np.zeros((2, n))
    selector_x[[0, 1], [0, 1]] = 1.0
    selector_v[[0, 1], [4, 5]] = 1.0
    mapping = np.zeros((4, 2))
    mapping[[0, 1], [0, 1]] = 1.0
    closed = a + b @ mapping @ (-stiffness * selector_x - damping * selector_v)
    omega = 2.0 * math.pi * UNBALANCE["freq"]
    amplitude = omega**2 * UNBALANCE["m"] * UNBALANCE["e"]
    augmented = np.zeros((n + 3, n + 3))
    augmented[:n, :n] = closed
    augmented[:n, n] = b @ mapping @ STATIC_FORCE
    augmented[:n, n + 1] = amplitude * (b @ mapping @ np.array([1.0, 0.0]))
    augmented[:n, n + 2] = amplitude * (b @ mapping @ np.array([0.0, 1.0]))
    augmented[n + 1, n + 2] = -omega
    augmented[n + 2, n + 1] = omega
    initial = np.zeros(n + 3)
    initial[n] = 1.0
    initial[n + 1] = math.cos(UNBALANCE["phase"])
    initial[n + 2] = math.sin(UNBALANCE["phase"])
    return (expm(augmented * end_time) @ initial)[:n]


# ---------------------------------------------------------------------------
# Integration core
# ---------------------------------------------------------------------------


def test_ros2_coefficients_and_l_stability() -> None:
    assert ROS2_GAMMA == pytest.approx(1.0 + 1.0 / math.sqrt(2.0))
    assert abs(ros2_stability_function(-1.0e9)) < 1.0e-8
    assert abs(ros2_stability_function(0.0) - 1.0) == 0.0


@pytest.mark.parametrize("jacobian_scale", [1.0, 0.0, 0.3])
def test_stepper_is_second_order_for_any_jacobian(jacobian_scale: float) -> None:
    matrix = np.array([[0.0, 1.0], [-400.0, -2.0]])

    def rhs(state: np.ndarray, time: float) -> np.ndarray:
        return matrix @ state + np.array([0.0, math.sin(7.0 * time)])

    def solve(steps: int) -> np.ndarray:
        stepper = Ros2Stepper(0.5 / steps, jacobian_scale * matrix)
        state = np.array([1.0, 0.0])
        for index in range(steps):
            state = stepper.step(rhs, index * 0.5 / steps, state)
        return state

    reference = solve(64000)
    errors = [np.linalg.norm(solve(steps) - reference) for steps in (400, 800, 1600)]
    for coarse, fine in zip(errors, errors[1:]):
        assert coarse / fine == pytest.approx(4.0, rel=0.15)


def test_options_validation() -> None:
    assert Ros2Options().jacobian_refresh is None
    assert Ros2Options(jacobian_refresh=5).jacobian_refresh == 5
    assert Ros2Options(jacobian_refresh="control_period").jacobian_refresh == "control_period"
    for invalid in (0, -1, True, 1.5, "always"):
        with pytest.raises(ValueError):
            Ros2Options(jacobian_refresh=invalid)
    with pytest.raises(ValueError):
        Ros2Options(displacement_step=0.0)
    with pytest.raises(ValueError):
        Ros2Options(jacobian_state=[np.nan])
    state = Ros2Options(jacobian_state=[1.0, 2.0]).jacobian_state
    assert not state.flags.writeable


# ---------------------------------------------------------------------------
# Accuracy
# ---------------------------------------------------------------------------


def test_linear_bearing_matches_matrix_exponential_with_second_order() -> None:
    plant = SinglePlant()
    stiffness, damping, end_time = 3.0e4, 40.0, 0.1
    exact = _exact_linear_state(stiffness, damping, end_time, plant)
    errors = []
    for time_step in (1.25e-4, 6.25e-5, 3.125e-5):
        runtime, _ = _run(
            AnalyticBearing(linear_law(stiffness, damping)),
            time_step=time_step,
            end_time=end_time,
            integrator="ros2",
            plant=plant,
        )
        state = runtime.rotor.current_state()
        errors.append(np.linalg.norm(state - exact) / np.linalg.norm(exact))
    assert errors[-1] < 5.0e-4
    for coarse, fine in zip(errors, errors[1:]):
        assert coarse / fine == pytest.approx(4.0, rel=0.15)


def _hardening_bearing(**kwargs) -> AnalyticBearing:
    return AnalyticBearing(
        hardening_law(stiffness=3.0e4, damping=40.0, scale=6.0e-4, alpha=8.0),
        **kwargs,
    )


def _hardening_state(time_step: float, integrator: str) -> np.ndarray:
    runtime, _ = _run(
        _hardening_bearing(),
        time_step=time_step,
        end_time=0.1,
        integrator=integrator,
    )
    return runtime.rotor.current_state()


def test_nonlinear_bearing_self_converges_with_second_order() -> None:
    states = [
        _hardening_state(time_step, "ros2")
        for time_step in (2.5e-4, 1.25e-4, 6.25e-5)
    ]
    # The hardening term is active: peak eccentricity reaches ~40 % of scale.
    assert np.max(np.abs(states[-1][:2])) > 2.0e-4
    ratio = np.linalg.norm(states[0] - states[1]) / np.linalg.norm(states[1] - states[2])
    assert ratio == pytest.approx(4.0, rel=0.15)


def test_staggered_converges_to_ros2_solution_with_first_order() -> None:
    reference = _hardening_state(1.5625e-5, "ros2")
    staggered = {
        time_step: _hardening_state(time_step, "staggered")
        for time_step in (1.25e-4, 6.25e-5, 3.125e-5)
    }
    errors = [
        np.linalg.norm(state - reference) / np.linalg.norm(reference)
        for state in staggered.values()
    ]
    assert errors[-1] < errors[0]
    for coarse, fine in zip(errors, errors[1:]):
        assert 1.8 < coarse / fine < 2.5
    # ROS2 at a step eight times coarser is still more accurate than the
    # finest staggered run, which reflects the removed one-step force lag.
    ros2_coarse = _hardening_state(2.5e-4, "ros2")
    assert np.linalg.norm(ros2_coarse - reference) < np.linalg.norm(
        staggered[3.125e-5] - reference
    )


# ---------------------------------------------------------------------------
# Jacobian
# ---------------------------------------------------------------------------


def test_autodiff_jacobian_matches_central_differences() -> None:
    pytest.importorskip("torch")
    displacement = np.array([2.0e-4, -3.0e-4])
    velocity = np.array([1.0e-2, 5.0e-3])
    parameters = {"stiffness": 3.0e4, "damping": 40.0, "scale": 6.0e-4, "alpha": 8.0}

    def jacobian(bearing: AnalyticBearing) -> np.ndarray:
        runtime, _ = _run(
            bearing,
            time_step=1.0e-3,
            end_time=1.0e-3,
            integrator="ros2",
            unbalance=False,
        )
        integrator = runtime._ros2
        state = np.zeros(integrator.size)
        state[[0, 1]] = displacement
        state[[4, 5]] = velocity
        return integrator.jacobian(state, 0.0)

    autodiff = jacobian(
        AnalyticBearing(
            hardening_law(**parameters),
            torch_law=hardening_torch_law(**parameters),
        )
    )
    differences = jacobian(AnalyticBearing(hardening_law(**parameters)))
    np.testing.assert_allclose(autodiff, differences, rtol=1.0e-6, atol=1.0e-6)


def test_jacobian_is_frozen_by_default_and_refresh_is_optional() -> None:
    frozen, _ = _run(
        _hardening_bearing(),
        time_step=1.0e-3,
        end_time=0.02,
        integrator="ros2",
    )
    refreshed, _ = _run(
        _hardening_bearing(),
        time_step=1.0e-3,
        end_time=0.02,
        integrator="ros2",
        options=Ros2Options(jacobian_refresh=5),
    )
    assert frozen._ros2.diagnostics()["w_factorizations"] == 1
    assert refreshed._ros2.diagnostics()["w_factorizations"] == 1 + 20 // 5


def test_two_force_evaluations_per_step_and_no_lagged_force() -> None:
    bearing = _hardening_bearing()
    runtime, snapshots = _run(
        bearing,
        time_step=1.0e-3,
        end_time=0.01,
        integrator="ros2",
    )
    jacobian_probes = 2 * 4  # central differences over displacement and velocity
    # Each step: one stage probe and one committed lifecycle evaluation.
    assert bearing.probes == 10 + jacobian_probes
    assert bearing.evaluations == 11
    final = snapshots[-1]
    displacement = final.values["rotor_displacement"][0]
    velocity = final.values["rotor_velocity"][0]
    np.testing.assert_array_equal(
        final.values["bearing_force"][0],
        bearing.law(displacement, velocity, None),
    )


def test_jacobian_state_must_match_rotor_state_size() -> None:
    with pytest.raises(ValueError, match="jacobian_state"):
        _run(
            _hardening_bearing(),
            time_step=1.0e-3,
            end_time=1.0e-3,
            integrator="ros2",
            options=Ros2Options(jacobian_state=[0.0, 0.0]),
        )


def test_jacobian_state_accepts_rotor_or_coupled_state() -> None:
    rotor_state = np.zeros(8)
    rotor_state[1] = -2.0e-4
    for supplied in (rotor_state, np.concatenate([rotor_state, [0.1, -0.1]])):
        runtime, _ = _run(
            _actuated(2),
            time_step=1.0e-3,
            end_time=2.0e-3,
            integrator="ros2",
            options=Ros2Options(jacobian_state=supplied),
        )
        assert runtime._ros2.diagnostics()["jacobian_evaluations"] == 1


# ---------------------------------------------------------------------------
# Sampled control and spool inputs
# ---------------------------------------------------------------------------


def _actuated(control_steps: int) -> ActuatedAnalyticBearing:
    return ActuatedAnalyticBearing(
        spool_law(stiffness=3.0e4, damping=40.0, spool_gain=200.0),
        gain=2.0e3,
        tau=5.0e-3,
        control_steps=control_steps,
    )


def test_actuated_controller_runs_every_m_steps_and_holds_command() -> None:
    bearing = _actuated(4)
    runtime, _ = _run(
        bearing,
        time_step=1.0e-3,
        end_time=0.03,
        integrator="ros2",
    )
    np.testing.assert_allclose(bearing.samples, np.arange(0, 31, 4) * 1.0e-3)
    assert runtime._ros2.diagnostics()["actuator_states"] == 2


def test_sampled_control_keeps_second_order_with_sample_instants_on_steps() -> None:
    control_period = 4.0e-3
    states = []
    for time_step in (1.0e-3, 5.0e-4, 2.5e-4):
        runtime, _ = _run(
            _actuated(int(round(control_period / time_step))),
            time_step=time_step,
            end_time=0.2,
            integrator="ros2",
        )
        states.append(runtime.rotor.current_state())
    ratio = np.linalg.norm(states[0] - states[1]) / np.linalg.norm(states[1] - states[2])
    assert ratio == pytest.approx(4.0, rel=0.2)


def test_direct_spool_provider_is_sampled_once_per_step() -> None:
    provider = LinearSpoolProvider(gain=500.0)
    bearing = DirectSpoolAnalyticBearing(
        spool_law(stiffness=3.0e4, damping=40.0, spool_gain=50.0)
    )
    _run(
        bearing,
        time_step=1.0e-3,
        end_time=0.01,
        integrator="ros2",
        spool_provider=provider,
    )
    np.testing.assert_allclose(provider.samples, np.arange(11) * 1.0e-3)


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


class _StatefulBearing(AnalyticBearing):
    """Bearing without a side-effect-free force (for example thermal state)."""

    probe_force = None  # type: ignore[assignment]


def test_runtime_without_side_effect_free_force_is_rejected() -> None:
    bearing = _StatefulBearing(linear_law(1.0e4, 10.0))
    with pytest.raises(TypeError, match="side"):
        _run(bearing, time_step=1.0e-3, end_time=1.0e-3, integrator="ros2")


def test_recorder_receives_every_committed_ros2_step() -> None:
    recorder = InMemoryResultRecorder()
    runtime, snapshots = _run(
        _hardening_bearing(),
        time_step=1.0e-3,
        end_time=0.005,
        integrator="ros2",
        dependencies=CouplingRuntimeDependencies(
            run_id="ros2-recorder",
            recorder=recorder,
        ),
    )
    receipt = runtime.end_run()
    assert receipt.record_count == 6
    assert [item.metadata["step_index"] for item in snapshots] == list(range(6))
    diagnostic = runtime.diagnostic_snapshot().metadata
    assert diagnostic["integrator"] == "ros2"
    assert diagnostic["ros2"]["rhs_evaluations"] == 1 + 2 * 5


class _FailingBearing(AnalyticBearing):
    def probe_force(self, dto):
        if dto.time > 2.5e-3:
            raise FloatingPointError("stage failure")
        return super().probe_force(dto)


def test_stage_failure_is_sealed_without_publishing_the_step() -> None:
    bearing = _FailingBearing(linear_law(1.0e4, 10.0))
    with pytest.raises(Ros2StageError, match="stage-2") as caught:
        _run(bearing, time_step=1.0e-3, end_time=0.005, integrator="ros2")
    assert isinstance(caught.value.__cause__, FloatingPointError)


def test_failure_snapshot_records_integrator() -> None:
    bearing = _FailingBearing(linear_law(1.0e4, 10.0))
    rotor = RossRotor(SinglePlant(), speed=1.0, dt=1.0e-3)
    runtime = _RotorBearingStepRuntime(
        rotor,
        TimeIterDt(1.0e-3, 5),
        CoupledBearingBinding(bearing, node_link=0),
        integrator="ros2",
    )
    runtime._reset_for_owner()
    committed = []
    with pytest.raises(Ros2StageError):
        for index in range(1, 6):
            committed.append(
                runtime.advance(
                    StepContext(index, 1.0e-3 * index, 1.0e-3, UnitSystem.DIMENSIONAL)
                )
            )
    snapshot = runtime.failure_snapshot()
    assert snapshot.metadata["integrator"] == "ros2"
    assert snapshot.metadata["physical_step_committed"] is False
    assert snapshot.metadata["attempted_context"]["step_index"] == len(committed) + 1
    with pytest.raises(RuntimeError, match="invalid"):
        runtime.output()


def test_integrator_arguments_are_validated() -> None:
    rotor = RossRotor(SinglePlant(), speed=1.0, dt=1.0e-3)
    binding = CoupledBearingBinding(_hardening_bearing(), node_link=0)
    with pytest.raises(ValueError, match="integrator"):
        _RotorBearingStepRuntime(rotor, TimeIterDt(1.0e-3, 1), binding, integrator="rk4")
    with pytest.raises(ValueError, match="ros2_options"):
        _RotorBearingStepRuntime(
            rotor,
            TimeIterDt(1.0e-3, 1),
            binding,
            ros2_options=Ros2Options(),
        )
