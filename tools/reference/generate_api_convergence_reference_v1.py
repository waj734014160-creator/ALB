"""Generate the numerical baseline used while simplifying the ALB user API."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import scipy


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ALB


DEFAULT_JSON = ROOT / "refs" / "api_convergence_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "api_convergence_reference_v1.npz"


def _source_commit() -> str:
    """Return the checked-out commit without changing repository state."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def build_reference() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Capture one small liquid-film calculation and its resolved defaults."""

    input_spec = {
        "family": "liquid_film",
        "unit_system": "dimensional",
        "time_step": 1.0e-3,
        "node": 0,
        "film": {
            "circumferential_elements": 5,
            "axial_elements": 3,
            "max_iterations": 8,
            "solver_tolerance": 1.0e-5,
        },
        "restrictors": None,
        "thermal": None,
    }
    sample = {
        "displacement": [1.0e-6, -2.0e-6],
        "velocity": [3.0e-4, -4.0e-4],
        "time": 0.125,
    }
    config = ALB.BearingConfig(input_spec)
    bearing = ALB.build_bearing(config)
    result = bearing.calculate(**sample)
    runtime = bearing._runtime
    model = runtime.main_model
    pressure = np.asarray(model.latest_result, dtype=float).copy()
    thickness = np.asarray(
        [node.h for node in model.nodes.values()],
        dtype=float,
    )
    resolved_names = (
        "freq",
        "miu",
        "c",
        "r",
        "l",
        "ps",
        "rho",
        "nx",
        "nz",
    )
    resolved_defaults = {
        name: model.args[name]
        for name in resolved_names
        if name in model.args
    }
    resolved_defaults["max_iter"] = runtime.max_iter
    resolved_defaults["error_set"] = runtime.input_args.data.error_set

    arrays = {
        "force": np.asarray(result.force).copy(),
        "pressure": pressure,
        "thickness": thickness,
    }
    payload = {
        "schema": "alb.api-convergence-reference.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": _source_commit(),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "platform": platform.platform(),
        },
        "input_spec": input_spec,
        "sample": sample,
        "resolved_defaults": resolved_defaults,
        "outputs": {
            "friction": float(result.details.values["friction"]),
            "converged": result.convergence.converged,
            "iterations": result.convergence.iterations,
            "force_shape": list(arrays["force"].shape),
            "pressure_shape": list(arrays["pressure"].shape),
            "thickness_shape": list(arrays["thickness"].shape),
        },
    }
    return payload, arrays


def main() -> None:
    """Write versioned JSON metadata and lossless NumPy arrays."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError(
            "reference already exists; advance the version instead of overwriting it"
        )
    payload, arrays = build_reference()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.npz, **arrays)
    payload["npz_sha256"] = hashlib.sha256(args.npz.read_bytes()).hexdigest()
    args.json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.json)
    print(args.npz)


if __name__ == "__main__":
    main()
