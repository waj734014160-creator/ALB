"""Freeze valid-path outputs before the ALB 0.4.3 boundary repairs.

Invalid rotor, load, JSON5, and spool inputs are specified by focused tests.
This reference records only deterministic successful paths whose numerical
outputs must remain bitwise identical after the boundary checks are tightened.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ALB
from ALB.contracts import BearingInput, UnitSystem
from ALB.surrogate.runtime import SurrogateBearingRuntime
from tools.reference.generate_alb_0_4_2_repair_reference_v1 import (
    _equilibrium_arrays,
    _facade_arrays,
)


class _DeterministicSurrogate:
    """Return a deterministic force from the supplied valid spool input."""

    def __init__(self) -> None:
        self._force = np.zeros(2, dtype=float)

    def input(
        self,
        displacement: object,
        velocity: object,
        spool: object,
        *,
        nodim: bool,
    ) -> None:
        coordinate = np.asarray(displacement, dtype=float)
        speed = np.asarray(velocity, dtype=float)
        command = np.asarray(spool, dtype=float)
        scale = 1.0 if nodim else 2.0
        self._force = scale * (
            coordinate + 0.25 * speed + np.array([command[0], -command[1]])
        )

    def output(self, *, nodim: bool) -> np.ndarray:
        del nodim
        return self._force.copy()


def _surrogate_arrays() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Capture one valid fixed-spool surrogate step."""

    fixed_spool = np.array([0.25, -0.5], dtype=float)
    runtime = SurrogateBearingRuntime(
        _DeterministicSurrogate(),
        unit_system=UnitSystem.NONDIMENSIONAL,
        node_link=0,
        external_spool=False,
        fixed_spool=fixed_spool,
    )
    output = runtime.step(
        BearingInput(
            displacement=np.array([0.1, -0.2], dtype=float),
            velocity=np.array([0.04, -0.08], dtype=float),
            time=0.0,
            unit_system=UnitSystem.NONDIMENSIONAL,
        )
    )
    snapshot = runtime.result_snapshot()
    return (
        {
            "unit_system": output.unit_system.value,
            "time": output.time,
            "converged": runtime.convergence_status.converged,
        },
        {
            "surrogate_force": output.force,
            "surrogate_spool": np.asarray(snapshot.values["spool"]),
        },
    )


def _array_manifest(
    arrays: dict[str, np.ndarray],
) -> dict[str, dict[str, object]]:
    """Return stable shape and dtype metadata for every reference array."""

    return {
        name: {
            "shape": list(np.asarray(value).shape),
            "dtype": str(np.asarray(value).dtype),
        }
        for name, value in sorted(arrays.items())
    }


def main() -> None:
    """Write the immutable JSON metadata and lossless NPZ arrays."""

    baseline_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    arrays: dict[str, np.ndarray] = {}
    cases: dict[str, object] = {}
    for name, build in (
        ("equilibrium", _equilibrium_arrays),
        ("facades", _facade_arrays),
        ("surrogate", _surrogate_arrays),
    ):
        metadata, case_arrays = build()
        cases[name] = metadata
        overlap = set(arrays).intersection(case_arrays)
        if overlap:
            raise RuntimeError(f"duplicate reference arrays: {sorted(overlap)}")
        arrays.update(case_arrays)

    json_path = ROOT / "refs/alb_0_4_3_guard_reference_v1.json"
    npz_path = ROOT / "refs/alb_0_4_3_guard_reference_v1.npz"
    np.savez(npz_path, **arrays)
    digest = hashlib.sha256(npz_path.read_bytes()).hexdigest()
    payload = {
        "schema": "alb.0.4.3-guard-reference.v1",
        "baseline_commit": baseline_commit,
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
        "npz_sha256": digest,
    }
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json_path)
    print(npz_path)
    print(digest)


if __name__ == "__main__":
    main()
