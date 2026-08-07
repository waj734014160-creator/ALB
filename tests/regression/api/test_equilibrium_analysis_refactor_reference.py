"""Exact regression coverage for the single public equilibrium model."""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import textwrap

import numpy as np
import pytest

import ALB
from ALB.api import _analysis_numerics
from ALB.physics.bearing import solver as bearing_solver_module


_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE_JSON = (
    _ROOT / "refs" / "equilibrium_analysis_refactor_reference_v1.json"
)
_REFERENCE_NPZ = (
    _ROOT / "refs" / "equilibrium_analysis_refactor_reference_v1.npz"
)


@pytest.mark.parametrize("case_name", ["liquid_film", "active_lubricated"])
def test_equilibrium_analysis_matches_pre_refactor_reference_exactly(
    case_name: str,
) -> None:
    metadata = json.loads(_REFERENCE_JSON.read_text(encoding="utf-8"))
    case = metadata["cases"][case_name]
    bearing = ALB.build_bearing(ALB.BearingConfig(case["config_spec"]))
    result = ALB.EquilibriumSolver(
        bearing,
        ALB.EquilibriumOptions(**case["options"]),
    ).solve(
        case["load"],
        case["initial_displacement"],
    )

    with np.load(_REFERENCE_NPZ) as reference:
        for field in case["array_fields"]:
            np.testing.assert_array_equal(
                result.values[field],
                reference[f"{case_name}_{field}"],
            )
    assert dict(result.metadata) == case["result_metadata"]
    assert result.convergence.residual == case["convergence"]["residual"]
    assert result.convergence.converged == case["convergence"]["converged"]
    assert result.convergence.iterations == case["convergence"]["iterations"]
    assert result.convergence.message == case["convergence"]["message"]


def test_bearing_analysis_delegates_to_public_equilibrium_solver() -> None:
    metadata = json.loads(_REFERENCE_JSON.read_text(encoding="utf-8"))
    case = metadata["cases"]["liquid_film"]
    bearing = ALB.build_bearing(ALB.BearingConfig(case["config_spec"]))
    result = bearing.analysis.find_equilibrium(
        case["load"],
        case["initial_displacement"],
        ALB.EquilibriumOptions(**case["options"]),
    )

    with np.load(_REFERENCE_NPZ) as reference:
        np.testing.assert_array_equal(
            result.values["displacement"],
            reference["liquid_film_displacement"],
        )
        np.testing.assert_array_equal(
            result.values["bearing_force"],
            reference["liquid_film_bearing_force"],
        )


def test_active_lubricated_equilibrium_supports_multiple_evaluations() -> None:
    metadata = json.loads(_REFERENCE_JSON.read_text(encoding="utf-8"))
    case = metadata["cases"]["active_lubricated"]
    bearing = ALB.build_bearing(ALB.BearingConfig(case["config_spec"]))
    load = np.asarray(case["load"], dtype=float) * 0.9

    result = ALB.EquilibriumSolver(
        bearing,
        ALB.EquilibriumOptions(
            max_iterations=5,
            damping=1.0,
            stall_patience=0,
        ),
    ).solve(load, case["initial_displacement"])

    assert result.convergence.converged
    assert result.convergence.residual < 1.0e-4
    assert result.metadata["evaluations"] == 7
    assert result.convergence.iterations == 2


@pytest.mark.parametrize(
    "method",
    [
        ALB.BearingAnalysis.find_equilibrium,
        ALB.EquilibriumSolver.solve,
        ALB.EquilibriumSolver._prepare,
        ALB.EquilibriumSolver._iterate,
        ALB.EquilibriumSolver._evaluate,
        ALB.EquilibriumSolver._newton_step,
    ],
)
def test_equilibrium_methods_contain_no_nested_function_definitions(
    method: object,
) -> None:
    source = textwrap.dedent(inspect.getsource(method))
    tree = ast.parse(source)
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node is not function
        for node in ast.walk(function)
    )


def test_equilibrium_has_one_public_solver_implementation() -> None:
    assert not hasattr(_analysis_numerics, "EquilibriumSolver")
    assert not hasattr(_analysis_numerics, "_solve_equilibrium_iteration")
    assert not hasattr(bearing_solver_module, "_InternalEquilibriumSolver")
