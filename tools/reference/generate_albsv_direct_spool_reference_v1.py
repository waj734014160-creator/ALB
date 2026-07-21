"""Generate the pre-adapter ALBSV direct-spool numerical reference."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config.system import NodimALBConfig
from ALB.systems.alb.assembly import nodim_alb


DEFAULT_JSON = ROOT / "refs" / "albsv_direct_spool_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "albsv_direct_spool_reference_v1.npz"

BEARING_INPUT = {
    "displacement": [0.1, -0.2],
    "velocity": [0.03, -0.04],
    "time": 0.0,
}
SPOOL_CASES = {
    "zero": [0.0, 0.0],
    "nonzero": [0.2, -0.3],
    "reversed": [-0.2, 0.3],
}
CONFIG = {
    "alb": "ALBSV",
    "servo": "static",
    "switch": False,
    "dt": 6.667e-4,
    "lambda_value": 1.2,
    "lr": 1.0,
    "lx": 80.0,
    "lz": 2.0,
    "nx": 79,
    "nz": 39,
    "coe": False,
    "max_iter": 80,
    "error_set": 1e-6,
    "damp": 0.70,
    "position": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
    "cq0": 6.0557,
    "cq1": 0.02313,
    "cq2": 0.002173,
    "ps": 1.0,
    "p0": 0.0,
    "xrange": [0.49, 0.51],
    "zrange": [0.2, 0.8],
    "h_tank": 2.0,
    "thermal_enabled": True,
    "thermal": {
        "args_nodim": True,
        "t_in": 1.0,
        "t_supply": 1.0,
        "t_ref": 1.0,
        "beta_nondim": 0.1083715596,
        "delta_t_scale": 1.0,
        "cp_lub": 1.0,
        "heat_partition": 0.9,
        "k_lub": 0.0,
        "relax": 0.6,
        "max_iter": 80,
        "tol": 1e-6,
        "coupling": "full",
        "pressure_backend": "skfem",
    },
}


def _sha256_array(array: np.ndarray) -> str:
    """Return a stable digest for one contiguous array."""

    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _git_head() -> str:
    """Return the source commit used for reference generation."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _run_case(spool: list[float]) -> tuple[dict[str, np.ndarray], dict]:
    """Execute one legacy direct-spool sequence exactly once."""

    config = NodimALBConfig.from_dict(CONFIG)
    model = nodim_alb(config, thermal_config=config.thermal_config)
    model.init()
    model.input(
        np.asarray(BEARING_INPUT["displacement"], dtype=float),
        np.asarray(BEARING_INPUT["velocity"], dtype=float),
        BEARING_INPUT["time"],
        sv=np.asarray(spool, dtype=float),
        nodim=True,
    )
    output = model.output(nodim=True)
    thermal = [pad._last_thermal for pad in model.pads]
    arrays = {
        "input.displacement": np.asarray(BEARING_INPUT["displacement"], dtype=float),
        "input.velocity": np.asarray(BEARING_INPUT["velocity"], dtype=float),
        "input.spool": np.asarray(spool, dtype=float),
        "output.force": np.asarray(output["force"], dtype=float),
        "output.friction": np.asarray([output["friction"]], dtype=float),
        "output.servovalve_spool": np.asarray(
            [servovalve.xv for servovalve in model.servovalves], dtype=float
        ),
        "thermal.t_eff": np.asarray([item["t_eff"] for item in thermal], dtype=float),
        "thermal.viscosity": np.asarray(
            [item["viscosity"] for item in thermal], dtype=float
        ),
        "thermal.iterations": np.asarray(
            [item["iterations"] for item in thermal], dtype=np.int64
        ),
        "thermal.viscosity_fields": np.vstack(
            [np.asarray(item["viscosity_field"], dtype=float) for item in thermal]
        ),
        "film.pressure_fields": np.vstack(
            [
                np.asarray(pad.bearing.main_model.output(), dtype=float)
                for pad in model.pads
            ]
        ),
    }
    status = {
        "unit_system": model.unit_system,
        "calculation_finished": bool(model.calc_is_finished()),
        "thermal_converged_by_pad": [bool(item["converged"]) for item in thermal],
        "solver_used_by_pad": [str(item["solver_used"]) for item in thermal],
    }
    return arrays, status


def generate(output_json: Path, output_npz: Path) -> None:
    """Write the JSON/NPZ pair without overwriting existing evidence."""

    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite reference: {output}")
    arrays = {}
    status = {}
    for case_id, spool in SPOOL_CASES.items():
        case_arrays, case_status = _run_case(spool)
        arrays.update(
            {f"{case_id}.{name}": value for name, value in case_arrays.items()}
        )
        status[case_id] = case_status
    metadata = {
        "schema": "alb.albsv-direct-spool-reference.v1",
        "baseline_commit": _git_head(),
        "environment": {
            "python": sys.version,
            "numpy": importlib.metadata.version("numpy"),
            "scipy": importlib.metadata.version("scipy"),
            "scikit-fem": importlib.metadata.version("scikit-fem"),
        },
        "bearing_input": BEARING_INPUT,
        "spool_cases": SPOOL_CASES,
        "config": CONFIG,
        "status": status,
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _sha256_array(value),
            }
            for name, value in arrays.items()
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
    """Parse optional output paths and generate the reference."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    generate(args.output_json, args.output_npz)


if __name__ == "__main__":
    main()
