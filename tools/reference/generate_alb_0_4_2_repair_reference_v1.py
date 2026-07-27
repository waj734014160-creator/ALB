"""Generate the immutable ALB 0.4.2 repair baseline from v0.4.1.

The script freezes only successful, deterministic paths that the repair must
preserve.  Invalid-input behavior is specified by red tests rather than by
recording the known faulty outputs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ALB
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    StepContext,
    UnitSystem,
)
from ALB.dynamics.rotor import RossRotor
from ALB.physics.bearing.units import BearingScaleSet, BearingUnitAdapter

BASELINE_COMMIT = "a26435e2eb7652d6d64af2194865dd3cf05db61d"


class _SyntheticEquilibriumRuntime:
    """Return the deterministic force used by the equilibrium reference."""

    def __init__(self) -> None:
        self._input: BearingInput | None = None
        self._output: BearingOutput | None = None
        self.convergence_status = ConvergenceStatus(0.0, True)

    @staticmethod
    def _reset_for_owner() -> None:
        return None

    def input(self, value: BearingInput) -> None:
        self._input = value

    def evaluate_static(self) -> None:
        assert self._input is not None
        coordinate = np.asarray(self._input.displacement, dtype=float)
        self._output = BearingOutput(
            force=np.array(
                [
                    2.0 * coordinate[0],
                    1.0 + 3.0 * coordinate[1],
                ]
            ),
            time=self._input.time,
            unit_system=UnitSystem.NONDIMENSIONAL,
        )

    def output(self) -> BearingOutput:
        assert self._output is not None
        return self._output


class _SyntheticEquilibriumBearing:
    config = SimpleNamespace(
        unit_system="nondimensional",
        control_mode="uncontrolled",
        family="liquid_film",
    )


class _SyntheticWhirlRuntime:
    """Return a deterministic linear force for the established whirl method."""

    unit_system = UnitSystem.DIMENSIONAL

    def __init__(self) -> None:
        self._stiffness = np.array(
            [[2.0e6, 3.0e5], [-4.0e5, 1.5e6]],
            dtype=float,
        )
        self._damping = np.array(
            [[800.0, -120.0], [75.0, 650.0]],
            dtype=float,
        )

    def calculate(
        self,
        *,
        displacement: object,
        velocity: object,
        time: float,
        spool: object = None,
    ) -> SimpleNamespace:
        del time, spool
        coordinate = np.asarray(displacement, dtype=float)
        speed = np.asarray(velocity, dtype=float)
        force = -(
            coordinate @ self._stiffness.T
            + speed @ self._damping.T
        )
        return SimpleNamespace(
            force=force,
            convergence=ConvergenceStatus(0.0, True, iterations=1),
        )


class _SyntheticWhirlBearing:
    """Provide isolated deterministic runtimes to BearingAnalysis."""

    config = SimpleNamespace(unit_system="dimensional")

    @staticmethod
    def _fresh() -> _SyntheticWhirlRuntime:
        return _SyntheticWhirlRuntime()


class _NodeRotorPlant:
    """Small deterministic rotor plant used by the public simulation facade."""

    ndof = 4
    number_dof = 4

    def _lti(self, speed: float) -> SimpleNamespace:
        del speed
        state_count = 2 * self.ndof
        return SimpleNamespace(
            A=-0.5 * np.eye(state_count),
            B=np.vstack((np.eye(self.ndof), 0.25 * np.eye(self.ndof))),
            C=np.eye(state_count),
            D=np.zeros((state_count, self.ndof)),
        )


def _liquid_spec(time_step: float, *, node: int = 0) -> dict[str, object]:
    """Return one small deterministic dimensional liquid-film config."""

    return {
        "family": "liquid_film",
        "unit_system": "dimensional",
        "time_step": time_step,
        "node": node,
        "film": {
            "circumferential_elements": 5,
            "axial_elements": 3,
            "max_iterations": 5,
            "solver_tolerance": 1.0e-6,
            "eccentricity": 0.0,
        },
        "restrictors": None,
        "thermal": None,
    }


def _assert_baseline_source() -> None:
    """Refuse generation when package code differs from the fixed candidate."""

    completed = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            BASELINE_COMMIT,
            "--",
            "ALB",
            "pyproject.toml",
        ],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "package source differs from the fixed v0.4.1 candidate"
        )


def _equilibrium_arrays() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Freeze a converged multi-step nonzero-load equilibrium path."""

    inputs = {
        "load": [0.0, -1.0],
        "initial_displacement": [0.4, -0.4],
        "max_iterations": 30,
        "relative_tolerance": 1.0e-4,
        "damping": 0.05,
        "jacobian_step": 1.0e-2,
        "fallback_stiffness": [5.0, 5.0],
        "stall_patience": 5,
        "stall_relative_tolerance": 0.0,
    }
    solver = ALB.EquilibriumSolver(
        _SyntheticEquilibriumBearing(),
        ALB.EquilibriumOptions(
            max_iterations=int(inputs["max_iterations"]),
            relative_tolerance=float(inputs["relative_tolerance"]),
            damping=float(inputs["damping"]),
            jacobian_step=float(inputs["jacobian_step"]),
            fallback_stiffness=(
                float(inputs["fallback_stiffness"][0]),
                float(inputs["fallback_stiffness"][1]),
            ),
            stall_patience=int(inputs["stall_patience"]),
            stall_relative_tolerance=float(
                inputs["stall_relative_tolerance"]
            ),
        ),
    )
    setattr(solver, "_new_runtime", _SyntheticEquilibriumRuntime)
    try:
        result = solver.solve(
            inputs["load"],
            initial_displacement=inputs["initial_displacement"],
        )
    except ALB.CalculationError as exc:
        if exc.failure_snapshot is None:
            raise
        values = exc.failure_snapshot.values
        result_metadata = exc.failure_snapshot.metadata
        residual = float(values["evaluation_relative_residual"][-1])
        converged = False
        iterations = int(inputs["max_iterations"]) - 1
    else:
        values = result.values
        result_metadata = result.metadata
        residual = result.convergence.residual
        converged = result.convergence.converged
        iterations = result.convergence.iterations
    metadata = {
        "input": inputs,
        "residual": residual,
        "converged": converged,
        "inner_converged": result_metadata["inner_converged"],
        "stop_reason": result_metadata["stop_reason"],
        "iterations": iterations,
    }
    arrays = {
        "equilibrium_coordinate": values["displacement"],
        "equilibrium_force": values["bearing_force"],
        "equilibrium_evaluation_coordinate": values[
            "evaluation_displacement"
        ],
        "equilibrium_evaluation_force": values["evaluation_force"],
        "equilibrium_evaluation_residual": (
            values["evaluation_relative_residual"]
        ),
        "equilibrium_evaluation_converged": (
            values["evaluation_inner_converged"]
        ),
    }
    return metadata, arrays


