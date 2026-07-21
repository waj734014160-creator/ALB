"""Freeze the pre-fix ALBSV convergence read-order behavior."""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

import numpy as np

from ALB.config.system import NodimALBConfig
from ALB.contracts import BearingInput, ValveOutput
from ALB.systems.alb import DirectSpoolBearingBlock, DirectSpoolBearingInput
from ALB.systems.alb.assembly import nodim_alb


ROOT = Path(__file__).resolve().parents[2]
SOURCE_JSON = ROOT / "refs/albsv_direct_spool_reference_v1.json"
OUTPUT_JSON = ROOT / "refs/albsv_convergence_state_reference_v2.json"
OUTPUT_NPZ = ROOT / "refs/albsv_convergence_state_reference_v2.npz"


def _sha256(array: np.ndarray) -> str:
    """Return a stable digest for one contiguous numeric array."""

    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def main() -> None:
    """Generate immutable pre-fix diagnostics and the corrected status contract."""

    if OUTPUT_JSON.exists() or OUTPUT_NPZ.exists():
        raise FileExistsError("v2 convergence reference already exists")

    source = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
    arrays: dict[str, np.ndarray] = {}
    cases: dict[str, dict[str, object]] = {}
    for case_id, spool in source["spool_cases"].items():
        config = NodimALBConfig.from_dict(source["config"])
        model = nodim_alb(config, thermal_config=config.thermal_config)
        model.init()
        bearing_data = source["bearing_input"]
        block = DirectSpoolBearingBlock(model)
        result = block.step(
            DirectSpoolBearingInput(
                BearingInput(
                    bearing_data["displacement"],
                    bearing_data["velocity"],
                    bearing_data["time"],
                    "nondimensional",
                ),
                ValveOutput(spool, bearing_data["time"], "nondimensional"),
            )
        )
        pressure_at_completion = np.vstack(
            [
                np.asarray(pad.bearing.main_model.latest_result, dtype=float).copy()
                for pad in model.pads
            ]
        )
        histories_before_query = np.asarray(
            [len(pad.bearing.main_model.adaptive_damp_history) for pad in model.pads],
            dtype=np.int64,
        )
        status_first_query = bool(model.calc_is_finished())
        histories_after_first_query = np.asarray(
            [len(pad.bearing.main_model.adaptive_damp_history) for pad in model.pads],
            dtype=np.int64,
        )
        status_second_query = bool(model.calc_is_finished())
        histories_after_second_query = np.asarray(
            [len(pad.bearing.main_model.adaptive_damp_history) for pad in model.pads],
            dtype=np.int64,
        )

        arrays[f"{case_id}.force"] = np.asarray(result.force, dtype=float)
        arrays[f"{case_id}.pressure_at_completion"] = pressure_at_completion
        arrays[f"{case_id}.history_lengths_before_query"] = histories_before_query
        arrays[f"{case_id}.history_lengths_after_first_query"] = (
            histories_after_first_query
        )
        arrays[f"{case_id}.history_lengths_after_second_query"] = (
            histories_after_second_query
        )
        cases[case_id] = {
            "spool": list(spool),
            "status_first_query_pre_fix": status_first_query,
            "status_second_query_pre_fix": status_second_query,
            "expected_status_after_fix": bool(block.convergence_status.converged),
            "block_status": block.convergence_status.converged,
        }

    metadata = {
        "schema": "alb.albsv-convergence-state-reference.v2",
        "source_reference": str(SOURCE_JSON.relative_to(ROOT)).replace("\\", "/"),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
        "contract": (
            "Completion status and pressure snapshots are read-only after a completed "
            "FilmSystem solve; repeated status queries do not update damping history."
        ),
        "cases": cases,
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _sha256(value),
            }
            for name, value in arrays.items()
        },
    }
    np.savez(OUTPUT_NPZ, **arrays)
    OUTPUT_JSON.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
