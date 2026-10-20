"""Freeze the pre-0.4.6 default rotor-bearing coupling path.

The reference is generated on the unmodified 0.4.5 source (``df7336f``) before
ALB 0.4.6 adds sampled control periods and the optional ROS2 integrator. It
captures the default path only: the staggered integrator, controllers updated
on every simulation step, and one shared ``time_step`` for every component.

Every case is deterministic and uses only small analytic or ROSS plants, so the
regression test can rebuild the same inputs through the public API and require
exact array equality.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import ALB  # noqa: E402
from ALB.config import FuzzyPIDConfig, PIDConfig  # noqa: E402
from ALB.control.fuzzy import FuzzyPID  # noqa: E402
from ALB.control.pid import PID  # noqa: E402
from ALB.dynamics.rotor import RossRotor  # noqa: E402


JSON_PATH = (
    REPOSITORY_ROOT / "refs" / "coupling_default_path_0_4_6_reference_v1.json"
)
NPZ_PATH = (
    REPOSITORY_ROOT / "refs" / "coupling_default_path_0_4_6_reference_v1.npz"
)
SOURCE_COMMIT = "df7336f"
TIME_STEP = 2.0e-5
FUZZY_RULE_ROOT = REPOSITORY_ROOT / "paper_config"
LOADS: tuple[dict[str, Any], ...] = (
    {"type": "static", "node": 0, "force": [0.0, -100.0]},
    {
        "type": "unbalance",
        "node": 0,
        "phase": 0.3,
        "m": 1.0e-3,
        "freq": 50.0,
        "e": 1.0e-2,
    },
)
CONTROLLER_ERRORS = np.asarray(
    [
        [0.0, 0.0],
        [0.1, -0.05],
        [0.25, 0.1],
        [-0.2, 0.3],
        [0.05, -0.4],
        [0.6, 0.2],
        [-0.1, -0.1],
        [0.0, 0.45],
    ],
    dtype=float,
)


class SinglePlant:
    """Physical one-node four-DOF plant with ROSS state ordering.

    The state is ``[q, dq/dt]`` with ``q = (x, y, alpha, beta)``. The matrices
    form a proper second-order system so that bearing feedback is physical.
    """

    ndof = 4
    number_dof = 4

    def __init__(
        self,
        mass: float = 50.0,
        stiffness: float = 2.0e6,
        damping: float = 4.0e2,
    ) -> None:
        self.mass = float(mass)
        self.stiffness = float(stiffness)
        self.damping = float(damping)

    def matrices(self) -> dict[str, np.ndarray]:
        """Return the continuous mass, damping, and stiffness matrices."""

        mass = np.diag([self.mass, self.mass, 0.05, 0.05])
        stiffness = np.diag(
            [self.stiffness, 1.1 * self.stiffness, 1.0e4, 1.0e4]
        )
        damping = np.diag([self.damping, self.damping, 1.0, 1.0])
        return {"M": mass, "K": stiffness, "C": damping}

    def _lti(self, speed: float) -> SimpleNamespace:
        del speed
        matrices = self.matrices()
        n = self.ndof
        inverse_mass = np.linalg.inv(matrices["M"])
        a = np.block(
            [
                [np.zeros((n, n)), np.eye(n)],
                [-inverse_mass @ matrices["K"], -inverse_mass @ matrices["C"]],
            ]
        )
        b = np.vstack((np.zeros((n, n)), inverse_mass))
        return SimpleNamespace(
            A=a,
            B=b,
            C=np.eye(2 * n),
            D=np.zeros((2 * n, n)),
        )


def liquid_film_spec(time_step: float = TIME_STEP) -> dict[str, Any]:
    """Return the small dimensional liquid-film bearing specification."""

    return {
        "family": "liquid_film",
        "unit_system": "dimensional",
        "time_step": time_step,
        "node": 0,
        "film": {
            "circumferential_elements": 5,
            "axial_elements": 3,
            "max_iterations": 20,
            "solver_tolerance": 1.0e-6,
            "eccentricity": 0.0,
        },
        "restrictors": None,
        "thermal": None,
    }


def active_spec(
    control: dict[str, Any],
    time_step: float = TIME_STEP,
) -> dict[str, Any]:
    """Return the small dimensional active-bearing specification."""

    return {
        "family": "active_lubricated",
        "unit_system": "dimensional",
        "time_step": time_step,
        "node": 0,
        "film": {
            "circumferential_elements": 5,
            "axial_elements": 3,
            "max_iterations": 20,
            "solver_tolerance": 1.0e-6,
        },
        "restrictors": {
            "positions": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            "orifice_diameter": 0.002,
            "orifice_length": 0.02,
            "valve_area": 1.22e-6,
            "discharge_coefficient": 0.6,
        },
        "tank": {
            "x_range": [0.49, 0.51],
            "z_range": [0.2, 0.8],
            "depth_ratio": 2.0,
        },
        "valve": {
            "model": "second_order",
            "natural_frequency_hz": 166.0,
            "damping_ratio": 0.7,
            "delay": 0.0,
        },
        "control": control,
        "thermal": None,
        "transforms": {},
    }


PID_CONTROL = {
    "mode": "pid",
    "frequency_hz": 50.0,
    "sensor_angles_deg": [45.0, 135.0],
    "gains": {"kp": 1.0, "ki": 0.5, "kd": 0.01, "feedforward": 0.0},
}
FUZZY_CONTROL = {
    "mode": "fuzzy_pid",
    "frequency_hz": 5.0,
    "sensor_angles_deg": [45.0, 135.0],
    "error_range": [-1.0, 1.0, 0.01],
    "delta_error_range": [-1.0, 1.0, 0.01],
    "kp_range": [0.0, 1.0, 0.01],
    "ki_range": [0.0, 0.0, 0.01],
    "kd_range": [0.0, 1.0, 0.01],
    "rule_path": "fuzzy_rules.csv",
}


def small_ross_rotor() -> Any:
    """Build a small deterministic ROSS rotor with two linear supports."""

    import ross as rs

    steel = rs.Material(name="Steel046", rho=7810.0, E=211.0e9, G_s=81.2e9)
    shaft = [
        rs.ShaftElement(
            L=0.1,
            idl=0.0,
            odl=0.04,
            material=steel,
            shear_effects=True,
            rotary_inertia=True,
            gyroscopic=True,
        )
        for _ in range(4)
    ]
    disk = rs.DiskElement.from_geometry(
        n=2,
        material=steel,
        width=0.04,
        i_d=0.04,
        o_d=0.2,
    )
    bearings = [
        rs.BearingElement(n=0, kxx=1.0e6, kyy=1.0e6, cxx=2.0e2, cyy=2.0e2),
        rs.BearingElement(n=4, kxx=1.0e6, kyy=1.0e6, cxx=2.0e2, cyy=2.0e2),
    ]
    return rs.Rotor(
        shaft_elements=shaft,
        disk_elements=[disk],
        bearing_elements=bearings,
    )


def _simulation_case(
    *,
    rotor: RossRotor,
    config: ALB.BearingConfig,
    steps: int,
    node: int = 0,
    loads: tuple[dict[str, Any], ...] = LOADS,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Run one default-path simulation and capture every committed array."""

    simulation = ALB.build_simulation(
        ALB.SimulationConfig(
            rotor=rotor,
            mounts=(ALB.BearingMount(config, node),),
            time_step=TIME_STEP,
            steps=steps,
            loads=loads,
        )
    )
    result = simulation.run()
    arrays = {
        "time": np.asarray(result.time, dtype=float),
        "rotor_displacement": np.asarray(result.rotor_displacement, dtype=float),
        "rotor_velocity": np.asarray(result.rotor_velocity, dtype=float),
        "bearing_force": np.asarray(result.bearing_force, dtype=float),
        "rotor_state_history": np.asarray(rotor._xouts, dtype=float),
        "rotor_final_state": np.asarray(rotor.current_state(), dtype=float),
    }
    metadata = {
        "steps": steps,
        "node": node,
        "time_step": TIME_STEP,
        "loads": list(loads),
        "result_metadata": {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in result.metadata.items()
        },
        "converged": bool(result.convergence.converged),
    }
    return metadata, arrays


