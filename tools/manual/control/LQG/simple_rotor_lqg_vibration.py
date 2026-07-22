"""Reproducible vibration test for the ALB standard LQG controller.

The test plant contains one planar second-order rotor mode in each lateral
direction. A rotating harmonic force excites the rotor at resonance, while
Gaussian displacement noise is added to the two sensor channels. The same
disturbance realization is used for the open-loop and controlled simulations.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

import control as cl
import matplotlib
import numpy as np

# Keep the diagnostic directly runnable from its nested test directory.
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ALB.control.lqg import ALBLQGController
from ALB.control.valve import moog_2nd_servovalve


@dataclass(frozen=True)
class SimpleRotorCaseConfig:
    """Physical, control, and simulation settings for the diagnostic case."""

    mass_kg: float = 10.0
    natural_frequency_hz: float = 50.0
    damping_ratio: float = 0.02
    shaft_frequency_hz: float = 50.0
    excitation_force_n: float = 100.0
    excitation_frequency_hz: float = 50.0
    measurement_noise_std_m: float = 2.0e-6
    actuator_force_gain_n: float = 3000.0
    dt_s: float = 2.0e-4
    duration_s: float = 1.0
    transient_s: float = 0.2
    random_seed: int = 20260714
    control_limit: float = 1.0


@dataclass
class SimulationTrace:
    """Time histories produced by one open-loop or closed-loop simulation."""

    time_s: np.ndarray
    displacement_m: np.ndarray
    measured_displacement_m: np.ndarray
    control: np.ndarray


@dataclass
class SimpleRotorCaseResult:
    """Complete comparison returned by :func:`run_simple_rotor_case`."""

    config: SimpleRotorCaseConfig
    open_loop: SimulationTrace
    closed_loop: SimulationTrace
    metrics: dict[str, float]


class SecondOrderPlanarRotor:
    """Minimal ROSS-compatible state-space rotor for LQG verification.

    The first two generalized coordinates are the lateral x/y displacements.
    Two stable auxiliary coordinates preserve the four-DOF-per-node layout
    assumed by the ALB rotor location mapping helpers.
    """

    ndof = 4

    def __init__(self, mass_kg: float, frequency_hz: float, damping_ratio: float):
        omega_n = 2.0 * np.pi * frequency_hz
        frequencies = np.array([omega_n, omega_n, 2.5 * omega_n, 2.5 * omega_n])
        damping = np.array([damping_ratio, damping_ratio, 0.2, 0.2])

        state_matrix = np.zeros((8, 8))
        state_matrix[:4, 4:] = np.eye(4)
        state_matrix[4:, :4] = -np.diag(frequencies**2)
        state_matrix[4:, 4:] = -np.diag(2.0 * damping * frequencies)

        input_matrix = np.zeros((8, 4))
        input_matrix[4:, :] = np.eye(4) / mass_kg
        output_matrix = np.eye(8)
        feedthrough_matrix = np.zeros((8, 4))
        self.system = cl.ss(
            state_matrix, input_matrix, output_matrix, feedthrough_matrix
        )

    def _lti(self, speed_rad_s: float):
        """Return the LTI model; speed is accepted for ROSS API compatibility."""
        del speed_rad_s
        return self.system


def _build_controller(config: SimpleRotorCaseConfig) -> ALBLQGController:
    """Build the current ALB LQG controller for the simple rotor plant."""
    rotor_model = SecondOrderPlanarRotor(
        config.mass_kg,
        config.natural_frequency_hz,
        config.damping_ratio,
    )
    rotor = SimpleNamespace(
        _rotor=rotor_model,
        _speed=2.0 * np.pi * config.shaft_frequency_hz,
    )

    controller = ALBLQGController(
        rotor,
        config.dt_s,
        config.shaft_frequency_hz,
        eso_enable=False,
        output_min=-config.control_limit,
        output_max=config.control_limit,
    )
    controller.add_bearing(
        moog_2nd_servovalve(config.dt_s),
        np.zeros((2, 2)),
        np.zeros((2, 2)),
        np.full(2, config.actuator_force_gain_n),
        act_node=0,
        sensor_node=0,
    )
    controller.add_unbalance_node(0)
    controller.build_plant()

    dimensions = controller.get_built_dimensions()
    state_weight = np.eye(dimensions["n_nom_states_phys"])
    state_weight[0, 0] = 1.0e9
    state_weight[1, 1] = 1.0e9
    state_weight[4, 4] = 1.0e4
    state_weight[5, 5] = 1.0e4

    controller.design_controller(
        state_weight,
        np.eye(dimensions["n_inputs"]),
        np.eye(dimensions["n_aug_states_phys"]),
        np.eye(dimensions["n_outputs"]) * 1.0e-8,
    )
    return controller


def _simulate(
    controller: ALBLQGController,
    config: SimpleRotorCaseConfig,
    time_s: np.ndarray,
    excitation_n: np.ndarray,
    sensor_noise_m: np.ndarray,
    controlled: bool,
) -> SimulationTrace:
    """Simulate the coupled rotor-valve plant using a zero-order hold model."""
    combined_input = np.hstack([controller.B_nom, controller.B_d])
    plant = cl.ss(
        controller.A_nom,
        combined_input,
        controller.C_nom,
        np.zeros((controller.C_nom.shape[0], combined_input.shape[1])),
    )
    plant_d = cl.c2d(plant, config.dt_s, method="zoh")

    state = np.zeros(plant_d.A.shape[0])
    displacement = np.zeros((time_s.size, 2))
    measured_displacement = np.zeros_like(displacement)
    control = np.zeros((time_s.size, 2))

    controller.init()
    for index, time_value in enumerate(time_s):
        true_output = np.asarray(plant_d.C @ state).reshape(-1)
        measured_output = true_output + sensor_noise_m[index]

        if controlled:
            controller.input(time_value, measured_output)
            controller.evaluate()
            command = controller.output()
        else:
            command = np.zeros(2)

        displacement[index] = true_output
        measured_displacement[index] = measured_output
        control[index] = command
        plant_input = np.concatenate([command, excitation_n[index]])
        state = np.asarray(plant_d.A @ state + plant_d.B @ plant_input).reshape(-1)

    return SimulationTrace(time_s, displacement, measured_displacement, control)


def _response_metrics(
    trace: SimulationTrace, analysis_mask: np.ndarray
) -> tuple[float, float]:
    """Return radial displacement RMS and peak values over the analysis window."""
    radial_displacement = np.linalg.norm(trace.displacement_m, axis=1)
    selected = radial_displacement[analysis_mask]
    return float(np.sqrt(np.mean(selected**2))), float(np.max(selected))


def run_simple_rotor_case(
    config: SimpleRotorCaseConfig | None = None,
) -> SimpleRotorCaseResult:
    """Run matched open-loop and LQG-controlled simulations."""
    config = config or SimpleRotorCaseConfig()
    sample_count = int(round(config.duration_s / config.dt_s))
    time_s = np.arange(sample_count, dtype=float) * config.dt_s

    excitation_angle = 2.0 * np.pi * config.excitation_frequency_hz * time_s
    excitation_n = config.excitation_force_n * np.column_stack(
        [np.sin(excitation_angle), np.cos(excitation_angle)]
    )
    random_generator = np.random.default_rng(config.random_seed)
    sensor_noise_m = random_generator.normal(
        0.0, config.measurement_noise_std_m, size=(sample_count, 2)
    )

    controller = _build_controller(config)
    open_loop = _simulate(
        controller,
        config,
        time_s,
        excitation_n,
        sensor_noise_m,
        controlled=False,
    )
    closed_loop = _simulate(
        controller,
        config,
        time_s,
        excitation_n,
        sensor_noise_m,
        controlled=True,
    )

    analysis_mask = time_s >= config.transient_s
    open_rms_m, open_peak_m = _response_metrics(open_loop, analysis_mask)
    closed_rms_m, closed_peak_m = _response_metrics(closed_loop, analysis_mask)
    attenuation_fraction = 1.0 - closed_rms_m / open_rms_m
    maximum_control = float(np.max(np.abs(closed_loop.control)))

    metrics = {
        "open_loop_radial_rms_m": open_rms_m,
        "open_loop_radial_peak_m": open_peak_m,
        "closed_loop_radial_rms_m": closed_rms_m,
        "closed_loop_radial_peak_m": closed_peak_m,
        "rms_attenuation_fraction": attenuation_fraction,
        "rms_attenuation_percent": attenuation_fraction * 100.0,
        "maximum_absolute_control": maximum_control,
    }
    return SimpleRotorCaseResult(config, open_loop, closed_loop, metrics)


def write_case_artifacts(result: SimpleRotorCaseResult, output_dir: Path) -> None:
    """Write a machine-readable summary and a compact response plot."""
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "case": "second_order_planar_rotor_standard_lqg",
        "configuration": asdict(result.config),
        "metrics": result.metrics,
        "units": {
            "displacement": "m",
            "force": "N",
            "frequency": "Hz",
            "rotor_speed_passed_to_lti": "rad/s",
            "time": "s",
        },
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, ensure_ascii=False, indent=2)
        file_handle.write("\n")

    time_s = result.open_loop.time_s
    radial_open_mm = 1.0e3 * np.linalg.norm(
        result.open_loop.displacement_m, axis=1
    )
    radial_closed_mm = 1.0e3 * np.linalg.norm(
        result.closed_loop.displacement_m, axis=1
    )

    figure, axes = plt.subplots(2, 1, figsize=(9.0, 6.5), sharex=True)
    axes[0].plot(time_s, radial_open_mm, label="Open loop", linewidth=1.2)
    axes[0].plot(time_s, radial_closed_mm, label="LQG controlled", linewidth=1.2)
    axes[0].axvline(
        result.config.transient_s,
        color="0.45",
        linestyle="--",
        linewidth=0.9,
        label="RMS window start",
    )
    axes[0].set_ylabel("Radial displacement (mm)")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper right")

    axes[1].plot(
        time_s, result.closed_loop.control[:, 0], label="Control x", linewidth=1.0
    )
    axes[1].plot(
        time_s, result.closed_loop.control[:, 1], label="Control y", linewidth=1.0
    )
    axes[1].axhline(
        result.config.control_limit, color="0.45", linestyle="--", linewidth=0.8
    )
    axes[1].axhline(
        -result.config.control_limit, color="0.45", linestyle="--", linewidth=0.8
    )
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Control command")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="upper right")

    figure.suptitle("ALB LQG vibration test: noisy resonant excitation")
    figure.tight_layout()
    figure.savefig(output_dir / "response.png", dpi=180, bbox_inches="tight")
    plt.close(figure)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output" / "simple_rotor_lqg",
        help="Directory for summary.json and response.png.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the default diagnostic case and print the resulting metrics."""
    arguments = _parse_args()
    result = run_simple_rotor_case()
    write_case_artifacts(result, arguments.output_dir)
    print(json.dumps(result.metrics, indent=2))
    print(f"Artifacts: {arguments.output_dir.resolve()}")


if __name__ == "__main__":
    main()
