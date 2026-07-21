"""Freeze duplicate-output defects and corrected control lifecycle targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import control as cl
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config import FuzzyPIDConfig, PIDConfig
from ALB.control.controllers import FuzzyPID, PID
from ALB.control.state_space import BaseLti


DEFAULT_JSON = ROOT / "refs/control_lifecycle_reference_v2.json"
DEFAULT_NPZ = ROOT / "refs/control_lifecycle_reference_v2.npz"


def _pid_arrays() -> dict[str, np.ndarray]:
    controller = PID(
        PIDConfig(
            dt=0.1,
            kp=1.0,
            ki=0.5,
            kd=0.1,
            freq=5.0,
            sensor_angles=[0.0, 90.0],
        )
    )
    controller.input(0.0, [0.2, -0.3])
    first = np.asarray(controller.output(), dtype=float)
    first_integral = np.asarray(controller.ki_intergral, dtype=float).copy()
    second = np.asarray(controller.output(), dtype=float)
    second_integral = np.asarray(controller.ki_intergral, dtype=float).copy()
    return {
        "pid.first_output": first,
        "pid.observed_duplicate_output": second,
        "pid.observed_duplicate_integral": second_integral,
        "pid.corrected_repeated_outputs": np.stack([first, first]),
        "pid.corrected_integral": first_integral,
        "pid.observed_result_rows": np.asarray([len(controller.results)], dtype=np.int64),
        "pid.corrected_result_rows": np.asarray([1], dtype=np.int64),
    }


def _fuzzy_arrays() -> dict[str, np.ndarray]:
    controller = FuzzyPID(
        FuzzyPIDConfig(
            dt=0.1,
            freq=5.0,
            rule_path=None,
            sensor_angles=[0.0, 90.0],
        )
    )
    controller.input(0.0, [0.2, -0.3])
    first = np.asarray(controller.output(), dtype=float)
    first_integral = np.asarray(controller.ki_intergral, dtype=float).copy()
    second = np.asarray(controller.output(), dtype=float)
    second_integral = np.asarray(controller.ki_intergral, dtype=float).copy()
    return {
        "fuzzy.first_output": first,
        "fuzzy.observed_duplicate_output": second,
        "fuzzy.observed_duplicate_integral": second_integral,
        "fuzzy.corrected_repeated_outputs": np.stack([first, first]),
        "fuzzy.corrected_integral": first_integral,
        "fuzzy.observed_result_rows": np.asarray([len(controller.results)], dtype=np.int64),
        "fuzzy.corrected_result_rows": np.asarray([1], dtype=np.int64),
    }


def _lti_arrays() -> dict[str, np.ndarray]:
    system = cl.ss([[-2.0]], [[1.0]], [[3.0]], [[0.0]])
    model = BaseLti(system, 0.05, x0=np.asarray([0.4], dtype=float))
    model.input(0.0, [0.25])
    first = np.asarray(model.output(), dtype=float)
    first_state = np.asarray(model.xk0, dtype=float).copy()
    second = np.asarray(model.output(), dtype=float)
    second_state = np.asarray(model.xk0, dtype=float).copy()
    return {
        "lti.first_output": first,
        "lti.observed_duplicate_output": second,
        "lti.observed_duplicate_state": second_state,
        "lti.corrected_repeated_outputs": np.stack([first, first]),
        "lti.corrected_state": first_state,
        "lti.observed_history_lengths": np.asarray(
            [len(model.xout), len(model.yout)], dtype=np.int64
        ),
        "lti.corrected_history_lengths": np.asarray([1, 1], dtype=np.int64),
    }


def collect_reference_arrays() -> dict[str, np.ndarray]:
    """Return observed defects and independent corrected lifecycle targets."""
    return {**_pid_arrays(), **_fuzzy_arrays(), **_lti_arrays()}


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
        raise FileExistsError("Refusing to overwrite control lifecycle reference v2")
    arrays = collect_reference_arrays()
    metadata = {
        "reference_name": "control_lifecycle_reference_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "observed_defect": (
            "BaseLti, PID, and FuzzyPID output calls mutate state and history "
            "without a newly latched input"
        ),
        "target_contract": (
            "input invalidates output, evaluate computes once, and repeated output "
            "reads one immutable result"
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
