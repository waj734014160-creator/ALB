"""Diagnose pressure-iteration limits in the ALB mesh-independence matrix."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
from pathlib import Path
import sys
from types import MethodType
from typing import Any

import numpy as np
from scipy.interpolate import RegularGridInterpolator


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.api import build_bearing, load_bearing_config


DEFAULT_CONFIG = Path(
    r"F:\BaiduSyncdisk\博士论文\PAPER_WORK\task\PAPER\config\alb12.json5"
)
DEFAULT_MATRIX = Path(
    r"F:\BaiduSyncdisk\博士论文\PAPER_WORK\figure\PAPER\data"
) / "alb_mesh_independence"
METHODS = {
    "tri_p1": ("triangular", 1),
    "tri_p2": ("triangular", 2),
    "quad_q1": ("quadrilateral", 1),
    "quad_q2": ("quadrilateral", 2),
}


def _atomic_json(path: Path, payload: Any) -> None:
    """Write one UTF-8 JSON artifact atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _case_config(base, method: str, nx: int, nz: int, overrides=None):
    """Return an immutable explicit-mesh diagnostic configuration."""

    mesh_type, order = METHODS[method]
    values = {
        "film.circumferential_elements": int(nx),
        "film.axial_elements": int(nz),
        "film.mesh_type": mesh_type,
        "film.element_order": order,
        "restrictors.flow_projection": "element_shape",
        "film.save_pressure": False,
        "film.save_thickness": False,
        "control.mode": "external_spool",
        "control.gains": None,
    }
    values.update(overrides or {})
    return base.with_overrides(values)


def _install_trace(system, pad_index: int, trace: list[dict[str, Any]]) -> None:
    """Instrument one film system without changing its numerical operations."""

    original_solve = system.solve
    original_evaluate = system._evaluate_convergence
    state = {"hydro_solve": -1, "iteration": 0}

    def traced_solve(self, *args, **kwargs):
        state["hydro_solve"] += 1
        state["iteration"] = 0
        return original_solve(*args, **kwargs)

    def traced_evaluate(self, *, update_adaptive_damp: bool):
        converged = original_evaluate(
            update_adaptive_damp=update_adaptive_damp
        )
        model = self.main_model
        orifice = self.simple_models[0] if self.simple_models else None
        correction = np.asarray(getattr(model, "_dp", []), dtype=float).reshape(-1)
        pressure = np.asarray(model.latest_result, dtype=float).reshape(-1)
        trace.append(
            {
                "pad": int(pad_index),
                "hydro_solve": int(state["hydro_solve"]),
                "iteration": int(state["iteration"]),
                "converged": bool(converged),
                "main_error": float(getattr(model, "errors", np.nan)),
                "main_tolerance": float(model._error_set),
                "orifice_error": (
                    None if orifice is None else float(getattr(orifice, "err", np.nan))
                ),
                "orifice_tolerance": (
                    None
                    if orifice is None
                    else float(getattr(orifice, "tol_err", np.nan))
                ),
                "damping": float(model.current_damp),
                "correction_rms": (
                    0.0
                    if correction.size == 0
                    else float(np.sqrt(np.mean(correction**2)))
                ),
                "correction_max_abs": (
                    0.0
                    if correction.size == 0
                    else float(np.max(np.abs(correction)))
                ),
                "pressure_min": float(np.min(pressure)),
                "pressure_max": float(np.max(pressure)),
                "pressure_zero_fraction": float(np.mean(pressure <= 1.0e-14)),
            }
        )
        state["iteration"] += 1
        return converged

    system.solve = MethodType(traced_solve, system)
    system._evaluate_convergence = MethodType(traced_evaluate, system)


