"""Freeze valid behavior around the third post-refactor review findings."""

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

from ALB.config import ALBConfig, NodimALBConfig
from ALB.control.controllers import ALBLQGController, RCConfig, RepetitiveController
from ALB.control.valve import moog_2nd_servovalve
from ALB.dynamics.rotor import RossRotor


DEFAULT_JSON = ROOT / "refs/third_review_compatibility_reference_v3.json"
DEFAULT_NPZ = ROOT / "refs/third_review_compatibility_reference_v3.npz"
RANDOM_SEED = 20260722


class _LegacyController:
    """Minimal historical controller whose output performs the calculation."""

    def __init__(self) -> None:
        self.time = 0.0
        self.error = np.zeros(2, dtype=float)
        self.output_calls = 0

    def input(self, time: float, error: np.ndarray) -> None:
        self.time = float(time)
        self.error = np.asarray(error, dtype=float).reshape(2)

    def output(self) -> np.ndarray:
        self.output_calls += 1
        return 1.5 * self.error + self.time


class _SixDofNodeRotorPlant:
    """Small deterministic plant exposing two six-DOF ROSS-style nodes."""

    ndof = 12
    number_dof = 6

    def _lti(self, speed: float) -> SimpleNamespace:
        del speed
        state_count = 2 * self.ndof
        return SimpleNamespace(
            A=-0.5 * np.eye(state_count, dtype=float),
            B=np.vstack(
                (
                    np.eye(self.ndof, dtype=float),
                    0.25 * np.eye(self.ndof, dtype=float),
                )
            ),
            C=np.eye(state_count, dtype=float),
            D=np.zeros((state_count, self.ndof), dtype=float),
        )


def _legacy_controller_arrays() -> dict[str, np.ndarray]:
    controller = _LegacyController()
    outputs = []
    for time, error in (
        (0.0, [0.2, -0.4]),
        (0.01, [-0.1, 0.3]),
        (0.02, [0.5, 0.25]),
    ):
        controller.input(time, error)
        outputs.append(controller.output())
    return {
        "legacy_controller.outputs": np.asarray(outputs, dtype=float),
        "legacy_controller.output_calls": np.asarray(
            [controller.output_calls], dtype=np.int64
        ),
    }


def _lqg_arrays() -> dict[str, np.ndarray]:
    controller = ALBLQGController(SimpleNamespace(), dt=0.01, eso_enable=False)
    controller.active_ctrl_sys_d = SimpleNamespace(
        A=np.asarray([[0.8]], dtype=float),
        B=np.asarray([[0.2, -0.1]], dtype=float),
        C=np.asarray([[2.0], [-3.0]], dtype=float),
        D=np.zeros((2, 2), dtype=float),
    )
    controller._init_runtime_state()
    outputs = []
    for time, measurement in (
        (0.0, [0.25, -0.5]),
        (0.01, [0.1, 0.2]),
        (0.02, [-0.3, 0.4]),
    ):
        controller.input(time, measurement)
        outputs.append(controller.output())
    return {
        "lqg.outputs": np.asarray(outputs, dtype=float),
        "lqg.final_x_hat": np.asarray(controller.x_hat, dtype=float).reshape(-1),
        "lqg.final_x_next": np.asarray(controller.x_next, dtype=float).reshape(-1),
    }


def _repetitive_controller_arrays() -> dict[str, np.ndarray]:
    controller = RepetitiveController(
        RCConfig(
            dt=0.01,
            freq=10.0,
            k_rc=np.asarray([0.4, -0.2], dtype=float),
            q_filter=0.95,
            m_lead=1,
        )
    )
    outputs = []
    for step in range(14):
        error = np.asarray(
            [np.sin(0.3 * step), np.cos(0.2 * step)], dtype=float
        )
        controller.input(step * controller.dt, error)
        outputs.append(controller.output())
    return {
        "repetitive.outputs": np.asarray(outputs, dtype=float),
        "repetitive.u_buffer": np.asarray(controller.u_buffer, dtype=float),
        "repetitive.e_buffer": np.asarray(controller.e_buffer, dtype=float),
        "repetitive.pointer": np.asarray([controller.ptr], dtype=np.int64),
    }


def _servo_valve_arrays() -> dict[str, np.ndarray]:
    valve = moog_2nd_servovalve(dt=0.001)
    outputs = []
    for time, command in (
        (0.0, 0.25),
        (0.001, -0.4),
        (0.002, 0.7),
        (0.003, 0.1),
    ):
        valve.input(time, command)
        outputs.append(np.asarray(valve.output(), dtype=float).reshape(-1))
    return {
        "servo.outputs": np.asarray(outputs, dtype=float),
        "servo.times": np.asarray(valve.ts, dtype=float),
        "servo.xout": np.asarray(valve.xout, dtype=float),
        "servo.yout": np.asarray(valve.yout, dtype=float),
    }


def _rotor_arrays() -> dict[str, np.ndarray]:
    rotor = RossRotor(_SixDofNodeRotorPlant(), speed=1.0, dt=0.001)
    rotor._xk0 = np.arange(24, dtype=float) + 0.25
    rotor._state_ready = True
    state = rotor.current_state([0, 1])
    return {
        "rotor.node_state_uxy": np.asarray(state["uxy"], dtype=float),
        "rotor.node_state_uxyt": np.asarray(state["uxyt"], dtype=float),
    }


def _config_arrays() -> dict[str, np.ndarray]:
    dimensional = ALBConfig.from_dict({})
    nondimensional = NodimALBConfig.from_dict({})
    return {
        "config.default_controller_flags": np.asarray(
            [
                dimensional.controller_config is not None,
                nondimensional.controller_config is not None,
            ],
            dtype=np.int8,
        ),
        "config.default_switch_flags": np.asarray(
            [dimensional.switch, nondimensional.switch], dtype=np.int8
        ),
    }


def collect_reference_arrays() -> dict[str, np.ndarray]:
    """Return deterministic valid behavior that the review fixes must preserve."""

    return {
        **_legacy_controller_arrays(),
        **_lqg_arrays(),
        **_repetitive_controller_arrays(),
        **_servo_valve_arrays(),
        **_rotor_arrays(),
        **_config_arrays(),
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
        raise FileExistsError("Refusing to overwrite third review reference v3")

    arrays = collect_reference_arrays()
    metadata = {
        "reference_name": "third_review_compatibility_reference_v3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "random_seed": RANDOM_SEED,
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "scope": (
            "Valid legacy/LQG/repetitive controller outputs, ServoValve2 input-output "
            "behavior, strict six-DOF node reads, and default controller configuration"
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