def run_plant_liquid_film() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Physical plant coupled to a dimensional liquid-film bearing."""

    plant = SinglePlant()
    metadata, arrays = _simulation_case(
        rotor=RossRotor(plant, speed=2.0 * np.pi * 50.0, dt=TIME_STEP),
        config=ALB.BearingConfig(liquid_film_spec()),
        steps=60,
    )
    metadata["bearing_spec"] = liquid_film_spec()
    metadata["plant"] = {"mass": plant.mass, "stiffness": plant.stiffness}
    return metadata, arrays


def run_plant_active_pid() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Physical plant coupled to an active PID bearing updated every step."""

    plant = SinglePlant()
    spec = active_spec(PID_CONTROL)
    metadata, arrays = _simulation_case(
        rotor=RossRotor(plant, speed=2.0 * np.pi * 50.0, dt=TIME_STEP),
        config=ALB.BearingConfig(spec),
        steps=25,
    )
    metadata["bearing_spec"] = spec
    metadata["plant"] = {"mass": plant.mass, "stiffness": plant.stiffness}
    return metadata, arrays


def run_plant_active_fuzzy_pid() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Physical plant coupled to an active fuzzy-PID bearing."""

    plant = SinglePlant()
    spec = active_spec(FUZZY_CONTROL)
    metadata, arrays = _simulation_case(
        rotor=RossRotor(plant, speed=2.0 * np.pi * 50.0, dt=TIME_STEP),
        config=ALB.BearingConfig(spec, resource_root=FUZZY_RULE_ROOT),
        steps=15,
    )
    metadata["bearing_spec"] = spec
    metadata["rule_resource"] = "paper_config/fuzzy_rules.csv"
    return metadata, arrays


def run_ross_rotor_liquid_film() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Small ROSS rotor with a liquid-film bearing at the disk node."""

    rotor = RossRotor(small_ross_rotor(), speed=2.0 * np.pi * 50.0, dt=TIME_STEP)
    loads = (
        {"type": "static", "node": 2, "force": [0.0, -50.0]},
        {
            "type": "unbalance",
            "node": 2,
            "phase": 0.0,
            "m": 1.0e-3,
            "freq": 50.0,
            "e": 1.0e-2,
        },
    )
    metadata, arrays = _simulation_case(
        rotor=rotor,
        config=ALB.BearingConfig(liquid_film_spec()),
        steps=40,
        node=2,
        loads=loads,
    )
    metadata["bearing_spec"] = liquid_film_spec()
    metadata["rotor"] = "small_ross_rotor(): four shaft elements, one disk"
    return metadata, arrays


