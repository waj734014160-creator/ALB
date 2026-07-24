"""Freeze native controller and servovalve trajectories."""

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

from ALB.control.lqg import ALBLQGController
from ALB.control.repetitive import RCConfig, RepetitiveController
from ALB.control.valve import moog_2nd_servovalve


DEFAULT_JSON = ROOT / "refs/native_control_lifecycle_reference_v9.json"
DEFAULT_NPZ = ROOT / "refs/native_control_lifecycle_reference_v9.npz"


def _array_sha256(value: np.ndarray) -> str:
    """Return a stable digest for one contiguous array."""

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _git_head() -> str:
    """Return the revision used to generate this reference."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _package_version(distribution_name: str) -> str:
    """Return an installed distribution version."""

    from importlib.metadata import version

    return version(distribution_name)


def _lqg_arrays() -> dict[str, np.ndarray]:
    """Collect one LQG calculation per latched sample."""

    controller = ALBLQGController(SimpleNamespace(), dt=0.01, eso_enable=False)
    controller.active_ctrl_sys_d = SimpleNamespace(
        A=np.asarray([[0.8]], dtype=float),
        B=np.asarray([[0.2, -0.1]], dtype=float),
        C=np.asarray([[2.0], [-3.0]], dtype=float),
        D=np.zeros((2, 2), dtype=float),
    )
    controller._init_runtime_state()
    times = np.arange(6, dtype=np.float64) * controller.dt
    errors = np.asarray(
        [
            [0.20, -0.30],
            [0.10, -0.15],
            [-0.05, 0.25],
            [0.40, 0.10],
            [-0.20, -0.10],
            [0.00, 0.30],
        ],
        dtype=np.float64,
    )
    outputs = []
    states = []
    next_states = []
    for time, error in zip(times, errors):
        controller.input(float(time), error)
        controller.evaluate()
        outputs.append(controller.output())
        states.append(np.asarray(controller.x_hat, dtype=float).reshape(-1))
        next_states.append(np.asarray(controller.x_next, dtype=float).reshape(-1))
    history = controller.get_history(to_dataframe=False)
    return {
        "lqg.times": times,
        "lqg.errors": errors,
        "lqg.outputs": np.asarray(outputs, dtype=np.float64),
        "lqg.states": np.asarray(states, dtype=np.float64),
        "lqg.next_states": np.asarray(next_states, dtype=np.float64),
        "lqg.history_times": np.asarray(history["t"], dtype=np.float64),
        "lqg.history_outputs": np.asarray(history["u"], dtype=np.float64),
    }


def _repetitive_arrays() -> dict[str, np.ndarray]:
    """Collect one repetitive-controller period plus wraparound."""

    controller = RepetitiveController(
        RCConfig(
            dt=0.01,
            freq=10.0,
            k_rc=np.asarray([0.4, -0.2]),
            q_filter=0.95,
            m_lead=1,
        )
    )
    times = np.arange(14, dtype=np.float64) * controller.dt
    phases = 2.0 * np.pi * np.arange(times.size, dtype=float) / controller.N
    errors = np.column_stack((np.cos(phases), np.sin(phases))).astype(np.float64)
    outputs = []
    pointers = []
    for time, error in zip(times, errors):
        controller.input(float(time), error)
        controller.evaluate()
        outputs.append(controller.output())
        pointers.append(controller.ptr)
    return {
        "repetitive.times": times,
        "repetitive.errors": errors,
        "repetitive.outputs": np.asarray(outputs, dtype=np.float64),
        "repetitive.pointers": np.asarray(pointers, dtype=np.int64),
        "repetitive.u_buffer": np.asarray(controller.u_buffer, dtype=np.float64),
        "repetitive.e_buffer": np.asarray(controller.e_buffer, dtype=np.float64),
    }


def _servovalve_arrays() -> dict[str, np.ndarray]:
    """Collect dynamic servovalve outputs and internal histories."""

    valve = moog_2nd_servovalve(dt=0.001)
    times = np.arange(8, dtype=np.float64) * 0.001
    commands = np.asarray(
        [0.0, 0.25, 0.5, -0.2, -0.6, 0.1, 0.75, 0.0], dtype=np.float64
    )
    outputs = []
    for time, command in zip(times, commands):
        valve.input(float(time), float(command))
        valve.evaluate()
        outputs.append(np.asarray(valve.output(), dtype=float).reshape(-1))
    return {
        "servovalve.times": times,
        "servovalve.commands": commands,
        "servovalve.outputs": np.asarray(outputs, dtype=np.float64),
        "servovalve.xout": np.asarray(valve.xout, dtype=np.float64),
        "servovalve.yout": np.asarray(valve.yout, dtype=np.float64).reshape(-1, 1),
    }


def collect_reference_arrays() -> dict[str, np.ndarray]:
    """Return all numerical trajectories protected by this migration."""

    return {**_lqg_arrays(), **_repetitive_arrays(), **_servovalve_arrays()}


def main() -> None:
    """Write a non-overwriting JSON/NPZ reference pair."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError("Refusing to overwrite native control lifecycle v9")

    arrays = collect_reference_arrays()
    metadata = {
        "reference_name": "native_control_lifecycle_reference_v9",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "random_seed": None,
        "dependencies": {
            name: _package_version(name)
            for name in ("control", "numpy", "pandas", "scipy")
        },
        "calculation_contract": (
            "Preserve each numerical update exactly once per input while moving "
            "all mutation into evaluate() and making output() read-only."
        ),
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _array_sha256(value),
            }
            for name, value in sorted(arrays.items())
        },
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.npz, **arrays)
    args.json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.json)
    print(args.npz)
    print(f"arrays={len(arrays)}")


if __name__ == "__main__":
    main()