def _whirl_arrays() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Freeze the established coherent forward/reverse whirl result."""

    time = np.arange(64, dtype=float) * 0.003125
    trajectory = ALB.EllipseTrajectory(
        center=(1.0e-5, -2.0e-5),
        semi_axes=(2.0e-4, 7.0e-5),
        orientation_rad=0.4,
    )
    result = ALB.BearingAnalysis(
        _SyntheticWhirlBearing()
    ).dynamic_coefficients(
        trajectory,
        time,
        frequency_hz=5.0,
    )
    names = (
        "forward_time",
        "forward_displacement",
        "forward_velocity",
        "forward_force",
        "reverse_time",
        "reverse_displacement",
        "reverse_velocity",
        "reverse_force",
        "transfer_real",
        "transfer_imag",
        "stiffness",
        "damping",
    )
    return (
        {
            "frequency_hz": 5.0,
            "center": trajectory.center.tolist(),
            "semi_axes": trajectory.semi_axes.tolist(),
            "orientation_rad": trajectory.orientation_rad,
            "method": result.metadata["method"],
        },
        {
            f"whirl_{name}": np.asarray(result.values[name])
            for name in names
        },
    )


def _adapter_arrays() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Freeze dimensional-to-nondimensional local context conversion."""

    scales = BearingScaleSet(
        rotor_unit=UnitSystem.DIMENSIONAL,
        bearing_unit=UnitSystem.NONDIMENSIONAL,
        Sx=2.0e-5,
        St=2.0e-4,
        Sv=0.1,
        Sf=2500.0,
        Sp=5.0e6,
        scale_id="alb-0.4.2-reference",
        pressure_scale_source="fixed reference",
        velocity_definition_id="Sx/St",
        residual_definition_id="bearing-local",
        provenance="v0.4.1 candidate",
    )
    global_context = StepContext(
        4,
        0.004,
        0.001,
        UnitSystem.DIMENSIONAL,
    )
    local = BearingUnitAdapter(scales).rotor_context_to_bearing(global_context)
    return (
        {
            "global": {
                "step_index": global_context.step_index,
                "time": global_context.time,
                "dt": global_context.dt,
                "unit_system": global_context.unit_system.value,
            },
            "local_unit_system": local.unit_system.value,
            "St": scales.St,
        },
        {
            "adapter_local_context": np.asarray(
                [local.step_index, local.time, local.dt],
                dtype=float,
            )
        },
    )


