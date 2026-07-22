"""Freeze valid behavior around the fourth post-refactor review findings."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config import ALBConfig, PIDConfig
from ALB.core import Signal
from ALB.systems.alb.assembly import ALB
from ALB.systems.alb.harmonic import alb_harmonic_linear


DEFAULT_JSON = ROOT / "refs/fourth_review_release_reference_v4.json"
DEFAULT_NPZ = ROOT / "refs/fourth_review_release_reference_v4.npz"
RANDOM_SEED = 20260722


class _ReferencePad:
    """Small deterministic pad used to exercise the public ALB lifecycle."""

    def __init__(self) -> None:
        self.signal = Signal(sys=self)
        self.main_model = SimpleNamespace(args={"c": 1.0, "w": 60.0, "vf": 1.0})
        self.last_position = np.zeros(2, dtype=float)

    def init(self) -> None:
        self.last_position = np.zeros(2, dtype=float)

    def input(self, *, t, uxy, uxyt, nodim=False) -> None:
        del t, uxyt, nodim
        self.last_position = np.asarray(uxy, dtype=float).reshape(2)

    def output(self, *, nodim=False) -> dict[str, object]:
        del nodim
        return {"force": 2.0 * self.last_position, "friction": 0.0}

    def finish_signal(self) -> None:
        return None


class _ReferenceValve:
    """Valve double that records every command sent by the ALB assembly."""

    def __init__(self) -> None:
        self.signal = Signal(sys=self)
        self.simple_models: list[object] = []
        self.commands: list[float] = []
        self.command = 0.0

    def init(self) -> None:
        self.commands = []
        self.command = 0.0

    def input(self, time, command, **kwargs) -> None:
        del time, kwargs
        self.command = float(command)
        self.commands.append(self.command)

    def output(self) -> float:
        return self.command

    def finish_signal(self) -> None:
        return None


class _ReferenceLegacyController:
    """Resettable legacy controller whose output owns the calculation."""

    def __init__(self) -> None:
        self.init()

    def init(self) -> None:
        self.time = 0.0
        self.error = np.zeros(2, dtype=float)
        self.output_calls = 0

    def input(self, time, error) -> None:
        self.time = float(time)
        self.error = np.asarray(error, dtype=float).reshape(2)

    def output(self) -> np.ndarray:
        self.output_calls += 1
        return 0.5 * self.error + self.time


def _run_harmonic_trajectory() -> dict[str, np.ndarray]:
    bearing = alb_harmonic_linear(node_link=2)
    positions = np.asarray(
        [
            [0.0, 0.0],
            [1.0e-6, -0.5e-6],
            [-0.75e-6, 1.25e-6],
            [0.5e-6, 0.25e-6],
        ],
        dtype=float,
    )
    velocities = np.asarray(
        [
            [0.0, 0.0],
            [0.01, -0.02],
            [-0.015, 0.005],
            [0.0025, 0.0075],
        ],
        dtype=float,
    )

    def run_once() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        forces = []
        commands = []
        spools = []
        for step, (position_delta, velocity) in enumerate(
            zip(positions, velocities, strict=True)
        ):
            bearing.input(
                bearing.coefficients.equilibrium_position + position_delta,
                velocity,
                step * bearing.dt,
            )
            output = bearing.output()
            bearing.finish_signal()
            forces.append(output["force"])
            commands.append(output["spool_command"])
            spools.append(output["spool"])
        return (
            np.asarray(forces, dtype=float),
            np.asarray(commands, dtype=float),
            np.asarray(spools, dtype=float),
        )

    first = run_once()
    first_rows = len(bearing.results)
    bearing.init()
    second = run_once()
    return {
        "harmonic.first_forces": first[0],
        "harmonic.first_commands": first[1],
        "harmonic.first_spools": first[2],
        "harmonic.second_forces": second[0],
        "harmonic.second_commands": second[1],
        "harmonic.second_spools": second[2],
        "harmonic.result_rows": np.asarray(
            [first_rows, len(bearing.results)], dtype=np.int64
        ),
    }


def _run_enabled_alb() -> dict[str, np.ndarray]:
    valves = [_ReferenceValve(), _ReferenceValve()]
    controller = _ReferenceLegacyController()
    config = ALBConfig(
        controller_config=None,
        switch=True,
        c=1.0,
        w=60.0,
        gxy=np.eye(2, dtype=float),
        gxyt=np.zeros((2, 2), dtype=float),
    )
    alb = ALB([_ReferencePad()], valves, controller=controller, alb_config=config)
    alb.init()
    forces = []
    for time, position in (
        (0.0, [0.2, -0.4]),
        (0.01, [-0.1, 0.3]),
        (0.02, [0.5, 0.25]),
    ):
        alb.input(position, np.zeros(2, dtype=float), time)
        forces.append(alb.output()["force"])
    return {
        "alb_enabled.valve_commands": np.column_stack(
            [valve.commands for valve in valves]
        ),
        "alb_enabled.forces": np.asarray(forces, dtype=float),
        "alb_enabled.output_calls": np.asarray(
            [controller.output_calls], dtype=np.int64
        ),
    }


def _pid_config_arrays() -> dict[str, np.ndarray]:
    source = ALBConfig(
        controller_config=PIDConfig(
            dt=0.002,
            kp=0.45,
            ki=0.15,
            kd=0.08,
            uf=0.3,
            freq=37.0,
            sensor_angles=np.asarray([25.0, 115.0], dtype=float),
        ),
        switch=False,
    )
    restored = ALBConfig.from_dict(source.to_dict())
    assert isinstance(restored.controller_config, PIDConfig)
    controller = restored.controller_config
    return {
        "config.pid_scalars": np.asarray(
            [
                controller.dt,
                controller.kp,
                controller.ki,
                controller.kd,
                controller.uf,
                controller.freq,
            ],
            dtype=float,
        ),
        "config.pid_sensor_angles": np.asarray(
            controller.sensor_angles, dtype=float
        ),
        "config.switch": np.asarray([restored.switch], dtype=np.int8),
    }


def collect_reference_arrays() -> dict[str, np.ndarray]:
    """Return deterministic valid behavior that the release fixes must preserve."""

    return {
        **_run_harmonic_trajectory(),
        **_run_enabled_alb(),
        **_pid_config_arrays(),
    }


def _sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError("Refusing to overwrite fourth review reference v4")

    arrays = collect_reference_arrays()
    metadata = {
        "reference_name": "fourth_review_release_reference_v4",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "random_seed": RANDOM_SEED,
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "scope": (
            "Default harmonic PID construction/run/reinitialization behavior, "
            "enabled ALB valve commands, and non-default PID config restoration"
        ),
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
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.json)
    print(args.npz)
    print(f"arrays={len(arrays)}")


if __name__ == "__main__":
    main()
