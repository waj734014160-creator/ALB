"""Run and summarize the full pressure/thermal ALB mesh-independence matrix."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from types import SimpleNamespace
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.api import BearingConfig, build_bearing, load_bearing_config
from ALB.api.building import _active_config
from ALB.api.results import BearingResult
from ALB.contracts import BearingInput, DirectSpoolBearingInput, UnitSystem, ValveOutput
from ALB.systems.alb.assembly_runtime import assemble_active_runtime


DEFAULT_CONFIG = Path(
    r"F:\BaiduSyncdisk\博士论文\PAPER_WORK\task\PAPER\config\alb12.json5"
)
DEFAULT_OUTPUT = Path(
    r"F:\BaiduSyncdisk\博士论文\PAPER_WORK\figure\PAPER\data"
) / "alb_mesh_independence"
GRID_LEVELS = (
    (10, 5),
    (20, 10),
    (30, 15),
    (40, 20),
    (50, 25),
    (60, 30),
    (80, 40),
    (100, 50),
    (150, 75),
    (200, 100),
)
METHODS = {
    "tri_p1": ("triangular", 1),
    "tri_p2": ("triangular", 2),
    "quad_q1": ("quadrilateral", 1),
    "quad_q2": ("quadrilateral", 2),
}
SUPPLY_STATES = {"supply_off": (0.0, 0.0), "supply_on": (0.2, 0.2)}
DISPLACEMENT = (-24.0e-6, -36.0e-6)
VELOCITY = (0.0, 0.0)
INTEGRATION_ORDER = 8
FILM_MAX_ITERATIONS = 240


@dataclass(frozen=True)
class CaseDefinition:
    """One cold-start case in the reproducible calculation matrix."""

    supply_state: str
    method: str
    nx: int
    nz: int

    @property
    def case_id(self) -> str:
        return f"{self.supply_state}__{self.method}__{self.nx}x{self.nz}"


class MemorySampler:
    """Sample process RSS without making psutil a hard runtime dependency."""

    def __init__(self, interval: float = 0.05):
        self.interval = float(interval)
        self.peak_bytes: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        try:
            import psutil

            self._process = psutil.Process()
        except ImportError:
            self._process = None

    def __enter__(self):
        if self._process is None:
            return self
        self.peak_bytes = int(self._process.memory_info().rss)

        def sample() -> None:
            while not self._stop.wait(self.interval):
                value = int(self._process.memory_info().rss)
                self.peak_bytes = max(int(self.peak_bytes or 0), value)

        self._thread = threading.Thread(target=sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._process is not None:
            self.peak_bytes = max(
                int(self.peak_bytes or 0), int(self._process.memory_info().rss)
            )
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    """Write one UTF-8 JSON object atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of one source file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _derived_config(base: BearingConfig, case: CaseDefinition) -> BearingConfig:
    """Create one validated immutable case without editing the source document."""

    mesh_type, element_order = METHODS[case.method]
    return base.with_overrides(
        {
            "film.circumferential_elements": case.nx,
            "film.axial_elements": case.nz,
            "film.mesh_type": mesh_type,
            "film.element_order": element_order,
            "restrictors.flow_projection": "element_shape",
            "film.max_iterations": FILM_MAX_ITERATIONS,
            "film.save_pressure": False,
            "film.save_thickness": False,
            "control.mode": "external_spool",
            "control.gains": None,
        }
    )


def _case_definitions(
    grids: Iterable[tuple[int, int]],
    methods: Iterable[str],
    supply_states: Iterable[str],
) -> list[CaseDefinition]:
    """Return the serial small-to-large case order."""

    return [
        CaseDefinition(supply, method, nx, nz)
        for supply in supply_states
        for method in methods
        for nx, nz in grids
    ]


