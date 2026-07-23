"""Generate the deterministic interface-refactor reference artifacts.

The reference captures public exports, signal propagation, the standard
dimensional bearing contract, and the ROSS-style rotor-bearing coupling
boundary.  Run this script only against the tagged pre-refactor baseline.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import inspect
import json
import pickle
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import ALB  # noqa: E402
from ALB import StepContext  # noqa: E402
from ALB.contracts import BearingInput  # noqa: E402
from ALB.systems.alb import alb_harmonic_linear  # noqa: E402
from ALB.systems.alb import ALBLinearAgent  # noqa: E402
from ALB.core import Signal, TimeIterDt  # noqa: E402
from ALB.dynamics.coupling import RsRotorBearingCouple  # noqa: E402
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode  # noqa: E402
from ALB.surrogate.training.transforms import MidpointMinMaxScaler  # noqa: E402


REFERENCE_STEM = "interface_contract_reference_v1"
EXPECTED_BASELINE_COMMIT = "24ea190becf19c6f0e33e3c05686c0052dfdbedd"
LEGACY_IMPORT_SURFACE = {
    "ALB.systems.alb": ["ALB", "ALBBuilder", "ALBLinearAgent", "ALBNNAgent"],
    "ALB.core.fem": [
        "BaseCSystem",
        "BaseSimpleModel",
        "BaseSystem",
        "Signal",
        "TimeIter",
        "TimeIterDt",
    ],
    "ALB.config": ["CsoArgs", "PIDConfig", "ThermalConfig", "TimeGridConfig"],
    "ALB.surrogate": ["ALBNN", "ALBNet", "Net", "albnn"],
    "ALB.physics.hydraulics": ["CSOrifice", "CsoArgs", "NodimCSOrifice"],
    "ALB.contracts.result_tree": ["DataFrameResult", "SaveTreeNode"],
    "ALB.infrastructure.notification": ["SmtpNotifier"],
}


class _SignalRecorder:
    """Record signal callback order without coupling to production models."""

    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events
        self.signal = Signal(sys=self)

    def finish_signal(self) -> None:
        self.events.append(self.name)


class _ReferenceRotor:
    """Minimal deterministic rotor implementation for coupling references."""

    def __init__(self, position: np.ndarray) -> None:
        self.signal = Signal(sys=self)
        base_position = np.asarray(position, dtype=float).reshape(2)
        self.positions = np.vstack(
            (
                base_position,
                base_position + np.array([1.0e-6, 0.0]),
                base_position + np.array([0.0, -1.5e-6]),
            )
        )
        self.velocities = np.array(
            [[0.0, 0.0], [1.0e-4, -2.0e-4], [-3.0e-4, 4.0e-4]]
        )
        self._output_index = 0
        self.last_time: float | None = None
        self.last_force: np.ndarray | None = None
        self.last_force0: np.ndarray | None = None
        self.last_nodes: np.ndarray | None = None
        self.time_history: list[float] = []
        self.force_history: list[np.ndarray] = []
        self.force0_history: list[np.ndarray] = []

    def init(self) -> None:
        self.last_time = None
        self.last_force = None
        self.last_force0 = None
        self.last_nodes = None
        self._output_index = 0
        self.time_history = []
        self.force_history = []
        self.force0_history = []

    def output(self, node_links) -> dict[str, np.ndarray]:
        count = len(np.asarray(node_links).reshape(-1))
        state_index = min(self._output_index, len(self.positions) - 1)
        self._output_index += 1
        return {
            "uxy": np.repeat(self.positions[state_index][None, :], count, axis=0),
            "uxyt": np.repeat(self.velocities[state_index][None, :], count, axis=0),
        }

    def input_force2node(self, t, force, node_links, force0=None) -> None:
        self.last_time = float(t)
        self.last_force = np.asarray(force, dtype=float).copy()
        self.last_force0 = np.asarray(force0, dtype=float).copy()
        self.last_nodes = np.asarray(node_links, dtype=int).copy()
        self.time_history.append(self.last_time)
        self.force_history.append(self.last_force.copy())
        self.force0_history.append(self.last_force0.copy())

    def advance(self) -> None:
        """Record the explicit lifecycle boundary while preserving frozen states."""

        return None

    def finish_signal(self) -> None:
        return None

    def save(self, tofile=False, *args, **kwargs) -> SaveTreeNode:
        return SaveTreeNode(
            "reference_rotor",
            DataFrameResult({"rotor": pd.DataFrame()}),
        )


def _git_head() -> str:
    """Return the exact source commit used to generate the artifacts."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _ensure_baseline_source() -> str:
    """Reject reference generation from any source other than the fixed tag."""

    head = _git_head()
    if head != EXPECTED_BASELINE_COMMIT:
        raise RuntimeError(
            f"Reference generation requires {EXPECTED_BASELINE_COMMIT}, got {head}"
        )
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "ALB",
            "pyproject.toml",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise RuntimeError(f"ALB source is dirty; refusing to generate refs:\n{status}")
    return head


