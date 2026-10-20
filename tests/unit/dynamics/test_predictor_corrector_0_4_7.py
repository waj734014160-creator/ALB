"""Predictor-corrector partitioned coupling added in ALB 0.4.7.

The tests use analytic rotor plants and bearing doubles only (no trained
surrogate package):

* interface-update rules (Aitken, IQN-ILS) on affine maps;
* the pure rotor trial hook against ``RossRotor._propagate``;
* a constant-coefficient bearing against the matrix-exponential solution of
  the closed loop: ``iterate`` and ``pece`` are second order, staggered first;
* a hardening bearing (self-convergence, same limit as ROS2 and staggered);
* a black-box bearing with stiffness memory (ROS2 rejects it; the
  predictor-corrector is second order, staggered first);
* a black-box sampled active bearing (controller exactly every m commits);
* a stiff damper (spectral radius above one): plain iteration fails, Aitken
  and IQN-ILS converge; non-convergence, trial failures, evaluation counts;
* spool providers with and without checkpoint support.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from ALB.contracts import StepContext, UnitSystem
from ALB.core.time import TimeIterDt
from ALB.dynamics.bindings import CoupledBearingBinding, CouplingRuntimeDependencies
from ALB.dynamics.coupling import _RotorBearingStepRuntime
from ALB.dynamics.predictor_corrector import (
    _filtered_least_squares,
    AitkenRelaxation,
    CouplingIterationError,
    CouplingIterationWarning,
    CouplingTrialError,
    FixedPointUpdate,
    IQNILSAccelerator,
    PredictorCorrectorOptions,
)
from ALB.dynamics.rotor import RossRotor
from ALB.infrastructure.recording import InMemoryResultRecorder
from tests._support.dynamics.analytic_bearings import (
    AnalyticBearing,
    DirectSpoolAnalyticBearing,
    LinearSpoolProvider,
    OpaqueLinearSpoolProvider,
    SinglePlant,
    hardening_law,
    linear_law,
    spool_law,
)
from tests._support.dynamics.memory_bearings import (
    MemoryAnalyticBearing,
    SampledActiveAnalyticBearing,
)
from tests.unit.dynamics.test_ros2_coupling_0_4_6 import (
    STATIC_FORCE,
    UNBALANCE,
    _exact_linear_state,
)


PC = "predictor_corrector"


class DiscretizablePlant(SinglePlant):
    """Analytic plant whose LTI model supports ``to_discrete`` (SciPy)."""

    def _lti(self, speed: float):
        from scipy import signal

        system = super()._lti(speed)
        return signal.StateSpace(system.A, system.B, system.C, system.D)


def _run(
    bearing,
    *,
    time_step: float,
    end_time: float,
    integrator: str = PC,
    options: PredictorCorrectorOptions | None = None,
    spool_provider=None,
    dependencies: CouplingRuntimeDependencies | None = None,
    discrete: bool = False,
    unbalance: bool = True,
) -> _RotorBearingStepRuntime:
    """Run one coupled simulation with the analytic one-node plant."""

    steps = int(round(end_time / time_step))
    plant = DiscretizablePlant() if discrete else SinglePlant()
    rotor = RossRotor(plant, speed=1.0, dt=time_step, discrete=discrete)
    kwargs: dict[str, object] = {"integrator": integrator}
    if options is not None:
        kwargs["predictor_corrector_options"] = options
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
    for index in range(1, steps + 1):
        runtime.advance(
            StepContext(index, time_step * index, time_step, UnitSystem.DIMENSIONAL)
        )
    return runtime


def _state(runtime: _RotorBearingStepRuntime) -> np.ndarray:
    return np.asarray(runtime.rotor.current_state(), dtype=float)


def _ratios(values: list[float]) -> list[float]:
    return [coarse / fine for coarse, fine in zip(values, values[1:])]


def _differences(states: list[np.ndarray]) -> list[float]:
    return [float(np.linalg.norm(a - b)) for a, b in zip(states, states[1:])]


# ---------------------------------------------------------------------------
# Options and interface-update rules
# ---------------------------------------------------------------------------


def test_options_defaults_and_validation() -> None:
    options = PredictorCorrectorOptions()
    assert options.mode == "iterate"
    assert options.predictor == "linear"
    assert options.relaxation == "aitken"
    assert options.omega == 0.5
    assert options.omega_bounds == (0.01, 1.5)
    assert options.iqn_reuse_steps == 0
    assert options.rtol == 1.0e-6 and options.atol == 1.0e-6
    assert options.max_iterations == 20
    assert options.on_nonconvergence == "warn"
    assert hash(options) == hash(PredictorCorrectorOptions())
    assert PredictorCorrectorOptions(omega_bounds=[0.1, 1]).omega_bounds == (0.1, 1.0)
    invalid = [
        {"mode": "newton"},
        {"predictor": "quadratic"},
        {"relaxation": "anderson"},
        {"on_nonconvergence": "ignore"},
        {"omega": 0.0},
        {"omega": math.nan},
        {"omega_bounds": (1.0, 0.5)},
        {"omega_bounds": (0.0, 1.0)},
        {"omega_bounds": (0.1,)},
        {"iqn_reuse_steps": -1},
        {"rtol": -1.0},
        {"rtol": 0.0, "atol": 0.0},
        {"max_iterations": 0},
    ]
    for arguments in invalid:
        with pytest.raises(ValueError):
            PredictorCorrectorOptions(**arguments)
    for arguments in ({"omega": True}, {"max_iterations": 2.5}, {"iqn_reuse_steps": "1"}):
        with pytest.raises(TypeError):
            PredictorCorrectorOptions(**arguments)


def test_pece_reports_the_options_it_does_not_use() -> None:
    assert PredictorCorrectorOptions().to_dict()["unused_in_pece"] == ()
    unused = PredictorCorrectorOptions(mode="pece").to_dict()["unused_in_pece"]
    assert set(unused) == {
        "relaxation",
        "omega",
        "omega_bounds",
        "iqn_reuse_steps",
        "rtol",
        "atol",
        "max_iterations",
        "on_nonconvergence",
    }


@pytest.mark.parametrize("slope", [-0.5, -2.0, -5.0, 0.3])
def test_aitken_second_update_reaches_the_fixed_point_of_a_scalar_map(slope: float) -> None:
    """``F~ = a P + b``: the optimal factor ``1/(1-a)`` lies in the bounds."""

    offset = 2.0
    fixed_point = offset / (1.0 - slope)
    assert 0.01 <= 1.0 / (1.0 - slope) <= 1.5
    relaxation = AitkenRelaxation(0.5, (0.01, 1.5))
    relaxation.begin_step()
    guess = np.array([0.0])
    for _ in range(2):
        trial = slope * guess + offset
        guess = relaxation.update(guess, trial, trial - guess)
    assert guess[0] == pytest.approx(fixed_point, rel=1.0e-12)


def test_aitken_factor_is_clipped_and_carried_over_steps() -> None:
    relaxation = AitkenRelaxation(0.5, (0.01, 1.5))
    relaxation.begin_step()
    guess = np.array([0.0])
    for _ in range(3):
        trial = 0.95 * guess + 1.0  # optimal factor 20 is outside the bounds
        guess = relaxation.update(guess, trial, trial - guess)
    assert relaxation.omega == 1.5
    relaxation.end_step()
    relaxation.begin_step()
    trial = 0.95 * guess + 1.0
    updated = relaxation.update(guess, trial, trial - guess)
    np.testing.assert_allclose(updated, guess + 1.5 * (trial - guess))
    assert relaxation.omega_range() == (0.5, 1.5)


@pytest.mark.parametrize("dimension", [2, 4, 6])
def test_iqn_ils_solves_an_affine_map_within_dimension_plus_two_updates(dimension: int) -> None:
    rng = np.random.default_rng(dimension)
    matrix = rng.normal(scale=1.5, size=(dimension, dimension))
    offset = rng.normal(size=dimension)
    fixed_point = np.linalg.solve(np.eye(dimension) - matrix, offset)
    accelerator = IQNILSAccelerator(0.5)
    accelerator.begin_step()
    guess = np.zeros(dimension)
    updates = 0
    while True:
        trial = matrix @ guess + offset
        residual = trial - guess
        if np.linalg.norm(residual) <= 1.0e-9 * np.linalg.norm(fixed_point):
            break
        guess = accelerator.update(guess, trial, residual)
        updates += 1
        assert updates <= dimension + 2
    np.testing.assert_allclose(guess, fixed_point, rtol=1.0e-8)


def test_iqn_ils_drops_dependent_columns() -> None:
    columns = np.array([[1.0, 2.0, 0.0], [1.0, 2.0, 1.0], [0.0, 0.0, 1.0]])
    solved = _filtered_least_squares(columns, np.array([1.0, 3.0, 2.0]), 1.0e-10)
    assert solved is not None
    coefficients, keep = solved
    np.testing.assert_array_equal(keep, [0, 2])
    np.testing.assert_allclose(coefficients, [1.0, 2.0])
    assert _filtered_least_squares(np.zeros((3, 2)), np.ones(3), 1.0e-10) is None


def test_iqn_ils_reuses_columns_of_previous_steps() -> None:
    matrix = np.array([[0.5, 2.0], [-1.0, 0.3]])
    offset = np.array([1.0, -1.0])
    fixed_point = np.linalg.solve(np.eye(2) - matrix, offset)

    def updates(accelerator: IQNILSAccelerator) -> int:
        accelerator.begin_step()
        guess = fixed_point + np.array([1.0, -2.0])
        count = 0
        while True:
            trial = matrix @ guess + offset
            residual = trial - guess
            if np.linalg.norm(residual) < 1.0e-10:
                break
            guess = accelerator.update(guess, trial, residual)
            count += 1
        accelerator.end_step()
        return count

    reused = IQNILSAccelerator(0.5, reuse_steps=1)
    first = updates(reused)
    assert len(reused._history) == 1
    # Reused secant columns give the exact inverse Jacobian of an affine
    # map, so the next step needs fewer updates.
    assert updates(reused) < first
    fresh = IQNILSAccelerator(0.5)
    updates(fresh)
    assert fresh._history == []


def test_plain_and_constant_updates() -> None:
    guess, trial = np.array([1.0, 2.0]), np.array([3.0, 0.0])
    np.testing.assert_array_equal(FixedPointUpdate().update(guess, trial, trial - guess), trial)
    np.testing.assert_allclose(
        FixedPointUpdate(0.25).update(guess, trial, trial - guess),
        guess + 0.25 * (trial - guess),
    )


# ---------------------------------------------------------------------------
# Rotor trial hook
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("discrete", [False, True])
def test_rotor_trial_propagation_matches_propagate_without_side_effects(discrete: bool) -> None:
    rotor = RossRotor(DiscretizablePlant(), speed=1.0, dt=1.0e-3, discrete=discrete)
    rng = np.random.default_rng(7)
    state = rng.normal(size=8) * 1.0e-4
    force0 = rng.normal(size=4)
    force1 = rng.normal(size=4)
    rotor._reset_for_owner(state.copy())
    before = (rotor.current_state(), list(rotor._t), len(rotor._xouts))
    trial = rotor._propagate_trial(state, force0, force1)
    np.testing.assert_array_equal(rotor.current_state(), before[0])
    assert rotor._t == before[1] and len(rotor._xouts) == before[2]
    rotor.input_force(1.0e-3, force1, force0=force0)
    np.testing.assert_array_equal(trial, rotor.advance())


# ---------------------------------------------------------------------------
# Accuracy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["iterate", "pece"])
def test_linear_bearing_matches_matrix_exponential_with_second_order(mode: str) -> None:
    plant = SinglePlant()
    stiffness, damping, end_time = 3.0e4, 40.0, 0.1
    exact = _exact_linear_state(stiffness, damping, end_time, plant)
    errors = []
    for time_step in (1.25e-4, 6.25e-5, 3.125e-5):
        runtime = _run(
            AnalyticBearing(linear_law(stiffness, damping)),
            time_step=time_step,
            end_time=end_time,
            options=PredictorCorrectorOptions(mode=mode),
        )
        errors.append(np.linalg.norm(_state(runtime) - exact) / np.linalg.norm(exact))
    assert errors[-1] < 1.0e-5
    for ratio in _ratios(errors):
        assert ratio == pytest.approx(4.0, rel=0.05)


def test_staggered_linear_bearing_is_first_order_against_the_same_solution() -> None:
    plant = SinglePlant()
    exact = _exact_linear_state(3.0e4, 40.0, 0.1, plant)
    errors = [
        np.linalg.norm(
            _state(
                _run(
                    AnalyticBearing(linear_law(3.0e4, 40.0)),
                    time_step=time_step,
                    end_time=0.1,
                    integrator="staggered",
                )
            )
            - exact
        )
        / np.linalg.norm(exact)
        for time_step in (1.25e-4, 6.25e-5, 3.125e-5)
    ]
    for ratio in _ratios(errors):
        assert ratio == pytest.approx(2.0, rel=0.05)


def _hardening() -> AnalyticBearing:
    return AnalyticBearing(
        hardening_law(stiffness=3.0e4, damping=40.0, scale=6.0e-4, alpha=8.0)
    )


def test_hardening_bearing_self_converges_to_the_ros2_and_staggered_limit() -> None:
    states = [
        _state(_run(_hardening(), time_step=time_step, end_time=0.1))
        for time_step in (2.5e-4, 1.25e-4, 6.25e-5)
    ]
    assert np.max(np.abs(states[-1][:2])) > 2.0e-4  # hardening term active
    ratio = _ratios(_differences(states))[0]
    assert ratio == pytest.approx(4.0, rel=0.1)
    reference = _state(_run(_hardening(), time_step=1.5625e-5, end_time=0.1, integrator="ros2"))
    pc_error = np.linalg.norm(states[-1] - reference) / np.linalg.norm(reference)
    staggered = [
        _state(_run(_hardening(), time_step=time_step, end_time=0.1, integrator="staggered"))
        for time_step in (6.25e-5, 3.125e-5)
    ]
    staggered_errors = [
        np.linalg.norm(state - reference) / np.linalg.norm(reference)
        for state in staggered
    ]
    assert pc_error < 1.0e-3
    assert staggered_errors[1] < staggered_errors[0]
    assert pc_error < staggered_errors[1] / 50.0


# ---------------------------------------------------------------------------
# Bearing with internal memory (black box, checkpointed trials)
# ---------------------------------------------------------------------------


def _memory_bearing(**kwargs) -> MemoryAnalyticBearing:
    return MemoryAnalyticBearing(
        stiffness=3.0e4,
        damping=40.0,
        scale=6.0e-4,
        alpha=2.0,
        tau=5.0e-3,
        **kwargs,
    )


def test_memory_bearing_is_rejected_by_ros2() -> None:
    with pytest.raises(TypeError, match="side effects"):
        _run(_memory_bearing(), time_step=1.0e-3, end_time=1.0e-3, integrator="ros2")


def test_memory_bearing_is_second_order_with_iterate_and_first_with_staggered() -> None:
    reference = _state(_run(_memory_bearing(), time_step=7.8125e-6, end_time=0.1))
    errors: dict[str, list[float]] = {PC: [], "staggered": []}
    for integrator in errors:
        for time_step in (1.25e-4, 6.25e-5, 3.125e-5):
            state = _state(
                _run(
                    _memory_bearing(),
                    time_step=time_step,
                    end_time=0.1,
                    integrator=integrator,
                )
            )
            errors[integrator].append(
                np.linalg.norm(state - reference) / np.linalg.norm(reference)
            )
    for ratio in _ratios(errors[PC]):
        assert ratio == pytest.approx(4.0, rel=0.1)
    for ratio in _ratios(errors["staggered"]):
        assert ratio == pytest.approx(2.0, rel=0.1)
    assert errors[PC][-1] < errors["staggered"][-1] / 100.0


def test_memory_is_advanced_only_by_commits() -> None:
    bearing = _memory_bearing()
    runtime = _run(bearing, time_step=1.0e-3, end_time=0.02)
    diagnostics = runtime._pc.diagnostics()
    # One committed history entry per committed evaluation (reset + steps);
    # every trial ran the full lifecycle and was rolled back.
    assert len(bearing.history) == 21
    assert [time for time, _ in bearing.history] == pytest.approx(
        [index * 1.0e-3 for index in range(21)]
    )
    assert bearing.lifecycle_evaluations == diagnostics["trial_iterations"] + 21
    assert diagnostics["trial_modes"] == ("checkpoint",)


# ---------------------------------------------------------------------------
# Sampled active bearing (black box)
# ---------------------------------------------------------------------------


def _active(control_steps: int, **kwargs) -> SampledActiveAnalyticBearing:
    return SampledActiveAnalyticBearing(
        stiffness=3.0e4,
        damping=40.0,
        spool_gain=200.0,
        gain=500.0,
        tau=5.0e-3,
        control_steps=control_steps,
        **kwargs,
    )


def test_controller_runs_exactly_every_m_commits_regardless_of_iterations() -> None:
    bearing = _active(4)
    runtime = _run(
        bearing,
        time_step=1.0e-3,
        end_time=0.03,
        options=PredictorCorrectorOptions(rtol=1.0e-12, atol=1.0e-12),
    )
    diagnostics = runtime._pc.diagnostics()
    assert diagnostics["trial_iterations"] > 2 * 30  # several trials per step
    np.testing.assert_allclose(bearing.samples, np.arange(0, 31, 4) * 1.0e-3)
    assert bearing.control_counter == 31
    # Trials run the controller too (rolled back afterwards).
    assert bearing.controller_runs > len(bearing.samples)


@pytest.mark.parametrize(
    ("control", "valve_hold", "expected"),
    [
        ("every_step", "first_order", 4.0),  # m = 1: second order
        ("fixed_period", "first_order", 2.0),  # m > 1: native FOH valve, first order
        ("fixed_period", "zero_order", 4.0),  # m > 1 with an exact ZOH valve
    ],
)
def test_sampled_active_bearing_convergence_order(
    control: str,
    valve_hold: str,
    expected: float,
) -> None:
    control_period = 1.0e-3
    states = []
    for time_step in (2.5e-4, 1.25e-4, 6.25e-5, 3.125e-5):
        steps = 1 if control == "every_step" else int(round(control_period / time_step))
        states.append(
            _state(
                _run(
                    _active(steps, valve_hold=valve_hold),
                    time_step=time_step,
                    end_time=0.1,
                )
            )
        )
    ratios = _ratios(_differences(states))
    assert ratios[-1] == pytest.approx(expected, rel=0.1)


# ---------------------------------------------------------------------------
# Iteration mechanics on a stiff damper
# ---------------------------------------------------------------------------


STIFF_DAMPING = 8.0e3  # rho ~ c h / (2 m) = 2 at h = 1 ms for the 2 kg plant


def test_stiff_damper_plain_iteration_does_not_converge_and_warns_once() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        runtime = _run(
            AnalyticBearing(linear_law(3.0e4, STIFF_DAMPING)),
            time_step=1.0e-3,
            end_time=3.0e-3,
            options=PredictorCorrectorOptions(relaxation="none", max_iterations=8),
        )
    issued = [item for item in caught if issubclass(item.category, CouplingIterationWarning)]
    assert len(issued) == 1
    diagnostics = runtime._pc.diagnostics()
    assert diagnostics["nonconverged_steps"] == 3
    assert diagnostics["iterations_per_step"]["max"] == 8
    assert diagnostics["residual_ratio"]["max"] > 1.0
    assert diagnostics["max_final_residual"] > 1.0


def test_stiff_damper_nonconvergence_raise_seals_the_step() -> None:
    bearing = AnalyticBearing(linear_law(3.0e4, STIFF_DAMPING))
    rotor = RossRotor(SinglePlant(), speed=1.0, dt=1.0e-3)
    runtime = _RotorBearingStepRuntime(
        rotor,
        TimeIterDt(1.0e-3, 3),
        CoupledBearingBinding(bearing, node_link=0),
        integrator=PC,
        predictor_corrector_options=PredictorCorrectorOptions(
            relaxation="none",
            max_iterations=8,
            on_nonconvergence="raise",
        ),
    )
    runtime.add_static_force(STATIC_FORCE, 0)
    runtime._reset_for_owner()
    with pytest.raises(CouplingIterationError):
        for index in range(1, 4):
            runtime.advance(
                StepContext(index, 1.0e-3 * index, 1.0e-3, UnitSystem.DIMENSIONAL)
            )
    snapshot = runtime.failure_snapshot()
    assert snapshot.metadata["integrator"] == PC
    assert snapshot.metadata["phase"] == "advance"
    assert snapshot.metadata["physical_step_committed"] is False
    assert snapshot.metadata["error_type"] == "CouplingIterationError"
    with pytest.raises(RuntimeError, match="invalid"):
        runtime.output()
    # The step that ended the run is counted with its eight trials.
    diagnostics = runtime._pc.diagnostics()
    assert diagnostics["nonconverged_steps"] == 1
    assert diagnostics["trial_iterations"] == bearing.probes
    assert dict(diagnostics["iterations_per_step"]["histogram"])[8] == 1


def test_warn_commits_the_last_iterate() -> None:
    """One trial without convergence commits exactly the PECE step."""

    states, forces = [], []
    for options in (
        PredictorCorrectorOptions(mode="pece"),
        PredictorCorrectorOptions(rtol=0.0, atol=1.0e-12, max_iterations=1),
    ):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            runtime = _run(
                _hardening(),
                time_step=1.0e-3,
                end_time=0.02,
                options=options,
            )
        issued = [item for item in caught if issubclass(item.category, CouplingIterationWarning)]
        assert len(issued) == (0 if options.mode == "pece" else 1)
        states.append(_state(runtime))
        forces.append(np.asarray(runtime._pc._forces).copy())
    np.testing.assert_array_equal(states[0], states[1])
    np.testing.assert_array_equal(forces[0], forces[1])


@pytest.mark.parametrize("relaxation", ["aitken", "iqn_ils"])
def test_stiff_damper_converges_with_aitken_and_iqn_ils(relaxation: str) -> None:
    runtime = _run(
        AnalyticBearing(linear_law(3.0e4, STIFF_DAMPING)),
        time_step=1.0e-3,
        end_time=0.05,
        options=PredictorCorrectorOptions(relaxation=relaxation, on_nonconvergence="raise"),
    )
    diagnostics = runtime._pc.diagnostics()
    assert diagnostics["nonconverged_steps"] == 0
    assert diagnostics["iterations_per_step"]["max"] <= 5
    reference = _state(
        _run(
            AnalyticBearing(linear_law(3.0e4, STIFF_DAMPING)),
            time_step=1.0e-3,
            end_time=0.05,
            options=PredictorCorrectorOptions(relaxation="aitken", rtol=1e-12, atol=1e-12),
        )
    )
    np.testing.assert_allclose(_state(runtime), reference, rtol=1.0e-6, atol=1.0e-12)


def test_pece_is_unstable_on_the_stiff_damper() -> None:
    runtime = _run(
        AnalyticBearing(linear_law(3.0e4, STIFF_DAMPING)),
        time_step=1.0e-3,
        end_time=0.02,
        options=PredictorCorrectorOptions(mode="pece"),
        unbalance=False,
    )
    converged = _run(
        AnalyticBearing(linear_law(3.0e4, STIFF_DAMPING)),
        time_step=1.0e-3,
        end_time=0.02,
        unbalance=False,
    )
    assert np.linalg.norm(_state(runtime)) > 1.0e3 * np.linalg.norm(_state(converged))


# ---------------------------------------------------------------------------
# Evaluation counts and diagnostics
# ---------------------------------------------------------------------------


def test_pece_uses_exactly_one_trial_and_one_commit_per_step() -> None:
    probed = _hardening()
    _run(probed, time_step=1.0e-3, end_time=0.01, options=PredictorCorrectorOptions(mode="pece"))
    assert probed.probes == 10
    assert probed.evaluations == 11

    memory = _memory_bearing()
    runtime = _run(memory, time_step=1.0e-3, end_time=0.01, options=PredictorCorrectorOptions(mode="pece"))
    assert memory.lifecycle_evaluations == 2 * 10 + 1
    diagnostics = runtime._pc.diagnostics()
    assert diagnostics["trial_iterations"] == 10
    assert diagnostics["commits"] == 11
    assert diagnostics["iterations_per_step"]["histogram"] == ((1, 10),)


def test_iterate_counts_trials_plus_one_commit_and_reports_diagnostics() -> None:
    bearing = _hardening()
    runtime = _run(bearing, time_step=1.0e-3, end_time=0.02)
    diagnostics = runtime._pc.diagnostics()
    assert bearing.probes == diagnostics["trial_iterations"] == diagnostics["trial_evaluations"]
    assert bearing.evaluations == diagnostics["commits"] == diagnostics["commit_evaluations"] == 21
    histogram = dict(diagnostics["iterations_per_step"]["histogram"])
    assert sum(histogram.values()) == diagnostics["steps"] == 20
    assert sum(trials * steps for trials, steps in histogram.items()) == (
        diagnostics["trial_iterations"]
    )
    assert diagnostics["iterations_per_step"]["mean"] == pytest.approx(
        diagnostics["trial_iterations"] / 20
    )
    for key in (
        "nonconverged_steps",
        "max_final_residual",
        "max_consistency_residual",
        "residual_ratio",
        "aitken_omega_range",
        "trial_modes",
        "spool_trials",
        "options",
    ):
        assert key in diagnostics
    low, high = diagnostics["aitken_omega_range"]
    assert 0.01 <= low <= high <= 1.5


def test_committed_force_is_evaluated_at_the_committed_state() -> None:
    bearing = _hardening()
    runtime = _run(bearing, time_step=1.0e-3, end_time=0.01)
    final = runtime.output()
    displacement = final.values["rotor_displacement"][0]
    velocity = final.values["rotor_velocity"][0]
    np.testing.assert_array_equal(
        final.values["bearing_force"][0],
        bearing.law(displacement, velocity, None),
    )


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


def test_trial_failure_restores_the_bearing_and_seals_the_step() -> None:
    bearing = _memory_bearing(fail_above=1.0e-6)
    rotor = RossRotor(SinglePlant(), speed=1.0, dt=1.0e-3)
    runtime = _RotorBearingStepRuntime(
        rotor,
        TimeIterDt(1.0e-3, 50),
        CoupledBearingBinding(bearing, node_link=0),
        integrator=PC,
    )
    runtime.add_static_force(np.array([0.0, -20.0]), 0)
    runtime._reset_for_owner()
    committed = []
    with pytest.raises(CouplingTrialError) as caught:
        for index in range(1, 51):
            committed.append(
                runtime.advance(
                    StepContext(index, 1.0e-3 * index, 1.0e-3, UnitSystem.DIMENSIONAL)
                )
            )
    assert isinstance(caught.value.__cause__, RuntimeError)
    # The bearing is back at its last committed state.
    assert bearing.lifecycle_state.value == "ready"
    assert len(bearing.history) == len(committed) + 1
    assert bearing.memory[2] == pytest.approx(1.0e-3 * len(committed))
    snapshot = runtime.failure_snapshot()
    assert snapshot.metadata["integrator"] == PC
    assert snapshot.metadata["phase"] == "advance"
    assert snapshot.metadata["physical_step_committed"] is False
    assert snapshot.metadata["attempted_context"]["step_index"] == len(committed) + 1
    with pytest.raises(RuntimeError, match="invalid"):
        runtime.output()
    # Completed trials of the failed step are counted as well.
    diagnostics = runtime._pc.diagnostics()
    histogram = dict(diagnostics["iterations_per_step"]["histogram"])
    assert sum(histogram.values()) == len(committed) + 1
    assert sum(trials * steps for trials, steps in histogram.items()) == (
        diagnostics["trial_iterations"]
    )


@pytest.mark.parametrize("mode", ["pece", "iterate"])
def test_two_bearings_are_trialled_on_the_same_rotor_state(mode: str) -> None:
    """Jacobi update with two bindings matches one bearing with the summed law."""

    steps = 20
    time_step = 1.0e-3

    def run(bearings: tuple[AnalyticBearing, ...]) -> _RotorBearingStepRuntime:
        rotor = RossRotor(SinglePlant(), speed=1.0, dt=time_step)
        runtime = _RotorBearingStepRuntime(
            rotor,
            TimeIterDt(time_step, steps),
            *(CoupledBearingBinding(bearing, node_link=0) for bearing in bearings),
            integrator=PC,
            predictor_corrector_options=PredictorCorrectorOptions(mode=mode),
        )
        runtime.add_static_force(STATIC_FORCE, 0)
        runtime.add_unbalance(node_link=0, **UNBALANCE)
        runtime._reset_for_owner()
        for index in range(1, steps + 1):
            runtime.advance(
                StepContext(index, time_step * index, time_step, UnitSystem.DIMENSIONAL)
            )
        return runtime

    pair = (
        AnalyticBearing(linear_law(1.0e4, 10.0)),
        AnalyticBearing(linear_law(2.0e4, 30.0)),
    )
    split = run(pair)
    single = run((AnalyticBearing(linear_law(3.0e4, 40.0)),))
    diagnostics = split._pc.diagnostics()
    assert diagnostics["trial_evaluations"] == 2 * diagnostics["trial_iterations"]
    assert diagnostics["commit_evaluations"] == 2 * diagnostics["commits"]
    for bearing in pair:
        assert bearing.probes == diagnostics["trial_iterations"]
        assert bearing.evaluations == steps + 1
    if mode == "pece":
        assert diagnostics["trial_iterations"] == steps
    np.testing.assert_allclose(_state(split), _state(single), rtol=1.0e-7, atol=1.0e-12)


def test_non_finite_trial_force_is_a_sealed_failure() -> None:
    def law(displacement, velocity, spool):
        del spool
        force = -3.0e4 * displacement - 40.0 * velocity
        if abs(displacement[1]) > 1.0e-6:
            force = force * np.nan
        return force

    with pytest.raises(FloatingPointError, match="non-finite"):
        _run(AnalyticBearing(law), time_step=1.0e-3, end_time=0.05)


def test_runtime_without_probe_or_checkpoint_is_rejected() -> None:
    class Opaque(AnalyticBearing):
        probe_force = None  # type: ignore[assignment]

    with pytest.raises(TypeError, match="checkpoint"):
        _run(Opaque(linear_law(1.0e4, 10.0)), time_step=1.0e-3, end_time=1.0e-3)


def test_multi_pad_child_without_checkpoint_is_rejected_at_reset() -> None:
    from ALB.physics.bearing.solver import MultiPad

    class Opaque(AnalyticBearing):
        probe_force = None  # type: ignore[assignment]

    rotor = RossRotor(SinglePlant(), speed=1.0, dt=1.0e-3)
    runtime = _RotorBearingStepRuntime(
        rotor,
        TimeIterDt(1.0e-3, 1),
        CoupledBearingBinding(MultiPad(Opaque(linear_law(1.0e4, 10.0))), node_link=0),
        integrator=PC,
    )
    with pytest.raises(TypeError, match="staggered"):
        runtime._reset_for_owner()


def test_integrator_arguments_are_validated() -> None:
    rotor = RossRotor(SinglePlant(), speed=1.0, dt=1.0e-3)
    binding = CoupledBearingBinding(_hardening(), node_link=0)
    with pytest.raises(ValueError, match="predictor_corrector_options"):
        _RotorBearingStepRuntime(
            rotor,
            TimeIterDt(1.0e-3, 1),
            binding,
            predictor_corrector_options=PredictorCorrectorOptions(),
        )
    with pytest.raises(TypeError, match="PredictorCorrectorOptions"):
        _RotorBearingStepRuntime(
            rotor,
            TimeIterDt(1.0e-3, 1),
            binding,
            integrator=PC,
            predictor_corrector_options={"mode": "pece"},
        )


def test_recorder_receives_every_committed_step() -> None:
    recorder = InMemoryResultRecorder()
    runtime = _run(
        _memory_bearing(),
        time_step=1.0e-3,
        end_time=0.005,
        dependencies=CouplingRuntimeDependencies(run_id="pc", recorder=recorder),
    )
    receipt = runtime.end_run()
    assert receipt.record_count == 6
    diagnostic = runtime.diagnostic_snapshot().metadata
    assert diagnostic["integrator"] == PC
    assert diagnostic["predictor_corrector"]["commits"] == 6


# ---------------------------------------------------------------------------
# Spool providers
# ---------------------------------------------------------------------------


def _spool_bearing() -> DirectSpoolAnalyticBearing:
    return DirectSpoolAnalyticBearing(spool_law(stiffness=3.0e4, damping=40.0, spool_gain=50.0))


def test_checkpointable_provider_is_called_by_every_trial_and_rolled_back() -> None:
    provider = LinearSpoolProvider(gain=500.0)
    runtime = _run(_spool_bearing(), time_step=1.0e-3, end_time=0.01, spool_provider=provider)
    diagnostics = runtime._pc.diagnostics()
    assert diagnostics["spool_trials"] == ("provider_checkpoint",)
    np.testing.assert_allclose(provider.samples, np.arange(11) * 1.0e-3)
    assert provider.evaluations == diagnostics["trial_iterations"] + 11


def test_opaque_provider_is_held_per_step() -> None:
    provider = OpaqueLinearSpoolProvider(gain=500.0)
    runtime = _run(_spool_bearing(), time_step=1.0e-3, end_time=0.01, spool_provider=provider)
    assert runtime._pc.diagnostics()["spool_trials"] == ("held_per_step",)
    np.testing.assert_allclose(provider.samples, np.arange(11) * 1.0e-3)
    assert provider.evaluations == 11


@pytest.mark.parametrize(
    ("provider_type", "expected"),
    [(LinearSpoolProvider, 4.0), (OpaqueLinearSpoolProvider, 2.0)],
)
def test_spool_channel_order_depends_on_provider_checkpoints(provider_type, expected) -> None:
    states = [
        _state(
            _run(
                _spool_bearing(),
                time_step=time_step,
                end_time=0.1,
                spool_provider=provider_type(gain=500.0),
            )
        )
        for time_step in (2.5e-4, 1.25e-4, 6.25e-5)
    ]
    assert _ratios(_differences(states))[0] == pytest.approx(expected, rel=0.1)


def test_discrete_rotor_is_supported() -> None:
    continuous = _state(_run(_hardening(), time_step=1.0e-4, end_time=0.02))
    discrete = _state(_run(_hardening(), time_step=1.0e-4, end_time=0.02, discrete=True))
    assert np.all(np.isfinite(discrete))
    # ROSS's zero-order-hold discrete model differs from the first-order
    # hold by O(h); both runs stay close.
    assert np.linalg.norm(discrete - continuous) < 0.05 * np.linalg.norm(continuous)