def _point_flow_fields(runtime) -> tuple[np.ndarray, np.ndarray]:
    """Collect pad-ordered dimensional hole flow and pressure arrays."""

    flows = []
    pressures = []
    for pad in runtime._pads:
        model = pad.bearing.main_model
        orifice = pad.bearing.simple_models[0]
        qw = float(orifice.qw)
        flows.append(np.asarray(orifice.qn, dtype=float).reshape(-1) * qw)
        pressures.append(
            np.asarray([point.p for point in orifice.node], dtype=float)
            * float(model.args["ps"])
        )
    return np.vstack(flows), np.vstack(pressures)


def _integration_force(model, intorder: int) -> np.ndarray:
    """Reintegrate one pressure solution at a requested quadrature order."""

    from skfem import Basis, ElementQuad1, ElementQuad2, ElementTriP1, ElementTriP2

    mesh_type = str(model.args["mesh_type"])
    order = int(model.args["element_order"])
    if mesh_type == "triangular":
        element = ElementTriP1() if order == 1 else ElementTriP2()
    else:
        element = ElementQuad1() if order == 1 else ElementQuad2()
    basis = Basis(model.mesh_skfem, element, intorder=intorder)
    pressure = basis.interpolate(np.asarray(model.latest_result, dtype=float))
    coords = basis.mapping.F(basis.X)
    force_nd = np.array(
        [
            np.sum(pressure * np.sin(coords[0]) * basis.dx),
            -np.sum(pressure * np.cos(coords[0]) * basis.dx),
        ],
        dtype=float,
    )
    return force_nd * float(model.args["ps"] * model.args["l"] / 2 * model.args["r"])


def _collect_case_arrays(bearing, result) -> tuple[dict[str, np.ndarray], dict]:
    """Collect fields and scalar diagnostics from one completed ALB calculation."""

    runtime = bearing._runtime
    pad_snapshots = [pad.result_snapshot() for pad in runtime._pads]
    models = [pad.bearing.main_model for pad in runtime._pads]
    pressure_nd = np.vstack(
        [np.asarray(snapshot.values["pressure"], dtype=float) for snapshot in pad_snapshots]
    )
    pressure_pa = np.vstack(
        [pressure_nd[index] * float(model.args["ps"]) for index, model in enumerate(models)]
    )
    temperature = np.vstack(
        [
            np.asarray(snapshot.values["temperature"], dtype=float)
            for snapshot in pad_snapshots
        ]
    )
    viscosity = np.vstack(
        [
            np.asarray(snapshot.values["viscosity_field"], dtype=float)
            for snapshot in pad_snapshots
        ]
    )
    thickness = np.vstack(
        [
            np.asarray(snapshot.values["film_thickness"], dtype=float)
            * float(model.args["c"])
            for snapshot, model in zip(pad_snapshots, models)
        ]
    )
    hole_flow, hole_pressure = _point_flow_fields(runtime)
    force = np.asarray(result.force, dtype=float)
    pad_force = np.asarray(result.details.values["pad_force"], dtype=float)
    force_int10 = np.sum(
        np.vstack([_integration_force(model, 10) for model in models]), axis=0
    )
    arrays = {
        "force": force,
        "pad_force": pad_force,
        "pressure_nondim": pressure_nd,
        "pressure_pa": pressure_pa,
        "temperature_c": temperature,
        "viscosity_pa_s": viscosity,
        "film_thickness_m": thickness,
        "hole_flow_m3_s": hole_flow,
        "hole_pressure_pa": hole_pressure,
        "force_int10": force_int10,
    }
    pad_iterations = [int(snapshot.metadata["iterations"]) for snapshot in pad_snapshots]
    converged_by_pad = [bool(snapshot.metadata["converged"]) for snapshot in pad_snapshots]
    denominator = max(float(np.linalg.norm(force)), np.finfo(float).tiny)
    summary = {
        "fx": float(force[0]),
        "fy": float(force[1]),
        "force_magnitude": float(np.linalg.norm(force)),
        "pad_force": pad_force.tolist(),
        "friction": float(result.friction or 0.0),
        "max_pressure_pa": float(np.max(pressure_pa)),
        "max_temperature_c": float(np.max(temperature)),
        "mean_temperature_c": float(np.mean(temperature)),
        "min_viscosity_pa_s": float(np.min(viscosity)),
        "max_viscosity_pa_s": float(np.max(viscosity)),
        "total_hole_flow_m3_s": float(np.sum(hole_flow)),
        "absolute_hole_flow_m3_s": float(np.sum(np.abs(hole_flow))),
        "converged": bool(result.convergence.converged and all(converged_by_pad)),
        "converged_by_pad": converged_by_pad,
        "iterations": int(max(pad_iterations, default=0)),
        "iterations_by_pad": pad_iterations,
        "integration_8_to_10_relative_force": float(
            np.linalg.norm(force_int10 - force) / denominator
        ),
    }
    return arrays, summary


