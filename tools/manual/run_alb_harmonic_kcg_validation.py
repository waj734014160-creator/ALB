"""Run a PD-controlled full nonlinear ALB trajectory validation.

The journal follows a prescribed circular orbit.  A real project PID controller
configured as PD drives the project second-order Moog servovalves, so the spool
motion is a controller response rather than an imposed harmonic input.  The
same recorded spool trajectory can then be used by the independently derived
K, C, and dF/dxv reconstruction.  This script writes only nonlinear transient
NCP results and controller/servovalve states; it never derives coefficients
from trajectory differences.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Allow direct execution from tools/manual without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ALB.config import PIDConfig
from ALB.control.pid import PID
from ALB.control.valve import moog_2nd_servovalve


def parse_args() -> argparse.Namespace:
    """Parse validation-grid, controller, servovalve, and output controls."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--diagnostic-root",
        type=Path,
        required=True,
        help="Directory containing the equation-linearization helper modules.",
    )
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--points", type=int, default=16)
    parser.add_argument("--cycles", type=int, default=4)
    parser.add_argument("--amplitude-um", type=float, default=5.0)
    parser.add_argument("--whirl-ratio", type=float, default=1.0)
    parser.add_argument("--kp", type=float, default=0.3)
    parser.add_argument("--ki", type=float, default=0.0)
    parser.add_argument("--kd", type=float, default=0.5)
    parser.add_argument(
        "--sensor-angles-deg",
        type=float,
        nargs=2,
        default=(45.0, 135.0),
    )
    parser.add_argument("--servo-natural-frequency-hz", type=float, default=166.0)
    parser.add_argument("--servo-zeta", type=float, default=0.7)
    parser.add_argument("--controller-warmup-steps", type=int, default=64)
    parser.add_argument(
        "--directions",
        nargs="+",
        choices=("forward", "reverse"),
        default=("forward", "reverse"),
    )
    return parser.parse_args()