def _facade_arrays() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Freeze equal-dt MultiPad and successful simulation histories."""

    dt = 1.0e-3
    multi_config = ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": dt,
            "node": 0,
            "pads": [
                _liquid_spec(dt),
                _liquid_spec(dt),
            ],
        }
    )
    multi = ALB.build_bearing(multi_config)
    multi_result = multi.calculate(displacement=(0.0, 0.0), time=0.0)

    memory_config = ALB.SimulationConfig(
        rotor=RossRotor(_NodeRotorPlant(), speed=1.0, dt=dt),
        mounts=(
            ALB.BearingMount(ALB.BearingConfig(_liquid_spec(dt)), 0),
        ),
        time_step=dt,
        steps=2,
    )
    memory = ALB.build_simulation(memory_config).run()

    with tempfile.TemporaryDirectory(prefix="alb_0_4_2_reference_") as temp:
        stream_root = Path(temp) / "stream"
        disk_config = ALB.SimulationConfig(
            rotor=RossRotor(_NodeRotorPlant(), speed=1.0, dt=dt),
            mounts=(
                ALB.BearingMount(ALB.BearingConfig(_liquid_spec(dt)), 0),
            ),
            time_step=dt,
            steps=2,
            history=ALB.HistoryPolicy(
                mode="disk_stream",
                fields=("bearing_force",),
                downsample=1,
                directory=stream_root,
            ),
        )
        disk = ALB.build_simulation(disk_config).run()
        records = sorted(stream_root.glob("step_*.npz"))
        disk_time = []
        disk_force = []
        for record in records:
            with np.load(record) as archive:
                disk_time.append(float(archive["time"][0]))
                disk_force.append(np.asarray(archive["bearing_force"]))
        manifest = json.loads(
            (stream_root / "history.json").read_text(encoding="utf-8")
        )

    metadata = {
        "time_step": dt,
        "multi_pad_count": 2,
        "simulation_committed_steps": memory.metadata["committed_steps"],
        "disk_record_files": [item["file"] for item in manifest["records"]],
        "disk_manifest_complete": manifest["complete"],
        "disk_result_complete": disk.metadata["complete"],
    }
    arrays = {
        "multi_pad_force": multi_result.force,
        "simulation_time": memory.time,
        "simulation_rotor_displacement": memory.rotor_displacement,
        "simulation_rotor_velocity": memory.rotor_velocity,
        "simulation_bearing_force": memory.bearing_force,
        "disk_time": np.asarray(disk_time, dtype=float),
        "disk_bearing_force": np.asarray(disk_force, dtype=float),
    }
    return metadata, arrays


def _array_manifest(arrays: dict[str, np.ndarray]) -> dict[str, object]:
    """Return stable shape and dtype metadata for every frozen array."""

    return {
        name: {
            "shape": list(np.asarray(value).shape),
            "dtype": str(np.asarray(value).dtype),
        }
        for name, value in sorted(arrays.items())
    }


def main() -> None:
    """Generate the JSON metadata and lossless NPZ array archive."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json",
        type=Path,
        default=ROOT / "refs/alb_0_4_2_repair_contract_v1.json",
    )
    parser.add_argument(
        "--npz",
        type=Path,
        default=ROOT / "refs/alb_0_4_2_repair_contract_v1.npz",
    )
    args = parser.parse_args()
    _assert_baseline_source()

    arrays: dict[str, np.ndarray] = {}
    cases: dict[str, object] = {}
    for name, build in (
        ("equilibrium", _equilibrium_arrays),
        ("whirl", _whirl_arrays),
        ("unit_adapter", _adapter_arrays),
        ("facades", _facade_arrays),
    ):
        metadata, case_arrays = build()
        cases[name] = metadata
        overlap = set(arrays).intersection(case_arrays)
        if overlap:
            raise RuntimeError(f"duplicate reference arrays: {sorted(overlap)}")
        arrays.update(case_arrays)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.npz, **arrays)
    npz_sha256 = hashlib.sha256(args.npz.read_bytes()).hexdigest()
    payload = {
        "schema": "alb.0.4.2-repair-contract.v1",
        "baseline_commit": BASELINE_COMMIT,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "alb": ALB.__version__,
        },
        "cases": cases,
        "arrays": _array_manifest(arrays),
        "npz_sha256": npz_sha256,
    }
    args.json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.json)
    print(args.npz)
    print(npz_sha256)


if __name__ == "__main__":
    main()
