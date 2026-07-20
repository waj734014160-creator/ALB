"""Generate the immutable thermal-convergence addendum from an explicit source tree.

The source tree is selected through ``ALB_REFERENCE_SOURCE_ROOT`` so the first
artifact can be generated from an archive of the pre-refactor commit. Existing
artifacts are never overwritten.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import sys
from typing import Any


SOURCE_ROOT = Path(os.environ["ALB_REFERENCE_SOURCE_ROOT"]).resolve()
SOURCE_COMMIT = os.environ["ALB_REFERENCE_SOURCE_COMMIT"]
SOURCE_TAG = os.environ.get("ALB_REFERENCE_SOURCE_TAG")
sys.path.insert(0, str(SOURCE_ROOT))

for _thread_variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_thread_variable, "1")

import numpy as np

from ALB.config import HydConfig, ThermalConfig

try:
    from ALB.physics.bearing import HydrostaticBearing
    from ALB.physics.thermal import ThermalHydroBearing
except ModuleNotFoundError:
    from ALB.bearing import HydrostaticBearing
    from ALB.thermal import ThermalHydroBearing

import ALB


SCHEMA = "alb.full-repo-refactor-thermal-addendum.v1"
SEED = 20260720


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        if np.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _array_digest(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).view(np.uint8)).hexdigest()


def _instrument(model: ThermalHydroBearing) -> dict[str, list[Any]]:
    """Record outer errors, relax values, pressure residuals, and Newton residuals."""

    trace: dict[str, list[Any]] = {
        "outer_rel_errors": [],
        "outer_relax_values": [],
        "pressure_residuals": [],
        "pressure_offsets": [0],
        "newton_residuals": [],
        "newton_offsets": [0],
    }

    pressure_model = model.bearing.main_model
    original_calc_error = pressure_model.calc_error

    def recorded_calc_error(*args: Any, **kwargs: Any) -> Any:
        value = original_calc_error(*args, **kwargs)
        array = np.asarray(value)
        if array.size == 1 and not isinstance(value, (bool, np.bool_)):
            trace["pressure_residuals"].append(float(array.reshape(-1)[0]))
        return value

    pressure_model.calc_error = recorded_calc_error
    original_bearing_output = model.bearing.output

    def recorded_bearing_output(*args: Any, **kwargs: Any) -> Any:
        result = original_bearing_output(*args, **kwargs)
        trace["pressure_offsets"].append(len(trace["pressure_residuals"]))
        return result

    model.bearing.output = recorded_bearing_output
    original_relaxed_update = model._relaxed_miu_update

    def recorded_relaxed_update(
        current: np.ndarray, target: np.ndarray, relax: float
    ) -> tuple[np.ndarray, float]:
        updated, relative_error = original_relaxed_update(current, target, relax)
        trace["outer_rel_errors"].append(float(relative_error))
        trace["outer_relax_values"].append(float(relax))
        return updated, relative_error

    model._relaxed_miu_update = recorded_relaxed_update

    thermal_model = model.thermal_model
    if hasattr(thermal_model, "_relative_residual_norm"):
        original_residual_norm = thermal_model._relative_residual_norm

        def recorded_residual_norm(*args: Any, **kwargs: Any) -> Any:
            value = original_residual_norm(*args, **kwargs)
            trace["newton_residuals"].append(float(value))
            return value

        thermal_model._relative_residual_norm = recorded_residual_norm
    if hasattr(thermal_model, "solve_segregated_newton"):
        original_newton = thermal_model.solve_segregated_newton

        def recorded_newton(*args: Any, **kwargs: Any) -> Any:
            result = original_newton(*args, **kwargs)
            trace["newton_offsets"].append(len(trace["newton_residuals"]))
            return result

        thermal_model.solve_segregated_newton = recorded_newton
    return trace


def _direct_case() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    hyd_config = HydConfig(
        nx=7,
        nz=5,
        e=0.2,
        angle=30.0,
        l=0.08,
        max_iter=40,
        error_set=1.0e-8,
        iter_method="newton",
    )
    thermal_config = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        k_lub=0.0,
        relax=0.6,
        max_iter=12,
        tol=0.03,
        coupling="full",
        pressure_backend="skfem",
        supg=True,
        args_nodim=False,
        delta_t_scale=30.0,
        iter_method="direct",
    )
    model = ThermalHydroBearing(HydrostaticBearing(hyd_config), thermal_config)
    trace = _instrument(model)
    model.init()
    displacement = np.array([1.6e-5, -0.8e-5], dtype=float)
    velocity = np.array([0.0, 0.0], dtype=float)
    model.input(displacement, velocity)
    output = model.output(calc=True, nodim=True)
    arrays = {
        "direct_input_displacement": displacement,
        "direct_input_velocity": velocity,
        "direct_force": np.asarray(output["force"], dtype=float),
        "direct_pressure_field": np.asarray(output["pressure_field"], dtype=float),
        "direct_temperature_field": np.asarray(
            output["temperature_field"], dtype=float
        ),
        "direct_viscosity_field": np.asarray(output["viscosity_field"], dtype=float),
        "direct_outer_rel_error_history": np.asarray(
            trace["outer_rel_errors"], dtype=float
        ),
        "direct_outer_relax_history": np.asarray(
            trace["outer_relax_values"], dtype=float
        ),
        "direct_pressure_residual_history": np.asarray(
            trace["pressure_residuals"], dtype=float
        ),
        "direct_pressure_residual_offsets": np.asarray(
            trace["pressure_offsets"], dtype=np.int64
        ),
        "direct_iterations": np.asarray(
            [output["thermal_iterations"]], dtype=np.int64
        ),
        "direct_converged": np.asarray(
            [output["thermal_converged"]], dtype=np.bool_
        ),
    }
    metadata = {
        "hyd_config": _json_value(hyd_config),
        "thermal_config": _json_value(thermal_config),
        "solver_used": str(output["thermal_solver_used"]),
        "thermal_state_keys": sorted(model.thermal_state),
        "newton_diagnostics": {"applicable": False},
    }
    return metadata, arrays


def _newton_case() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    hyd_config = HydConfig(
        nx=11,
        nz=7,
        e=0.25,
        angle=30.0,
        max_iter=120,
        error_set=1.0e-8,
        iter_method="newton",
    )
    thermal_config = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        relax=0.6,
        max_iter=6,
        tol=5.0e-2,
        coupling="full",
        pressure_backend="skfem",
        args_nodim=False,
        iter_method="newton",
        thermal_newton_max_iter=12,
        thermal_newton_tol=1.0e-5,
    )
    model = ThermalHydroBearing(HydrostaticBearing(hyd_config), thermal_config)
    trace = _instrument(model)
    model.init()
    displacement = np.array([0.25 * hyd_config.c, 0.0], dtype=float)
    velocity = np.array([0.0, 0.0], dtype=float)
    model.input(displacement, velocity)
    output = model.output(calc=True, nodim=True)
    arrays = {
        "newton_input_displacement": displacement,
        "newton_input_velocity": velocity,
        "newton_force": np.asarray(output["force"], dtype=float),
        "newton_pressure_field": np.asarray(output["pressure_field"], dtype=float),
        "newton_temperature_field": np.asarray(
            output["temperature_field"], dtype=float
        ),
        "newton_viscosity_field": np.asarray(output["viscosity_field"], dtype=float),
        "newton_outer_rel_error_history": np.asarray(
            trace["outer_rel_errors"], dtype=float
        ),
        "newton_outer_relax_history": np.asarray(
            trace["outer_relax_values"], dtype=float
        ),
        "newton_pressure_residual_history": np.asarray(
            trace["pressure_residuals"], dtype=float
        ),
        "newton_pressure_residual_offsets": np.asarray(
            trace["pressure_offsets"], dtype=np.int64
        ),
        "newton_inner_residual_history": np.asarray(
            trace["newton_residuals"], dtype=float
        ),
        "newton_inner_residual_offsets": np.asarray(
            trace["newton_offsets"], dtype=np.int64
        ),
        "newton_iterations": np.asarray(
            [output["thermal_newton_iterations"]], dtype=np.int64
        ),
        "newton_final_residual": np.asarray(
            [output["thermal_newton_residual"]], dtype=float
        ),
        "newton_line_search_steps": np.asarray(
            [output["thermal_newton_line_search_steps"]], dtype=np.int64
        ),
        "newton_converged": np.asarray(
            [output["thermal_converged"]], dtype=np.bool_
        ),
    }
    metadata = {
        "hyd_config": _json_value(hyd_config),
        "thermal_config": _json_value(thermal_config),
        "solver_used": str(output["thermal_solver_used"]),
        "thermal_state_keys": sorted(model.thermal_state),
        "newton_diagnostics": {"applicable": True},
    }
    return metadata, arrays


def _transient_case() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    hyd_config = HydConfig(
        nx=5,
        nz=3,
        e=0.15,
        angle=15.0,
        l=0.08,
        max_iter=30,
        error_set=1.0e-8,
        iter_method="newton",
        damp=0.6,
    )
    thermal_config = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        k_lub=0.0,
        relax=0.5,
        max_iter=8,
        tol=0.03,
        coupling="full",
        pressure_backend="skfem",
        args_nodim=False,
        transient_enabled=True,
        dt=0.005,
        iter_method="direct",
    )
    model = ThermalHydroBearing(HydrostaticBearing(hyd_config), thermal_config)
    trace = _instrument(model)
    model.init()
    positions = np.array(
        [[1.2e-5, 0.0], [1.0e-5, 0.4e-5], [0.6e-5, 0.8e-5]], dtype=float
    )
    velocities = np.array(
        [[0.0, 0.0], [-4.0e-4, 8.0e-4], [-8.0e-4, 8.0e-4]], dtype=float
    )
    candidates: list[np.ndarray] = []
    committed: list[np.ndarray] = []
    before_states: list[np.ndarray] = []
    before_indices: list[int] = []
    commit_flags: list[bool] = []
    forces: list[np.ndarray] = []
    for index, (position, velocity) in enumerate(zip(positions, velocities)):
        if model._temperature_prev is not None:
            before_states.append(model._temperature_prev.copy())
            before_indices.append(index)
        model.input(position, velocity, t=index * thermal_config.dt, nodim=False)
        output = model.output(calc=True, nodim=False)
        candidate = np.asarray(output["temperature"], dtype=float).copy()
        state = np.asarray(model._temperature_prev, dtype=float).copy()
        candidates.append(candidate)
        committed.append(state)
        commit_flags.append(bool(np.array_equal(candidate, state)))
        forces.append(np.asarray(output["force"], dtype=float))
    arrays = {
        "transient_positions": positions,
        "transient_velocities": velocities,
        "transient_candidate_temperature": np.stack(candidates),
        "transient_committed_temperature": np.stack(committed),
        "transient_before_temperature": np.stack(before_states),
        "transient_before_step_indices": np.asarray(before_indices, dtype=np.int64),
        "transient_commit_flags": np.asarray(commit_flags, dtype=np.bool_),
        "transient_force": np.vstack(forces),
        "transient_outer_rel_error_history": np.asarray(
            trace["outer_rel_errors"], dtype=float
        ),
        "transient_outer_relax_history": np.asarray(
            trace["outer_relax_values"], dtype=float
        ),
        "transient_pressure_residual_history": np.asarray(
            trace["pressure_residuals"], dtype=float
        ),
        "transient_pressure_residual_offsets": np.asarray(
            trace["pressure_offsets"], dtype=np.int64
        ),
    }
    metadata = {
        "hyd_config": _json_value(hyd_config),
        "thermal_config": _json_value(thermal_config),
        "step_count": len(positions),
        "first_before_state": None,
        "newton_diagnostics": {"applicable": False},
    }
    return metadata, arrays


def build_payload() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    random.seed(SEED)
    np.random.seed(SEED)
    imported_root = Path(ALB.__file__).resolve().parent.parent
    if imported_root != SOURCE_ROOT:
        raise RuntimeError(
            f"Imported ALB from {imported_root}, expected explicit source {SOURCE_ROOT}"
        )
    direct_metadata, direct_arrays = _direct_case()
    newton_metadata, newton_arrays = _newton_case()
    transient_metadata, transient_arrays = _transient_case()
    arrays = {**direct_arrays, **newton_arrays, **transient_arrays}
    if any(np.issubdtype(value.dtype, np.floating) and not np.all(np.isfinite(value)) for value in arrays.values()):
        raise ValueError("Addendum arrays must not contain NaN or infinity")
    required_histories = (
        "direct_outer_rel_error_history",
        "direct_pressure_residual_history",
        "newton_outer_rel_error_history",
        "newton_inner_residual_history",
        "newton_pressure_residual_history",
    )
    if any(arrays[name].size == 0 for name in required_histories):
        raise ValueError("Required convergence histories must be nonempty")
    script_path = Path(__file__).resolve()
    payload = {
        "schema": SCHEMA,
        "seed": SEED,
        "source": {
            "tag": SOURCE_TAG,
            "commit": SOURCE_COMMIT,
            "alb_file": Path(ALB.__file__).resolve().relative_to(SOURCE_ROOT).as_posix(),
            "generator": script_path.name,
            "generator_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": _distribution_version("scipy"),
            "scikit-fem": _distribution_version("scikit-fem"),
        },
        "cases": {
            "direct": direct_metadata,
            "newton": newton_metadata,
            "transient": transient_metadata,
        },
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _array_digest(value),
            }
            for name, value in arrays.items()
        },
    }
    return payload, arrays


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    json_path = output_dir / "thermal_convergence.json"
    npz_path = output_dir / "thermal_convergence.npz"
    if json_path.exists() or npz_path.exists():
        raise FileExistsError(f"Refusing to overwrite addendum under {output_dir}")
    payload, arrays = build_payload()
    output_dir.mkdir(parents=True, exist_ok=False)
    np.savez(npz_path, **arrays)
    json_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
