"""Generate the pre-refactor reference for mixed-film runtime composition."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import scipy


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config import HydConfig, HybridOrificeConfig, NodimPadConfig
from ALB.contracts import BearingInput
from ALB.physics.bearing.solver import (
    _DimensionalMixedFilmRuntime,
    _NondimensionalMixedFilmRuntime,
)


DEFAULT_JSON = ROOT / "refs" / "mixed_film_composition_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "mixed_film_composition_reference_v1.npz"


def _source_commit() -> str:
    """Return the checked-out commit without modifying repository state."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def _json_value(value: Any) -> Any:
    """Convert NumPy-backed values into stable JSON-compatible values."""

    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _capture_case(
    name: str,
    runtime: Any,
    dto: BearingInput,
    arrays: dict[str, np.ndarray],
) -> dict[str, Any]:
    """Evaluate one runtime and capture its observable numeric and lifecycle state."""

    output = runtime.step(dto)
    result = runtime.result_snapshot()
    force_key = f"{name}.force"
    pressure_key = f"{name}.pressure"
    arrays[force_key] = np.asarray(output.force).copy()
    arrays[pressure_key] = np.asarray(runtime.main_model.latest_result).copy()
    return {
        "dto": {
            "displacement": list(dto.displacement),
            "velocity": list(dto.velocity),
            "time": dto.time,
            "unit_system": dto.unit_system.value,
        },
        "outputs": {
            "force_array": force_key,
            "pressure_array": pressure_key,
            "friction": float(result.values["friction"]),
            "lifecycle_state": runtime.lifecycle_state.value,
            "converged": runtime.convergence_status.converged,
            "iterations": runtime.convergence_status.iterations,
            "final_iter": int(runtime.final_iter),
            "result_metadata": _json_value(dict(result.metadata)),
            "diagnostic_metadata": _json_value(
                dict(runtime.diagnostic_snapshot().metadata)
            ),
        },
    }


def build_reference() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Build deterministic dimensional, hybrid, and nondimensional cases."""

    arrays: dict[str, np.ndarray] = {}
    dimensional_config = {
        "nx": 5,
        "nz": 3,
        "max_iter": 8,
        "error_set": 1.0e-5,
        "save_p": False,
        "save_h": False,
    }
    dimensional_dto = BearingInput(
        displacement=[1.0e-6, -2.0e-6],
        velocity=[3.0e-4, -4.0e-4],
        time=0.125,
        unit_system="dimensional",
    )
    dimensional = _DimensionalMixedFilmRuntime(HydConfig(**dimensional_config))
    dimensional_case = _capture_case(
        "dimensional",
        dimensional,
        dimensional_dto,
        arrays,
    )
    dimensional_case["config"] = dimensional_config
    dimensional_case["orifices"] = None

    hybrid_orifices = {
        "positions": [[0.5, 0.5]],
        "pressure": HydConfig(**dimensional_config).ps,
        "cq": 0.1,
    }
    hybrid = _DimensionalMixedFilmRuntime(
        HydConfig(**dimensional_config),
        orifices=HybridOrificeConfig(**hybrid_orifices),
    )
    hybrid_case = _capture_case(
        "dimensional_hybrid",
        hybrid,
        dimensional_dto,
        arrays,
    )
    hybrid_case["config"] = dimensional_config
    hybrid_case["orifices"] = hybrid_orifices

    nondimensional_config = {
        "lambda_value": 1.2,
        "lr": 1.0,
        "lx": 360.0,
        "lz": 2.0,
        "nx": 5,
        "nz": 3,
        "max_iter": 8,
        "error_set": 1.0e-5,
        "scale_w": 3000.0,
    }
    nondimensional_dto = BearingInput(
        displacement=[0.1, -0.05],
        velocity=[0.01, -0.02],
        time=0.25,
        unit_system="nondimensional",
    )
    nondimensional = _NondimensionalMixedFilmRuntime(
        NodimPadConfig(**nondimensional_config),
        x0=10.0,
    )
    nondimensional_case = _capture_case(
        "nondimensional",
        nondimensional,
        nondimensional_dto,
        arrays,
    )
    nondimensional_case["config"] = nondimensional_config
    nondimensional_case["x0"] = 10.0
    nondimensional_case["orifices"] = None

    payload = {
        "schema": "alb.mixed-film-composition-reference.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": _source_commit(),
        "source_file": "ALB/physics/bearing/solver.py",
        "source_file_sha256": hashlib.sha256(
            (ROOT / "ALB/physics/bearing/solver.py").read_bytes()
        ).hexdigest(),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "platform": platform.platform(),
        },
        "cases": {
            "dimensional": dimensional_case,
            "dimensional_hybrid": hybrid_case,
            "nondimensional": nondimensional_case,
        },
    }
    return payload, arrays


def main() -> None:
    """Write the versioned JSON metadata and lossless NPZ numeric arrays."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError(
            "reference already exists; advance the version instead of overwriting it"
        )
    payload, arrays = build_reference()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.npz, **arrays)
    payload["npz_sha256"] = hashlib.sha256(args.npz.read_bytes()).hexdigest()
    args.json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.json)
    print(args.npz)


if __name__ == "__main__":
    main()