def _run_case(
    base: BearingConfig,
    case: CaseDefinition,
    output_dir: Path,
    *,
    force: bool,
) -> dict[str, Any]:
    """Run or resume one cold-start case and seal its artifacts."""

    case_dir = output_dir / "cases" / case.case_id
    result_json = case_dir / "case.json"
    field_npz = case_dir / "fields.npz"
    if not force and result_json.is_file() and field_npz.is_file():
        previous = json.loads(result_json.read_text(encoding="utf-8"))
        expected_mesh, expected_order = METHODS[case.method]
        compatible = (
            previous.get("status") == "completed"
            and previous.get("case_id") == case.case_id
            and previous.get("supply_state") == case.supply_state
            and previous.get("method") == case.method
            and previous.get("mesh_type") == expected_mesh
            and previous.get("element_order") == expected_order
            and previous.get("integration_order") == INTEGRATION_ORDER
            and previous.get("film_max_iterations") == FILM_MAX_ITERATIONS
            and previous.get("nx") == case.nx
            and previous.get("nz") == case.nz
        )
        if compatible:
            print(f"RESUME {case.case_id}", flush=True)
            return previous
        print(f"RERUN  {case.case_id}: cached settings are stale", flush=True)

    case_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    print(f"START  {case.case_id}", flush=True)
    try:
        config = _derived_config(base, case)
        with MemorySampler() as memory:
            bearing = build_bearing(config)
            result = bearing.calculate(
                displacement=DISPLACEMENT,
                velocity=VELOCITY,
                time=0.0,
                spool=SUPPLY_STATES[case.supply_state],
            )
            arrays, summary = _collect_case_arrays(bearing, result)
        np.savez_compressed(field_npz, **arrays)
        elapsed = time.perf_counter() - started
        metadata = dict(result.details.metadata)
        payload = {
            "schema": "alb.mesh-independence-case.v1",
            "status": "completed",
            "case_id": case.case_id,
            "supply_state": case.supply_state,
            "spool": list(SUPPLY_STATES[case.supply_state]),
            "method": case.method,
            "mesh_type": metadata["mesh_type"],
            "element_order": int(metadata["element_order"]),
            "integration_order": int(metadata["integration_order"]),
            "film_max_iterations": FILM_MAX_ITERATIONS,
            "nx": case.nx,
            "nz": case.nz,
            "actual_elements_per_pad": int(metadata["actual_element_count"]),
            "pressure_dofs_per_pad": int(metadata["pressure_dofs"]),
            "temperature_dofs_per_pad": int(metadata["temperature_dofs"]),
            "elapsed_seconds": float(elapsed),
            "peak_rss_bytes": memory.peak_bytes,
            "fields": str(field_npz.relative_to(output_dir)),
            **summary,
        }
        _atomic_json(result_json, payload)
        print(
            f"DONE   {case.case_id} {elapsed:.2f}s "
            f"F=({payload['fx']:.6g},{payload['fy']:.6g})",
            flush=True,
        )
        return payload
    except Exception as exc:
        elapsed = time.perf_counter() - started
        payload = {
            "schema": "alb.mesh-independence-case.v1",
            "status": "failed",
            "case_id": case.case_id,
            "supply_state": case.supply_state,
            "method": case.method,
            "nx": case.nx,
            "nz": case.nz,
            "elapsed_seconds": float(elapsed),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        _atomic_json(result_json, payload)
        print(f"FAILED {case.case_id}: {type(exc).__name__}: {exc}", flush=True)
        return payload


def _run_case_worker(
    config_path: str,
    case: CaseDefinition,
    output_dir: str,
    force: bool,
) -> dict[str, Any]:
    """Load isolated state and run one case in a spawned worker process."""

    base = load_bearing_config(Path(config_path))
    return _run_case(base, case, Path(output_dir), force=force)


def _run_triangle_mirror_validation(
    base: BearingConfig,
    output_dir: Path,
    nx: int,
    nz: int,
) -> list[dict[str, Any]]:
    """Compare the fixed and mirrored triangle diagonals outside the 80 cases."""

    validation_dir = output_dir / "validation" / f"triangle_diagonal_{nx}x{nz}"
    validation_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for supply_state, spool in SUPPLY_STATES.items():
        for method in ("tri_p1", "tri_p2"):
            case = CaseDefinition(supply_state, method, nx, nz)
            standard = _run_case(base, case, output_dir, force=False)
            if standard.get("status") != "completed":
                rows.append(
                    {
                        "supply_state": supply_state,
                        "method": method,
                        "nx": nx,
                        "nz": nz,
                        "status": "skipped",
                        "reason": "default diagonal case failed",
                    }
                )
                continue
            config = _derived_config(base, case)
            native_config = _active_config(config)
            native_config.pad_config.triangle_diagonal = "mirrored"
            started = time.perf_counter()
            try:
                runtime = assemble_active_runtime(native_config)
                dto = DirectSpoolBearingInput(
                    BearingInput(
                        DISPLACEMENT,
                        VELOCITY,
                        0.0,
                        UnitSystem.DIMENSIONAL,
                    ),
                    ValveOutput(spool, 0.0, UnitSystem.NONDIMENSIONAL),
                )
                output = runtime.step(dto)
                details = runtime.result_snapshot()
                result = BearingResult(
                    force=output.force,
                    time=output.time,
                    unit_system=output.unit_system,
                    convergence=runtime.convergence_status,
                    details=details,
                )
                arrays, summary = _collect_case_arrays(
                    SimpleNamespace(_runtime=runtime), result
                )
                mirror_npz = validation_dir / f"{supply_state}__{method}.npz"
                np.savez_compressed(mirror_npz, **arrays)
                default_force = np.array([standard["fx"], standard["fy"]])
                mirror_force = np.array([summary["fx"], summary["fy"]])
                relative = float(
                    np.linalg.norm(mirror_force - default_force)
                    / max(np.linalg.norm(default_force), np.finfo(float).tiny)
                )
                rows.append(
                    {
                        "supply_state": supply_state,
                        "method": method,
                        "nx": nx,
                        "nz": nz,
                        "status": "completed",
                        "default_fx": float(default_force[0]),
                        "default_fy": float(default_force[1]),
                        "mirrored_fx": float(mirror_force[0]),
                        "mirrored_fy": float(mirror_force[1]),
                        "relative_force_difference": relative,
                        "pass": bool(relative < 0.01),
                        "elapsed_seconds": float(time.perf_counter() - started),
                        "fields": str(mirror_npz.relative_to(output_dir)),
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "supply_state": supply_state,
                        "method": method,
                        "nx": nx,
                        "nz": nz,
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
    payload = {
        "schema": "alb.triangle-diagonal-sensitivity.v1",
        "criterion": 0.01,
        "rows": rows,
    }
    _atomic_json(validation_dir / "triangle_diagonal_sensitivity.json", payload)
    _write_csv(validation_dir / "triangle_diagonal_sensitivity.csv", rows)
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write heterogeneous scalar rows with deterministic columns."""

    path.parent.mkdir(parents=True, exist_ok=True)
    scalar_rows = []
    for row in rows:
        scalar_rows.append(
            {
                key: value
                for key, value in row.items()
                if value is None or isinstance(value, (str, int, float, bool))
            }
        )
    fields = sorted({key for row in scalar_rows for key in row})
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(scalar_rows)
    temporary.replace(path)


def _completed_rows(
    output_dir: Path,
    expected_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Read all sealed cases without trusting an in-memory run state."""

    rows = []
    for path in sorted((output_dir / "cases").glob("*/case.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if expected_case_ids is None or row.get("case_id") in expected_case_ids:
            rows.append(row)
    return rows


def _sequence_value(row: dict[str, Any], field: str) -> float:
    if field == "fx":
        return float(row["fx"])
    if field == "fy":
        return float(row["fy"])
    return float(row["force_magnitude"])


def _gci_component(
    coarse: float,
    medium: float,
    fine: float,
    *,
    refinement_ratio: float = 2.0,
    safety_factor: float = 1.25,
) -> dict[str, Any]:
    """Return apparent order and fine-grid GCI for one scalar sequence."""

    delta_coarse = coarse - medium
    delta_fine = medium - fine
    monotonic = bool(delta_coarse * delta_fine > 0.0)
    result = {
        "monotonic": monotonic,
        "apparent_order": None,
        "fine_gci": None,
        "valid": False,
    }
    if not monotonic or delta_fine == 0.0 or fine == 0.0:
        return result
    ratio = abs(delta_coarse / delta_fine)
    if not np.isfinite(ratio) or ratio <= 0.0:
        return result
    order = math.log(ratio) / math.log(refinement_ratio)
    denominator = refinement_ratio**order - 1.0
    if not np.isfinite(order) or order <= 0.0 or denominator <= 0.0:
        return result
    gci = safety_factor * abs((fine - medium) / fine) / denominator
    result.update(
        {
            "apparent_order": float(order),
            "fine_gci": float(gci),
            "valid": bool(np.isfinite(gci)),
        }
    )
    return result


def build_convergence_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute force criteria, GCI, thermal changes, and fine-grid agreement."""

    valid = [
        row
        for row in rows
        if row.get("status") == "completed" and row.get("converged") is True
    ]
    sequences = []
    lookup = {
        (row["supply_state"], row["method"], int(row["nx"])): row for row in valid
    }
    for supply in SUPPLY_STATES:
        for method in METHODS:
            fine = lookup.get((supply, method, 200))
            penultimate = lookup.get((supply, method, 150))
            row = {
                "supply_state": supply,
                "method": method,
                "last_force_relative_change": None,
                "last_force_pass": False,
                "temperature_last_relative_change": None,
                "viscosity_last_relative_change": None,
                "mean_temperature_last_relative_change": None,
                "max_temperature_last_relative_change": None,
                "min_viscosity_last_relative_change": None,
                "max_viscosity_last_relative_change": None,
            }
            if fine is not None and penultimate is not None:
                fine_force = np.array([fine["fx"], fine["fy"]], dtype=float)
                previous_force = np.array(
                    [penultimate["fx"], penultimate["fy"]], dtype=float
                )
                relative = float(
                    np.linalg.norm(fine_force - previous_force)
                    / max(np.linalg.norm(fine_force), np.finfo(float).tiny)
                )
                row["last_force_relative_change"] = relative
                row["last_force_pass"] = relative < 0.01
                mean_temperature_change = abs(
                    float(fine["mean_temperature_c"])
                    - float(penultimate["mean_temperature_c"])
                ) / max(abs(float(fine["mean_temperature_c"])), np.finfo(float).tiny)
                max_temperature_change = abs(
                    float(fine["max_temperature_c"])
                    - float(penultimate["max_temperature_c"])
                ) / max(abs(float(fine["max_temperature_c"])), np.finfo(float).tiny)
                min_viscosity_change = abs(
                    float(fine["min_viscosity_pa_s"])
                    - float(penultimate["min_viscosity_pa_s"])
                ) / max(abs(float(fine["min_viscosity_pa_s"])), np.finfo(float).tiny)
                max_viscosity_change = abs(
                    float(fine["max_viscosity_pa_s"])
                    - float(penultimate["max_viscosity_pa_s"])
                ) / max(abs(float(fine["max_viscosity_pa_s"])), np.finfo(float).tiny)
                row["temperature_last_relative_change"] = mean_temperature_change
                row["viscosity_last_relative_change"] = min_viscosity_change
                row["mean_temperature_last_relative_change"] = mean_temperature_change
                row["max_temperature_last_relative_change"] = max_temperature_change
                row["min_viscosity_last_relative_change"] = min_viscosity_change
                row["max_viscosity_last_relative_change"] = max_viscosity_change
            for field in ("fx", "fy", "force_magnitude"):
                selected = [lookup.get((supply, method, nx)) for nx in (50, 100, 200)]
                if all(item is not None for item in selected):
                    gci = _gci_component(
                        *[_sequence_value(item, field) for item in selected]
                    )
                else:
                    gci = {
                        "monotonic": False,
                        "apparent_order": None,
                        "fine_gci": None,
                        "valid": False,
                    }
                row[f"{field}_monotonic"] = gci["monotonic"]
                row[f"{field}_apparent_order"] = gci["apparent_order"]
                row[f"{field}_fine_gci"] = gci["fine_gci"]
                row[f"{field}_gci_valid"] = gci["valid"]
            magnitude_gci = row["force_magnitude_fine_gci"]
            row["force_magnitude_gci_pass"] = bool(
                row["force_magnitude_gci_valid"]
                and magnitude_gci is not None
                and magnitude_gci < 0.01
            )
            row["force_grid_independent"] = bool(
                row["last_force_pass"] and row["force_magnitude_gci_pass"]
            )
            sequences.append(row)

    pairwise = []
    for supply in SUPPLY_STATES:
        available = {
            method: lookup.get((supply, method, 200)) for method in METHODS
        }
        for left_index, left in enumerate(METHODS):
            for right in list(METHODS)[left_index + 1 :]:
                left_row = available[left]
                right_row = available[right]
                if left_row is None or right_row is None:
                    difference = None
                    passed = False
                else:
                    left_force = np.array([left_row["fx"], left_row["fy"]])
                    right_force = np.array([right_row["fx"], right_row["fy"]])
                    denominator = max(
                        np.linalg.norm(left_force),
                        np.linalg.norm(right_force),
                        np.finfo(float).tiny,
                    )
                    difference = float(
                        np.linalg.norm(left_force - right_force) / denominator
                    )
                    passed = difference < 0.01
                pairwise.append(
                    {
                        "supply_state": supply,
                        "left_method": left,
                        "right_method": right,
                        "relative_force_difference": difference,
                        "pass": passed,
                    }
                )
    return {
        "schema": "alb.mesh-independence-convergence.v1",
        "criteria": {
            "last_grid_force_relative": 0.01,
            "fine_grid_gci_magnitude": 0.01,
            "fine_grid_method_pairwise": 0.01,
            "gci_grids": ["50x25", "100x50", "200x100"],
            "gci_safety_factor": 1.25,
        },
        "sequences": sequences,
        "fine_grid_pairwise": pairwise,
    }


def _plot_diagnostics(rows: list[dict[str, Any]], output_dir: Path) -> None:
    """Create Python-only diagnostic plots from completed converged cases."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    valid = [
        row
        for row in rows
        if row.get("status") == "completed" and row.get("converged") is True
    ]
    if not valid:
        return
    figure_dir = output_dir / "diagnostics"
    figure_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.linewidth": 0.8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    colors = {
        "tri_p1": "#0072B2",
        "tri_p2": "#56B4E9",
        "quad_q1": "#D55E00",
        "quad_q2": "#009E73",
    }
    markers = {"tri_p1": "o", "tri_p2": "s", "quad_q1": "^", "quad_q2": "D"}

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2))
    for column, supply in enumerate(SUPPLY_STATES):
        supply_rows = [row for row in valid if row["supply_state"] == supply]
        for method in METHODS:
            sequence = sorted(
                [row for row in supply_rows if row["method"] == method],
                key=lambda item: item["nx"],
            )
            if not sequence:
                continue
            nx = np.asarray([row["nx"] for row in sequence], dtype=float)
            force = np.asarray(
                [[row["fx"], row["fy"]] for row in sequence], dtype=float
            )
            fine = force[-1]
            relative = np.linalg.norm(force - fine, axis=1) / max(
                np.linalg.norm(fine), np.finfo(float).tiny
            )
            axes[0, column].plot(
                nx,
                relative * 100.0,
                color=colors[method],
                marker=markers[method],
                markersize=3.5,
                linewidth=1.1,
                label=method,
            )
            axes[1, column].plot(
                nx,
                [row["elapsed_seconds"] for row in sequence],
                color=colors[method],
                marker=markers[method],
                markersize=3.5,
                linewidth=1.1,
                label=method,
            )
        axes[0, column].axhline(1.0, color="0.35", linestyle="--", linewidth=0.8)
        axes[0, column].set_yscale("log")
        axes[0, column].set_ylabel("Force difference from finest (%)")
        axes[0, column].set_title(supply.replace("_", " "))
        axes[1, column].set_yscale("log")
        axes[1, column].set_xlabel("Circumferential macro elements")
        axes[1, column].set_ylabel("Elapsed time (s)")
        axes[0, column].grid(True, which="both", color="0.9", linewidth=0.5)
        axes[1, column].grid(True, which="both", color="0.9", linewidth=0.5)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles,
            labels,
            ncol=4,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.985),
            frameon=False,
        )
    fig.subplots_adjust(top=0.90, bottom=0.10, left=0.10, right=0.98, hspace=0.30, wspace=0.25)
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(
            figure_dir / f"force_convergence_and_cost.{suffix}",
            dpi=300,
            bbox_inches="tight",
        )
    plt.close(fig)


