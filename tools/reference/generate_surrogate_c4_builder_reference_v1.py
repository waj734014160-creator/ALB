"""Freeze surrogate-builder forces before adding package symmetry resolution.

The reference must be generated from the unmodified builder. It records:

* the bare ``family: "surrogate"`` builder force, which is what every package
  produced before ``model_package.symmetry`` existed;
* the existing ``ALBNNC4Canonical`` wrapper force for the same calls, which is
  the target of the new ``symmetry: "c4"`` builder path.

Two synthetic packages are rebuilt from arrays stored in the NPZ so tests do
not depend on sibling projects: one fitted only on ``ex, ey >= 0`` and one
fitted on the full eccentricity plane. The real M42 and M35 deployment
packages are added when present and bound by their manifest SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import torch

import ALB
from ALB.surrogate.inference import (
    ALBNN_BASE_INPUT_COLS,
    ALBNN_OUTPUT_COLS,
    ALBNNC4Canonical,
    SelectiveMinMaxScaler,
)
from ALB.surrogate.package import create_model_package, load_albnn_package

REF_STEM = "surrogate_c4_builder_reference_v1"
SCHEMA = "alb.surrogate-c4-builder-reference.v1"
SYNTHETIC_ARCHITECTURE = [12, 16, 16, 2]
SYNTHETIC_SEED = 20261009

# Nondimensional runtime constants for the synthetic packages. The dimensional
# entries convert displacement/velocity and scale the force exactly as the
# dimensional builder path does.
SYNTHETIC_PARAMETERS = {
    "lambda_value": 0.33,
    "beta_nondim": 0.108,
    "lr": 0.75,
    "cq0": 1.35,
    "cq1": 0.208,
    "cq2": 0.0098,
    "c": 1.2e-4,
    "freq": 50.0,
    "vf": 1.0,
    "ps": 7.0e6,
    "l": 0.06,
    "r": 0.04,
}

# T03 runtime constants (NEW_SMALL_PAPER day2_linearization, 3000 rpm), copied
# from the hash-verified S0011 metadata recorded in t03_results.json.
REAL_PARAMETERS = {
    "lambda_value": 0.3281842325625051,
    "beta_nondim": 0.10837155963302753,
    "lr": 0.75,
    "cq0": 1.3457122291523556,
    "cq1": 0.20818792014191256,
    "cq2": 0.009778479703566049,
    "c": 0.00012,
    "freq": 50.0,
    "vf": 1.0,
    "ps": 7000000.0,
    "l": 0.06,
    "r": 0.04,
}

# Real packages are addressed relative to the ALB_PROJECTS workspace root.
REAL_PACKAGES = {
    "m42": "SURROGATE_TRAIN/models/M0042_no_supply_quasisteady_20261006/model_package",
    "m35": (
        "SURROGATE_TRAIN/outputs/thermal_memory/"
        "S0012_m35_thermal_memory_32w_20260923/baseline_m35"
    ),
}

# The eight T03 static points (all ey < 0), followed by points covering every
# quadrant and both axes with nonzero velocity and spool vectors.
T03_POINTS = [
    (1.0 / 12.0, -0.5),
    (0.0, -0.3),
    (0.0, -0.5),
    (0.1, -0.6),
    (-0.1, -0.4),
    (0.05, -0.7),
    (0.2, -0.2),
    (-0.15, -0.55),
]
EXTRA_POINTS = [
    ((0.3, 0.2), (0.05, -0.08), (0.2, 0.1)),
    ((-0.3, 0.2), (0.08, 0.05), (-0.1, 0.2)),
    ((-0.3, -0.2), (-0.05, 0.08), (-0.2, -0.1)),
    ((0.3, -0.2), (-0.08, -0.05), (0.1, -0.2)),
    ((0.0, 0.4), (0.1, 0.0), (0.0, 0.3)),
    ((-0.4, 0.0), (0.0, 0.1), (-0.3, 0.0)),
    ((0.0, -0.4), (-0.1, 0.0), (0.0, -0.3)),
    ((0.4, 0.0), (0.0, -0.1), (0.3, 0.0)),
]


def _t03_spool(q: np.ndarray) -> np.ndarray:
    """Apply the T03 45/135-degree spool projection."""

    angles = np.deg2rad([45.0, 135.0])
    return 0.3 * np.column_stack((np.cos(angles), np.sin(angles))) @ q


def _query_arrays() -> dict[str, np.ndarray]:
    """Return nondimensional eccentricity, velocity, and spool rows."""

    ecc, vel, spool = [], [], []
    for q in T03_POINTS:
        q_arr = np.asarray(q, dtype=float)
        ecc.append(q_arr)
        vel.append(np.zeros(2))
        spool.append(_t03_spool(q_arr))
    for e, v, s in EXTRA_POINTS:
        ecc.append(np.asarray(e, dtype=float))
        vel.append(np.asarray(v, dtype=float))
        spool.append(np.asarray(s, dtype=float))
    return {
        "query_eccentricity": np.asarray(ecc, dtype=float),
        "query_velocity_nondim": np.asarray(vel, dtype=float),
        "query_spool": np.asarray(spool, dtype=float),
    }


def _synthetic_arrays() -> dict[str, np.ndarray]:
    """Return synthetic weights and two scaler fitting frames."""

    rng = np.random.default_rng(SYNTHETIC_SEED)
    arrays: dict[str, np.ndarray] = {}
    widths = SYNTHETIC_ARCHITECTURE
    for index in range(len(widths) - 1):
        fan_in, fan_out = widths[index], widths[index + 1]
        bound = 1.0 / np.sqrt(fan_in)
        arrays[f"synthetic_layer{index}_weight"] = rng.uniform(
            -bound, bound, size=(fan_out, fan_in)
        ).astype(np.float32)
        arrays[f"synthetic_layer{index}_bias"] = rng.uniform(
            -bound, bound, size=(fan_out,)
        ).astype(np.float32)
    # Two fitting rows per scaler: column minima and maxima. Scalar columns
    # bracket SYNTHETIC_PARAMETERS so no column has a zero range.
    scalar_lo = [0.006, 0.05, 0.5, 1.0, 0.1, 0.005]
    scalar_hi = [1.32, 0.15, 1.0, 1.5, 0.3, 0.015]
    motion_lo = [-0.4, -0.4, -0.6, -0.6]
    motion_hi = [0.4, 0.4, 0.6, 0.6]
    arrays["synthetic_quadrant_fit_frame"] = np.asarray(
        [
            [1.0e-5, 2.0e-6, *motion_lo, *scalar_lo],
            [0.85, 0.85, *motion_hi, *scalar_hi],
        ],
        dtype=float,
    )
    arrays["synthetic_full_fit_frame"] = np.asarray(
        [
            [-0.85, -0.85, *motion_lo, *scalar_lo],
            [0.85, 0.85, *motion_hi, *scalar_hi],
        ],
        dtype=float,
    )
    arrays["synthetic_output_fit_frame"] = np.asarray(
        [[-3.0, -2.5], [3.5, 2.0]],
        dtype=float,
    )
    return arrays


def build_synthetic_package(
    destination: Path,
    arrays: dict[str, np.ndarray],
    fit_frame_key: str,
) -> Path:
    """Write one synthetic v0.4 package from reference arrays.

    Tests reuse this exact construction so package bytes need not be stored.
    """

    state = {}
    for index in range(len(SYNTHETIC_ARCHITECTURE) - 1):
        state[f"layers.{index}.weight"] = torch.from_numpy(
            np.asarray(arrays[f"synthetic_layer{index}_weight"], dtype=np.float32)
        )
        state[f"layers.{index}.bias"] = torch.from_numpy(
            np.asarray(arrays[f"synthetic_layer{index}_bias"], dtype=np.float32)
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = destination.parent / f"{destination.name}_checkpoint.pt"
    torch.save(
        {
            "architecture": list(SYNTHETIC_ARCHITECTURE),
            "activation": "gelu",
            "model_state_dict": state,
        },
        checkpoint,
    )
    input_scaler = SelectiveMinMaxScaler().fit(
        pd.DataFrame(arrays[fit_frame_key], columns=ALBNN_BASE_INPUT_COLS)
    )
    output_scaler = SelectiveMinMaxScaler().fit(
        pd.DataFrame(arrays["synthetic_output_fit_frame"], columns=ALBNN_OUTPUT_COLS)
    )
    create_model_package(
        destination,
        checkpoint=checkpoint,
        input_scaler=input_scaler,
        output_scaler=output_scaler,
        metadata={
            "input_cols": ALBNN_BASE_INPUT_COLS,
            "output_cols": ALBNN_OUTPUT_COLS,
            "use_augment": False,
            "feature_set": "default",
            "target_output": "cartesian",
        },
    )
    return destination


def _dimensional_motion(
    query: dict[str, np.ndarray],
    parameters: dict[str, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Convert nondimensional query rows to SI displacement and velocity."""

    c = parameters["c"]
    omega = 2.0 * np.pi * parameters["freq"]
    displacement = query["query_eccentricity"] * c
    velocity = query["query_velocity_nondim"] * (c * parameters["vf"] * omega)
    return displacement, velocity


