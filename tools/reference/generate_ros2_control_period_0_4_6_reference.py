"""Freeze the new ALB 0.4.6 ROS2 and control-period behavior.

Unlike ``generate_coupling_default_path_0_4_6_reference.py`` (frozen on the
unmodified 0.4.5 source), this reference is generated from the finished 0.4.6
implementation. It pins the new algorithms so later refactors cannot change
them silently (ADR-0007 rules 5 and 6, ADR-0009):

* ROS2 with a liquid-film bearing and with an active PID bearing sampled every
  four steps;
* the staggered integrator with the same sampled active PID bearing;
* ROS2 with an analytic hardening bearing on the coupling runtime;
* an automatic time-step adjustment (requested step not dividing the
  controller period) and its recorded metadata.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Callable
import warnings

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import ALB  # noqa: E402
from ALB.contracts import (  # noqa: E402
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    LifecycleState,
    StepContext,
    UnitSystem,
    result_snapshot,
)
from ALB.core.time import TimeIterDt  # noqa: E402
from ALB.dynamics.bindings import CoupledBearingBinding  # noqa: E402
from ALB.dynamics.coupling import _RotorBearingStepRuntime  # noqa: E402
from ALB.dynamics.ros2 import Ros2Options  # noqa: E402
from ALB.dynamics.rotor import RossRotor  # noqa: E402
from tools.reference.generate_coupling_default_path_0_4_6_reference import (  # noqa: E402
    LOADS,
    PID_CONTROL,
    TIME_STEP,
    SinglePlant,
    _version,
    active_spec,
    liquid_film_spec,
)


JSON_PATH = (
    REPOSITORY_ROOT / "refs" / "ros2_control_period_0_4_6_reference_v1.json"
)
NPZ_PATH = (
    REPOSITORY_ROOT / "refs" / "ros2_control_period_0_4_6_reference_v1.npz"
)
CONTROL_STEPS = 4


def _plain(value: Any) -> Any:
    """Return JSON-compatible primitives for nested metadata."""

    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _simulate(
    config: ALB.SimulationConfig,
) -> tuple[dict[str, Any], dict[str, np.ndarray], Any]:
    simulation = ALB.build_simulation(config)
    result = simulation.run()
    arrays = {
        "time": np.asarray(result.time, dtype=float),
        "rotor_displacement": np.asarray(result.rotor_displacement, dtype=float),
        "rotor_velocity": np.asarray(result.rotor_velocity, dtype=float),
        "bearing_force": np.asarray(result.bearing_force, dtype=float),
        "rotor_final_state": np.asarray(config.rotor.current_state(), dtype=float),
    }
    metadata = {"result_metadata": _plain(dict(result.metadata))}
    return metadata, arrays, simulation


def run_ros2_liquid_film() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """ROS2 with the dimensional liquid-film bearing of the default case."""

    rotor = RossRotor(SinglePlant(), speed=2.0 * np.pi * 50.0, dt=TIME_STEP)
    metadata, arrays, _ = _simulate(
        ALB.SimulationConfig(
            rotor=rotor,
            mounts=(ALB.BearingMount(ALB.BearingConfig(liquid_film_spec()), 0),),
            time_step=TIME_STEP,
            steps=60,
            loads=LOADS,
            integrator="ros2",
        )
    )
    return metadata, arrays


def _sampled_active(integrator: str) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    spec = active_spec(
        dict(PID_CONTROL, control_period=CONTROL_STEPS * TIME_STEP)
    )
    rotor = RossRotor(SinglePlant(), speed=2.0 * np.pi * 50.0, dt=TIME_STEP)
    metadata, arrays, simulation = _simulate(
        ALB.SimulationConfig(
            rotor=rotor,
            mounts=(ALB.BearingMount(ALB.BearingConfig(spec), 0),),
            time_step=TIME_STEP,
            steps=24,
            loads=LOADS,
            integrator=integrator,
        )
    )
    controller = simulation._coupling.bindings[0].bearing._controller
    arrays["controller_times"] = np.asarray(
        controller.results["t"], dtype=float
    )
    arrays["controller_outputs"] = np.vstack(
        [np.asarray(item, dtype=float) for item in controller.results["output"]]
    )
    metadata["bearing_spec"] = spec
    return metadata, arrays


def run_ros2_active_pid_sampled() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """ROS2 with an active PID bearing sampled every four steps."""

    return _sampled_active("ros2")


def run_staggered_active_pid_sampled() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Staggered integrator with the same sampled active PID bearing."""

    return _sampled_active("staggered")


class _HardeningBearing:
    """Analytic bearing ``F = -k0 (1 + a (r/s)^2) x - c v`` (no lifecycle state)."""

    input_dto_type = BearingInput
    unit_system = UnitSystem.DIMENSIONAL
    node_link = 0
    lifecycle_state = LifecycleState.READY
    convergence_status = ConvergenceStatus(0.0, True)

    def __init__(self) -> None:
        self._dto: Any = None
        self._output: Any = None

    @staticmethod
    def law(displacement: np.ndarray, velocity: np.ndarray) -> np.ndarray:
        ratio = float(displacement @ displacement) / (6.0e-4) ** 2
        return -3.0e4 * (1.0 + 8.0 * ratio) * displacement - 40.0 * velocity

    def _reset_for_owner(self) -> None:
        self._dto = None
        self._output = None

    def input(self, dto: Any) -> None:
        self._dto = dto

    def evaluate(self) -> None:
        self._output = BearingOutput(
            self.probe_force(self._dto), self._dto.time, self.unit_system
        )

    def output(self) -> Any:
        return self._output

    def step(self, dto: Any) -> Any:
        self.input(dto)
        self.evaluate()
        return self.output()

    def probe_force(self, dto: Any) -> np.ndarray:
        return self.law(
            np.asarray(dto.displacement, dtype=float),
            np.asarray(dto.velocity, dtype=float),
        )

    def result_snapshot(self) -> Any:
        return result_snapshot({"force": self._output.force}, {})

    def failure_snapshot(self) -> Any:
        return result_snapshot({}, {})

    def diagnostic_snapshot(self) -> Any:
        return result_snapshot({}, {})


