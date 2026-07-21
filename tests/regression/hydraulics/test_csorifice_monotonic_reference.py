"""Exact regression against the pre-edit CSOrifice monotonic v2 oracle."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any

import numpy as np

from ALB.physics.hydraulics.orifice import (
    _assembly_flow_jacobian,
    _node_flow_jacobian,
    define_equations,
    solve_q,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs" / "csorifice_monotonic_reference_v2.json"
REFERENCE_NPZ = ROOT / "refs" / "csorifice_monotonic_reference_v2.npz"
EQUIVALENCE_TEST = (
    ROOT / "tests" / "regression" / "bearing" / "test_nodim_alb_equivalence.py"
)


def _finite_difference_jacobian(case: dict[str, Any], step: float) -> np.ndarray:
    pn = np.asarray(case["pn"], dtype=float)
    columns = []
    for index in range(len(pn)):
        delta = np.zeros_like(pn)
        delta[index] = step
        plus = solve_q(
            case["cq0"],
            case["cq1_h2"],
            case["cq2"],
            pn + delta,
            case["xv"],
            case["ps"],
            0.0,
        )[2:]
        minus = solve_q(
            case["cq0"],
            case["cq1_h2"],
            case["cq2"],
            pn - delta,
            case["xv"],
            case["ps"],
            0.0,
        )[2:]
        columns.append((plus - minus) / (2.0 * step))
    return np.column_stack(columns)


def _actual_local(metadata: dict[str, Any]) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    for name, case in metadata["local_cases"].items():
        pn = np.asarray(case["pn"], dtype=float)
        cq1_h2 = np.asarray(case["cq1_h2"], dtype=float)
        answer = solve_q(
            case["cq0"],
            cq1_h2,
            case["cq2"],
            pn,
            case["xv"],
            case["ps"],
            0.0,
        )
        prefix = f"local.{name}"
        arrays[f"{prefix}.answer"] = np.asarray(answer, dtype=np.float64)
        arrays[f"{prefix}.residual"] = np.asarray(
            define_equations(
                case["cq0"],
                cq1_h2,
                case["cq2"],
                pn,
                case["xv"],
                case["ps"],
                0.0,
            )(answer),
            dtype=np.float64,
        )
        arrays[f"{prefix}.dqndpn"] = np.asarray(
            _node_flow_jacobian(
                case["cq0"],
                cq1_h2,
                case["cq2"],
                pn,
                abs(case["xv"]),
                case["ps"],
                float(answer[1]),
            ),
            dtype=np.float64,
        )
        arrays[f"{prefix}.assembly_qdp"] = np.asarray(
            _assembly_flow_jacobian(
                case["cq0"],
                cq1_h2,
                case["cq2"],
                pn,
                abs(case["xv"]),
                case["ps"],
                float(answer[1]),
            ),
            dtype=np.float64,
        )
        arrays[f"{prefix}.dqndpn_fd"] = np.asarray(
            _finite_difference_jacobian(case, float(case["fd_step"])),
            dtype=np.float64,
        )
    return arrays


def _actual_coupled(metadata: dict[str, Any]) -> dict[str, np.ndarray]:
    namespace = runpy.run_path(str(EQUIVALENCE_TEST))
    flow_cases = [tuple(case) for case in metadata["coupled_cases"]["flow_cases"]]
    thermal_case = tuple(metadata["coupled_cases"]["thermal_case"])
    arrays: dict[str, np.ndarray] = {}
    dim_forces = []
    nd_forces = []
    for case in flow_cases:
        dim_model, dim_force = namespace["_run_dimensional"](case)
        cq0, cq1, cq2 = namespace["_orifice_coefficients"](dim_model)
        _, nd_force = namespace["_run_nodim"](
            case, cq0=cq0, cq1=cq1, cq2=cq2
        )
        dim_forces.append(dim_force)
        nd_forces.append(nd_force)
    arrays["flow.inputs"] = np.asarray(flow_cases, dtype=np.float64)
    arrays["flow.dim_force"] = np.asarray(dim_forces, dtype=np.float64)
    arrays["flow.nd_force"] = np.asarray(nd_forces, dtype=np.float64)

    dim_model, dim_force = namespace["_run_dimensional_thermal"](thermal_case)
    coefficients = [
        namespace["_orifice_coefficients"](orifice=item)
        for item in namespace["_all_orifices"](dim_model)
    ]
    nd_model, nd_force = namespace["_run_nodim_thermal"](
        thermal_case, branch_orifice_coefficients=coefficients
    )
    arrays["thermal.input"] = np.asarray(thermal_case, dtype=np.float64)
    arrays["thermal.dim_force"] = np.asarray(dim_force, dtype=np.float64)
    arrays["thermal.nd_force"] = np.asarray(nd_force, dtype=np.float64)
    for label, model in (("dim", dim_model), ("nd", nd_model)):
        arrays[f"thermal.{label}.pressure"] = np.stack(
            [pad.post_process.pressure_field for pad in model.pads]
        ).astype(np.float64)
        arrays[f"thermal.{label}.temperature"] = np.stack(
            [pad.post_process.temperature_field for pad in model.pads]
        ).astype(np.float64)
        arrays[f"thermal.{label}.viscosity"] = np.stack(
            [pad.post_process.viscosity_field for pad in model.pads]
        ).astype(np.float64)
        arrays[f"thermal.{label}.iterations"] = np.asarray(
            [pad.thermal_state["iterations"] for pad in model.pads], dtype=np.int64
        )
        orifices = namespace["_all_orifices"](model)
        arrays[f"thermal.{label}.psv"] = np.asarray(
            [item.psv for item in orifices], dtype=np.float64
        )
        arrays[f"thermal.{label}.qn"] = np.stack(
            [item.qn for item in orifices]
        ).astype(np.float64)
    return arrays


def test_csorifice_monotonic_v2_reference_is_exact():
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    expected = np.load(REFERENCE_NPZ)
    actual = {**_actual_local(metadata), **_actual_coupled(metadata)}

    assert set(actual) == set(expected.files) == set(metadata["arrays"])
    for name in sorted(actual):
        np.testing.assert_array_equal(actual[name], expected[name], err_msg=name)
        assert list(actual[name].shape) == metadata["arrays"][name]["shape"]
        assert str(actual[name].dtype) == metadata["arrays"][name]["dtype"]
        digest = hashlib.sha256(
            np.ascontiguousarray(expected[name]).tobytes()
        ).hexdigest()
        assert digest == metadata["arrays"][name]["sha256"]