def run_standalone_controllers() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Feed one deterministic error sequence through PID and fuzzy PID."""

    dt = 1.0e-3
    pid = PID(
        PIDConfig(
            dt=dt,
            kp=1.0,
            ki=0.5,
            kd=0.01,
            freq=50.0,
            sensor_angles=np.asarray([45.0, 135.0]),
        )
    )
    fuzzy = FuzzyPID(
        FuzzyPIDConfig(
            dt=dt,
            freq=5.0,
            rule_path=str(FUZZY_RULE_ROOT / "fuzzy_rules.csv"),
            sensor_angles=[45.0, 135.0],
        )
    )
    outputs: dict[str, list[np.ndarray]] = {"pid": [], "fuzzy_pid": []}
    for name, controller in (("pid", pid), ("fuzzy_pid", fuzzy)):
        controller._reset_for_owner()
        for index, error in enumerate(CONTROLLER_ERRORS):
            controller.input(index * dt, error)
            controller.evaluate()
            outputs[name].append(np.asarray(controller.output(), dtype=float))
    arrays = {
        "errors": CONTROLLER_ERRORS.copy(),
        "pid_outputs": np.vstack(outputs["pid"]),
        "fuzzy_pid_outputs": np.vstack(outputs["fuzzy_pid"]),
    }
    return {"dt": dt}, arrays


CASES: dict[str, Callable[[], tuple[dict[str, Any], dict[str, np.ndarray]]]] = {
    "plant_liquid_film": run_plant_liquid_film,
    "plant_active_pid": run_plant_active_pid,
    "plant_active_fuzzy_pid": run_plant_active_fuzzy_pid,
    "ross_rotor_liquid_film": run_ross_rotor_liquid_film,
    "standalone_controllers": run_standalone_controllers,
}


def capture_case(name: str) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Run one named case and prefix its arrays with the case name."""

    metadata, arrays = CASES[name]()
    return metadata, {f"{name}.{key}": value for key, value in arrays.items()}


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
    ).strip()


def build_reference() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Build the immutable reference payload from the unmodified source."""

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
        "schema": "alb.coupling-default-path-0.4.6-reference.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": SOURCE_COMMIT,
        "generator_head": _git_head(),
        "purpose": (
            "Freeze the 0.4.5 default rotor-bearing coupling path (staggered "
            "integrator, controller updated every step, one shared time_step) "
            "before ALB 0.4.6 adds control periods and ROS2."
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
            "scikit-fuzzy": _version("scikit-fuzzy"),
        },
        "time_step": TIME_STEP,
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
    """Write the pre-change JSON/NPZ reference pair exactly once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing reference pair intentionally.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=JSON_PATH,
        help="Output JSON path (defaults to refs/).",
    )
    parser.add_argument(
        "--npz",
        type=Path,
        default=NPZ_PATH,
        help="Output NPZ path (defaults to refs/).",
    )
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