def builder_forces(
    package: Path,
    query: dict[str, np.ndarray],
    parameters: dict[str, float],
    *,
    unit_system: str,
    model_package_extra: dict[str, Any] | None = None,
) -> np.ndarray:
    """Evaluate the public surrogate builder on every query row."""

    config = ALB.BearingConfig(
        {
            "family": "surrogate",
            "unit_system": unit_system,
            "time_step": 1.0e-3,
            "node": 0,
            "model_package": {"path": package.name, **(model_package_extra or {})},
            "runtime": {"spool_mode": "external", "parameters": dict(parameters)},
        },
        resource_root=package.parent,
    )
    bearing = ALB.build_bearing(config)
    if unit_system == "dimensional":
        displacement, velocity = _dimensional_motion(query, parameters)
    else:
        displacement = query["query_eccentricity"]
        velocity = query["query_velocity_nondim"]
    forces = []
    for i in range(len(displacement)):
        # Each row is an independent static query at t=0 in a fresh session.
        bearing.reset()
        forces.append(
            bearing.calculate(
                displacement=displacement[i],
                velocity=velocity[i],
                time=0.0,
                spool=query["query_spool"][i],
            ).force
        )
    return np.asarray(forces, dtype=float)


def wrapper_forces(
    package: Path,
    query: dict[str, np.ndarray],
    parameters: dict[str, float],
    *,
    unit_system: str,
) -> np.ndarray:
    """Evaluate ``ALBNNC4Canonical`` with the runtime's call sequence."""

    model = ALBNNC4Canonical(
        load_albnn_package(package, runtime_parameters=dict(parameters))
    )
    nodim = unit_system == "nondimensional"
    if nodim:
        displacement = query["query_eccentricity"]
        velocity = query["query_velocity_nondim"]
    else:
        displacement, velocity = _dimensional_motion(query, parameters)
    forces = []
    for i in range(len(displacement)):
        model.input(displacement[i], velocity[i], query["query_spool"][i], nodim=nodim)
        forces.append(np.asarray(model.output(nodim=nodim), dtype=float).reshape(-1))
    return np.asarray(forces, dtype=float)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_manifest(arrays: dict[str, np.ndarray]) -> dict[str, dict[str, object]]:
    return {
        name: {"shape": list(np.asarray(value).shape), "dtype": str(np.asarray(value).dtype)}
        for name, value in sorted(arrays.items())
    }


