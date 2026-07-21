"""Generate the pre-fix RossRotor time-validation v2 reference.

The numeric arrays freeze valid continuous rotor trajectories before changing
time-step validation.  Metadata separately records the historical defect that
accepted an invalid second timestamp; that defect is intentionally not used as
an expected post-fix behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.dynamics.rotor import RossRotor


DEFAULT_JSON = ROOT / "refs" / "ross_rotor_time_validation_reference_v2.json"
DEFAULT_NPZ = ROOT / "refs" / "ross_rotor_time_validation_reference_v2.npz"


class _LinearRotorPlant:
    """Provide the deterministic two-state plant used by rotor regressions."""

    ndof = 1
    number_dof = 1

    def _lti(self, speed: float) -> SimpleNamespace:
        del speed
        return SimpleNamespace(
            A=np.array([[-1.5, 0.25], [-0.5, -0.75]], dtype=float),
            B=np.array([[1.0], [0.2]], dtype=float),
            C=np.eye(2, dtype=float),
            D=np.zeros((2, 1), dtype=float),
        )


class _NodeRotorPlant:
    """Provide enough global DOFs to exercise per-node force mapping."""

    ndof = 4
    number_dof = 4

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


def _sha256_array(array: np.ndarray) -> str:
    """Hash an array using its contiguous byte representation."""
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _git_head() -> str:
    """Return the source commit used for reference generation."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _run_global_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Run valid global-force timestamps through the continuous wrapper."""
    dt = 1.0e-3
    times = np.arange(4, dtype=float) * dt
    forces = np.array([[0.0], [1.0], [0.5], [-0.25]], dtype=float)
    rotor = RossRotor(_LinearRotorPlant(), speed=2.0 * np.pi * 50.0, dt=dt)
    states = []
    for time_value, force in zip(times, forces):
        rotor.input_force(time_value, force)
        states.append(np.asarray(rotor.advance(), dtype=float).copy())
    arrays = {
        "global.times": times,
        "global.forces": forces,
        "global.states": np.vstack(states),
        "global.time_history": np.asarray(rotor._t, dtype=float),
        "global.state_history": np.asarray(rotor._xouts, dtype=float),
        "global.output_history": np.asarray(rotor._youts, dtype=float),
        "global.Ad": np.asarray(rotor._a, dtype=float),
        "global.Bd0": np.asarray(rotor._Bd0, dtype=float),
        "global.Bd1": np.asarray(rotor._Bd1, dtype=float),
    }
    return arrays, {
        "speed_rad_s": 2.0 * np.pi * 50.0,
        "dt": dt,
        "discrete": False,
    }


def _run_node_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Run valid per-node force timestamps through the same bookkeeping path."""
    dt = 2.0e-3
    times = np.arange(3, dtype=float) * dt
    node_forces = np.array(
        [[1.0, -0.5], [0.25, 0.75], [-0.2, 0.1]], dtype=float
    )
    rotor = RossRotor(_NodeRotorPlant(), speed=10.0, dt=dt)
    global_forces = []
    states = []
    for time_value, force in zip(times, node_forces):
        rotor.input_force2node(time_value, force, node=[0])
        global_forces.append(np.asarray(rotor._force1, dtype=float).copy())
        states.append(np.asarray(rotor.advance(), dtype=float).copy())
    arrays = {
        "node.times": times,
        "node.input_forces": node_forces,
        "node.global_forces": np.vstack(global_forces),
        "node.states": np.vstack(states),
        "node.time_history": np.asarray(rotor._t, dtype=float),
    }
    return arrays, {
        "speed_rad_s": 10.0,
        "dt": dt,
        "node": [0],
        "discrete": False,
    }


def _observe_invalid_timestamp_defect() -> dict[str, Any]:
    """Record the pre-fix invalid-timestamp acceptance without freezing it."""
    dt = 1.0e-3
    global_rotor = RossRotor(_LinearRotorPlant(), speed=1.0, dt=dt)
    global_rotor.input_force(0.0, np.array([1.0], dtype=float))
    global_rotor.advance()
    global_accepted = True
    try:
        global_rotor.input_force(0.5 * dt, np.array([2.0], dtype=float))
    except ValueError:
        global_accepted = False

    node_rotor = RossRotor(_NodeRotorPlant(), speed=1.0, dt=dt)
    node_rotor.input_force2node(0.0, np.array([1.0, -1.0]), node=[0])
    node_rotor.advance()
    node_accepted = True
    try:
        node_rotor.input_force2node(
            1.5 * dt, np.array([2.0, -2.0], dtype=float), node=[0]
        )
    except ValueError:
        node_accepted = False

    return {
        "global_invalid_time": 0.5 * dt,
        "global_invalid_time_accepted_pre_fix": global_accepted,
        "node_invalid_time": 1.5 * dt,
        "node_invalid_time_accepted_pre_fix": node_accepted,
        "root_cause": (
            "input_force and input_force2node appended t before _check_time; "
            "the check then compared t with the just-appended final element."
        ),
        "post_fix_contract": (
            "Reject non-finite or non-dt timestamps before mutating time, force, "
            "or lifecycle state."
        ),
    }


def generate(output_json: Path, output_npz: Path) -> None:
    """Generate the JSON/NPZ pair without overwriting existing evidence."""
    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite existing reference: {output}")

    global_arrays, global_config = _run_global_case()
    node_arrays, node_config = _run_node_case()
    arrays = {**global_arrays, **node_arrays}
    metadata = {
        "schema": "alb.ross-rotor-time-validation-reference.v2",
        "reference_name": "ross_rotor_time_validation_reference_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_before_time_validation_fix": True,
        "baseline_commit": _git_head(),
        "random_seed": None,
        "environment": {
            "python": sys.version,
            "numpy": importlib.metadata.version("numpy"),
            "scipy": importlib.metadata.version("scipy"),
            "ross-rotordynamics": importlib.metadata.version("ross-rotordynamics"),
        },
        "cases": {
            "global_force": global_config,
            "node_force": node_config,
        },
        "observed_defect": _observe_invalid_timestamp_defect(),
        "arrays": {
            name: {
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "sha256": _sha256_array(array),
            }
            for name, array in arrays.items()
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    np.savez(output_npz, **arrays)
    print(f"Wrote {output_json}")
    print(f"Wrote {output_npz}")


def main() -> None:
    """Parse output paths and generate the reference bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    generate(args.output_json, args.output_npz)


if __name__ == "__main__":
    main()
