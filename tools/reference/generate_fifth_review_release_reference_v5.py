"""Freeze valid behavior around the fifth post-refactor review findings."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config import ALBConfig, FuzzyPIDConfig, NodimALBConfig, PIDConfig
from ALB.systems.alb.assembly import ALBSV, NodimALB, NodimALBSV
from tools.reference.generate_fourth_review_release_reference_v4 import (
    _ReferencePad,
    _ReferenceValve,
    collect_reference_arrays as collect_fourth_review_arrays,
)


DEFAULT_JSON = ROOT / "refs/fifth_review_release_reference_v5.json"
DEFAULT_NPZ = ROOT / "refs/fifth_review_release_reference_v5.npz"
RANDOM_SEED = 20260722


def _controller_round_trip_arrays() -> dict[str, np.ndarray]:
    """Return exact valid tagged-controller round-trip values."""

    controller_cases = {
        "pid": PIDConfig(
            dt=0.002,
            kp=0.45,
            ki=0.15,
            kd=0.08,
            uf=0.3,
            freq=37.0,
            sensor_angles=np.asarray([25.0, 115.0], dtype=float),
        ),
        "fuzzy": FuzzyPIDConfig(
            dt=0.003,
            freq=41.0,
            error_range=[-0.8, 0.9, 0.05],
            delta_error_range=[-0.4, 0.7, 0.02],
            kp_range=[0.1, 0.9, 0.04],
            ki_range=[0.0, 0.2, 0.01],
            kd_range=[0.05, 0.6, 0.025],
            rule_path="rules/custom.csv",
            sensor_angles=[30.0, 120.0],
        ),
    }
    arrays: dict[str, np.ndarray] = {}
    for config_type in (ALBConfig, NodimALBConfig):
        config_name = config_type.__name__.lower()
        for controller_name, controller in controller_cases.items():
            restored = config_type.from_dict(
                config_type(controller_config=controller).to_dict()
            )
            assert type(restored.controller_config) is type(controller)
            payload = restored.controller_config.to_dict()
            numeric_values = [
                float(value)
                for value in payload.values()
                if isinstance(value, (int, float, np.integer, np.floating))
                and not isinstance(value, bool)
            ]
            arrays[f"config.{config_name}.{controller_name}.numeric"] = np.asarray(
                numeric_values, dtype=float
            )
            arrays[f"config.{config_name}.{controller_name}.sensor_angles"] = (
                np.asarray(payload["sensor_angles"], dtype=float)
            )
    return arrays


def _default_subclass_arrays() -> dict[str, np.ndarray]:
    """Return initial matrices from public constructors using omitted configs."""

    arrays: dict[str, np.ndarray] = {}
    for model_type in (ALBSV, NodimALB, NodimALBSV):
        model = model_type(
            [_ReferencePad()],
            [_ReferenceValve(), _ReferenceValve()],
        )
        prefix = f"defaults.{model_type.__name__.lower()}"
        arrays[f"{prefix}.gxy"] = np.asarray(model.gxy, dtype=float).copy()
        arrays[f"{prefix}.gxyt"] = np.asarray(model.gxyt, dtype=float).copy()
    return arrays


def collect_reference_arrays() -> dict[str, np.ndarray]:
    """Return deterministic valid behavior protected through fifth-review fixes."""

    return {
        **{
            f"fourth.{name}": value
            for name, value in collect_fourth_review_arrays().items()
        },
        **_controller_round_trip_arrays(),
        **_default_subclass_arrays(),
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
        raise FileExistsError("Refusing to overwrite fifth review reference v5")

    arrays = collect_reference_arrays()
    metadata = {
        "reference_name": "fifth_review_release_reference_v5",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "random_seed": RANDOM_SEED,
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "scope": (
            "Successful harmonic execution and reinitialization, valid tagged PID and "
            "FuzzyPID restoration, and fresh public ALB subclass defaults"
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
