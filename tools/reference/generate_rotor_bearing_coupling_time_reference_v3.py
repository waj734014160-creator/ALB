"""Freeze the corrected target-time contract for rotor-bearing coupling.

The current implementation is executed before the production edit to record
the observed off-by-one trajectory.  The same deterministic model also has an
independent target trajectory for the intended t=0 snapshot plus three physical
advances to dt, 2*dt, and 3*dt.
"""

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

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    UnitSystem,
    result_snapshot,
)
from ALB.core import RuntimeLifecycle, TimeIterDt
from ALB.dynamics.coupling import RsRotorBearingCouple


DEFAULT_JSON = ROOT / "refs/rotor_bearing_coupling_time_reference_v3.json"
DEFAULT_NPZ = ROOT / "refs/rotor_bearing_coupling_time_reference_v3.npz"


class _ReferenceBearing:
    """Minimal zero-force bearing for deterministic exchange timing."""

    node_link = 0
    unit_system = UnitSystem.DIMENSIONAL
    input_dto_type = BearingInput

    def __init__(self) -> None:
        self._lifecycle = RuntimeLifecycle("reference bearing")
        self._input = None
        self._output = None
        self.init()

    @property
    def lifecycle_state(self):
        """Return the formal runtime state."""

        return self._lifecycle.state

    @property
    def convergence_status(self):
        """Return deterministic convergence."""

        return ConvergenceStatus(0.0, True)

    def init(self) -> None:
        """Reset the stateless bearing."""

        self._input = None
        self._output = None
        self._lifecycle.reset()

    def input(self, dto: BearingInput) -> None:
        """Latch the coupling input without changing zero force."""

        self._lifecycle.require_input_slot()
        self._input = dto
        self._lifecycle.latch()

    def evaluate(self) -> None:
        """Publish the deterministic zero force."""

        with self._lifecycle.evaluation():
            self._output = BearingOutput(
                np.zeros(2, dtype=float),
                self._input.time,
                self.unit_system,
            )

    def output(self) -> BearingOutput:
        """Return a deterministic zero force without recalculation."""

        self._lifecycle.require_output()
        return self._output

    def step(self, dto: BearingInput) -> BearingOutput:
        """Compose the formal three-phase lifecycle."""

        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self):
        """Return the current deterministic force."""

        return result_snapshot({"force": self.output().force}, {})

    def failure_snapshot(self):
        """Reject failure access for this deterministic runtime."""

        raise RuntimeError("no reference bearing failure")

    def diagnostic_snapshot(self):
        """Return the current lifecycle state."""

        return result_snapshot({}, {"state": self.lifecycle_state.value})


class _ReferenceRotor:
    """Rotor whose state increases by one on every physical advance."""

    def __init__(self) -> None:
        self.input_times: list[float] = []
        self.states: list[np.ndarray] = []
        self.state = np.zeros((1, 2), dtype=float)

    def init(self) -> None:
        """Reset state and histories."""
        self.input_times = []
        self.states = []
        self.state = np.zeros((1, 2), dtype=float)

    def input_force2node(self, time, force, node_links, force0=None) -> None:
        """Record the target time supplied by the coupling."""
        del force, node_links, force0
        self.input_times.append(float(time))

    def advance(self) -> None:
        """Advance one easily audited unit state."""
        self.state = self.state + 1.0
        self.states.append(self.state.copy())

    def output(self, node_links) -> dict[str, np.ndarray]:
        """Return the current translational state."""
        count = len(np.asarray(node_links).reshape(-1))
        return {
            "uxy": np.repeat(self.state, count, axis=0),
            "uxyt": np.zeros((count, 2), dtype=float),
        }

def _sha256(array: np.ndarray) -> str:
    """Return the digest of one contiguous array."""
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _git_head() -> str:
    """Return the source revision used for reference generation."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _legacy_arrays() -> dict[str, np.ndarray]:
    """Run the unmodified coupling and expose its extra t=0 advance."""
    rotor = _ReferenceRotor()
    coupling = RsRotorBearingCouple(rotor, TimeIterDt(0.1, 3))
    coupling.add_bearing(_ReferenceBearing(), node_link=0)
    coupling.solve()
    output = coupling.output()
    return {
        "legacy.input_times": np.asarray(rotor.input_times, dtype=np.float64),
        "legacy.states": np.asarray(rotor.states, dtype=np.float64),
        "legacy.result_times": coupling.results["bearing0"]["t"].to_numpy(
            dtype=np.float64
        ),
        "legacy.final_metadata": np.asarray(
            [output.metadata["step_index"], output.metadata["time"]],
            dtype=np.float64,
        ),
    }


def _corrected_arrays() -> dict[str, np.ndarray]:
    """Return the independent target-time oracle for three intervals."""
    return {
        "corrected.initial_time": np.asarray([0.0], dtype=np.float64),
        "corrected.initial_state": np.zeros((1, 2), dtype=np.float64),
        "corrected.input_times": np.asarray([0.1, 0.2, 0.3], dtype=np.float64),
        "corrected.states": np.asarray(
            [[[1.0, 1.0]], [[2.0, 2.0]], [[3.0, 3.0]]], dtype=np.float64
        ),
        "corrected.result_times": np.asarray([0.1, 0.2, 0.3], dtype=np.float64),
        "corrected.final_metadata": np.asarray([3.0, 0.3], dtype=np.float64),
    }


def main() -> None:
    """Generate the immutable coupling-time reference pair."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError("Refusing to overwrite coupling-time reference v3")

    arrays = {**_legacy_arrays(), **_corrected_arrays()}
    metadata = {
        "reference_name": "rotor_bearing_coupling_time_reference_v3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "observed_defect": (
            "an inclusive four-sample grid with three intervals advances four times"
        ),
        "corrected_contract": (
            "t=0 is a committed read-only initial snapshot; only target samples "
            "dt through end_time advance the rotor"
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
