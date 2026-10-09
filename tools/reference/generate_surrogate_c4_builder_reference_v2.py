"""Freeze default 15-percent-quadrant C4 builder forces near every half-axis.

Real packages use the same ALB_PROJECTS-relative paths and manifest digests
as v1. Missing external packages are recorded for clean regression skips.
Run with OMP_NUM_THREADS=2 and MKL_THREADING_LAYER=SEQUENTIAL.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import torch

from ALB.surrogate.features import C4_DEFAULT_BLEND_RATIO
from tools.reference.generate_surrogate_c4_builder_reference_v1 import (
    REAL_PACKAGES,
    REAL_PARAMETERS,
    _array_manifest,
    _sha256,
    builder_forces,
)

REF_STEM = "surrogate_c4_builder_reference_v2"
SCHEMA = "alb.surrogate-c4-builder-reference.v2"


def query_arrays() -> dict[str, np.ndarray]:
    """Include both sides, the axis, band edges, and interior quadrant rows."""
    offsets = np.array([-25.0, -13.5, -5.0, 0.0, 5.0, 13.5, 25.0, 45.0])
    angles = np.deg2rad(np.concatenate([offsets + 90.0 * k for k in range(4)]))
    e = 0.5 * np.column_stack((np.cos(angles), np.sin(angles)))
    v = np.tile([0.03, -0.04], (len(e), 1))
    s = np.tile([0.2, -0.1], (len(e), 1))
    return {"query_eccentricity": e, "query_velocity_nondim": v, "query_spool": s}


def main() -> None:
    json_path = ROOT / "refs" / f"{REF_STEM}.json"
    npz_path = ROOT / "refs" / f"{REF_STEM}.npz"
    if json_path.exists() or npz_path.exists():
        raise FileExistsError("reference already exists; advance the version instead")
    arrays = query_arrays()
    package = ROOT.parent / REAL_PACKAGES["m42"]
    record = {"available": (package / "manifest.json").is_file(),
              "relative_path": REAL_PACKAGES["m42"]}
    if record["available"]:
        record["manifest_sha256"] = _sha256(package / "manifest.json")
        for units, tag in (("nondimensional", "nondim"), ("dimensional", "dim")):
            arrays[f"m42_c4_blend_builder_{tag}"] = builder_forces(
                package, arrays, REAL_PARAMETERS, unit_system=units,
                model_package_extra={"symmetry": "c4"},
            )
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    np.savez(npz_path, **arrays)
    sources = ["ALB/surrogate/inference.py", "ALB/surrogate/package.py",
               "ALB/api/config.py", "ALB/api/_config_fields.py", "ALB/api/building.py",
               "tools/reference/generate_surrogate_c4_builder_reference_v2.py"]
    payload = {
        "schema": SCHEMA, "purpose": "Default smooth C4 builder forces for M0042.",
        "blend_ratio": C4_DEFAULT_BLEND_RATIO,
        "baseline_commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "baseline_note": "Source digests identify the executed working-tree implementation.",
        "source_sha256": {p: _sha256(ROOT / p) for p in sources},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "torch": torch.__version__},
        "parameters": REAL_PARAMETERS, "package": record,
        "query": {"rows": len(arrays["query_eccentricity"]), "time": 0.0,
                  "spool_mode": "external", "offsets_deg": [-25, -13.5, -5, 0, 5, 13.5, 25, 45]},
        "npz_sha256": _sha256(npz_path), "arrays": _array_manifest(arrays),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {json_path} and {npz_path}")


if __name__ == "__main__":
    main()