def _refresh_outputs(
    output_dir: Path,
    expected: list[CaseDefinition],
    config_path: Path,
    *,
    plots: bool,
) -> dict[str, Any]:
    """Refresh resumable summary, manifest, GCI tables, and plots."""

    expected_case_ids = {case.case_id for case in expected}
    rows = _completed_rows(output_dir, expected_case_ids)
    _write_csv(output_dir / "summary.csv", rows)
    convergence = build_convergence_report(rows)
    _atomic_json(output_dir / "convergence.json", convergence)
    _write_csv(output_dir / "gci.csv", convergence["sequences"])
    _write_csv(output_dir / "fine_grid_pairwise.csv", convergence["fine_grid_pairwise"])
    complete = sum(row.get("status") == "completed" for row in rows)
    failed = sum(row.get("status") == "failed" for row in rows)
    converged = sum(
        row.get("status") == "completed" and row.get("converged") is True
        for row in rows
    )
    nonconverged = sum(
        row.get("status") == "completed" and row.get("converged") is not True
        for row in rows
    )
    reused = sum("reused_from_converged_cold_start" in row for row in rows)
    integration_sensitivities = [
        float(row["integration_8_to_10_relative_force"])
        for row in rows
        if row.get("status") == "completed"
        and row.get("integration_8_to_10_relative_force") is not None
    ]
    triangle_validation = sorted(
        str(path.relative_to(output_dir))
        for path in (output_dir / "validation").glob(
            "triangle_diagonal_*/triangle_diagonal_sensitivity.json"
        )
    )
    manifest = {
        "schema": "alb.mesh-independence-manifest.v1",
        "source_config": str(config_path.resolve()),
        "source_config_sha256": _sha256(config_path),
        "displacement_m": list(DISPLACEMENT),
        "eccentricity_ratio": [-0.2, -0.3],
        "velocity_m_s": list(VELOCITY),
        "supply_states": {key: list(value) for key, value in SUPPLY_STATES.items()},
        "methods": {
            key: {"mesh_type": value[0], "element_order": value[1]}
            for key, value in METHODS.items()
        },
        "integration_order": INTEGRATION_ORDER,
        "film_max_iterations": FILM_MAX_ITERATIONS,
        "expected_case_count": len(expected),
        "completed_case_count": complete,
        "converged_case_count": converged,
        "nonconverged_case_count": nonconverged,
        "failed_case_count": failed,
        "reused_converged_cold_start_case_count": reused,
        "pending_case_count": len(expected) - complete - failed,
        "nonconverged_cases": [
            row["case_id"]
            for row in rows
            if row.get("status") == "completed" and row.get("converged") is not True
        ],
        "maximum_integration_8_to_10_relative_force": (
            max(integration_sensitivities) if integration_sensitivities else None
        ),
        "expected_cases": [case.case_id for case in expected],
        "artifacts": {
            "summary_csv": "summary.csv",
            "convergence_json": "convergence.json",
            "gci_csv": "gci.csv",
            "fine_grid_pairwise_csv": "fine_grid_pairwise.csv",
            "case_root": "cases",
            "diagnostic_root": "diagnostics",
            "triangle_diagonal_sensitivity_json": triangle_validation,
        },
    }
    _atomic_json(output_dir / "manifest.json", manifest)
    if plots:
        _plot_diagnostics(rows, output_dir)
    return manifest


