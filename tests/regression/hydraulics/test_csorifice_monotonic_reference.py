"""Exact regression against the pre-edit CSOrifice monotonic v2 oracle."""

from __future__ import annotations

import hashlib
import json
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


def test_csorifice_monotonic_v2_reference_is_exact():
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    expected = np.load(REFERENCE_NPZ)
    actual = _actual_local(metadata)

    expected_local = {
        name for name in expected.files if name.startswith("local.")
    }
    assert set(actual) == expected_local
    for name in sorted(actual):
        np.testing.assert_array_equal(actual[name], expected[name], err_msg=name)
        assert list(actual[name].shape) == metadata["arrays"][name]["shape"]
        assert str(actual[name].dtype) == metadata["arrays"][name]["dtype"]
        digest = hashlib.sha256(
            np.ascontiguousarray(expected[name]).tobytes()
        ).hexdigest()
        assert digest == metadata["arrays"][name]["sha256"]
