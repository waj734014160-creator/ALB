"""Freeze the pre-0.3 ALB runtime, coupling, history, save, and scale behavior.

The reference deliberately combines a small real nondimensional ALBSV case
with the existing real ROSS 4-DOF coupling oracle.  It is generated before the
strict runtime migration so later adapters, recorders, and unit conversion
objects can be checked against the exact 0.2 numerical results.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config import ALBConfig, NodimALBConfig
from ALB.contracts import (
    BearingInput,
    DirectSpoolBearingInput,
    ValveOutput,
)
from ALB.core import Signal
from ALB.systems.alb import DirectSpoolBearingBlock
from ALB.systems.alb.factories import nodim_alb
from ALB.systems.alb.runtime import ALB
from tools.reference.generate_albsv_direct_spool_reference_v1 import (
    CONFIG as DIRECT_SPOOL_CONFIG,
)
from tools.reference.generate_rotor_dof_coupling_reference_v4 import (
    _run_case as run_ross_coupling_case,
)


DEFAULT_JSON = ROOT / "refs" / "alb_runtime_transition_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "alb_runtime_transition_reference_v1.npz"
DT = 6.667e-4
INPUTS = (
    {
        "time": 0.0,
        "displacement": [0.1, -0.2],
        "velocity": [0.03, -0.04],
        "spool": [0.2, -0.3],
    },
    {
        "time": DT,
        "displacement": [0.08, -0.17],
        "velocity": [0.01, -0.02],
        "spool": [-0.15, 0.25],
    },
)


def _reference_config() -> dict[str, Any]:
    """Return a compact deterministic ALBSV configuration."""

    payload = copy.deepcopy(DIRECT_SPOOL_CONFIG)
    payload.update(
        {
            "alb": "ALBSV",
            "servo": "static",
            "switch": False,
            "dt": DT,
            "nx": 15,
            "nz": 7,
            "thermal_enabled": False,
        }
    )
    payload.pop("thermal", None)
    return payload


def _new_direct_spool_model():
    """Build one fresh real nondimensional direct-spool ALB."""

    config = NodimALBConfig.from_dict(_reference_config())
    model = nodim_alb(config)
    model.init()
    return model


def _run_raw_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Run the legacy calculation-in-output lifecycle for two samples."""

    model = _new_direct_spool_model()
    force_rows = []
    friction_rows = []
    for sample in INPUTS:
        model.input(
            DirectSpoolBearingInput(
                BearingInput(
                    sample["displacement"],
                    sample["velocity"],
                    sample["time"],
                    "nondimensional",
                ),
                ValveOutput(
                    sample["spool"],
                    sample["time"],
                    "nondimensional",
                ),
            )
        )
        model.evaluate()
        output = model.output()
        force_rows.append(np.asarray(output.force, dtype=float))
        friction_rows.append(float(model.result_snapshot().values["friction"]))
        model.finish_signal()

    save_tree = model.save(tofile=False, path="runtime_reference", name="alb")
    arrays = {
        "raw.force": np.asarray(force_rows, dtype=float),
        "raw.friction": np.asarray(friction_rows, dtype=float),
        "raw.signal_history": model.results.to_numpy(dtype=float),
        "raw.final_spool": np.asarray(
            [valve.xv for valve in model.servovalves], dtype=float
        ),
        "raw.final_pressure": np.vstack(
            [
                np.asarray(
                    getattr(pad, "bearing", pad).main_model.latest_result,
                    dtype=float,
                )
                for pad in model.pads
            ]
        ),
    }
    metadata = {
        "signal_history_columns": list(model.results.columns),
        "save_tree": save_tree.get_dir(),
        "save_snapshot_schema": save_tree.result_snapshot().metadata["schema"],
        "save_snapshot_root": save_tree.result_snapshot().metadata["logical_root"],
    }
    return arrays, metadata


