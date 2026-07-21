"""Generate the independent CSOrifice monotonic-solver v2 reference.

The production solver is intentionally not used for the expected local roots.
This script supplies an independent scalar mass-balance oracle, patches it into
the unchanged runtime only while collecting full ALB outputs, and stores both
local equation data and coupled dimensional/nondimensional results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import runpy
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.physics.hydraulics import orifice as orifice_module


DEFAULT_JSON = ROOT / "refs" / "csorifice_monotonic_reference_v2.json"
DEFAULT_NPZ = ROOT / "refs" / "csorifice_monotonic_reference_v2.npz"
EQUIVALENCE_TEST = (
    ROOT / "tests" / "regression" / "bearing" / "test_nodim_alb_equivalence.py"
)


def _vector(value: Any) -> np.ndarray:
    """Return a flat float vector for the independent oracle."""
    return np.asarray(value, dtype=float).reshape(-1)


def _node_flows(
    psv: float, pn: np.ndarray, cq1_h2: np.ndarray, cq2: float
) -> np.ndarray:
    """Evaluate the algebraically stable signed node-flow relation."""
    pressure_delta = psv - pn
    absolute_delta = np.abs(pressure_delta)
    denominator = np.sqrt(cq2**2 + 4.0 * cq1_h2 * absolute_delta) + cq2
    flows = np.zeros_like(pressure_delta)
    active = absolute_delta > 0.0
    if np.any(active & (denominator == 0.0)):
        raise ValueError("cq1_h2 and cq2 cannot both vanish for nonzero pressure")
    flows[active] = 2.0 * pressure_delta[active] / denominator[active]
    return flows


def _source_flow(psv: float, cq0: float, xv: float, ps: float) -> float:
    """Evaluate the signed zero-leakage source flow."""
    pressure_delta = ps - psv
    return float(
        np.sign(pressure_delta)
        * cq0
        * abs(xv)
        * np.sqrt(abs(pressure_delta))
    )


def _solve_scalar(
    cq0: Any,
    cq1_h2: Any,
    cq2: Any,
    pn: Any,
    xv: Any,
    ps: Any,
    q_leak: Any,
    init: Any = None,
) -> np.ndarray:
    """Solve the zero-leakage orifice equations through one monotonic root."""
    del init
    pn = _vector(pn)
    cq0 = float(_vector(cq0)[0])
    cq1_h2 = np.broadcast_to(_vector(cq1_h2), pn.shape).astype(float, copy=False)
    cq2 = float(_vector(cq2)[0])
    xv = abs(float(_vector(xv)[0]))
    ps = float(_vector(ps)[0])
    q_leak = float(_vector(q_leak)[0])
    if q_leak != 0.0:
        raise ValueError("The v2 oracle requires q_leak == 0.0")

    def balance(psv: float) -> float:
        return _source_flow(psv, cq0, xv, ps) - float(
            np.sum(_node_flows(psv, pn, cq1_h2, cq2))
        )

    lower = min(ps, float(np.min(pn)))
    upper = max(ps, float(np.max(pn)))
    lower_value = balance(lower)
    upper_value = balance(upper)
    if lower_value < 0.0 or upper_value > 0.0:
        raise RuntimeError("The monotonic root is not enclosed by pressure bounds")
    if lower == upper or lower_value == 0.0:
        psv = lower
    elif upper_value == 0.0:
        psv = upper
    else:
        psv = float(
            brentq(
                balance,
                lower,
                upper,
                xtol=np.nextafter(0.0, 1.0),
                rtol=4.0 * np.finfo(float).eps,
                maxiter=300,
            )
        )
    node_flow = _node_flows(psv, pn, cq1_h2, cq2)
    return np.concatenate(([float(np.sum(node_flow)), psv], node_flow))


def _flow_jacobian(
    cq0: float,
    cq1_h2: np.ndarray,
    cq2: float,
    pn: np.ndarray,
    xv: float,
    ps: float,
    psv: float,
) -> np.ndarray:
    """Return the implicit derivative of node flows with respect to pn."""
    node_conductance = 1.0 / np.sqrt(
        cq2**2 + 4.0 * cq1_h2 * np.abs(psv - pn)
    )
    source_delta = abs(ps - psv)
    if source_delta == 0.0:
        dpsv_dpn = np.zeros_like(node_conductance)
    else:
        source_conductance = cq0 * abs(xv) / (2.0 * np.sqrt(source_delta))
        dpsv_dpn = node_conductance / (
            source_conductance + float(np.sum(node_conductance))
        )
    return np.outer(node_conductance, dpsv_dpn) - np.diag(node_conductance)


def _oracle_cal_qdp(self: Any, pn: Any) -> np.ndarray:
    """Return the positive stiffness contribution expected by film assembly."""
    pn = _vector(self._node_pressure_for_equations(pn))
    if self.xv == 0:
        return np.zeros((len(pn), len(pn)), dtype=float)
    return -_flow_jacobian(
        float(self.cq0),
        np.broadcast_to(_vector(self.cq1_h2), pn.shape),
        float(self.cq2),
        pn,
        abs(float(self.xv)),
        float(self._supply_pressure_for_equations()),
        float(self.psv),
    )


@contextmanager
def _patched_oracle() -> Iterator[None]:
    """Install the independent q/qdp oracle for coupled reference runs."""
    original_solve = orifice_module.solve_q
    original_qdp = orifice_module.NodimCSOrifice._cal_qdp
    orifice_module.solve_q = _solve_scalar
    orifice_module.NodimCSOrifice._cal_qdp = _oracle_cal_qdp
    try:
        yield
    finally:
        orifice_module.solve_q = original_solve
        orifice_module.NodimCSOrifice._cal_qdp = original_qdp


def _finite_difference_jacobian(case: dict[str, Any], step: float) -> np.ndarray:
    """Build an independent central-difference qn Jacobian."""
    pn = np.asarray(case["pn"], dtype=float)
    columns = []
    for index in range(len(pn)):
        delta = np.zeros_like(pn)
        delta[index] = step
        plus = _solve_scalar(
            case["cq0"],
            case["cq1_h2"],
            case["cq2"],
            pn + delta,
            case["xv"],
            case["ps"],
            0.0,
        )[2:]
        minus = _solve_scalar(
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


def _local_arrays() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Generate representative supply, return, reverse, and endpoint roots."""
    cases = {
        "supply": {
            "cq0": 1.7,
            "cq1_h2": [0.8, 1.2, 2.0],
            "cq2": 0.3,
            "pn": [0.2, 0.35, 0.5],
            "xv": 0.6,
            "ps": 1.0,
            "fd_step": 1e-6,
        },
        "zero_source_return": {
            "cq0": 1.7,
            "cq1_h2": [0.8, 1.2, 2.0],
            "cq2": 0.3,
            "pn": [-1.8e-9, -2.6e-9, -1.78e-9],
            "xv": 0.4,
            "ps": 0.0,
            "fd_step": 3e-10,
        },
        "reverse": {
            "cq0": 1.7,
            "cq1_h2": [0.8, 1.2, 2.0],
            "cq2": 0.3,
            "pn": [0.7, 0.8, 0.9],
            "xv": 0.6,
            "ps": 0.0,
            "fd_step": 1e-6,
        },
        "endpoint": {
            "cq0": 1.7,
            "cq1_h2": [0.8, 1.2, 2.0],
            "cq2": 0.3,
            "pn": [0.0, 0.0, 0.0],
            "xv": 0.6,
            "ps": 0.0,
            "fd_step": 1e-12,
        },
    }
    arrays: dict[str, np.ndarray] = {}
    for name, case in cases.items():
        answer = _solve_scalar(
            case["cq0"],
            case["cq1_h2"],
            case["cq2"],
            case["pn"],
            case["xv"],
            case["ps"],
            0.0,
        )
        pn = np.asarray(case["pn"], dtype=float)
        cq1_h2 = np.asarray(case["cq1_h2"], dtype=float)
        jacobian = _flow_jacobian(
            float(case["cq0"]),
            cq1_h2,
            float(case["cq2"]),
            pn,
            float(case["xv"]),
            float(case["ps"]),
            float(answer[1]),
        )
        equations = orifice_module.define_equations(
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
            equations(answer), dtype=np.float64
        )
        arrays[f"{prefix}.dqndpn"] = np.asarray(jacobian, dtype=np.float64)
        arrays[f"{prefix}.assembly_qdp"] = np.asarray(-jacobian, dtype=np.float64)
        arrays[f"{prefix}.dqndpn_fd"] = np.asarray(
            _finite_difference_jacobian(case, float(case["fd_step"])),
            dtype=np.float64,
        )
    return arrays, cases


