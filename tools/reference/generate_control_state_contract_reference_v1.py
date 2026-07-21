"""Freeze valid control-state behavior before post-refactor bug fixes.

The reference protects ordinary PID, FuzzyPID, and SISO LTI trajectories while
also storing an independently evaluated MIMO output contract for the currently
unreachable multi-input path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import control as cl
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config import FuzzyPIDConfig, PIDConfig
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.state_space import BaseLti, lti_state_space_matrix_init


DEFAULT_JSON = ROOT / "refs/control_state_contract_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs/control_state_contract_reference_v1.npz"


def _sha256(array: np.ndarray) -> str:
    """Return the digest of one contiguous array."""
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _git_head() -> str:
    """Return the source revision used for reference generation."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _pid_arrays() -> dict[str, np.ndarray]:
    """Collect a two-step fresh PID trajectory."""
    config = PIDConfig(
        dt=0.1,
        kp=1.0,
        ki=0.5,
        kd=0.1,
        freq=5.0,
        sensor_angles=[0.0, 90.0],
    )
    controller = PID(config)
    times = np.asarray([0.0, 0.1], dtype=np.float64)
    errors = np.asarray([[0.2, -0.3], [0.1, -0.2]], dtype=np.float64)
    outputs = []
    kp_values = []
    ki_values = []
    kd_values = []
    for time, error in zip(times, errors):
        controller.input(float(time), error)
        outputs.append(controller.output())
        kp_values.append(np.asarray(controller.kp_calc, dtype=float))
        ki_values.append(np.asarray(controller.ki_calc, dtype=float))
        kd_values.append(np.asarray(controller.kd_calc, dtype=float))
    return {
        "pid.times": times,
        "pid.errors": errors,
        "pid.outputs": np.asarray(outputs, dtype=np.float64),
        "pid.kp_calc": np.asarray(kp_values, dtype=np.float64),
        "pid.ki_calc": np.asarray(ki_values, dtype=np.float64),
        "pid.kd_calc": np.asarray(kd_values, dtype=np.float64),
    }


def _fuzzy_arrays() -> tuple[dict[str, np.ndarray], list[str]]:
    """Collect valid variable-gain outputs from the default fixed-Ki model."""
    config = FuzzyPIDConfig(
        dt=0.1,
        freq=5.0,
        rule_path=None,
        sensor_angles=[0.0, 90.0],
    )
    times = np.asarray([0.0, 0.1], dtype=np.float64)
    errors = np.asarray([[0.2, -0.3], [0.1, -0.2]], dtype=np.float64)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        controller = FuzzyPID(config)
        outputs = []
        gains = []
        for time, error in zip(times, errors):
            controller.input(float(time), error)
            outputs.append(controller.output())
            gains.append(
                np.stack(
                    [
                        np.asarray(controller.kp, dtype=float),
                        np.asarray(controller.ki, dtype=float),
                        np.asarray(controller.kd, dtype=float),
                    ]
                )
            )
    arrays = {
        "fuzzy.times": times,
        "fuzzy.errors": errors,
        "fuzzy.outputs": np.asarray(outputs, dtype=np.float64),
        "fuzzy.gains": np.asarray(gains, dtype=np.float64),
    }
    return arrays, [str(item.message) for item in caught]


def _siso_lti_arrays() -> dict[str, np.ndarray]:
    """Collect a valid SISO history whose numerical states must not drift."""
    system = cl.ss([[-2.0]], [[1.0]], [[3.0]], [[0.0]])
    model = BaseLti(system, 0.05, x0=np.asarray([0.4], dtype=float))
    times = np.asarray([0.0, 0.05, 0.1], dtype=np.float64)
    inputs = np.asarray([[0.1], [0.2], [-0.1]], dtype=np.float64)
    for time, value in zip(times, inputs):
        model.input(float(time), value)
        model.output()
    return {
        "lti_siso.times": times,
        "lti_siso.inputs": inputs,
        "lti_siso.states": np.asarray(model.xout, dtype=np.float64).reshape(-1, 1),
        "lti_siso.outputs": np.asarray(model.yout, dtype=np.float64).reshape(-1, 1),
    }


def _mimo_contract_arrays() -> dict[str, np.ndarray]:
    """Evaluate the intended MIMO current-output contract independently."""
    a = np.diag([-1.0, -2.0])
    b = np.eye(2)
    c = np.asarray([[1.0, 2.0], [0.5, -1.0]], dtype=float)
    d = np.asarray([[0.2, 0.1], [-0.3, 0.4]], dtype=float)
    dt = 0.1
    ad, bd0, bd1, _, _ = lti_state_space_matrix_init(a, b, c, d, dt)
    x0 = np.asarray([0.25, -0.5], dtype=float)
    inputs = np.asarray([[1.0, -2.0], [0.5, 0.25]], dtype=float)
    initial_output = c @ x0 + d @ inputs[0]
    # Preserve the established zero pre-history used by the first FOH step.
    x1 = x0 @ ad + np.zeros(2) @ bd0 + inputs[1] @ bd1
    next_output = c @ x1 + d @ inputs[1]
    return {
        "lti_mimo.A": a,
        "lti_mimo.B": b,
        "lti_mimo.C": c,
        "lti_mimo.D": d,
        "lti_mimo.x0": x0,
        "lti_mimo.inputs": inputs,
        "lti_mimo.expected_states": np.stack([x0, x1]),
        "lti_mimo.expected_outputs": np.stack([initial_output, next_output]),
    }


def main() -> None:
    """Generate the immutable control reference pair."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError("Refusing to overwrite control-state reference v1")

    fuzzy_arrays, fuzzy_warnings = _fuzzy_arrays()
    arrays = {
        **_pid_arrays(),
        **fuzzy_arrays,
        **_siso_lti_arrays(),
        **_mimo_contract_arrays(),
    }
    metadata = {
        "reference_name": "control_state_contract_reference_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "fuzzy_warnings_before_fix": fuzzy_warnings,
        "mimo_contract": (
            "output returns the current Cx+Du vector; histories remain available "
            "through yout/xout"
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
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.json)
    print(args.npz)
    print(f"arrays={len(arrays)}")


if __name__ == "__main__":
    main()