def main() -> None:
    baseline_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source_files = [
        "ALB/api/building.py",
        "ALB/api/config.py",
        "ALB/surrogate/package.py",
        "ALB/surrogate/runtime.py",
        "ALB/surrogate/inference.py",
    ]
    arrays: dict[str, np.ndarray] = {}
    query = _query_arrays()
    arrays.update(query)
    synthetic = _synthetic_arrays()
    arrays.update(synthetic)
    cases: dict[str, Any] = {}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        quadrant = build_synthetic_package(
            tmp_root / "quadrant" / "model", synthetic, "synthetic_quadrant_fit_frame"
        )
        full = build_synthetic_package(
            tmp_root / "full" / "model", synthetic, "synthetic_full_fit_frame"
        )
        for unit_system, tag in (("nondimensional", "nondim"), ("dimensional", "dim")):
            arrays[f"synthetic_quadrant_bare_builder_{tag}"] = builder_forces(
                quadrant, query, SYNTHETIC_PARAMETERS, unit_system=unit_system
            )
            arrays[f"synthetic_quadrant_c4_wrapper_{tag}"] = wrapper_forces(
                quadrant, query, SYNTHETIC_PARAMETERS, unit_system=unit_system
            )
            arrays[f"synthetic_full_bare_builder_{tag}"] = builder_forces(
                full, query, SYNTHETIC_PARAMETERS, unit_system=unit_system
            )
        cases["synthetic"] = {
            "architecture": SYNTHETIC_ARCHITECTURE,
            "activation": "gelu",
            "seed": SYNTHETIC_SEED,
            "scaler": "ALB.surrogate.inference.SelectiveMinMaxScaler (input and output)",
            "parameters": SYNTHETIC_PARAMETERS,
            "packages": {
                "quadrant": "input scaler fitted on synthetic_quadrant_fit_frame (ex, ey >= 0)",
                "full": "input scaler fitted on synthetic_full_fit_frame (ex, ey in [-0.85, 0.85])",
            },
        }

    workspace = ROOT.parent
    real_cases: dict[str, Any] = {}
    for name, relative in REAL_PACKAGES.items():
        package = workspace / relative
        if not (package / "manifest.json").is_file():
            real_cases[name] = {"available": False, "relative_path": relative}
            continue
        arrays[f"{name}_bare_builder_dim"] = builder_forces(
            package, query, REAL_PARAMETERS, unit_system="dimensional"
        )
        arrays[f"{name}_c4_wrapper_dim"] = wrapper_forces(
            package, query, REAL_PARAMETERS, unit_system="dimensional"
        )
        real_cases[name] = {
            "available": True,
            "relative_path": relative,
            "manifest_sha256": _sha256(package / "manifest.json"),
        }
    cases["real_packages"] = {"parameters": REAL_PARAMETERS, "packages": real_cases}

    json_path = ROOT / "refs" / f"{REF_STEM}.json"
    npz_path = ROOT / "refs" / f"{REF_STEM}.npz"
    if json_path.exists() or npz_path.exists():
        raise FileExistsError("reference already exists; advance the version instead")
    np.savez(npz_path, **arrays)
    payload = {
        "schema": SCHEMA,
        "purpose": (
            "Pre-change surrogate builder forces (bare ALBNN) and ALBNNC4Canonical "
            "forces for quadrant-I-trained packages; see "
            "tests/regression/surrogate/test_surrogate_c4_builder_reference.py."
        ),
        "baseline_commit": baseline_commit,
        "baseline_note": (
            "Working tree had unrelated uncommitted changes; source digests below "
            "identify the exact files that were executed."
        ),
        "source_sha256": {path: _sha256(ROOT / path) for path in source_files},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "torch": torch.__version__,
        },
        "query": {
            "t03_rows": len(T03_POINTS),
            "extra_rows": len(EXTRA_POINTS),
            "velocity_rule": "dimensional velocity = v * c * vf * 2*pi*freq",
            "t03_spool_rule": "spool = 0.3 * [[cos45, sin45], [cos135, sin135]] @ q",
            "time": 0.0,
            "spool_mode": "external",
        },
        "cases": cases,
        "npz_sha256": _sha256(npz_path),
        "arrays": _array_manifest(arrays),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {json_path} and {npz_path}")


if __name__ == "__main__":
    main()
