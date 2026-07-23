"""Freeze coupling publication, failure sealing, and logical save behavior."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB import StepContext
from ALB.contracts.result_tree import NpyResult, SaveTreeNode
from ALB.core import Signal, TimeIterDt
from ALB.dynamics.coupling import RsRotorBearingCouple


DEFAULT_JSON = ROOT / "refs" / "coupling_failure_save_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "coupling_failure_save_reference_v1.npz"
DT = 0.01


class _ReferenceBearing:
    """Small state-dependent bearing with an injectable completion failure."""

    node_link = 0
    unit_system = "dimensional"

    def __init__(self, *, fail_on_finish: bool = False) -> None:
        self.signal = Signal(sys=self)
        self.fail_on_finish = fail_on_finish
        self.init()

    def init(self) -> None:
        self.time = 0.0
        self.displacement = np.zeros(2, dtype=float)
        self.velocity = np.zeros(2, dtype=float)
        self.force = np.zeros(2, dtype=float)
        self.input_history: list[np.ndarray] = []
        self.force_history: list[np.ndarray] = []

    def input(self, uxy, uxyt, t) -> None:
        self.time = float(t)
        self.displacement = np.asarray(uxy, dtype=float).reshape(2)
        self.velocity = np.asarray(uxyt, dtype=float).reshape(2)
        self.input_history.append(
            np.concatenate(
                ([self.time], self.displacement, self.velocity)
            )
        )

    def output(self) -> dict[str, np.ndarray]:
        stiffness = np.asarray([[2.0, 0.5], [-0.25, 1.5]])
        damping = np.asarray([[0.1, 0.0], [0.0, 0.2]])
        self.force = (
            np.asarray([1.0, -2.0])
            - stiffness @ self.displacement
            - damping @ self.velocity
        )
        self.force_history.append(self.force.copy())
        return {"force": self.force.copy()}

    def finish_signal(self) -> None:
        if self.fail_on_finish:
            raise RuntimeError("injected bearing completion failure")

    def save(self, *args: Any, **kwargs: Any) -> SaveTreeNode:
        del args
        path = kwargs.get("path", "bearing")
        name = kwargs.get("name", "bearing")
        return SaveTreeNode(
            path,
            NpyResult({name: np.asarray(self.force_history, dtype=float)}),
        )


class _ReferenceRotor:
    """Deterministic rotor exposing old save and Signal interfaces."""

    def __init__(self) -> None:
        self.signal = Signal(sys=self)
        self.init()

    def init(self) -> None:
        self.state = np.zeros((1, 2), dtype=float)
        self.velocity = np.zeros((1, 2), dtype=float)
        self.input_calls = 0
        self.advance_calls = 0
        self.force_history: list[np.ndarray] = []
        self.previous_force_history: list[np.ndarray] = []

    def input_force2node(self, time, force, node_links, force0=None) -> None:
        del time, node_links
        self.input_calls += 1
        self.force_history.append(np.asarray(force, dtype=float).copy())
        self.previous_force_history.append(
            np.asarray(force0, dtype=float).copy()
        )

    def advance(self) -> None:
        self.advance_calls += 1
        self.state = self.state + np.asarray([[0.25, -0.5]])
        self.velocity = self.velocity + np.asarray([[0.1, -0.2]])

    def output(self, node_links) -> dict[str, np.ndarray]:
        count = len(np.asarray(node_links).reshape(-1))
        return {
            "uxy": np.repeat(self.state, count, axis=0),
            "uxyt": np.repeat(self.velocity, count, axis=0),
        }

    def finish_signal(self) -> None:
        return None

    def save(self, *args: Any, **kwargs: Any) -> SaveTreeNode:
        del args, kwargs
        return SaveTreeNode(
            "rotor",
            NpyResult({"state": self.state.copy()}),
        )


def _success_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Run two successful steps and capture publication/save state."""

    rotor = _ReferenceRotor()
    bearing = _ReferenceBearing()
    coupling = RsRotorBearingCouple(
        rotor,
        TimeIterDt(DT, 2),
        bearing,
    )
    coupling.init()
    initial = coupling.output()
    first_context = StepContext(1, DT, DT, "dimensional")
    second_context = StepContext(2, 2.0 * DT, DT, "dimensional")
    first = coupling.advance(first_context)
    second = coupling.advance(second_context)

    duplicate_error = None
    calls_before_duplicate = rotor.input_calls
    try:
        coupling.advance(second_context)
    except RuntimeError as exc:
        duplicate_error = str(exc)
    if duplicate_error is None:
        raise AssertionError("duplicate context must be rejected")
    if rotor.input_calls != calls_before_duplicate:
        raise AssertionError("duplicate validation must happen before mutation")

    save_tree = coupling.save(
        tofile=False,
        path="coupling_reference",
        name="RBC",
    )
    arrays = {
        "success.initial_bearing_force": np.asarray(
            initial.values["bearing_force"],
            dtype=float,
        ),
        "success.first_bearing_force": np.asarray(
            first.values["bearing_force"],
            dtype=float,
        ),
        "success.second_bearing_force": np.asarray(
            second.values["bearing_force"],
            dtype=float,
        ),
        "success.first_nodal_force": np.asarray(
            first.values["nodal_force"],
            dtype=float,
        ),
        "success.second_nodal_force": np.asarray(
            second.values["nodal_force"],
            dtype=float,
        ),
        "success.rotor_state": rotor.state.copy(),
        "success.rotor_velocity": rotor.velocity.copy(),
        "success.rotor_force_history": np.asarray(
            rotor.force_history,
            dtype=float,
        ),
        "success.rotor_previous_force_history": np.asarray(
            rotor.previous_force_history,
            dtype=float,
        ),
        "success.bearing_input_history": np.asarray(
            bearing.input_history,
            dtype=float,
        ),
        "success.bearing_force_history": np.asarray(
            bearing.force_history,
            dtype=float,
        ),
        "success.coupling_history": coupling.results[
            "bearing0"
        ].to_numpy(dtype=float),
    }
    metadata = {
        "initial_context": {
            "step_index": initial.metadata["step_index"],
            "time": initial.metadata["time"],
        },
        "last_context": {
            "step_index": coupling._step_ledger.last_context.step_index,
            "time": coupling._step_ledger.last_context.time,
        },
        "duplicate_error": duplicate_error,
        "rotor_input_calls": rotor.input_calls,
        "rotor_advance_calls": rotor.advance_calls,
        "save_tree": save_tree.get_dir(),
        "save_snapshot_schema": save_tree.result_snapshot().metadata["schema"],
        "save_snapshot_root": save_tree.result_snapshot().metadata["logical_root"],
    }
    return arrays, metadata