class _AnalyticPlant(SinglePlant):
    """Lighter plant matching the analytic-bearing unit tests."""

    def __init__(self) -> None:
        super().__init__(mass=2.0, stiffness=2.0e4, damping=20.0)

    def matrices(self) -> dict[str, np.ndarray]:
        return {
            "M": np.diag([self.mass, self.mass, 0.01, 0.01]),
            "K": np.diag([self.stiffness, 1.3 * self.stiffness, 50.0, 50.0]),
            "C": np.diag([self.damping, self.damping, 0.1, 0.1]),
        }


def run_ros2_analytic_hardening() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """ROS2 on the coupling runtime with a nonlinear analytic bearing."""

    time_step = 2.5e-4
    steps = 400
    rotor = RossRotor(_AnalyticPlant(), speed=1.0, dt=time_step)
    runtime = _RotorBearingStepRuntime(
        rotor,
        TimeIterDt(time_step, steps),
        CoupledBearingBinding(_HardeningBearing(), node_link=0),
        integrator="ros2",
        ros2_options=Ros2Options(),
    )
    runtime.add_static_force(np.array([3.0, -20.0]), 0)
    runtime.add_unbalance(node_link=0, phase=0.3, m=2.0e-3, freq=12.0, e=1.0e-2)
    runtime._reset_for_owner()
    forces = [np.asarray(runtime.output().values["bearing_force"], dtype=float)]
    for index in range(1, steps + 1):
        snapshot = runtime.advance(
            StepContext(index, time_step * index, time_step, UnitSystem.DIMENSIONAL)
        )
        forces.append(np.asarray(snapshot.values["bearing_force"], dtype=float))
    arrays = {
        "rotor_state_history": np.asarray(rotor._xouts, dtype=float),
        "bearing_force": np.asarray(forces, dtype=float),
    }
    return {"diagnostics": _plain(runtime._ros2.diagnostics())}, arrays


def run_adjusted_time_step() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Requested step 3e-5 s with Ts = 1e-4 s: adjusted to 2.5e-5 s, m = 4."""

    requested = 3.0e-5
    spec = active_spec(dict(PID_CONTROL, control_period=1.0e-4), requested)
    rotor = RossRotor(SinglePlant(), speed=2.0 * np.pi * 50.0, dt=requested)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = ALB.SimulationConfig(
            rotor=rotor,
            mounts=(ALB.BearingMount(ALB.BearingConfig(spec), 0),),
            time_step=requested,
            steps=10,
            loads=LOADS,
        )
    metadata, arrays, _ = _simulate(config)
    metadata["warnings"] = [
        {"category": item.category.__name__, "message": str(item.message)}
        for item in caught
    ]
    return metadata, arrays


CASES: dict[str, Callable[[], tuple[dict[str, Any], dict[str, np.ndarray]]]] = {
    "ros2_liquid_film": run_ros2_liquid_film,
    "ros2_active_pid_sampled": run_ros2_active_pid_sampled,
    "staggered_active_pid_sampled": run_staggered_active_pid_sampled,
    "ros2_analytic_hardening": run_ros2_analytic_hardening,
    "adjusted_time_step": run_adjusted_time_step,
}


def capture_case(name: str) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Run one named case and prefix its arrays with the case name."""

    metadata, arrays = CASES[name]()
    return metadata, {f"{name}.{key}": value for key, value in arrays.items()}


def build_reference() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Build the JSON/NPZ payload from the finished 0.4.6 implementation."""

    metadata_cases: dict[str, Any] = {}
    arrays: dict[str, np.ndarray] = {}
    for name in CASES:
        metadata, case_arrays = capture_case(name)
        metadata_cases[name] = {
            **metadata,
            "arrays": {
                key: {"shape": list(value.shape), "dtype": str(value.dtype)}
                for key, value in case_arrays.items()
            },
        }
        arrays.update(case_arrays)
    payload = {
        "schema": "alb.ros2-control-period-0.4.6-reference.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, text=True
        ).strip(),
        "purpose": (
            "Freeze the new 0.4.6 ROS2 integrator and sampled-control "
            "behavior generated from the finished implementation."
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "alb": ALB.__version__,
            "numpy": np.__version__,
            "scipy": _version("scipy"),
            "control": _version("control"),
            "slycot": _version("slycot"),
            "pandas": _version("pandas"),
            "ross-rotordynamics": _version("ross-rotordynamics"),
            "scikit-fem": _version("scikit-fem"),
        },
        "time_step": TIME_STEP,
        "control_steps": CONTROL_STEPS,
        "cases": metadata_cases,
        "comparison": {
            "arrays": "np.testing.assert_array_equal",
            "scope": (
                "exact equality in the recorded environment; other platforms "
                "may differ at floating-point round-off level"
            ),
        },
    }
    return payload, arrays


def main() -> int:
    """Write the JSON/NPZ reference pair exactly once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", type=Path, default=JSON_PATH)
    parser.add_argument("--npz", type=Path, default=NPZ_PATH)
    args = parser.parse_args()
    if not args.force and (args.json.exists() or args.npz.exists()):
        raise FileExistsError("reference exists; pass --force only intentionally")
    payload, arrays = build_reference()
    args.json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    np.savez(args.npz, **arrays)
    print(args.json)
    print(args.npz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