def _parse_grids(value: str) -> tuple[tuple[int, int], ...]:
    """Parse comma-separated ``NXxNZ`` grid identifiers."""

    result = []
    for item in value.split(","):
        nx_text, separator, nz_text = item.lower().partition("x")
        if not separator:
            raise argparse.ArgumentTypeError(f"invalid grid: {item!r}")
        nx, nz = int(nx_text), int(nz_text)
        if nx < 2 or nz < 2:
            raise argparse.ArgumentTypeError("grid counts must be >= 2")
        result.append((nx, nz))
    return tuple(result)


def _parse_names(value: str, allowed: dict[str, Any], label: str) -> tuple[str, ...]:
    """Parse and validate one comma-separated name selection."""

    values = tuple(item.strip() for item in value.split(",") if item.strip())
    invalid = sorted(set(values) - set(allowed))
    if invalid:
        raise argparse.ArgumentTypeError(f"invalid {label}: {invalid}")
    return values


def main() -> None:
    """Run the selected matrix and refresh all durable outputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--grids",
        type=_parse_grids,
        default=GRID_LEVELS,
        help="Comma-separated NXxNZ levels.",
    )
    parser.add_argument(
        "--methods",
        type=lambda value: _parse_names(value, METHODS, "method"),
        default=tuple(METHODS),
    )
    parser.add_argument(
        "--supply-states",
        type=lambda value: _parse_names(value, SUPPLY_STATES, "supply state"),
        default=tuple(SUPPLY_STATES),
    )
    parser.add_argument("--force", action="store_true", help="Recompute completed cases.")
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        choices=range(1, 5),
        default=1,
        help="Independent single-thread worker processes (1-4).",
    )
    parser.add_argument(
        "--triangle-mirror-check",
        type=_parse_grids,
        help="Run one separate triangle-diagonal check, for example 40x20.",
    )
    args = parser.parse_args()

    config_path = args.config.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    base = load_bearing_config(config_path)
    expected = _case_definitions(args.grids, args.methods, args.supply_states)
    if args.workers == 1:
        for case in expected:
            _run_case(base, case, output_dir, force=args.force)
            _refresh_outputs(
                output_dir,
                expected,
                config_path,
                plots=False,
            )
    else:
        # Spawned numerical workers inherit these limits before importing NumPy.
        for variable in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            os.environ[variable] = "1"
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    _run_case_worker,
                    str(config_path),
                    case,
                    str(output_dir),
                    args.force,
                ): case
                for case in expected
            }
            for future in as_completed(futures):
                case = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    print(
                        f"WORKER FAILED {case.case_id}: "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )
                _refresh_outputs(
                    output_dir,
                    expected,
                    config_path,
                    plots=False,
                )
    if args.triangle_mirror_check is not None:
        if len(args.triangle_mirror_check) != 1:
            parser.error("--triangle-mirror-check accepts exactly one grid")
        mirror_nx, mirror_nz = args.triangle_mirror_check[0]
        _run_triangle_mirror_validation(base, output_dir, mirror_nx, mirror_nz)
    manifest = _refresh_outputs(
        output_dir,
        expected,
        config_path,
        plots=not args.no_plots,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