def load_diagnostic_modules(root: Path):
    """Import the previously verified analytic and transient NCP helpers."""

    resolved = root.resolve()
    required = (
        "analytic_harmonic_linearization_temp.py",
        "cavitation_moving_boundary_harmonic.py",
        "thermal_inertia_cavitation_harmonic.py",
    )
    missing = [name for name in required if not (resolved / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Diagnostic root {resolved} is missing: {', '.join(missing)}"
        )
    if str(resolved) not in sys.path:
        sys.path.insert(0, str(resolved))
    analytic = importlib.import_module("analytic_harmonic_linearization_temp")
    # Reuse only the refined steady-NCP builder from this historical module.
    # The moving-active-set linear trajectory routine is never called here.
    ncp_builder = importlib.import_module(
        "cavitation_moving_boundary_harmonic"
    )
    thermal = importlib.import_module("thermal_inertia_cavitation_harmonic")
    return analytic, ncp_builder, thermal


def harmonic_motion(
    analytic,
    amplitude_um: float,
    direction: int,
    phase: float,
    whirl_omega: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build the prescribed circular journal displacement and velocity."""

    amplitude_m = float(amplitude_um) * 1.0e-6
    cosine = np.cos(phase)
    sine = np.sin(phase)
    displacement = np.array(
        [amplitude_m * cosine, direction * amplitude_m * sine], dtype=float
    )
    velocity = np.array(
        [
            -amplitude_m * whirl_omega * sine,
            direction * amplitude_m * whirl_omega * cosine,
        ],
        dtype=float,
    )
    delta_input = np.zeros(len(analytic.INPUT_NAMES), dtype=float)
    delta_input[:2] = displacement / analytic.CLEARANCE_M
    delta_input[2:4] = velocity / (
        analytic.CLEARANCE_M * analytic.OMEGA_SHAFT
    )
    return delta_input, displacement, velocity


def sensor_matrix(sensor_angles_deg: np.ndarray) -> np.ndarray:
    """Return the two-channel displacement sensor projection matrix."""

    angles_rad = np.deg2rad(np.asarray(sensor_angles_deg, dtype=float))
    return np.column_stack((np.cos(angles_rad), np.sin(angles_rad)))


def scalar_output(value) -> float:
    """Convert a scalar-like model output to a Python float."""

    values = np.asarray(value, dtype=float).reshape(-1)
    if values.size != 1:
        raise ValueError(f"Expected one servovalve output, received {values.size}")
    return float(values[0])


def build_warmed_pd_servo(
    analytic,
    dt: float,
    kp: float,
    ki: float,
    kd: float,
    sensor_angles_deg: np.ndarray,
    servo_natural_frequency_hz: float,
    servo_zeta: float,
    warmup_steps: int,
) -> tuple[PID, list, dict]:
    """Create and settle the project PD and Moog models at the strict base."""

    sensors = sensor_matrix(sensor_angles_deg)
    expected_command = float(kp) * (sensors @ analytic.CENTER_NONDIM)
    base_spool = np.asarray(analytic.SPOOL_NONDIM, dtype=float)
    if not np.allclose(expected_command, base_spool, rtol=0.0, atol=1.0e-12):
        raise ValueError(
            "Controller static output does not match the coefficient base spool: "
            f"expected={expected_command.tolist()}, base={base_spool.tolist()}"
        )

    controller = PID(
        PIDConfig(
            dt=float(dt),
            kp=float(kp),
            ki=float(ki),
            kd=float(kd),
            freq=float(analytic.SHAFT_FREQ_HZ),
            sensor_angles=np.asarray(sensor_angles_deg, dtype=float),
        )
    )
    controller.init()
    tw = 1.0 / (2.0 * np.pi * float(servo_natural_frequency_hz))
    valves = [
        moog_2nd_servovalve(float(dt), tw=tw, zeta=float(servo_zeta))
        for _ in range(2)
    ]
    for valve in valves:
        valve.init()

    command = np.zeros(2, dtype=float)
    spool = np.zeros(2, dtype=float)
    for step in range(int(warmup_steps)):
        t = step * dt
        controller.input(t, analytic.CENTER_NONDIM)
        controller.evaluate()
        command = np.asarray(controller.output(), dtype=float).reshape(2)
        for index, valve in enumerate(valves):
            valve.input(t, command[index])
            spool[index] = scalar_output(valve.output())

    warmup_error = spool - base_spool
    if not np.allclose(spool, base_spool, rtol=0.0, atol=1.0e-8):
        raise RuntimeError(
            "Servovalve warm-up did not reach the coefficient base spool: "
            f"actual={spool.tolist()}, base={base_spool.tolist()}"
        )
    audit = {
        "expected_static_command": expected_command,
        "final_controller_command": command.copy(),
        "final_spool": spool.copy(),
        "base_spool": base_spool.copy(),
        "warmup_error": warmup_error.copy(),
        "warmup_steps": int(warmup_steps),
        "warmup_duration_s": float(warmup_steps * dt),
    }
    return controller, valves, audit


def first_harmonic_audit(
    phases: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return mean, complex first-harmonic phasor, and residual ratio."""

    values = np.asarray(values, dtype=float)
    mean = np.mean(values, axis=0)
    centered = values - mean
    carrier = np.exp(-1j * np.asarray(phases, dtype=float))
    phasor = (2.0 / len(phases)) * np.sum(centered * carrier[:, None], axis=0)
    reconstructed = np.real(
        np.exp(1j * np.asarray(phases, dtype=float))[:, None]
        * phasor[None, :]
    )
    error = relative_l2(centered, reconstructed)
    return mean, phasor, error


def complex_vector_payload(values: np.ndarray) -> dict:
    """Serialize a two-channel complex vector without implicit conversion."""

    vector = np.asarray(values, dtype=complex).reshape(2)
    return {
        "real": vector.real.tolist(),
        "imag": vector.imag.tolist(),
        "magnitude": np.abs(vector).tolist(),
        "phase_deg": np.rad2deg(np.angle(vector)).tolist(),
    }


def relative_l2(reference: np.ndarray, candidate: np.ndarray) -> float:
    """Return a protected relative L2 difference."""

    denominator = max(float(np.linalg.norm(reference)), np.finfo(float).tiny)
    return float(np.linalg.norm(candidate - reference) / denominator)


def run_direction(
    analytic,
    dynamic_pads,
    amplitude_um: float,
    direction_name: str,
    points: int,
    cycles: int,
    whirl_ratio: float,
    whirl_frequency_hz: float,
    whirl_omega: float,
    dt: float,
    kp: float,
    ki: float,
    kd: float,
    sensor_angles_deg: np.ndarray,
    servo_natural_frequency_hz: float,
    servo_zeta: float,
    warmup_steps: int,
) -> tuple[list[dict], dict]:
    """Advance one direction with PD/servo and nonlinear-state continuation."""

    direction = 1 if direction_name == "forward" else -1
    total_steps = int(points * cycles)
    controller, valves, base_audit = build_warmed_pd_servo(
        analytic,
        dt,
        kp,
        ki,
        kd,
        sensor_angles_deg,
        servo_natural_frequency_hz,
        servo_zeta,
        warmup_steps,
    )
    previous_temperature = [
        pad.system.base_state[pad.n : 2 * pad.n].copy()
        for pad in dynamic_pads
    ]
    previous_state = [pad.system.base_state.copy() for pad in dynamic_pads]
    previous_mask = [
        pad.system.base_pressurized.copy() for pad in dynamic_pads
    ]
    rows: list[dict] = []
    previous_cycle_force = None
    cycle_repeat = np.nan

    for step in range(total_steps):
        phase = 2.0 * np.pi * (step + 1) / points
        delta_input, displacement, velocity = harmonic_motion(
            analytic,
            amplitude_um,
            direction,
            phase,
            whirl_omega,
        )
        displacement_nondim = analytic.CENTER_NONDIM + delta_input[:2]
        t = (warmup_steps + step) * dt
        controller.input(t, displacement_nondim)
        controller.evaluate()
        controller_command = np.asarray(
            controller.output(), dtype=float
        ).reshape(2)
        spool = np.zeros(2, dtype=float)
        for index, valve in enumerate(valves):
            valve.input(t, controller_command[index])
            spool[index] = scalar_output(valve.output())
        delta_spool = spool - analytic.SPOOL_NONDIM
        delta_input[4:6] = delta_spool
        input_vector = analytic.BASE_INPUT + delta_input
        force_nondim = np.zeros(2, dtype=float)
        max_merit = 0.0
        max_iterations = 0
        switched_nodes = 0
        converged = True

        for pad_index, dynamic_pad in enumerate(dynamic_pads):
            nonlinear = dynamic_pad.solve_nonlinear_step(
                input_vector,
                previous_temperature[pad_index],
                previous_state[pad_index],
                previous_mask[pad_index],
            )
            previous_state[pad_index] = nonlinear["state"].copy()
            previous_mask[pad_index] = nonlinear["pressurized"].copy()
            previous_temperature[pad_index] = nonlinear["state"][
                dynamic_pad.n : 2 * dynamic_pad.n
            ].copy()
            force_nondim += dynamic_pad.pad.force_operator @ (
                nonlinear["state"][: dynamic_pad.n]
                - dynamic_pad.system.base_state[: dynamic_pad.n]
            )
            max_merit = max(max_merit, float(nonlinear["merit_l2"]))
            max_iterations = max(max_iterations, int(nonlinear["iterations"]))
            switched_nodes += int(
                np.count_nonzero(
                    nonlinear["pressurized"]
                    ^ dynamic_pad.system.base_pressurized
                )
            )
            converged &= bool(nonlinear["converged"])

        force = force_nondim * analytic.FORCE_SCALE_N
        rows.append(
            {
                "amplitude_um": float(amplitude_um),
                "whirl_ratio": float(whirl_ratio),
                "whirl_frequency_hz": float(whirl_frequency_hz),
                "direction": direction_name,
                "direction_sign": direction,
                "step": step,
                "cycle": step // points,
                "phase_index": (step + 1) % points,
                "phase_rad": phase % (2.0 * np.pi),
                "time_s": t,
                "dx_m": displacement[0],
                "dy_m": displacement[1],
                "vx_m_per_s": velocity[0],
                "vy_m_per_s": velocity[1],
                "controller_kp": float(kp),
                "controller_ki": float(ki),
                "controller_kd": float(kd),
                "sensor_angle_x_deg": float(sensor_angles_deg[0]),
                "sensor_angle_y_deg": float(sensor_angles_deg[1]),
                "servo_natural_frequency_hz": float(
                    servo_natural_frequency_hz
                ),
                "servo_zeta": float(servo_zeta),
                "controller_u_x": controller_command[0],
                "controller_u_y": controller_command[1],
                "xv_x_nondim": spool[0],
                "xv_y_nondim": spool[1],
                "dsx_nondim": delta_spool[0],
                "dsy_nondim": delta_spool[1],
                "controller_saturated": bool(
                    np.any(np.abs(controller_command) >= 1.0 - 1.0e-12)
                ),
                "servovalve_saturated": bool(
                    np.any(np.abs(spool) >= 1.0 - 1.0e-12)
                ),
                "nonlinear_delta_fx_N": force[0],
                "nonlinear_delta_fy_N": force[1],
                "nonlinear_switched_nodes": switched_nodes,
                "maximum_nonlinear_merit_l2": max_merit,
                "maximum_nonlinear_iterations": max_iterations,
                "nonlinear_converged": converged,
            }
        )

        progress_interval = max(1, points // 4)
        if (step + 1) % progress_interval == 0:
            print(
                "trajectory_progress "
                f"direction={direction_name} step={step + 1}/{total_steps} "
                f"switches={switched_nodes} merit={max_merit:.3e} "
                f"iterations={max_iterations} converged={converged}",
                flush=True,
            )

        if (step + 1) % points == 0:
            current_cycle_force = np.asarray(
                [
                    [row["nonlinear_delta_fx_N"], row["nonlinear_delta_fy_N"]]
                    for row in rows[-points:]
                ],
                dtype=float,
            )
            if previous_cycle_force is not None:
                cycle_repeat = relative_l2(
                    previous_cycle_force, current_cycle_force
                )
            previous_cycle_force = current_cycle_force

    final_rows = rows[-points:]
    final_phases = np.asarray([row["phase_rad"] for row in final_rows])
    final_spool_delta = np.asarray(
        [[row["dsx_nondim"], row["dsy_nondim"]] for row in final_rows]
    )
    spool_mean, spool_phasor, spool_harmonic_error = first_harmonic_audit(
        final_phases, final_spool_delta
    )
    summary = {
        "direction": direction_name,
        "cycle_repeat_relative_l2": cycle_repeat,
        "maximum_nonlinear_merit_l2": max(
            row["maximum_nonlinear_merit_l2"] for row in final_rows
        ),
        "maximum_nonlinear_iterations": max(
            row["maximum_nonlinear_iterations"] for row in final_rows
        ),
        "maximum_nonlinear_switched_nodes": max(
            row["nonlinear_switched_nodes"] for row in final_rows
        ),
        "all_final_cycle_steps_converged": all(
            row["nonlinear_converged"] for row in final_rows
        ),
        "controller_saturated_in_final_cycle": any(
            row["controller_saturated"] for row in final_rows
        ),
        "servovalve_saturated_in_final_cycle": any(
            row["servovalve_saturated"] for row in final_rows
        ),
        "maximum_abs_controller_command_final_cycle": np.max(
            np.abs(
                np.asarray(
                    [
                        [row["controller_u_x"], row["controller_u_y"]]
                        for row in final_rows
                    ]
                )
            ),
            axis=0,
        ),
        "maximum_abs_spool_delta_final_cycle": np.max(
            np.abs(final_spool_delta), axis=0
        ),
        "spool_delta_mean_final_cycle": spool_mean,
        "spool_delta_first_harmonic": complex_vector_payload(spool_phasor),
        "spool_first_harmonic_reconstruction_relative_l2": spool_harmonic_error,
        "strict_base_warmup": base_audit,
    }
    return rows, summary


def main() -> int:
    """Run the nonlinear validation and persist traceable source data."""

    args = parse_args()
    if args.points < 4 or args.cycles < 1:
        raise ValueError("points must be >= 4 and cycles must be >= 1")
    if args.amplitude_um <= 0.0:
        raise ValueError("The journal orbit amplitude must be positive")
    if args.kp < 0.0 or args.ki != 0.0 or args.kd < 0.0:
        raise ValueError("Use nonnegative kp/kd and ki=0 for this PD validation")
    if args.servo_natural_frequency_hz <= 0.0 or args.servo_zeta <= 0.0:
        raise ValueError("Servovalve frequency and damping must be positive")
    if args.controller_warmup_steps < 2:
        raise ValueError("controller-warmup-steps must be >= 2")
    analytic, ncp_builder, thermal = load_diagnostic_modules(
        args.diagnostic_root
    )
    started = time.perf_counter()
    whirl_ratio = float(args.whirl_ratio)
    whirl_frequency_hz = analytic.whirl_frequency_hz(whirl_ratio)
    whirl_omega = analytic.whirl_omega_rad_s(whirl_ratio)
    dt = 1.0 / (whirl_frequency_hz * args.points)
    systems, base_audits, physical_force, refined_force = (
        ncp_builder.build_refined_systems()
    )
    if not all(row["converged"] for row in base_audits):
        raise RuntimeError("Steady NCP base refinement failed")

    all_rows: list[dict] = []
    direction_summaries = []
    for direction_name in args.directions:
        dynamic_pads = [
            thermal.DynamicPadSystem(system, dt) for system in systems
        ]
        rows, summary = run_direction(
            analytic,
            dynamic_pads,
            args.amplitude_um,
            direction_name,
            args.points,
            args.cycles,
            whirl_ratio,
            whirl_frequency_hz,
            whirl_omega,
            dt,
            args.kp,
            args.ki,
            args.kd,
            np.asarray(args.sensor_angles_deg, dtype=float),
            args.servo_natural_frequency_hz,
            args.servo_zeta,
            args.controller_warmup_steps,
        )
        all_rows.extend(rows)
        direction_summaries.append(summary)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_csv(args.output_csv, index=False, encoding="utf-8")
    payload = {
        "status": "complete",
        "validation_model": "full nonlinear transient ALB NCP with thermal inertia",
        "linear_force_columns_generated": False,
        "coefficients_derived_from_trajectory": False,
        "moving_active_set_linearization_used": False,
        "direct_spool_harmonic_imposed": False,
        "spool_input_source": "project PID configured as PD -> project second-order Moog servovalve",
        "input_definition": {
            "journal": "[A*cos(theta), d*A*sin(theta)]",
            "spool": "actual PD/servovalve response; no prescribed spool harmonic",
            "direction_sign_d": "forward=+1, reverse=-1",
        },
        "configuration": {
            "amplitude_um": float(args.amplitude_um),
            "whirl_ratio": whirl_ratio,
            "whirl_frequency_hz": whirl_frequency_hz,
            "whirl_omega_rad_s": whirl_omega,
            "points_per_cycle": int(args.points),
            "cycles": int(args.cycles),
            "dt_s": dt,
            "directions": list(args.directions),
            "controller": {
                "type": "PD",
                "kp": float(args.kp),
                "ki": float(args.ki),
                "kd": float(args.kd),
                "sensor_angles_deg": list(args.sensor_angles_deg),
                "frequency_hz_for_nondimensional_derivative": float(
                    analytic.SHAFT_FREQ_HZ
                ),
            },
            "servovalve": {
                "model": "project second-order Moog core",
                "natural_frequency_hz": float(args.servo_natural_frequency_hz),
                "zeta": float(args.servo_zeta),
                "unit_dc_gain": True,
            },
            "controller_warmup_steps": int(args.controller_warmup_steps),
        },
        "base": {
            "pad_audits": base_audits,
            "physical_solver_force_N": (
                physical_force * analytic.FORCE_SCALE_N
            ),
            "refined_NCP_force_N": refined_force * analytic.FORCE_SCALE_N,
            "coefficient_base_spool_nondim": analytic.SPOOL_NONDIM,
        },
        "direction_summaries": direction_summaries,
        "runtime_s": time.perf_counter() - started,
        "trajectory_csv": str(args.output_csv.resolve()),
    }
    args.output_json.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=thermal.json_default,
        ),
        encoding="utf-8",
    )
    print(f"trajectory={args.output_csv.resolve()}")
    print(f"summary={args.output_json.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
