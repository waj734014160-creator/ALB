"""Generate coupled-consumer references for the CSOrifice monotonic fix.

The independent scalar oracle was frozen before the production edit in
``csorifice_monotonic_reference_v2``.  This generator reuses that oracle only
inside a temporary patch while collecting the ALBSV direct-spool and S0011
thermal results that depend on CSOrifice.  Existing v1/v2 references are never
overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import runpy
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config.system import NodimALBConfig
from ALB.contracts import BearingInput, ValveOutput
from ALB.systems.alb import DirectSpoolBearingBlock, DirectSpoolBearingInput
from ALB.systems.alb.assembly import nodim_alb


DEFAULT_JSON = ROOT / "refs/csorifice_monotonic_consumers_reference_v2.json"
DEFAULT_NPZ = ROOT / "refs/csorifice_monotonic_consumers_reference_v2.npz"
DIRECT_SOURCE_JSON = ROOT / "refs/albsv_direct_spool_reference_v1.json"
S0011_SOURCE_JSON = ROOT / "refs/thermal_segregated_newton_reference_v2.json"
MONOTONIC_ORACLE = ROOT / "tools/reference/generate_csorifice_monotonic_reference_v2.py"
S0011_TEST = ROOT / "tests/unit/bearing/test_thermal_segregated_newton.py"
ORACLE_SOURCE_COMMIT = "765b9b6"


def _sha256(array: np.ndarray) -> str:
    """Return the SHA-256 digest of an array's contiguous bytes."""
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _direct_spool_arrays() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Collect corrected direct-spool outputs under the independent oracle."""
    source = json.loads(DIRECT_SOURCE_JSON.read_text(encoding="utf-8"))
    arrays: dict[str, np.ndarray] = {}
    statuses: dict[str, Any] = {}
    for case_id, spool in source["spool_cases"].items():
        config = NodimALBConfig.from_dict(source["config"])
        model = nodim_alb(config, thermal_config=config.thermal_config)
        model.init()
        bearing_data = source["bearing_input"]
        block = DirectSpoolBearingBlock(model)
        dto = DirectSpoolBearingInput(
            BearingInput(
                bearing_data["displacement"],
                bearing_data["velocity"],
                bearing_data["time"],
                "nondimensional",
            ),
            ValveOutput(spool, bearing_data["time"], "nondimensional"),
        )
        result = block.step(dto)
        thermal = [pad._last_thermal for pad in model.pads]
        pressure = np.vstack(
            [
                np.asarray(pad.bearing.main_model.latest_result, dtype=float).copy()
                for pad in model.pads
            ]
        )
        histories_before = np.asarray(
            [len(pad.bearing.main_model.adaptive_damp_history) for pad in model.pads],
            dtype=np.int64,
        )
        first_status = bool(model.calc_is_finished())
        histories_after_first = np.asarray(
            [len(pad.bearing.main_model.adaptive_damp_history) for pad in model.pads],
            dtype=np.int64,
        )
        second_status = bool(model.calc_is_finished())
        histories_after_second = np.asarray(
            [len(pad.bearing.main_model.adaptive_damp_history) for pad in model.pads],
            dtype=np.int64,
        )
        prefix = f"direct_spool.{case_id}"
        case_arrays = {
            "input.displacement": dto.bearing.displacement,
            "input.velocity": dto.bearing.velocity,
            "input.spool": dto.spool.spool,
            "output.force": result.force,
            "output.servovalve_spool": np.asarray(
                [servovalve.xv for servovalve in model.servovalves], dtype=float
            ),
            "thermal.t_eff": np.asarray(
                [item["t_eff"] for item in thermal], dtype=float
            ),
            "thermal.viscosity": np.asarray(
                [item["viscosity"] for item in thermal], dtype=float
            ),
            "thermal.iterations": np.asarray(
                [item["iterations"] for item in thermal], dtype=np.int64
            ),
            "thermal.viscosity_fields": np.vstack(
                [np.asarray(item["viscosity_field"], dtype=float) for item in thermal]
            ),
            "pressure_at_completion": pressure,
            "history_lengths_before_query": histories_before,
            "history_lengths_after_first_query": histories_after_first,
            "history_lengths_after_second_query": histories_after_second,
        }
        arrays.update(
            {
                f"{prefix}.{name}": np.asarray(value)
                for name, value in case_arrays.items()
            }
        )
        statuses[case_id] = {
            "block_converged": bool(block.convergence_status.converged),
            "status_first_query": first_status,
            "status_second_query": second_status,
            "thermal_converged_by_pad": [
                bool(item["converged"]) for item in thermal
            ],
        }
    metadata = {
        "bearing_input": source["bearing_input"],
        "spool_cases": source["spool_cases"],
        "status": statuses,
    }
    return arrays, metadata


def _s0011_arrays() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Collect the corrected S0011 thermal diagnostic replay."""
    metadata = json.loads(S0011_SOURCE_JSON.read_text(encoding="utf-8"))
    namespace = runpy.run_path(str(S0011_TEST))
    values = namespace["_run_s0011_reference"](metadata)
    arrays = {
        f"s0011.{name}": np.asarray(value) for name, value in values.items()
    }
    case = metadata["cases"]["s0011_diagnostic_fixed_point"]
    return arrays, {
        "sample_ids": [int(item["sample_id"]) for item in case["records"]],
        "config_provenance": case["config_provenance"],
    }


def main() -> None:
    """Write the non-overwriting coupled-consumer reference package."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError("Refusing to overwrite an existing v2 reference")

    oracle = runpy.run_path(str(MONOTONIC_ORACLE))
    with oracle["_patched_oracle"]():
        direct_arrays, direct_metadata = _direct_spool_arrays()
        s0011_arrays, s0011_metadata = _s0011_arrays()
    arrays = {**direct_arrays, **s0011_arrays}
    metadata = {
        "reference_name": "csorifice_monotonic_consumers_reference_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "oracle_source_commit": ORACLE_SOURCE_COMMIT,
        "oracle_reference": "refs/csorifice_monotonic_reference_v2.json",
        "supersedes_numeric_expectations": [
            "refs/albsv_direct_spool_reference_v1.npz",
            "refs/albsv_convergence_state_reference_v2.npz",
            "refs/thermal_segregated_newton_reference_v2.npz:s0011_*",
        ],
        "environment": {
            "python": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        "direct_spool": direct_metadata,
        "s0011": s0011_metadata,
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