def _run_traced_case(
    base,
    *,
    name: str,
    method: str,
    nx: int,
    nz: int,
    spool: tuple[float, float],
    overrides=None,
    disable_projection: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Run one isolated case and return scalar and per-iteration diagnostics."""

    bearing = build_bearing(_case_config(base, method, nx, nz, overrides))
    trace: list[dict[str, Any]] = []
    thermal_trace: list[dict[str, Any]] = []
    for index, pad in enumerate(bearing._runtime._pads):
        if disable_projection:
            model = pad.bearing.main_model

            def identity_projection(self, values):
                return values

            model._reynold_boundary = MethodType(identity_projection, model)
        _install_trace(pad.bearing, index, trace)
        original_update = pad._relaxed_miu_update
        state = {"iteration": 0}

        def traced_update(
            self,
            miu_field,
            miu_target,
            relax,
            *,
            _pad=index,
            _state=state,
            _original=original_update,
        ):
            result = _original(miu_field, miu_target, relax)
            thermal_trace.append(
                {
                    "pad": int(_pad),
                    "iteration": int(_state["iteration"]),
                    "relative_viscosity_error": float(result[1]),
                    "relaxation": float(relax),
                    "viscosity_min": float(np.min(result[0])),
                    "viscosity_max": float(np.max(result[0])),
                }
            )
            _state["iteration"] += 1
            return result

        pad._relaxed_miu_update = MethodType(traced_update, pad)
    result = bearing.calculate(
        displacement=(-24.0e-6, -36.0e-6),
        velocity=(0.0, 0.0),
        time=0.0,
        spool=spool,
    )
    pad_snapshots = [pad.result_snapshot() for pad in bearing._runtime._pads]
    pressure = np.vstack(
        [np.asarray(item.values["pressure"], dtype=float) for item in pad_snapshots]
    )
    temperature = np.vstack(
        [np.asarray(item.values["temperature"], dtype=float) for item in pad_snapshots]
    )
    viscosity = np.vstack(
        [np.asarray(item.values["viscosity_field"], dtype=float) for item in pad_snapshots]
    )
    final_rows = []
    for pad_index, pad in enumerate(bearing._runtime._pads):
        system = pad.bearing
        model = system.main_model
        orifice = system.simple_models[0]
        main_error = float(getattr(model, "errors", np.nan))
        orifice_error = float(orifice.calc_error())
        main_failed = bool(main_error > model._error_set)
        orifice_failed = bool(orifice_error > orifice.tol_err)
        pad_thermal_trace = [
            row for row in thermal_trace if row["pad"] == pad_index
        ]
        final_rows.append(
            {
                "pad": pad_index,
                "film_converged": bool(system.last_converged),
                "film_iterations": int(system.final_iter),
                "main_error": main_error,
                "main_tolerance": float(model._error_set),
                "orifice_error": orifice_error,
                "orifice_tolerance": float(orifice.tol_err),
                "limiting_component": (
                    "both"
                    if main_failed and orifice_failed
                    else "pressure"
                    if main_failed
                    else "orifice"
                    if orifice_failed
                    else "none"
                ),
                "thermal_converged": bool(pad.thermal_state.get("converged", False)),
                "thermal_iterations": int(pad.thermal_state.get("iterations", 0)),
                "thermal_final_relaxation": float(
                    pad.thermal_state.get("relax", np.nan)
                ),
                "thermal_final_relative_viscosity_error": (
                    None
                    if not pad_thermal_trace
                    else float(pad_thermal_trace[-1]["relative_viscosity_error"])
                ),
            }
        )
    force = np.asarray(result.force, dtype=float)
    summary = {
        "name": name,
        "method": method,
        "nx": nx,
        "nz": nz,
        "spool": list(spool),
        "overrides": dict(overrides or {}),
        "disable_projection": bool(disable_projection),
        "converged": bool(result.convergence.converged),
        "fx": float(force[0]),
        "fy": float(force[1]),
        "force_magnitude": float(np.linalg.norm(force)),
        "pressure_min": float(np.min(pressure)),
        "pressure_max": float(np.max(pressure)),
        "temperature_min_c": float(np.min(temperature)),
        "temperature_max_c": float(np.max(temperature)),
        "viscosity_min_pa_s": float(np.min(viscosity)),
        "viscosity_max_pa_s": float(np.max(viscosity)),
        "pads": final_rows,
    }
    return summary, trace, thermal_trace


def _trial_worker(config_path: str, trial):
    """Execute one independent convergence trial in a worker process."""

    name, method, nx, nz, spool, overrides, disable_projection = trial
    base = load_bearing_config(Path(config_path))
    summary, pressure_trace, thermal_trace = _run_traced_case(
        base,
        name=name,
        method=method,
        nx=nx,
        nz=nz,
        spool=spool,
        overrides=overrides,
        disable_projection=disable_projection,
    )
    return summary, pressure_trace, thermal_trace


def _normalized_coordinates(base, method: str, nx: int, nz: int) -> list[np.ndarray]:
    """Return normalized basis coordinates for every pad without solving."""

    bearing = build_bearing(_case_config(base, method, nx, nz))
    coordinates = []
    for pad in bearing._runtime._pads:
        values = np.asarray(pad.bearing.main_model.basis.doflocs, dtype=float).copy()
        for axis in (0, 1):
            low = float(np.min(values[axis]))
            span = float(np.max(values[axis]) - low)
            values[axis] = (values[axis] - low) / span
        coordinates.append(values)
    return coordinates


def _tensor_field(values: np.ndarray, coordinates: np.ndarray):
    """Place one structured explicit-basis field on sorted coordinate axes."""

    x_axis = np.unique(np.round(coordinates[0], 13))
    z_axis = np.unique(np.round(coordinates[1], 13))
    ix = np.searchsorted(x_axis, np.round(coordinates[0], 13))
    iz = np.searchsorted(z_axis, np.round(coordinates[1], 13))
    field = np.full((x_axis.size, z_axis.size), np.nan, dtype=float)
    field[ix, iz] = np.asarray(values, dtype=float).reshape(-1)
    if np.any(~np.isfinite(field)):
        raise ValueError("explicit field does not span a complete tensor grid")
    return x_axis, z_axis, field


def _field_comparison(
    base,
    matrix_root: Path,
    supply: str,
    method: str,
    coarse: tuple[int, int],
    fine: tuple[int, int],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Compare adjacent fields after interpolation to the finer DOF grid."""

    coarse_id = f"{supply}__{method}__{coarse[0]}x{coarse[1]}"
    fine_id = f"{supply}__{method}__{fine[0]}x{fine[1]}"
    coarse_npz = np.load(matrix_root / "cases" / coarse_id / "fields.npz")
    fine_npz = np.load(matrix_root / "cases" / fine_id / "fields.npz")
    coarse_coords = _normalized_coordinates(base, method, *coarse)
    fine_coords = _normalized_coordinates(base, method, *fine)
    report: dict[str, Any] = {
        "supply_state": supply,
        "method": method,
        "coarse_case": coarse_id,
        "fine_case": fine_id,
        "fields": {},
    }
    arrays: dict[str, np.ndarray] = {}
    for field_name in ("pressure_pa", "temperature_c", "viscosity_pa_s"):
        pad_rows = []
        interpolated_rows = []
        difference_rows = []
        for pad in range(4):
            x_axis, z_axis, coarse_field = _tensor_field(
                coarse_npz[field_name][pad], coarse_coords[pad]
            )
            _, _, fine_field = _tensor_field(
                fine_npz[field_name][pad], fine_coords[pad]
            )
            interpolator = RegularGridInterpolator(
                (x_axis, z_axis), coarse_field, bounds_error=True
            )
            points = fine_coords[pad].T
            interpolated_vector = interpolator(points)
            _, _, interpolated_field = _tensor_field(
                interpolated_vector, fine_coords[pad]
            )
            difference = fine_field - interpolated_field
            denominator = max(
                float(np.linalg.norm(fine_field)), np.finfo(float).tiny
            )
            pad_rows.append(
                {
                    "pad": pad,
                    "relative_l2": float(np.linalg.norm(difference) / denominator),
                    "max_abs_difference": float(np.max(np.abs(difference))),
                    "fine_min": float(np.min(fine_field)),
                    "fine_max": float(np.max(fine_field)),
                }
            )
            interpolated_rows.append(interpolated_field)
            difference_rows.append(difference)
        report["fields"][field_name] = pad_rows
        arrays[f"{field_name}_coarse_on_fine"] = np.stack(interpolated_rows)
        arrays[f"{field_name}_difference"] = np.stack(difference_rows)
    return report, arrays


def _write_trace_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write trace rows in an Excel-friendly UTF-8 CSV file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _plot_trace(trials: list[dict[str, Any]], traces, output: Path) -> None:
    """Create a compact pressure/orifice convergence diagnostic figure."""

    import matplotlib as mpl
    import matplotlib.pyplot as plt

    mpl.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 7,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), constrained_layout=True)
    colors = plt.get_cmap("tab10")
    for index, (trial, rows) in enumerate(zip(trials, traces)):
        if trial["name"].startswith("q2_"):
            continue
        pad_rows = [row for row in rows if row["pad"] == 2]
        if not pad_rows:
            continue
        final_solve = max(row["hydro_solve"] for row in pad_rows)
        selected = [
            row for row in pad_rows if row["hydro_solve"] == final_solve
        ]
        if not selected:
            continue
        x = [row["iteration"] for row in selected]
        axes[0].semilogy(
            x,
            [max(row["main_error"], 1e-18) for row in selected],
            color=colors(index),
            label=trial["name"],
        )
        axes[1].semilogy(
            x,
            [max(row["orifice_error"] or 0.0, 1e-18) for row in selected],
            color=colors(index),
            label=trial["name"],
        )
    axes[0].axhline(1e-6, color="0.3", linestyle="--", linewidth=0.8)
    axes[1].axhline(1e-3, color="0.3", linestyle="--", linewidth=0.8)
    axes[0].set(title="Pressure update residual", xlabel="Recorded iteration", ylabel="Mean squared update")
    axes[1].set(title="Orifice pressure residual", xlabel="Recorded iteration", ylabel="Relative update")
    axes[1].legend(frameon=False, fontsize=6, loc="upper right")
    for label, axis in zip(("a", "b"), axes):
        axis.text(-0.12, 1.04, label, transform=axis.transAxes, weight="bold", fontsize=8)
    output.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(output / f"supply_convergence_trace.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_thermal_trace(trials, traces, output: Path) -> None:
    """Plot the Q2 viscosity-coupling residual for the unstable pad."""

    import matplotlib as mpl
    import matplotlib.pyplot as plt

    mpl.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 7,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    fig, axis = plt.subplots(figsize=(5.3, 2.8), constrained_layout=True)
    colors = plt.get_cmap("tab10")
    plotted = 0
    for trial, rows in zip(trials, traces):
        if not trial["name"].startswith("q2_"):
            continue
        selected = [row for row in rows if row["pad"] == 1]
        if not selected:
            continue
        axis.semilogy(
            [row["iteration"] for row in selected],
            [max(row["relative_viscosity_error"], 1.0e-18) for row in selected],
            color=colors(plotted),
            label=trial["name"],
        )
        plotted += 1
    axis.axhline(1.0e-3, color="0.3", linestyle="--", linewidth=0.8)
    axis.set(
        xlabel="Thermal coupling iteration",
        ylabel="Relative viscosity update",
        title="Q2 thermal-coupling residual, pad 2",
    )
    axis.legend(
        frameon=False,
        fontsize=6,
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
    )
    output.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(
            output / f"q2_thermal_convergence_trace.{suffix}",
            dpi=300,
            bbox_inches="tight",
        )
    plt.close(fig)


def _plot_field_comparison(
    supply: str,
    method: str,
    coarse: tuple[int, int],
    fine: tuple[int, int],
    arrays: dict[str, np.ndarray],
    output: Path,
) -> None:
    """Plot the most-loaded pad before and after one mesh transition."""

    import matplotlib as mpl
    import matplotlib.pyplot as plt

    mpl.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 7,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    pressure_coarse = arrays["pressure_pa_coarse_on_fine"]
    pressure_difference = arrays["pressure_pa_difference"]
    pressure_fine = pressure_coarse + pressure_difference
    pad = int(np.argmax(np.max(pressure_fine, axis=(1, 2))))
    temperature_coarse = arrays["temperature_c_coarse_on_fine"][pad]
    temperature_difference = arrays["temperature_c_difference"][pad]
    temperature_fine = temperature_coarse + temperature_difference
    fields = (
        (pressure_coarse[pad] / 1.0e6, "Coarse on fine", "Pressure (MPa)"),
        (pressure_fine[pad] / 1.0e6, "Fine", "Pressure (MPa)"),
        (pressure_difference[pad] / 1.0e6, "Fine - coarse", "Pressure difference (MPa)"),
        (temperature_coarse, "Coarse on fine", "Temperature (°C)"),
        (temperature_fine, "Fine", "Temperature (°C)"),
        (temperature_difference, "Fine - coarse", "Temperature difference (°C)"),
    )
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.1), constrained_layout=True)
    for index, (axis, (field, title, colorbar_label)) in enumerate(
        zip(axes.flat, fields)
    ):
        cmap = "coolwarm" if index in (2, 5) else "viridis"
        image = axis.imshow(
            field.T,
            origin="lower",
            aspect="auto",
            extent=(0.0, 1.0, 0.0, 1.0),
            cmap=cmap,
        )
        axis.set(title=title, xlabel="Circumferential coordinate")
        if index % 3 == 0:
            axis.set_ylabel("Axial coordinate")
        fig.colorbar(image, ax=axis, label=colorbar_label, shrink=0.82)
        axis.text(
            -0.14,
            1.04,
            chr(ord("a") + index),
            transform=axis.transAxes,
            weight="bold",
            fontsize=8,
        )
    fig.suptitle(
        f"{supply}, {method}, pad {pad + 1}: "
        f"{coarse[0]}×{coarse[1]} to {fine[0]}×{fine[1]}"
    )
    output.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{supply}_{method}_{coarse[0]}x{coarse[1]}_to_"
        f"{fine[0]}x{fine[1]}_fields"
    )
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(output / f"{stem}.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _diagnosis_summary(comparisons, summaries, thermal_traces) -> dict[str, Any]:
    """Build a compact machine-readable statement of the controlled evidence."""

    by_name = {row["name"]: row for row in summaries}
    trace_by_name = {
        row["name"]: trace for row, trace in zip(summaries, thermal_traces)
    }

    def pad(summary_name: str, pad_index: int) -> dict[str, Any]:
        return by_name[summary_name]["pads"][pad_index]

    def last_window(summary_name: str, pad_index: int) -> dict[str, float]:
        values = [
            float(row["relative_viscosity_error"])
            for row in trace_by_name[summary_name]
            if row["pad"] == pad_index
        ][-20:]
        return {
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
            "mean": float(np.mean(values)),
        }

    comparison_by_key = {
        (row["supply_state"], row["method"]): row for row in comparisons
    }
    supply_field = comparison_by_key[("supply_on", "tri_p2")]["fields"]
    q2_off_field = comparison_by_key[("supply_off", "quad_q2")]["fields"]
    q2_on_field = comparison_by_key[("supply_on", "quad_q2")]["fields"]
    baseline = pad("supply_on_baseline", 2)
    long_run = pad("supply_on_long", 2)
    unprojected = by_name["supply_on_unprojected"]
    q2_trials = (
        "q2_supply_off_baseline",
        "q2_supply_off_relax_0p1",
        "q2_supply_off_adaptive",
        "q2_supply_off_conductive",
    )
    return {
        "schema": "alb.mesh-independence-convergence-diagnosis.v1",
        "pressure_supply_coupling": {
            "finding": (
                "The original supply-on stop is an iteration-budget cutoff, "
                "not pressure divergence or thermal runaway."
            ),
            "baseline_60_iterations": {
                "converged": by_name["supply_on_baseline"]["converged"],
                "limiting_pad_zero_based": 2,
                "pressure_error": baseline["main_error"],
                "pressure_tolerance": baseline["main_tolerance"],
                "orifice_error": baseline["orifice_error"],
                "orifice_tolerance": baseline["orifice_tolerance"],
                "limiting_component": baseline["limiting_component"],
            },
            "accepted_240_iteration_control": {
                "converged": by_name["supply_on_long"]["converged"],
                "limiting_pad_zero_based": 2,
                "iterations": long_run["film_iterations"],
                "pressure_error": long_run["main_error"],
                "orifice_error": long_run["orifice_error"],
            },
            "unprojected_control_rejected": {
                "converged": unprojected["converged"],
                "pressure_min_nondimensional": unprojected["pressure_min"],
                "reason": (
                    "It violates the nonnegative-pressure constraint and can "
                    "select a different cavitation branch."
                ),
            },
            "most_loaded_pad_50x25_to_60x30": {
                "pad_zero_based": 0,
                "pressure_relative_l2": supply_field["pressure_pa"][0][
                    "relative_l2"
                ],
                "pressure_max_abs_difference_pa": supply_field["pressure_pa"][0][
                    "max_abs_difference"
                ],
                "temperature_relative_l2": supply_field["temperature_c"][0][
                    "relative_l2"
                ],
                "temperature_max_abs_difference_c": supply_field[
                    "temperature_c"
                ][0]["max_abs_difference"],
                "viscosity_relative_l2": supply_field["viscosity_pa_s"][0][
                    "relative_l2"
                ],
            },
        },
        "q2_thermal_coupling": {
            "finding": (
                "The remaining Q2 failures are thermal-coupling limit cycles "
                "that occur with supply both off and on."
            ),
            "supply_off_baseline": pad("q2_supply_off_baseline", 1),
            "supply_on_baseline": pad("q2_supply_on_baseline", 1),
            "controlled_trial_last_20_error": {
                name: last_window(name, 1) for name in q2_trials
            },
            "supply_off_40x20_to_50x25": {
                "pad_zero_based": 1,
                "temperature_relative_l2": q2_off_field["temperature_c"][1][
                    "relative_l2"
                ],
                "temperature_max_abs_difference_c": q2_off_field[
                    "temperature_c"
                ][1]["max_abs_difference"],
                "viscosity_relative_l2": q2_off_field["viscosity_pa_s"][1][
                    "relative_l2"
                ],
            },
            "supply_on_40x20_to_50x25": {
                "pad_zero_based": 1,
                "temperature_relative_l2": q2_on_field["temperature_c"][1][
                    "relative_l2"
                ],
                "temperature_max_abs_difference_c": q2_on_field[
                    "temperature_c"
                ][1]["max_abs_difference"],
            },
            "inference": (
                "The evidence points to the current high-order thermal "
                "stabilization, boundary enforcement, and clipping interaction; "
                "ordinary relaxation and conductivity changes do not resolve it."
            ),
        },
    }


def main() -> None:
    """Run field comparisons and controlled pressure-convergence trials."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--matrix-root", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--skip-traces", action="store_true")
    parser.add_argument("--workers", type=int, default=1, choices=range(1, 5))
    parser.add_argument("--force-traces", action="store_true")
    args = parser.parse_args()
    matrix_root = args.matrix_root.resolve()
    output = matrix_root / "diagnostics" / "supply_convergence"
    output.mkdir(parents=True, exist_ok=True)
    base = load_bearing_config(args.config.resolve())

    comparisons = []
    comparison_arrays = {}
    comparison_specs = (
        ("supply_off", "tri_p2", (50, 25), (60, 30)),
        ("supply_on", "tri_p2", (50, 25), (60, 30)),
        ("supply_off", "quad_q2", (40, 20), (50, 25)),
        ("supply_on", "quad_q2", (40, 20), (50, 25)),
    )
    for supply, method, coarse, fine in comparison_specs:
        report, arrays = _field_comparison(
            base, matrix_root, supply, method, coarse, fine
        )
        comparisons.append(report)
        prefix = (
            f"{supply}.{method}.{coarse[0]}x{coarse[1]}."
            f"{fine[0]}x{fine[1]}"
        )
        comparison_arrays.update(
            {f"{prefix}.{name}": value for name, value in arrays.items()}
        )
        _plot_field_comparison(
            supply, method, coarse, fine, arrays, output
        )
    _atomic_json(output / "field_comparison.json", comparisons)
    np.savez_compressed(output / "field_comparison.npz", **comparison_arrays)

    if args.skip_traces:
        return
    trials = (
        ("supply_off_baseline", "tri_p2", 60, 30, (0.0, 0.0), {}, False),
        ("supply_on_baseline", "tri_p2", 60, 30, (0.2, 0.2), {}, False),
        ("supply_on_unprojected", "tri_p2", 60, 30, (0.2, 0.2), {}, True),
        (
            "supply_on_long",
            "tri_p2",
            60,
            30,
            (0.2, 0.2),
            {"film.max_iterations": 240},
            False,
        ),
        (
            "supply_on_relax_0p4",
            "tri_p2",
            60,
            30,
            (0.2, 0.2),
            {"film.max_iterations": 240, "film.relaxation": 0.4},
            False,
        ),
        (
            "supply_on_adaptive",
            "tri_p2",
            60,
            30,
            (0.2, 0.2),
            {
                "film.max_iterations": 240,
                "film.adaptive_damping": {
                    "enabled": True,
                    "min_value": 0.05,
                    "max_value": 0.8,
                },
            },
            False,
        ),
        ("q2_supply_off_baseline", "quad_q2", 50, 25, (0.0, 0.0), {}, False),
        ("q2_supply_on_baseline", "quad_q2", 50, 25, (0.2, 0.2), {}, False),
        (
            "q2_supply_off_relax_0p1",
            "quad_q2",
            50,
            25,
            (0.0, 0.0),
            {"thermal.relax": 0.1, "thermal.max_iter": 240},
            False,
        ),
        (
            "q2_supply_off_adaptive",
            "quad_q2",
            50,
            25,
            (0.0, 0.0),
            {
                "thermal.max_iter": 240,
                "thermal.adaptive_damp": {
                    "enabled": True,
                    "min_value": 0.02,
                    "max_value": 0.5,
                },
            },
            False,
        ),
        (
            "q2_supply_off_conductive",
            "quad_q2",
            50,
            25,
            (0.0, 0.0),
            {"thermal.k_lub": 0.13, "thermal.max_iter": 240},
            False,
        ),
    )
    results = {}
    pending_trials = []
    for trial in trials:
        cached_path = output / f"{trial[0]}.json"
        if cached_path.exists() and not args.force_traces:
            cached = json.loads(cached_path.read_text(encoding="utf-8"))
            results[trial[0]] = (
                cached["summary"],
                cached["pressure_trace"],
                cached["thermal_trace"],
            )
            print(f"RESUME {trial[0]}", flush=True)
        else:
            pending_trials.append(trial)
    if args.workers == 1:
        for trial in pending_trials:
            print(f"START {trial[0]}", flush=True)
            results[trial[0]] = _trial_worker(str(args.config.resolve()), trial)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(_trial_worker, str(args.config.resolve()), trial): trial[0]
                for trial in pending_trials
            }
            for future in as_completed(futures):
                name = futures[future]
                results[name] = future.result()
                print(f"DONE  {name}", flush=True)
    summaries = []
    all_traces = []
    all_thermal_traces = []
    for trial in trials:
        name = trial[0]
        summary, trace, thermal_trace = results[name]
        summaries.append(summary)
        all_traces.append(trace)
        all_thermal_traces.append(thermal_trace)
        _atomic_json(
            output / f"{name}.json",
            {
                "summary": summary,
                "pressure_trace": trace,
                "thermal_trace": thermal_trace,
            },
        )
        _write_trace_csv(output / f"{name}_trace.csv", trace)
        _write_trace_csv(output / f"{name}_thermal_trace.csv", thermal_trace)
        print(f"SEALED {name} converged={summary['converged']}", flush=True)
    _atomic_json(output / "controlled_trials.json", summaries)
    _atomic_json(
        output / "diagnosis_summary.json",
        _diagnosis_summary(comparisons, summaries, all_thermal_traces),
    )
    _plot_trace(summaries, all_traces, output)
    _plot_thermal_trace(summaries, all_thermal_traces, output)


if __name__ == "__main__":
    main()