def _distribution_version(name: str) -> str | None:
    """Return an installed distribution version when available."""

    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _array_manifest(arrays: dict[str, np.ndarray]) -> dict[str, dict[str, object]]:
    """Describe every stored array without duplicating its numeric payload."""

    return {
        name: {"shape": list(value.shape), "dtype": str(value.dtype)}
        for name, value in arrays.items()
    }


def _signal_reference() -> dict[str, object]:
    """Capture the current parent-before-child completion event contract."""

    events: list[str] = []
    parent = _SignalRecorder("parent", events)
    child = _SignalRecorder("child", events)
    parent.signal.add_child(child.signal)
    parent.signal.lead_loop("finish_signal")
    return {
        "callback_order": events,
        "parent_reset": bool(parent.signal.signal is False),
        "child_reset": bool(child.signal.signal is False),
    }


def _bearing_reference() -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Capture a short deterministic standard-bearing trajectory."""

    bearing = alb_harmonic_linear(node_link=12)
    bearing.init()
    amplitude_m = 2.0e-6
    omega = bearing.coefficients.whirl_omega_rad_s
    outputs = []
    times = []
    positions = []
    velocities = []
    for step in range(8):
        phase = bearing.phase_step * (step + 1)
        displacement = amplitude_m * np.array([np.cos(phase), np.sin(phase)])
        velocity = amplitude_m * omega * np.array([-np.sin(phase), np.cos(phase)])
        time_s = step * bearing.dt
        position = bearing.uxy0 + displacement
        bearing.input(BearingInput(position, velocity, time_s, "dimensional"))
        bearing.evaluate()
        outputs.append(dict(bearing.result_snapshot().values))
        times.append(time_s)
        positions.append(position)
        velocities.append(velocity)

    arrays = {
        "bearing_time": np.asarray(times, dtype=float),
        "bearing_position": np.vstack(positions),
        "bearing_velocity": np.vstack(velocities),
        "bearing_force": np.vstack([item["force"] for item in outputs]),
        "bearing_force_stiffness": np.vstack(
            [item["force_stiffness"] for item in outputs]
        ),
        "bearing_force_damping": np.vstack(
            [item["force_damping"] for item in outputs]
        ),
        "bearing_force_spool": np.vstack(
            [item["force_spool"] for item in outputs]
        ),
        "bearing_spool": np.vstack([item["spool"] for item in outputs]),
        "bearing_spool_command": np.vstack(
            [item["spool_command"] for item in outputs]
        ),
        "bearing_K": bearing.K,
        "bearing_C": bearing.C,
        "bearing_G_xv_real": bearing.G_xv.real,
        "bearing_G_xv_imag": bearing.G_xv.imag,
    }
    metadata = {
        "class_name": type(bearing).__name__,
        "node_link": bearing.node_link,
        "dt_s": bearing.dt,
        "input_signature": str(inspect.signature(type(bearing).input)),
        "output_signature": str(inspect.signature(type(bearing).output)),
        "save_signature": str(inspect.signature(type(bearing).save)),
        "output_keys": sorted(outputs[-1]),
        "result_columns": list(bearing.results.columns),
        "result_rows": len(bearing.results),
        "save_tree": bearing.save(tofile=False).get_dir(),
    }
    return metadata, arrays


def _legacy_linear_reference() -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Capture the legacy ALBLinearAgent call order and force equation."""

    static_force = np.array([10.0, -5.0])
    fdxv = np.array([[2.0, -3.0], [4.0, 5.0]])
    stiffness = np.array([[6.0, 7.0], [8.0, 9.0]])
    damping = np.array([[0.1, 0.2], [0.3, 0.4]])
    base_spool = np.array([0.1, -0.2])
    base_position = np.array([1.0e-5, -2.0e-5])
    times = np.array([0.0, 0.01, 0.02, 0.03])
    positions = base_position + np.array(
        [
            [0.0, 0.0],
            [1.0e-6, -2.0e-6],
            [-3.0e-6, 4.0e-6],
            [2.0e-6, 1.0e-6],
        ]
    )
    velocities = np.array(
        [
            [0.0, 0.0],
            [1.0e-4, -2.0e-4],
            [-3.0e-4, 4.0e-4],
            [2.0e-4, 1.0e-4],
        ]
    )
    spool = np.array(
        [
            [0.1, -0.2],
            [0.11, -0.18],
            [0.08, -0.23],
            [0.14, -0.21],
        ]
    )
    agent = ALBLinearAgent(
        static_force.copy(),
        fdxv.copy(),
        stiffness.copy(),
        damping.copy(),
        base_spool.copy(),
        base_position.copy(),
    )
    agent.init()
    outputs = []
    for time_s, position, velocity, spool_state in zip(
        times, positions, velocities, spool
    ):
        for valve, value in zip(agent.of, spool_state):
            valve.xv = float(value)
        agent.input(time_s, position, velocity)
        outputs.append(agent.output()["force"].copy())

    arrays = {
        "legacy_static_force": static_force,
        "legacy_fdxv": fdxv,
        "legacy_K": stiffness,
        "legacy_C": damping,
        "legacy_base_spool": base_spool,
        "legacy_base_position": base_position,
        "legacy_time": times,
        "legacy_position": positions,
        "legacy_velocity": velocities,
        "legacy_spool": spool,
        "legacy_force": np.vstack(outputs),
    }
    metadata = {
        "class_name": type(agent).__name__,
        "input_signature": str(inspect.signature(type(agent).input)),
        "output_signature": str(inspect.signature(type(agent).output)),
        "save_signature": str(inspect.signature(type(agent).save)),
        "output_keys": ["force"],
        "result_columns": list(agent.results.columns),
        "result_rows": len(agent.results),
    }
    return metadata, arrays