def _coupled_arrays() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Collect corrected full-model arrays under the independent oracle."""
    namespace = runpy.run_path(str(EQUIVALENCE_TEST))
    thermal_case = (0.45, -0.25, 0.10, -0.08, 0.6, -0.4)
    flow_cases = [
        (0.0, 0.0, 0.0, 0.0, 0.3, -0.2),
        thermal_case,
        (-0.55, 0.20, -0.12, 0.09, -0.7, 0.5),
        (0.65, 0.35, 0.2, -0.15, 0.8, 0.7),
    ]
    arrays: dict[str, np.ndarray] = {}
    with _patched_oracle():
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
                [pad.thermal_state["iterations"] for pad in model.pads],
                dtype=np.int64,
            )
            orifices = namespace["_all_orifices"](model)
            arrays[f"thermal.{label}.psv"] = np.asarray(
                [item.psv for item in orifices], dtype=np.float64
            )
            arrays[f"thermal.{label}.qn"] = np.stack(
                [item.qn for item in orifices]
            ).astype(np.float64)
    metadata = {
        "thermal_case": list(thermal_case),
        "flow_cases": [list(case) for case in flow_cases],
    }
    return arrays, metadata


def _sha256(array: np.ndarray) -> str:
    """Return the SHA-256 digest of an array's raw C-order bytes."""
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _git_head() -> str:
    """Return the source commit used before the production correction."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def main() -> None:
    """Generate the immutable v2 metadata and numeric archive."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError("Refusing to overwrite an existing v2 reference")

    local_arrays, local_cases = _local_arrays()
    coupled_arrays, coupled_cases = _coupled_arrays()
    arrays = {**local_arrays, **coupled_arrays}
    metadata = {
        "reference_name": "csorifice_monotonic_reference_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "q_leak_contract": "exactly_zero",
        "oracle": "independent monotonic scalar mass balance with implicit qdp",
        "local_cases": local_cases,
        "coupled_cases": coupled_cases,
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _sha256(value),
            }
            for name, value in sorted(arrays.items())
        },
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.npz, **arrays)
    args.json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.json)
    print(args.npz)
    print(f"arrays={len(arrays)}")


if __name__ == "__main__":
    main()
