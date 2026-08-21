"""Freeze the legacy Q1 pressure/thermal ALB path before mesh refactoring."""

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

from ALB.api import build_bearing, load_bearing_config


DEFAULT_CONFIG = Path(
    r"F:\BaiduSyncdisk\博士论文\PAPER_WORK\task\PAPER\config\alb12.json5"
)
DEFAULT_JSON = ROOT / "refs" / "mesh_independence_legacy_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "mesh_independence_legacy_reference_v1.npz"
SPOOL_CASES = {"supply_off": (0.0, 0.0), "supply_on": (0.2, 0.2)}
DISPLACEMENT = (-24.0e-6, -36.0e-6)
VELOCITY = (0.0, 0.0)
NX = 10
NZ = 5


def _sha256_array(array: np.ndarray) -> str:
    """Return the digest of one contiguous numerical array."""

    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _git_head() -> str:
    """Return the source commit used to generate the frozen evidence."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _legacy_config(path: Path):
    """Derive the small legacy case without changing the source document."""

    return load_bearing_config(path).with_overrides(
        {
            "film.circumferential_elements": NX,
            "film.axial_elements": NZ,
            "film.save_pressure": False,
            "film.save_thickness": False,
            "control.mode": "external_spool",
            "control.gains": None,
        }
    )


def _orifice_arrays(runtime: Any) -> tuple[np.ndarray, np.ndarray]:
    """Return pad-ordered point flows and resolved point pressures."""

    flow_rows = []
    pressure_rows = []
    for pad in runtime._pads:
        model = pad.bearing.main_model
        orifice = pad.bearing.simple_models[0]
        flow_rows.append(np.asarray(orifice.qn, dtype=float).reshape(-1))
        pressure_rows.append(
            np.asarray([node.p for node in orifice.node], dtype=float)
        )
    return np.vstack(flow_rows), np.vstack(pressure_rows)


def _run_case(config, spool: tuple[float, float]):
    """Run one cold-start public calculation and collect full legacy fields."""

    bearing = build_bearing(config)
    result = bearing.calculate(
        displacement=DISPLACEMENT,
        velocity=VELOCITY,
        time=0.0,
        spool=spool,
    )
    runtime = bearing._runtime
    pad_results = [pad.result_snapshot() for pad in runtime._pads]
    pressure = np.vstack(
        [
            np.asarray(pad.bearing.main_model.output(), dtype=float)
            for pad in runtime._pads
        ]
    )
    thickness = np.vstack(
        [
            np.asarray(
                [node.h for node in pad.bearing.main_model.nodes.values()],
                dtype=float,
            )
            for pad in runtime._pads
        ]
    )
    flows, point_pressure = _orifice_arrays(runtime)
    arrays = {
        "input.displacement": np.asarray(DISPLACEMENT, dtype=float),
        "input.velocity": np.asarray(VELOCITY, dtype=float),
        "input.spool": np.asarray(spool, dtype=float),
        "output.force": np.asarray(result.force, dtype=float),
        "output.pad_force": np.asarray(
            result.details.values["pad_force"], dtype=float
        ),
        "output.friction": np.asarray([result.friction], dtype=float),
        "film.pressure_fields": pressure,
        "film.thickness_fields": thickness,
        "thermal.temperature_fields": np.vstack(
            [np.asarray(item.values["temperature"], dtype=float) for item in pad_results]
        ),
        "thermal.viscosity_fields": np.vstack(
            [
                np.asarray(item.values["viscosity_field"], dtype=float)
                for item in pad_results
            ]
        ),
        "thermal.t_eff": np.asarray(
            [item.values["t_eff"] for item in pad_results], dtype=float
        ),
        "thermal.iterations": np.asarray(
            [item.metadata["iterations"] for item in pad_results], dtype=np.int64
        ),
        "orifice.flow_fields": flows,
        "orifice.pressure_fields": point_pressure,
    }
    status = {
        "converged": bool(result.convergence.converged),
        "iterations": (
            None
            if result.convergence.iterations is None
            else int(result.convergence.iterations)
        ),
        "message": str(result.convergence.message),
        "thermal_converged_by_pad": [
            bool(item.metadata["converged"]) for item in pad_results
        ],
        "thermal_iterations_by_pad": [
            int(item.metadata["iterations"]) for item in pad_results
        ],
    }
    return arrays, status


def generate(config_path: Path, output_json: Path, output_npz: Path) -> None:
    """Write a new immutable JSON/NPZ reference pair."""

    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite reference: {output}")

    config = _legacy_config(config_path)
    arrays: dict[str, np.ndarray] = {}
    status = {}
    for case_id, spool in SPOOL_CASES.items():
        case_arrays, case_status = _run_case(config, spool)
        arrays.update(
            {f"{case_id}.{name}": value for name, value in case_arrays.items()}
        )
        status[case_id] = case_status

    metadata = {
        "schema": "alb.mesh-independence-legacy-reference.v1",
        "baseline_commit": _git_head(),
        "source_config": str(config_path.resolve()),
        "derived_spec": config.to_dict()["spec"],
        "environment": {
            "python": sys.version,
            "numpy": importlib.metadata.version("numpy"),
            "scipy": importlib.metadata.version("scipy"),
            "scikit-fem": importlib.metadata.version("scikit-fem"),
        },
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
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    np.savez_compressed(output_npz, **arrays)
    print(f"Wrote {output_json}")
    print(f"Wrote {output_npz}")


def main() -> None:
    """Parse output paths and generate the pre-change reference."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    generate(args.config, args.output_json, args.output_npz)


if __name__ == "__main__":
    main()