def _failure_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Fail after mutable advancement and capture the sealed public state."""

    rotor = _ReferenceRotor()
    bearing = _ReferenceBearing(fail_on_finish=True)
    coupling = RsRotorBearingCouple(
        rotor,
        TimeIterDt(DT, 1),
        bearing,
    )
    coupling.init()
    context = StepContext(1, DT, DT, "dimensional")
    failure_message = None
    try:
        coupling.advance(context)
    except RuntimeError as exc:
        failure_message = str(exc)
    if failure_message is None:
        raise AssertionError("injected failure must escape advance")

    blocked: dict[str, str] = {}
    operations = {
        "output": coupling.output,
        "results": lambda: coupling.results,
        "save": lambda: coupling.save(tofile=False),
        "advance": lambda: coupling.advance(context),
    }
    for name, operation in operations.items():
        try:
            operation()
        except RuntimeError as exc:
            blocked[name] = str(exc)
        else:
            raise AssertionError(f"{name} must be blocked after failure")

    arrays = {
        "failure.rotor_state": rotor.state.copy(),
        "failure.rotor_velocity": rotor.velocity.copy(),
        "failure.rotor_force_history": np.asarray(
            rotor.force_history,
            dtype=float,
        ),
        "failure.bearing_input_history": np.asarray(
            bearing.input_history,
            dtype=float,
        ),
        "failure.bearing_force_history": np.asarray(
            bearing.force_history,
            dtype=float,
        ),
    }
    last_context = coupling._step_ledger.last_context
    metadata = {
        "failure_message": failure_message,
        "lifecycle_state": coupling.lifecycle_state.value,
        "rotor_input_calls": rotor.input_calls,
        "rotor_advance_calls": rotor.advance_calls,
        "ledger_last_context": {
            "step_index": last_context.step_index,
            "time": last_context.time,
        },
        "blocked": blocked,
    }
    return arrays, metadata


def collect_reference() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Collect successful and failed coupling behavior."""

    success_arrays, success_metadata = _success_case()
    failure_arrays, failure_metadata = _failure_case()
    return (
        {**success_arrays, **failure_arrays},
        {
            "success": success_metadata,
            "failure": failure_metadata,
        },
    )


def _sha256_array(value: np.ndarray) -> str:
    """Return the stable byte digest for one array."""

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def generate(output_json: Path, output_npz: Path) -> None:
    """Generate the reference pair without overwriting prior evidence."""

    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite reference: {output}")
    arrays, contracts = collect_reference()
    metadata = {
        "schema": "alb.coupling-failure-save-reference.v1",
        "baseline_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).strip(),
        "environment": {
            "python": sys.version,
            "numpy": importlib.metadata.version("numpy"),
        },
        "contracts": contracts,
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _sha256_array(value),
            }
            for name, value in sorted(arrays.items())
        },
    }
    output_json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    np.savez(output_npz, **arrays)
    print(f"Wrote {output_json}")
    print(f"Wrote {output_npz}")


def main() -> None:
    """Parse output paths and generate the reference."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    generate(args.output_json, args.output_npz)


if __name__ == "__main__":
    main()