def _pickle_reference() -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Capture a fitted legacy object to protect old pickle import paths."""

    values = pd.DataFrame(
        {
            "constant": [3.0, 3.0, 3.0],
            "varying": [1.0, 2.0, 5.0],
        }
    )
    scaler = MidpointMinMaxScaler(feature_range=(-1.0, 1.0)).fit(values)
    transformed = scaler.transform(values)
    serialized = pickle.dumps(scaler, protocol=pickle.HIGHEST_PROTOCOL)
    arrays = {
        "pickle_scaler_bytes": np.frombuffer(serialized, dtype=np.uint8).copy(),
        "pickle_scaler_input": values.to_numpy(dtype=float),
        "pickle_scaler_output": transformed,
    }
    metadata = {
        "class_module": type(scaler).__module__,
        "class_name": type(scaler).__name__,
        "columns": list(values.columns),
        "pickle_protocol": pickle.HIGHEST_PROTOCOL,
    }
    return metadata, arrays


def _coupling_reference() -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Capture the rotor-bearing exchange and hierarchical save contract."""

    bearing = alb_harmonic_linear(node_link=12)
    rotor = _ReferenceRotor(bearing.uxy0)
    time_grid = TimeIterDt(bearing.dt, num=2)
    coupling = RsRotorBearingCouple(rotor, time_grid)
    coupling.add_bearing(bearing, node_link=12)
    coupling.init()
    coupling.advance(StepContext(1, bearing.dt, bearing.dt, "dimensional"))
    coupling.advance(StepContext(2, 2.0 * bearing.dt, bearing.dt, "dimensional"))

    assert rotor.last_force is not None
    assert rotor.last_force0 is not None
    assert rotor.last_nodes is not None
    arrays = {
        "coupling_time_history": np.asarray(rotor.time_history, dtype=float),
        "coupling_force_history": np.stack(rotor.force_history),
        "coupling_previous_force_history": np.stack(rotor.force0_history),
        "coupling_last_force": rotor.last_force,
        "coupling_previous_force": rotor.last_force0,
        "coupling_node_links": rotor.last_nodes,
        "coupling_bearing_results": coupling.results["bearing0"].to_numpy(
            dtype=float
        ),
    }
    metadata = {
        "class_name": type(coupling).__name__,
        "bearing_count": len(coupling.bearings),
        "result_keys": sorted(coupling.results),
        "result_rows": len(coupling.results["bearing0"]),
        "save_tree": coupling.save(tofile=False).get_dir(),
    }
    return metadata, arrays


