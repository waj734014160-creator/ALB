"""Plot equation-linearized and PD-controlled nonlinear ALB responses.

The equation response uses independently derived continuous K, C, and complex
dF/dxv coefficients.  Journal motion is prescribed, while the spool phasor is
extracted from the recorded project PD and second-order Moog response.  The
trajectory is validation input only and is never used to derive coefficients.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Arial",
    "DejaVu Sans",
    "Liberation Sans",
]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["font.size"] = 7.5
plt.rcParams["axes.linewidth"] = 0.8
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False
plt.rcParams["legend.frameon"] = False


LINEAR_COLOR = "#0F4D92"
ALB_COLOR = "#272727"
ERROR_COLOR = "#B64342"
STIFFNESS_COLOR = "#D17C16"
DAMPING_COLOR = "#16827A"
SPOOL_COLOR = "#8A4F9E"
GRID_COLOR = "#D8D8D8"

REQUIRED_COLUMNS = {
    "amplitude_um",
    "direction",
    "cycle",
    "phase_index",
    "phase_rad",
    "dx_m",
    "dy_m",
    "vx_m_per_s",
    "vy_m_per_s",
    "controller_kp",
    "controller_ki",
    "controller_kd",
    "sensor_angle_x_deg",
    "sensor_angle_y_deg",
    "servo_natural_frequency_hz",
    "servo_zeta",
    "controller_u_x",
    "controller_u_y",
    "xv_x_nondim",
    "xv_y_nondim",
    "dsx_nondim",
    "dsy_nondim",
    "controller_saturated",
    "servovalve_saturated",
    "nonlinear_delta_fx_N",
    "nonlinear_delta_fy_N",
    "maximum_nonlinear_merit_l2",
    "maximum_nonlinear_iterations",
    "nonlinear_converged",
}


def parse_args() -> argparse.Namespace:
    """Parse source paths and publication export controls."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory-csv", type=Path, required=True)
    parser.add_argument("--trajectory-json", type=Path, required=True)
    parser.add_argument("--coefficient-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-data-dir", type=Path, required=True)
    parser.add_argument("--amplitude-um", type=float, default=5.0)
    parser.add_argument("--clearance-um", type=float, default=120.0)
    parser.add_argument(
        "--case-tag",
        default="",
        help="Optional filesystem-safe tag inserted into exported filenames.",
    )
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def load_coefficients(
    path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Load formal continuous K, C, and complex dF/dxv matrices."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    frequency = payload["strict_frequency_domain"]["continuous_iomega"]
    stiffness = np.asarray(frequency["K_N_per_m"], dtype=float)
    damping = np.asarray(frequency["C_N_s_per_m"], dtype=float)
    spool_payload = frequency["spool_transfer_N_per_nondim"]
    if not isinstance(spool_payload, dict):
        raise TypeError("Complex dF/dxv must contain real and imag arrays")
    spool_transfer = np.asarray(spool_payload["real"], dtype=float) + 1j * np.asarray(
        spool_payload["imag"], dtype=float
    )
    if any(matrix.shape != (2, 2) for matrix in (stiffness, damping, spool_transfer)):
        raise ValueError("K, C, and dF/dxv must all be 2 x 2 matrices")
    return stiffness, damping, spool_transfer, payload["configuration"]


def load_trajectory_summary(path: Path, amplitude_um: float) -> dict:
    """Load and validate provenance for the nonlinear PD trajectory."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("direct_spool_harmonic_imposed") is not False:
        raise ValueError("The validation must not impose a spool harmonic")
    if payload.get("coefficients_derived_from_trajectory") is not False:
        raise ValueError("Trajectory-derived coefficients are not allowed")
    configured_amplitude = float(payload["configuration"]["amplitude_um"])
    if not np.isclose(configured_amplitude, float(amplitude_um)):
        raise ValueError(
            "Trajectory JSON amplitude does not match the requested figure"
        )
    return payload


def select_last_cycle(frame: pd.DataFrame, amplitude_um: float) -> pd.DataFrame:
    """Select the final converged cycle for both whirl directions."""

    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Trajectory data are missing columns: {sorted(missing)}")
    amplitude_mask = np.isclose(
        frame["amplitude_um"].to_numpy(dtype=float),
        float(amplitude_um),
    )
    selected = frame.loc[amplitude_mask].copy()
    if selected.empty:
        available = sorted(frame["amplitude_um"].unique().tolist())
        raise ValueError(
            f"Amplitude {amplitude_um:g} um is unavailable; choices are {available}"
        )
    final_cycle = int(selected["cycle"].max())
    selected = selected.loc[selected["cycle"] == final_cycle].copy()
    directions = set(selected["direction"].unique())
    if directions != {"forward", "reverse"}:
        raise ValueError("The final cycle must contain forward and reverse data")
    if not bool(selected["nonlinear_converged"].all()):
        raise RuntimeError("The selected nonlinear ALB cycle contains failed steps")
    return selected.sort_values(["direction", "phase_rad"]).reset_index(drop=True)


def relative_l2(reference: np.ndarray, candidate: np.ndarray) -> float:
    """Return an L2 error normalized by the reference series norm."""

    denominator = max(float(np.linalg.norm(reference)), np.finfo(float).tiny)
    return float(np.linalg.norm(candidate - reference) / denominator)


def first_harmonic(
    phases: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Extract a complex first-harmonic phasor and reconstruction audit."""

    phases = np.asarray(phases, dtype=float)
    values = np.asarray(values, dtype=float)
    mean = np.mean(values, axis=0)
    centered = values - mean
    phasor = (2.0 / len(phases)) * np.sum(
        centered * np.exp(-1j * phases)[:, None], axis=0
    )
    reconstructed = np.real(np.exp(1j * phases)[:, None] * phasor[None, :])
    residual = relative_l2(centered, reconstructed)
    return mean, phasor, reconstructed, residual


def complex_vector_payload(values: np.ndarray) -> dict:
    """Return traceable real, imaginary, magnitude, and phase arrays."""

    vector = np.asarray(values, dtype=complex).reshape(2)
    return {
        "real": vector.real.tolist(),
        "imag": vector.imag.tolist(),
        "magnitude": np.abs(vector).tolist(),
        "phase_deg": np.rad2deg(np.angle(vector)).tolist(),
    }


def complex_scalar_payload(value: complex) -> dict:
    """Return traceable scalar complex magnitude and phase data."""

    scalar = complex(value)
    return {
        "real": scalar.real,
        "imag": scalar.imag,
        "magnitude": abs(scalar),
        "phase_deg": float(np.rad2deg(np.angle(scalar))),
    }


def add_linear_response(
    frame: pd.DataFrame,
    stiffness: np.ndarray,
    damping: np.ndarray,
    spool_transfer: np.ndarray,
) -> tuple[pd.DataFrame, dict]:
    """Evaluate K, C, and complex dF/dxv contributions at ALB samples."""

    result = frame.copy()
    result["phase_fraction"] = result["phase_rad"] / (2.0 * np.pi)
    response_columns = (
        "stiffness_delta_fx_N",
        "stiffness_delta_fy_N",
        "damping_delta_fx_N",
        "damping_delta_fy_N",
        "spool_delta_fx_N",
        "spool_delta_fy_N",
        "linear_total_delta_fx_N",
        "linear_total_delta_fy_N",
        "error_fx_N",
        "error_fy_N",
        "spool_harmonic_dsx_nondim",
        "spool_harmonic_dsy_nondim",
        "spool_harmonic_residual_x_nondim",
        "spool_harmonic_residual_y_nondim",
    )
    for column in response_columns:
        result[column] = np.nan

    spool_audits: dict[str, dict] = {}
    for direction in ("forward", "reverse"):
        indices = result.index[result["direction"] == direction]
        group = result.loc[indices]
        phases = group["phase_rad"].to_numpy(dtype=float)
        displacement = group[["dx_m", "dy_m"]].to_numpy(dtype=float)
        velocity = group[["vx_m_per_s", "vy_m_per_s"]].to_numpy(dtype=float)
        spool_delta = group[["dsx_nondim", "dsy_nondim"]].to_numpy(dtype=float)
        spool_mean, spool_phasor, spool_harmonic, harmonic_error = first_harmonic(
            phases, spool_delta
        )
        force_phasor = spool_transfer @ spool_phasor
        spool_force = np.real(
            np.exp(1j * phases)[:, None] * force_phasor[None, :]
        )
        stiffness_force = -displacement @ stiffness.T
        damping_force = -velocity @ damping.T
        linear_force = stiffness_force + damping_force + spool_force
        alb_force = group[
            ["nonlinear_delta_fx_N", "nonlinear_delta_fy_N"]
        ].to_numpy(dtype=float)
        error = alb_force - linear_force
        spool_residual = spool_delta - spool_mean - spool_harmonic

        result.loc[indices, ["stiffness_delta_fx_N", "stiffness_delta_fy_N"]] = (
            stiffness_force
        )
        result.loc[indices, ["damping_delta_fx_N", "damping_delta_fy_N"]] = (
            damping_force
        )
        result.loc[indices, ["spool_delta_fx_N", "spool_delta_fy_N"]] = spool_force
        result.loc[
            indices, ["linear_total_delta_fx_N", "linear_total_delta_fy_N"]
        ] = linear_force
        result.loc[indices, ["error_fx_N", "error_fy_N"]] = error
        result.loc[
            indices,
            ["spool_harmonic_dsx_nondim", "spool_harmonic_dsy_nondim"],
        ] = spool_harmonic
        result.loc[
            indices,
            [
                "spool_harmonic_residual_x_nondim",
                "spool_harmonic_residual_y_nondim",
            ],
        ] = spool_residual
        spool_audits[direction] = {
            "mean_delta_spool_nondim": spool_mean.tolist(),
            "first_harmonic_delta_spool_nondim": complex_vector_payload(
                spool_phasor
            ),
            "first_harmonic_force_N": complex_vector_payload(force_phasor),
            "first_harmonic_reconstruction_relative_l2": harmonic_error,
        }
    return result, spool_audits


def comparison_metrics(frame: pd.DataFrame) -> dict:
    """Compute direction-wise component and vector relative errors."""

    metrics: dict[str, dict[str, float]] = {}
    for direction in ("forward", "reverse"):
        group = frame.loc[frame["direction"] == direction]
        alb = group[
            ["nonlinear_delta_fx_N", "nonlinear_delta_fy_N"]
        ].to_numpy(dtype=float)
        linear = group[
            ["linear_total_delta_fx_N", "linear_total_delta_fy_N"]
        ].to_numpy(dtype=float)
        without_spool = (
            group[["stiffness_delta_fx_N", "stiffness_delta_fy_N"]].to_numpy(
                dtype=float
            )
            + group[["damping_delta_fx_N", "damping_delta_fy_N"]].to_numpy(
                dtype=float
            )
        )
        metrics[direction] = {
            "fx_relative_l2": relative_l2(alb[:, 0], linear[:, 0]),
            "fy_relative_l2": relative_l2(alb[:, 1], linear[:, 1]),
            "vector_relative_l2": relative_l2(alb, linear),
            "without_spool_vector_relative_l2": relative_l2(alb, without_spool),
            "maximum_force_error_N": float(np.max(np.abs(alb - linear))),
        }
    return metrics


def trajectory_diagnostics(frame: pd.DataFrame) -> dict:
    """Summarize convergence, saturation, and final-cycle repeatability."""

    diagnostics: dict[str, dict[str, float | int | bool]] = {}
    for direction in ("forward", "reverse"):
        group = frame.loc[frame["direction"] == direction].copy()
        cycles = sorted(int(value) for value in group["cycle"].unique())
        if len(cycles) < 2:
            raise ValueError("At least two cycles are required for repeatability")
        previous = group.loc[group["cycle"] == cycles[-2]].sort_values("phase_index")
        final = group.loc[group["cycle"] == cycles[-1]].sort_values("phase_index")
        previous_force = previous[
            ["nonlinear_delta_fx_N", "nonlinear_delta_fy_N"]
        ].to_numpy(dtype=float)
        final_force = final[
            ["nonlinear_delta_fx_N", "nonlinear_delta_fy_N"]
        ].to_numpy(dtype=float)
        diagnostics[direction] = {
            "final_cycle": cycles[-1],
            "cycle_repeat_relative_l2": relative_l2(previous_force, final_force),
            "maximum_final_cycle_merit_l2": float(
                final["maximum_nonlinear_merit_l2"].max()
            ),
            "maximum_final_cycle_iterations": int(
                final["maximum_nonlinear_iterations"].max()
            ),
            "all_final_cycle_steps_converged": bool(
                final["nonlinear_converged"].all()
            ),
            "controller_saturated": bool(final["controller_saturated"].any()),
            "servovalve_saturated": bool(final["servovalve_saturated"].any()),
        }
    return diagnostics


def controller_chain_audit(
    frame: pd.DataFrame,
    trajectory_summary: dict,
    clearance_m: float,
) -> dict:
    """Verify the recorded PD law and characterize the discrete valve response."""

    config = trajectory_summary["configuration"]
    controller = config["controller"]
    servovalve = config["servovalve"]
    angles = np.deg2rad(np.asarray(controller["sensor_angles_deg"], dtype=float))
    sensors = np.column_stack((np.cos(angles), np.sin(angles)))
    kp = float(controller["kp"])
    kd = float(controller["kd"])
    omega_r = 2.0 * np.pi * float(
        controller["frequency_hz_for_nondimensional_derivative"]
    )
    dt = float(config["dt_s"])
    omega_w = float(config["whirl_omega_rad_s"])
    tw = 1.0 / (
        2.0 * np.pi * float(servovalve["natural_frequency_hz"])
    )
    zeta = float(servovalve["zeta"])
    continuous_valve = 1.0 / (
        tw**2 * (1j * omega_w) ** 2
        + 2.0 * zeta * tw * (1j * omega_w)
        + 1.0
    )

    audit: dict[str, dict] = {}
    for direction in ("forward", "reverse"):
        group = frame.loc[frame["direction"] == direction].sort_values(
            "phase_rad"
        )
        displacement_nondim = (
            group[["dx_m", "dy_m"]].to_numpy(dtype=float) / clearance_m
        )
        sensor_delta = displacement_nondim @ sensors.T
        expected_command_delta = kp * sensor_delta + (kd / omega_r) * (
            sensor_delta - np.roll(sensor_delta, 1, axis=0)
        ) / dt
        recorded_command = group[
            ["controller_u_x", "controller_u_y"]
        ].to_numpy(dtype=float)
        recorded_command_delta = recorded_command - np.mean(
            recorded_command, axis=0
        )
        pd_relative_error = relative_l2(
            expected_command_delta, recorded_command_delta
        )
        phases = group["phase_rad"].to_numpy(dtype=float)
        _, command_phasor, _, command_harmonic_error = first_harmonic(
            phases, recorded_command_delta
        )
        spool_delta = group[["dsx_nondim", "dsy_nondim"]].to_numpy(
            dtype=float
        )
        _, spool_phasor, _, _ = first_harmonic(phases, spool_delta)
        valve_transfer_channels = spool_phasor / command_phasor
        valve_transfer = np.mean(valve_transfer_channels)
        audit[direction] = {
            "pd_sequence_relative_l2": pd_relative_error,
            "pd_sequence_maximum_abs_error": float(
                np.max(np.abs(expected_command_delta - recorded_command_delta))
            ),
            "controller_command_first_harmonic": complex_vector_payload(
                command_phasor
            ),
            "controller_command_harmonic_relative_l2": command_harmonic_error,
            "measured_discrete_valve_transfer": complex_scalar_payload(
                valve_transfer
            ),
            "valve_channel_consistency_relative_max": float(
                np.max(np.abs(valve_transfer_channels - valve_transfer))
                / abs(valve_transfer)
            ),
            "continuous_valve_transfer": complex_scalar_payload(
                continuous_valve
            ),
            "discrete_vs_continuous_valve_relative_difference": float(
                abs(valve_transfer - continuous_valve) / abs(valve_transfer)
            ),
        }
    return audit


def dense_linear_curve(
    amplitude_um: float,
    direction: str,
    whirl_omega: float,
    stiffness: np.ndarray,
    damping: np.ndarray,
    spool_transfer: np.ndarray,
    spool_phasor: np.ndarray,
    point_count: int = 721,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Evaluate smooth K, C, complex dF/dxv, and total curves."""

    phase = np.linspace(0.0, 2.0 * np.pi, point_count)
    amplitude_m = float(amplitude_um) * 1.0e-6
    sign = 1.0 if direction == "forward" else -1.0
    displacement = np.column_stack(
        [
            amplitude_m * np.cos(phase),
            sign * amplitude_m * np.sin(phase),
        ]
    )
    velocity = np.column_stack(
        [
            -amplitude_m * whirl_omega * np.sin(phase),
            sign * amplitude_m * whirl_omega * np.cos(phase),
        ]
    )
    stiffness_force = -displacement @ stiffness.T
    damping_force = -velocity @ damping.T
    force_phasor = spool_transfer @ np.asarray(spool_phasor, dtype=complex)
    spool_force = np.real(np.exp(1j * phase)[:, None] * force_phasor[None, :])
    contributions = {
        "stiffness": stiffness_force,
        "damping": damping_force,
        "spool": spool_force,
        "total": stiffness_force + damping_force + spool_force,
    }
    return phase / (2.0 * np.pi), contributions


def configure_main_axis(ax: plt.Axes) -> None:
    """Apply consistent response-panel styling."""

    ax.axhline(0.0, color=GRID_COLOR, lw=0.7, zorder=0)
    ax.grid(axis="x", color=GRID_COLOR, lw=0.5, alpha=0.65)
    ax.tick_params(direction="out", length=3.0, width=0.7)
    ax.set_xlim(0.0, 1.0)


def configure_error_axis(ax: plt.Axes) -> None:
    """Apply consistent residual-panel styling."""

    ax.axhline(0.0, color=ALB_COLOR, lw=0.65, alpha=0.7)
    ax.grid(axis="x", color=GRID_COLOR, lw=0.5, alpha=0.65)
    ax.tick_params(direction="out", length=2.5, width=0.65)
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel(r"Normalized time, $t/T_w$")


def make_figure(
    frame: pd.DataFrame,
    stiffness: np.ndarray,
    damping: np.ndarray,
    spool_transfer: np.ndarray,
    whirl_omega: float,
    amplitude_um: float,
    spool_audits: dict,
    metrics: dict,
) -> plt.Figure:
    """Build a four-panel response grid with aligned residual strips."""

    width_in = 180.0 / 25.4
    height_in = 158.0 / 25.4
    fig = plt.figure(figsize=(width_in, height_in))
    outer = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.28)
    main_axes = []
    error_axes = []
    for cell in (outer[0, 0], outer[0, 1], outer[1, 0], outer[1, 1]):
        inner = cell.subgridspec(2, 1, height_ratios=(3.2, 1.0), hspace=0.05)
        main_axes.append(fig.add_subplot(inner[0, 0]))
        error_axes.append(fig.add_subplot(inner[1, 0], sharex=main_axes[-1]))

    panels = [
        ("a", "forward", 0, r"Forward whirl: $\Delta F_x$"),
        ("b", "forward", 1, r"Forward whirl: $\Delta F_y$"),
        ("c", "reverse", 0, r"Reverse whirl: $\Delta F_x$"),
        ("d", "reverse", 1, r"Reverse whirl: $\Delta F_y$"),
    ]
    component_columns = (
        ("nonlinear_delta_fx_N", "error_fx_N"),
        ("nonlinear_delta_fy_N", "error_fy_N"),
    )

    legend_handles = None
    for main_ax, error_ax, (label, direction, component, title) in zip(
        main_axes, error_axes, panels
    ):
        group = frame.loc[frame["direction"] == direction]
        phasor_payload = spool_audits[direction][
            "first_harmonic_delta_spool_nondim"
        ]
        spool_phasor = np.asarray(phasor_payload["real"]) + 1j * np.asarray(
            phasor_payload["imag"]
        )
        phase_dense, force_dense = dense_linear_curve(
            amplitude_um,
            direction,
            whirl_omega,
            stiffness,
            damping,
            spool_transfer,
            spool_phasor,
        )
        alb_column, error_column = component_columns[component]
        stiffness_line = main_ax.plot(
            phase_dense,
            force_dense["stiffness"][:, component],
            color=STIFFNESS_COLOR,
            lw=0.95,
            ls="--",
            label=r"$-K\,\Delta x$",
            zorder=1,
        )[0]
        damping_line = main_ax.plot(
            phase_dense,
            force_dense["damping"][:, component],
            color=DAMPING_COLOR,
            lw=0.95,
            ls="-.",
            label=r"$-C\,\Delta \dot{x}$",
            zorder=1,
        )[0]
        spool_line = main_ax.plot(
            phase_dense,
            force_dense["spool"][:, component],
            color=SPOOL_COLOR,
            lw=1.05,
            ls=":",
            label=r"$(\partial F/\partial x_v)_\omega$ term (PD/Moog)",
            zorder=1,
        )[0]
        linear_line = main_ax.plot(
            phase_dense,
            force_dense["total"][:, component],
            color=LINEAR_COLOR,
            lw=1.8,
            label="Total equation linearization",
            zorder=2,
        )[0]
        alb_line = main_ax.plot(
            group["phase_fraction"],
            group[alb_column],
            color=ALB_COLOR,
            marker="o",
            ms=3.0,
            mfc="white",
            mew=0.8,
            lw=0.9,
            label="Full nonlinear ALB NCP",
            zorder=3,
        )[0]
        if legend_handles is None:
            legend_handles = [
                stiffness_line,
                damping_line,
                spool_line,
                linear_line,
                alb_line,
            ]
        configure_main_axis(main_ax)
        main_ax.set_title(title, loc="left", fontsize=8.3, pad=4.0)
        main_ax.set_ylabel("Force increment (N)")
        main_ax.tick_params(labelbottom=False)
        error_key = "fx_relative_l2" if component == 0 else "fy_relative_l2"
        main_ax.text(
            0.98,
            0.94,
            rf"$\varepsilon_{{L2}}$ = {100.0 * metrics[direction][error_key]:.2f}%",
            transform=main_ax.transAxes,
            ha="right",
            va="top",
            fontsize=7.0,
            color=ALB_COLOR,
        )
        main_ax.text(
            -0.13,
            1.04,
            label,
            transform=main_ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=9.0,
            fontweight="bold",
        )

        error_ax.plot(
            group["phase_fraction"],
            group[error_column],
            color=ERROR_COLOR,
            marker="o",
            ms=2.4,
            lw=0.9,
        )
        error_ax.fill_between(
            group["phase_fraction"].to_numpy(dtype=float),
            0.0,
            group[error_column].to_numpy(dtype=float),
            color=ERROR_COLOR,
            alpha=0.12,
            linewidth=0.0,
        )
        configure_error_axis(error_ax)
        error_ax.set_ylabel("ALB - linear\n(N)", fontsize=6.5)

    fig.legend(
        legend_handles,
        [handle.get_label() for handle in legend_handles],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.955),
        ncol=3,
        handlelength=2.2,
        columnspacing=1.4,
        fontsize=6.9,
    )
    kp = float(frame["controller_kp"].iloc[0])
    kd = float(frame["controller_kd"].iloc[0])
    servo_frequency = float(frame["servo_natural_frequency_hz"].iloc[0])
    servo_zeta = float(frame["servo_zeta"].iloc[0])
    fig.suptitle(
        rf"Equation $K$, $C$, and complex $(\partial F/\partial x_v)_\omega$ "
        rf"vs full ALB NCP: {amplitude_um:g} $\mu$m PD orbit "
        rf"($k_p={kp:g}$, $k_d={kd:g}$; Moog {servo_frequency:g} Hz, "
        rf"$\zeta={servo_zeta:g}$; no imposed spool harmonic)",
        y=0.995,
        fontsize=8.7,
        fontweight="bold",
    )
    fig.subplots_adjust(left=0.11, right=0.98, bottom=0.09, top=0.81)
    return fig


def export_outputs(
    figure: plt.Figure,
    frame: pd.DataFrame,
    metrics: dict,
    stiffness: np.ndarray,
    damping: np.ndarray,
    spool_transfer: np.ndarray,
    configuration: dict,
    diagnostics: dict,
    spool_audits: dict,
    control_chain_audit: dict,
    trajectory_summary: dict,
    clearance_m: float,
    output_dir: Path,
    source_data_dir: Path,
    case_tag: str,
    dpi: int,
) -> list[Path]:
    """Export editable graphics, preview raster, source data, and metrics."""

    output_dir.mkdir(parents=True, exist_ok=True)
    source_data_dir.mkdir(parents=True, exist_ok=True)
    stem = "alb_harmonic_kcg_pd_time_response"
    if case_tag:
        if not case_tag.replace("_", "").isalnum():
            raise ValueError("case_tag may contain only letters, digits, and underscores")
        stem = f"{stem}_{case_tag}"
    base = output_dir / f"{stem}_comparison"
    outputs = []
    for extension in ("svg", "pdf", "png"):
        path = base.with_suffix(f".{extension}")
        save_kwargs = {"bbox_inches": "tight"}
        if extension == "png":
            save_kwargs["dpi"] = int(dpi)
        figure.savefig(path, **save_kwargs)
        outputs.append(path)

    source_columns = [
        "amplitude_um",
        "direction",
        "cycle",
        "phase_rad",
        "phase_fraction",
        "dx_m",
        "dy_m",
        "vx_m_per_s",
        "vy_m_per_s",
        "controller_kp",
        "controller_ki",
        "controller_kd",
        "sensor_angle_x_deg",
        "sensor_angle_y_deg",
        "servo_natural_frequency_hz",
        "servo_zeta",
        "controller_u_x",
        "controller_u_y",
        "xv_x_nondim",
        "xv_y_nondim",
        "dsx_nondim",
        "dsy_nondim",
        "spool_harmonic_dsx_nondim",
        "spool_harmonic_dsy_nondim",
        "spool_harmonic_residual_x_nondim",
        "spool_harmonic_residual_y_nondim",
        "nonlinear_delta_fx_N",
        "nonlinear_delta_fy_N",
        "stiffness_delta_fx_N",
        "stiffness_delta_fy_N",
        "damping_delta_fx_N",
        "damping_delta_fy_N",
        "spool_delta_fx_N",
        "spool_delta_fy_N",
        "linear_total_delta_fx_N",
        "linear_total_delta_fy_N",
        "error_fx_N",
        "error_fy_N",
    ]
    source_path = source_data_dir / f"{stem}_source_data.csv"
    frame[source_columns].to_csv(source_path, index=False, encoding="utf-8")
    outputs.append(source_path)

    metadata = {
        "definition": (
            "delta_F_linear(t) = -K delta_x(t) - C delta_xdot(t) + "
            "Re{G_xv(Omega_w) xhat_v exp(i Omega_w t)}"
        ),
        "coefficient_source": (
            "continuous equation-based fixed-active-set harmonic linearization"
        ),
        "coefficient_derivation_uses_trajectory_differences": False,
        "comparison_source": "full nonlinear ALB thermal-inertia trajectory",
        "spool_source": (
            "recorded project PD -> second-order Moog response; no direct spool harmonic"
        ),
        "spool_phasor_use": (
            "The final-cycle first harmonic is an input representation only; "
            "it is not used to identify K, C, or dF/dxv."
        ),
        "validation_amplitude_um": float(frame["amplitude_um"].iloc[0]),
        "clearance_m": float(clearance_m),
        "controller": trajectory_summary["configuration"]["controller"],
        "servovalve": trajectory_summary["configuration"]["servovalve"],
        "strict_base_warmup": {
            row["direction"]: row["strict_base_warmup"]
            for row in trajectory_summary["direction_summaries"]
        },
        "direct_spool_harmonic_imposed": False,
        "points_per_direction": int(
            frame.groupby("direction", sort=False).size().iloc[0]
        ),
        "whirl_ratio_definition": "gamma = Omega_w / Omega_r",
        "whirl_ratio": float(configuration["whirl_ratio"]),
        "shaft_rotation_frequency_hz": float(
            configuration["shaft_rotation_frequency_hz"]
        ),
        "whirl_frequency_hz": float(configuration["whirl_frequency_hz"]),
        "whirl_omega_rad_s": float(configuration["whirl_omega_rad_s"]),
        "K_N_per_m": stiffness.tolist(),
        "C_N_s_per_m": damping.tolist(),
        "dF_dxv_N_per_nondim": {
            "real": spool_transfer.real.tolist(),
            "imag": spool_transfer.imag.tolist(),
        },
        "pd_servovalve_first_harmonic_audit": spool_audits,
        "pd_servovalve_chain_audit": control_chain_audit,
        "metrics": metrics,
        "nonlinear_trajectory_diagnostics": diagnostics,
        "nonlinear_validation_runtime_s": trajectory_summary["runtime_s"],
        "nonlinear_validation_model": trajectory_summary["validation_model"],
    }
    metrics_path = source_data_dir / f"{stem}_metrics.json"
    metrics_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    outputs.append(metrics_path)
    return outputs


def main() -> int:
    """Generate the comparison figure and its source-data package."""

    args = parse_args()
    stiffness, damping, spool_transfer, configuration = load_coefficients(
        args.coefficient_json
    )
    trajectory_summary = load_trajectory_summary(
        args.trajectory_json, args.amplitude_um
    )
    trajectory = pd.read_csv(args.trajectory_csv)
    selected = select_last_cycle(trajectory, args.amplitude_um)
    diagnostics = trajectory_diagnostics(
        trajectory.loc[
            np.isclose(
                trajectory["amplitude_um"].to_numpy(dtype=float),
                float(args.amplitude_um),
            )
        ]
    )
    comparison, spool_audits = add_linear_response(
        selected, stiffness, damping, spool_transfer
    )
    metrics = comparison_metrics(comparison)
    clearance_m = float(args.clearance_um) * 1.0e-6
    if clearance_m <= 0.0:
        raise ValueError("clearance-um must be positive")
    control_chain_audit = controller_chain_audit(
        selected, trajectory_summary, clearance_m
    )
    whirl_omega = float(configuration["whirl_omega_rad_s"])
    figure = make_figure(
        comparison,
        stiffness,
        damping,
        spool_transfer,
        whirl_omega,
        args.amplitude_um,
        spool_audits,
        metrics,
    )
    outputs = export_outputs(
        figure,
        comparison,
        metrics,
        stiffness,
        damping,
        spool_transfer,
        configuration,
        diagnostics,
        spool_audits,
        control_chain_audit,
        trajectory_summary,
        clearance_m,
        args.output_dir,
        args.source_data_dir,
        args.case_tag,
        args.dpi,
    )
    plt.close(figure)
    for path in outputs:
        print(path)
    for direction, values in metrics.items():
        print(
            f"{direction}: vector_relative_l2="
            f"{values['vector_relative_l2']:.8f}"
        )
        print(
            f"{direction}: spool_harmonic_relative_l2="
            f"{spool_audits[direction]['first_harmonic_reconstruction_relative_l2']:.8f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
