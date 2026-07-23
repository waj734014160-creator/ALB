"""Freeze the complete ALB bearing unit boundary before adapter extraction."""

from __future__ import annotations

import argparse
import copy
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

from ALB.config import NodimALBConfig
from ALB.systems.alb.factories import nodim_alb
from tools.reference.generate_albsv_direct_spool_reference_v1 import (
    CONFIG as BASE_CONFIG,
)


DEFAULT_JSON = ROOT / "refs" / "bearing_unit_boundary_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "bearing_unit_boundary_reference_v1.npz"
SCALE_VALUES = {
    "Sx": 8.0e-5,
    "Sp": 7.0e6,
    "r": 0.04,
    "l": 0.06,
    "w_rpm": 3_000.0,
    "vf": 1.0,
}


def _config() -> NodimALBConfig:
    """Return a scaled nondimensional bearing configuration."""

    payload = copy.deepcopy(BASE_CONFIG)
    payload.update(
        {
            "nx": 15,
            "nz": 7,
            "thermal_enabled": False,
            "alb": "ALBSV",
            "servo": "static",
            "switch": False,
            "scale_miu": 0.0195,
            "scale_c": SCALE_VALUES["Sx"],
            "scale_r": SCALE_VALUES["r"],
            "scale_l": SCALE_VALUES["l"],
            "scale_ps": SCALE_VALUES["Sp"],
            "scale_rho": 872.0,
            "scale_w": SCALE_VALUES["w_rpm"],
            "vf": SCALE_VALUES["vf"],
        }
    )
    payload.pop("thermal", None)
    return NodimALBConfig.from_dict(payload)


def collect_reference() -> tuple[dict[str, np.ndarray], dict[str, object]]:
    """Collect exact bidirectional scale examples and real force conversion."""

    config = _config()
    model = nodim_alb(config)
    model.init()
    displacement_nd = np.asarray([0.1, -0.2], dtype=float)
    velocity_nd = np.asarray([0.03, -0.04], dtype=float)
    spool = np.asarray([0.2, -0.3], dtype=float)
    model.input(
        displacement_nd,
        velocity_nd,
        0.0,
        sv=spool,
        nodim=True,
    )
    output = model.output(nodim=True)

    angular_speed = SCALE_VALUES["w_rpm"] / 60.0 * 2.0 * np.pi
    sx = SCALE_VALUES["Sx"]
    st = 1.0 / (SCALE_VALUES["vf"] * angular_speed)
    sv = sx / st
    sp = SCALE_VALUES["Sp"]
    sf = sp * SCALE_VALUES["l"] * SCALE_VALUES["r"] / 2.0

    time_nd = np.asarray([0.0, 0.25, 1.0], dtype=float)
    pressure_nd = np.vstack(
        [
            np.asarray(pad.main_model.latest_result, dtype=float)
            for pad in model.pads
        ]
    )
    per_pad_force_nd = np.vstack(
        [
            np.asarray(
                pad.calc_capacity(calc=False, nodim=True),
                dtype=float,
            )
            for pad in model.pads
        ]
    )
    per_pad_force_dim = np.vstack(
        [
            np.asarray(
                pad.calc_capacity(calc=False, nodim=False),
                dtype=float,
            )
            for pad in model.pads
        ]
    )
    arrays = {
        "input.displacement_nondimensional": displacement_nd,
        "input.displacement_dimensional": displacement_nd * sx,
        "input.velocity_nondimensional": velocity_nd,
        "input.velocity_dimensional": velocity_nd * sv,
        "input.spool_nondimensional": spool,
        "context.time_nondimensional": time_nd,
        "context.time_dimensional": time_nd * st,
        "pressure.nondimensional": pressure_nd,
        "pressure.dimensional": pressure_nd * sp,
        "force.per_pad_nondimensional": per_pad_force_nd,
        "force.per_pad_dimensional": per_pad_force_dim,
        "force.total_nondimensional": np.asarray(output["force"], dtype=float),
        "force.total_dimensional": np.sum(per_pad_force_dim, axis=0),
        "residual.local": np.asarray(
            [pad.main_model.errors for pad in model.pads],
            dtype=float,
        ),
        "iterations.local": np.asarray(
            [pad.final_iter for pad in model.pads],
            dtype=np.int64,
        ),
    }
    np.testing.assert_array_equal(
        per_pad_force_dim,
        per_pad_force_nd * sf,
    )
    contracts: dict[str, object] = {
        "schema": "alb.bearing-scale-set.v1",
        "scale_id": "stage0-explicit-film-scales",
        "source_unit": "nondimensional",
        "target_unit": "dimensional",
        "scale_definition": "dimensional_per_nondimensional",
        "applied_transforms": [
            "rotor_to_bearing",
            "bearing_to_rotor",
        ],
        "Sx": sx,
        "St": st,
        "Sv": sv,
        "Sf": sf,
        "Sp": sp,
        "velocity_definition_id": "journal_surface_time.v1",
        "residual_definition_id": "film.relative_pressure_change.v1",
        "residual_unit": "nondimensional",
        "provenance": "NodimPadConfig explicit scale_* fields",
        "global_context": {
            "step_index": 4,
            "time": float(time_nd[-1] * st),
            "dt": float(0.25 * st),
            "unit_system": "dimensional",
        },
        "bearing_local_context": {
            "step_index": 4,
            "time": float(time_nd[-1]),
            "dt": 0.25,
            "unit_system": "nondimensional",
        },
    }
    return arrays, contracts


def _sha256_array(value: np.ndarray) -> str:
    """Return the stable byte digest for one array."""

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def generate(output_json: Path, output_npz: Path) -> None:
    """Generate the reference pair without replacing prior evidence."""

    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite reference: {output}")
    arrays, contracts = collect_reference()
    metadata = {
        "schema": "alb.bearing-unit-boundary-reference.v1",
        "baseline_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).strip(),
        "environment": {
            "python": sys.version,
            "numpy": importlib.metadata.version("numpy"),
            "scipy": importlib.metadata.version("scipy"),
            "scikit-fem": importlib.metadata.version("scikit-fem"),
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
