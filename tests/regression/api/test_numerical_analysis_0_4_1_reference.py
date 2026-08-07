"""Regression contracts for numerical methods restored in ALB 0.4.1."""

from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import ALB
from ALB.api import analysis as analysis_module
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    UnitSystem,
)


_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE_JSON = _ROOT / "refs" / "alb_0_4_1_numerical_contract_v1.json"
_REFERENCE_NPZ = _ROOT / "refs" / "alb_0_4_1_numerical_contract_v1.npz"


@pytest.fixture(scope="module")
def reference_metadata() -> dict[str, object]:
    return json.loads(_REFERENCE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def reference_arrays() -> dict[str, np.ndarray]:
    with np.load(_REFERENCE_NPZ) as archive:
        return {name: archive[name].copy() for name in archive.files}


class _SyntheticEquilibriumRuntime:
    def __init__(self, failure_evaluation: int | None) -> None:
        self._failure_evaluation = failure_evaluation
        self._evaluation_count = 0
        self._input: BearingInput | None = None
        self._output: BearingOutput | None = None
        self.convergence_status = ConvergenceStatus(0.0, True)

    @staticmethod
    def _reset_for_owner() -> None:
        return None

    def input(self, value: BearingInput) -> None:
        self._input = value

    def evaluate_static(self) -> None:
        assert self._input is not None
        self._evaluation_count += 1
        coordinate = np.asarray(self._input.displacement, dtype=float)
        converged = self._evaluation_count != self._failure_evaluation
        self.convergence_status = ConvergenceStatus(0.0, converged)
        self._output = BearingOutput(
            force=np.array(
                [
                    2.0 * coordinate[0],
                    1.0 + 3.0 * coordinate[1],
                ]
            ),
            time=float(self._input.time),
            unit_system=UnitSystem.NONDIMENSIONAL,
        )

    def output(self) -> BearingOutput:
        assert self._output is not None
        return self._output


class _SyntheticEquilibriumBearing:
    config = SimpleNamespace(
        unit_system="nondimensional",
        control_mode="uncontrolled",
        family="liquid_film",
    )


def _liquid_linearization_config() -> ALB.BearingConfig:
    return ALB.BearingConfig(
        {
            "family": "liquid_film",
            "unit_system": "dimensional",
            "time_step": 6.667e-4,
            "node": 0,
            "film": {
                "circumferential_elements": 7,
                "axial_elements": 5,
                "max_iterations": 80,
                "solver_tolerance": 1.0e-9,
                "continuous_boundary": False,
                "solver": "newton",
            },
            "restrictors": None,
            "thermal": None,
        }
    )


def _active_linearization_config() -> ALB.BearingConfig:
    return ALB.BearingConfig(
        {
            "family": "active_lubricated",
            "unit_system": "dimensional",
            "time_step": 6.667e-4,
            "node": 0,
            "film": {
                "circumferential_elements": 7,
                "axial_elements": 5,
                "max_iterations": 300,
                "solver_tolerance": 1.0e-9,
                "continuous_boundary": False,
                "solver": "newton",
            },
            "restrictors": {
                "positions": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            },
            "tank": {},
            "valve": {
                "model": "transfer_function",
                "numerator": [1.0],
                "denominator": [1.0],
            },
            "control": {"mode": "external_spool"},
            "transforms": {},
            "thermal": None,
        }
    )


def test_equilibrium_options_are_public_immutable_and_stable() -> None:
    options = ALB.EquilibriumOptions()

    assert options == ALB.EquilibriumOptions(
        max_iterations=30,
        relative_tolerance=1.0e-4,
        damping=0.05,
        jacobian_step=1.0e-2,
        fallback_stiffness=(5.0, 5.0),
        stall_patience=5,
        stall_relative_tolerance=0.0,
        time=0.0,
    )
    with pytest.raises(FrozenInstanceError):
        options.damping = 1.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("case_name", "failure_evaluation"),
    [
        ("initial", None),
        ("multi_step", None),
        ("inner_failure", 1),
        ("frozen_jacobian", 5),
    ],
)
def test_equilibrium_algorithm_matches_frozen_reference_exactly(
    case_name: str,
    failure_evaluation: int | None,
    reference_metadata: dict[str, object],
    reference_arrays: dict[str, np.ndarray],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = reference_metadata["cases"]
    assert isinstance(cases, dict)
    equilibrium = cases["static_equilibrium"]
    assert isinstance(equilibrium, dict)
    case = equilibrium[case_name]
    assert isinstance(case, dict)
    inputs = case["input"]
    assert isinstance(inputs, dict)
    solver = ALB.EquilibriumSolver(
        _SyntheticEquilibriumBearing(),
        ALB.EquilibriumOptions(
            max_iterations=int(inputs["iter_num"]),
            relative_tolerance=float(inputs["error_set"]),
            damping=float(inputs["damp"]),
            jacobian_step=float(inputs["delta"]),
            stall_patience=int(inputs.get("newton_stall_patience", 5)),
            stall_relative_tolerance=0.0,
        ),
    )
    runtime = _SyntheticEquilibriumRuntime(failure_evaluation)
    monkeypatch.setattr(solver, "_new_runtime", lambda: runtime)

    try:
        result = solver.solve(
            inputs["load"],
            initial_displacement=inputs["initial_displacement"],
        )
    except ALB.CalculationError as exc:
        assert exc.failure_snapshot is not None
        values = exc.failure_snapshot.values
        metadata = exc.failure_snapshot.metadata
        residual = float(values["evaluation_relative_residual"][-1])
        iterations = 0
    else:
        values = result.values
        metadata = result.metadata
        residual = result.convergence.residual
        iterations = result.convergence.iterations

    np.testing.assert_array_equal(
        values["displacement"],
        reference_arrays[f"static_{case_name}_final"],
    )
    np.testing.assert_array_equal(
        values["bearing_force"],
        reference_arrays[f"static_{case_name}_force"],
    )
    np.testing.assert_array_equal(
        values["evaluation_displacement"],
        reference_arrays[f"static_{case_name}_evaluated_points"],
    )
    np.testing.assert_array_equal(
        np.asarray(values["evaluation_inner_converged"], dtype=np.int8),
        reference_arrays[f"static_{case_name}_convergence_flags"],
    )
    assert residual == case["residual"]
    assert metadata["success"] is case["finished"]
    assert metadata["inner_converged"] is case["inner_converged"]
    assert metadata["stop_reason"] == case["stop_reason"]
    assert iterations == case["iterations"]


class _SyntheticWhirlRuntime:
    unit_system = UnitSystem.DIMENSIONAL

    def __init__(self) -> None:
        self._stiffness = np.array(
            [[2.0e6, 3.0e5], [-4.0e5, 1.5e6]]
        )
        self._damping = np.array([[800.0, -120.0], [75.0, 650.0]])

    def calculate(
        self,
        *,
        displacement: object,
        velocity: object,
        time: float,
        spool: object = None,
    ) -> SimpleNamespace:
        del time, spool
        coordinate = np.asarray(displacement, dtype=float)
        speed = np.asarray(velocity, dtype=float)
        force = -(
            coordinate @ self._stiffness.T
            + speed @ self._damping.T
        )
        return SimpleNamespace(
            force=force,
            convergence=ConvergenceStatus(0.0, True, iterations=1),
        )


class _SyntheticWhirlBearing:
    config = SimpleNamespace(unit_system="dimensional")

    @staticmethod
    def _fresh() -> _SyntheticWhirlRuntime:
        return _SyntheticWhirlRuntime()


class _FailedWhirlRuntime(_SyntheticWhirlRuntime):
    def calculate(self, **kwargs: object) -> SimpleNamespace:
        result = super().calculate(**kwargs)
        result.convergence = ConvergenceStatus(
            1.0,
            False,
            iterations=1,
            message="synthetic trajectory failure",
        )
        return result


class _FailedWhirlBearing:
    config = SimpleNamespace(unit_system="dimensional")

    @staticmethod
    def _fresh() -> _FailedWhirlRuntime:
        return _FailedWhirlRuntime()


def test_rotated_two_whirl_identification_matches_reference_exactly(
    reference_arrays: dict[str, np.ndarray],
) -> None:
    trajectory = ALB.EllipseTrajectory(
        center=(1.0e-5, -2.0e-5),
        semi_axes=(2.0e-4, 7.0e-5),
        orientation_rad=0.4,
    )
    result = ALB.BearingAnalysis(
        _SyntheticWhirlBearing()
    ).dynamic_coefficients(
        trajectory,
        reference_arrays["whirl_time"],
        frequency_hz=5.0,
    )

    for name in (
        "forward_displacement",
        "forward_velocity",
        "forward_force",
        "reverse_displacement",
        "reverse_velocity",
        "reverse_force",
        "transfer_real",
        "transfer_imag",
        "stiffness",
        "damping",
    ):
        np.testing.assert_array_equal(
            result.values[name],
            reference_arrays[f"whirl_{name}"],
        )
    np.testing.assert_array_equal(
        result.values["forward_time"],
        reference_arrays["whirl_time"],
    )
    np.testing.assert_array_equal(
        result.values["reverse_time"],
        reference_arrays["whirl_time"],
    )
    np.testing.assert_array_equal(
        result.values["forward_converged"],
        np.ones(reference_arrays["whirl_time"].shape, dtype=bool),
    )
    np.testing.assert_array_equal(
        result.values["reverse_converged"],
        np.ones(reference_arrays["whirl_time"].shape, dtype=bool),
    )
    assert result.diagnostics["method"] == "forward_reverse_whirl_fft"


def test_dynamic_coefficients_do_not_publish_after_sample_failure(
    reference_arrays: dict[str, np.ndarray],
) -> None:
    trajectory = ALB.EllipseTrajectory(
        center=(1.0e-5, -2.0e-5),
        semi_axes=(2.0e-4, 7.0e-5),
        orientation_rad=0.4,
    )

    with pytest.raises(ALB.CalculationError) as caught:
        ALB.BearingAnalysis(_FailedWhirlBearing()).dynamic_coefficients(
            trajectory,
            reference_arrays["whirl_time"],
            frequency_hz=5.0,
        )

    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["forward_converged"] is False
    assert snapshot.metadata["reverse_converged"] is False
    assert set(snapshot.values) == {"forward", "reverse"}


def test_dynamic_coefficients_have_no_single_trajectory_least_squares() -> None:
    source = inspect.getsource(analysis_module)
    assert "lstsq" not in source


def test_liquid_equation_derivative_linearization_matches_reference_exactly(
    reference_arrays: dict[str, np.ndarray],
) -> None:
    result = ALB.build_bearing(
        _liquid_linearization_config()
    ).analysis.harmonic_linearize(
        (8.0e-6, -4.0e-6),
        5.0,
    )

    for name in ("static_force", "stiffness", "damping"):
        np.testing.assert_array_equal(
            result.values[name],
            reference_arrays[f"liquid_{name}"],
        )


def test_equilibrium_uses_an_isolated_runtime_and_preserves_latest_result() -> None:
    bearing = ALB.build_bearing(_liquid_linearization_config())
    latest = bearing.calculate(displacement=(0.0, 0.0), time=0.0)

    equilibrium = bearing.analysis.find_equilibrium(
        load=-latest.force,
        initial_displacement=(0.0, 0.0),
    )

    np.testing.assert_array_equal(
        equilibrium.values["displacement"],
        np.zeros(2),
    )
    np.testing.assert_array_equal(
        equilibrium.values["bearing_force"],
        latest.force,
    )
    assert bearing.latest_result is latest


def test_active_equation_derivative_linearization_matches_reference_exactly(
    reference_arrays: dict[str, np.ndarray],
) -> None:
    result = ALB.build_bearing(
        _active_linearization_config()
    ).analysis.harmonic_linearize(
        (8.0e-6, -4.0e-6),
        5.0,
        spool=(0.2, 0.15),
    )

    for name in (
        "static_force",
        "stiffness",
        "damping",
        "pad_stiffness",
        "pad_damping",
        "spool_jacobian",
        "base_spool",
    ):
        np.testing.assert_array_equal(
            result.values[name],
            reference_arrays[f"active_{name}"],
        )


def test_active_harmonic_rejects_unverified_restrictor_topology() -> None:
    spec = _active_linearization_config().to_dict()["spec"]
    spec["restrictors"]["positions"] = [[0.5, 0.25], [0.5, 0.75]]
    bearing = ALB.build_bearing(ALB.BearingConfig(spec))

    with pytest.raises(
        ALB.CalculationError,
        match="three-node CSOrifice topology",
    ):
        bearing.analysis.harmonic_linearize(
            (8.0e-6, -4.0e-6),
            5.0,
            spool=(0.2, 0.15),
        )


class _NeverConvergedRuntime:
    convergence_status = ConvergenceStatus(
        residual=1.0,
        converged=False,
        iterations=1,
        message="synthetic inner failure",
    )

    @staticmethod
    def _reset_for_owner() -> None:
        return None

    def step(self, bearing_input: object) -> BearingOutput:
        return BearingOutput(
            force=np.array([0.0, 0.5]),
            time=float(bearing_input.time),
            unit_system=UnitSystem.NONDIMENSIONAL,
        )


class _NeverConvergedBearing:
    config = SimpleNamespace(
        unit_system="nondimensional",
        control_mode="uncontrolled",
        family="liquid_film",
    )


class _RaisingRuntime(_NeverConvergedRuntime):
    def __init__(self) -> None:
        self.calls = 0
        self.convergence_status = ConvergenceStatus(0.5, True)

    def step(self, bearing_input: object) -> BearingOutput:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("synthetic inner exception")
        return BearingOutput(
            force=np.array([0.0, 0.5]),
            time=float(bearing_input.time),
            unit_system=UnitSystem.NONDIMENSIONAL,
        )


def test_equilibrium_inner_failure_raises_with_complete_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    solver = ALB.EquilibriumSolver(_NeverConvergedBearing())
    monkeypatch.setattr(
        solver,
        "_new_runtime",
        lambda: _NeverConvergedRuntime(),
    )

    with pytest.raises(ALB.CalculationError) as caught:
        solver.solve(
            (0.0, -1.0),
            initial_displacement=(0.2, -0.1),
        )

    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["stop_reason"] == "inner_not_converged"
    assert snapshot.metadata["inner_converged"] is False
    np.testing.assert_array_equal(
        snapshot.values["evaluation_inner_converged"],
        [False],
    )


def test_equilibrium_inner_exception_keeps_last_trusted_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    solver = ALB.EquilibriumSolver(_NeverConvergedBearing())
    monkeypatch.setattr(solver, "_new_runtime", _RaisingRuntime)

    with pytest.raises(ALB.CalculationError) as caught:
        solver.solve(
            (0.0, -1.0),
            initial_displacement=(0.2, -0.1),
        )

    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["stop_reason"] == "inner_exception"
    assert snapshot.metadata["exception_type"] == "RuntimeError"
    np.testing.assert_array_equal(
        snapshot.values["last_trusted_displacement"],
        [[0.2, -0.1]],
    )
    np.testing.assert_array_equal(
        snapshot.values["last_trusted_force"],
        [[0.0, 0.5]],
    )


def test_harmonic_signature_has_no_trajectory_fit_parameters() -> None:
    parameters = inspect.signature(
        ALB.BearingAnalysis.harmonic_linearize
    ).parameters
    assert "amplitude" not in parameters
    assert "points_per_cycle" not in parameters


def test_harmonic_rejects_unverified_bearing_families() -> None:
    gas = ALB.BearingConfig(
        {
            "family": "gas_film",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "film": {},
        }
    )

    with pytest.raises(
        ALB.CalculationError,
        match="only verified dimensional",
    ):
        ALB.build_bearing(gas).analysis.harmonic_linearize(
            (0.0, 0.0),
            5.0,
        )