def _run_block_case() -> dict[str, np.ndarray]:
    """Run the existing strict DTO block over the same two inputs."""

    model = _new_direct_spool_model()
    block = DirectSpoolBearingBlock(model)
    force_rows = []
    for sample in INPUTS:
        output = block.step(
            DirectSpoolBearingInput(
                BearingInput(
                    sample["displacement"],
                    sample["velocity"],
                    sample["time"],
                    "nondimensional",
                ),
                ValveOutput(
                    sample["spool"],
                    sample["time"],
                    "nondimensional",
                ),
            )
        )
        force_rows.append(output.force)
        model.finish_signal()
    return {
        "block.force": np.asarray(force_rows, dtype=float),
        "block.signal_history": model.results.to_numpy(dtype=float),
    }


class _ScalePad:
    """Minimal pad exposing the historical dimensional scale source."""

    def __init__(self, *, clearance: float, rpm: float, velocity_factor: float):
        self.signal = Signal(sys=self)
        self.main_model = SimpleNamespace(
            args={
                "c": clearance,
                "w": rpm,
                "vf": velocity_factor,
            }
        )

    def init(self) -> None:
        """Provide the lifecycle hook required by the auto-initializing runtime."""


def _run_scale_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Capture the historical implicit dimensional/nondimensional conversion."""

    config = ALBConfig(
        c=2.5e-4,
        w=3_600.0,
        node_link=2,
        controller_config=None,
        switch=False,
    )
    model = ALB(
        [_ScalePad(clearance=9.9e-4, rpm=99.0, velocity_factor=0.5)],
        [],
        controller=None,
        alb_config=config,
    )
    displacement_nd = np.asarray([0.25, -0.4], dtype=float)
    velocity_nd = np.asarray([0.03, -0.08], dtype=float)
    arrays = {
        "scale.input_displacement_nondimensional": displacement_nd,
        "scale.input_velocity_nondimensional": velocity_nd,
        "scale.displacement_dimensional": displacement_nd * model._c,
        "scale.velocity_dimensional": (
            velocity_nd * model._c * model._vf * model._w_rad
        ),
        "scale.roundtrip_displacement_nondimensional": displacement_nd,
        "scale.roundtrip_velocity_nondimensional": velocity_nd,
    }
    metadata = {
        "clearance_scale": float(model._c),
        "rpm_scale": float(model._w),
        "angular_speed_scale": float(model._w_rad),
        "velocity_factor": float(model._vf),
        "velocity_scale": float(model._c * model._vf * model._w_rad),
        "scale_definition": "dimensional_per_nondimensional",
    }
    return arrays, metadata


def collect_reference() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Collect every deterministic array and non-array contract."""

    raw_arrays, raw_metadata = _run_raw_case()
    arrays = {
        **raw_arrays,
        **_run_block_case(),
        **{
            f"coupling.{name}": value
            for name, value in run_ross_coupling_case(4).items()
        },
    }
    scale_arrays, scale_metadata = _run_scale_case()
    arrays.update(scale_arrays)
    metadata = {
        "raw": raw_metadata,
        "scale": scale_metadata,
    }
    return arrays, metadata


def _sha256_array(value: np.ndarray) -> str:
    """Return a digest of one contiguous array."""

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _git_head() -> str:
    """Return the committed source baseline."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def generate(output_json: Path, output_npz: Path) -> None:
    """Generate the versioned reference without overwriting prior evidence."""

    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite reference: {output}")
    arrays, contracts = collect_reference()
    metadata = {
        "schema": "alb.runtime-transition-reference.v1",
        "baseline_commit": _git_head(),
        "random_seed": 20260723,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": importlib.metadata.version("numpy"),
            "scipy": importlib.metadata.version("scipy"),
            "scikit-fem": importlib.metadata.version("scikit-fem"),
            "ross-rotordynamics": importlib.metadata.version(
                "ross-rotordynamics"
            ),
        },
        "config": _reference_config(),
        "inputs": INPUTS,
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
    output_json.parent.mkdir(parents=True, exist_ok=True)
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