def generate(output_dir: Path) -> tuple[Path, Path]:
    """Generate JSON metadata and lossless numeric arrays."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{REFERENCE_STEM}.json"
    npz_path = output_dir / f"{REFERENCE_STEM}.npz"
    if json_path.exists() or npz_path.exists():
        raise FileExistsError(
            f"Reference already exists; advance the version instead: {REFERENCE_STEM}"
        )

    baseline_commit = _ensure_baseline_source()
    bearing_metadata, bearing_arrays = _bearing_reference()
    legacy_metadata, legacy_arrays = _legacy_linear_reference()
    coupling_metadata, coupling_arrays = _coupling_reference()
    pickle_metadata, pickle_arrays = _pickle_reference()
    arrays = {
        **bearing_arrays,
        **legacy_arrays,
        **coupling_arrays,
        **pickle_arrays,
    }
    export_map = ALB.__dict__["_EXPORTS"]
    export_manifest = sorted(export_map)
    payload = {
        "schema": "alb.interface-contract-reference.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": baseline_commit,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": _distribution_version("scipy"),
            "control": _distribution_version("control"),
            "ross_rotordynamics": _distribution_version("ross-rotordynamics"),
            "scikit_fem": _distribution_version("scikit-fem"),
            "scikit_learn": _distribution_version("scikit-learn"),
        },
        "public_exports": export_manifest,
        "legacy___all__": sorted(ALB.__all__),
        "known_export_drift": sorted(set(export_manifest) - set(ALB.__all__)),
        "public_export_targets": {
            name: {"module": export_map[name][0], "attribute": export_map[name][1]}
            for name in export_manifest
        },
        "legacy_import_surface": LEGACY_IMPORT_SURFACE,
        "signal": _signal_reference(),
        "bearing": bearing_metadata,
        "legacy_linear": legacy_metadata,
        "coupling": coupling_metadata,
        "pickle": pickle_metadata,
        "arrays": _array_manifest(arrays),
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    np.savez(npz_path, **arrays)
    return json_path, npz_path


def main() -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "refs",
        help="Reference output directory.",
    )
    args = parser.parse_args()
    json_path, npz_path = generate(args.output_dir.resolve())
    print(json_path)
    print(npz_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
