"""Exact API replay after simplifying the public bearing runtime boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

import ALB


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs" / "api_convergence_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs" / "api_convergence_reference_v1.npz"


def test_public_liquid_film_result_matches_frozen_reference_exactly() -> None:
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    assert metadata["schema"] == "alb.api-convergence-reference.v1"
    assert hashlib.sha256(REFERENCE_NPZ.read_bytes()).hexdigest() == metadata[
        "npz_sha256"
    ]
    arrays = np.load(REFERENCE_NPZ, allow_pickle=False)

    bearing = ALB.build_bearing(ALB.BearingConfig(metadata["input_spec"]))
    result = bearing.calculate(**metadata["sample"])
    defaults = metadata["resolved_defaults"]

    np.testing.assert_array_equal(result.force, arrays["force"])
    assert result.friction == metadata["outputs"]["friction"]
    assert result.pressure is not None
    assert result.film_thickness is not None
    pressure_shape = tuple(result.diagnostics["field_shape"])
    np.testing.assert_array_equal(
        result.pressure,
        arrays["pressure"].reshape(pressure_shape) * defaults["ps"],
    )
    np.testing.assert_array_equal(
        result.film_thickness,
        arrays["thickness"].reshape(pressure_shape) * defaults["c"],
    )
    assert result.diagnostics["pressure_unit"] == "Pa"
    assert result.diagnostics["film_thickness_unit"] == "m"

    runtime = bearing._runtime
    model = runtime.main_model
    resolved = {
        name: model.args[name]
        for name in ("miu", "c", "r", "l", "ps", "rho", "nx", "nz")
    }
    resolved["max_iter"] = runtime.max_iter
    resolved["error_set"] = runtime.input_args.data.error_set
    assert resolved == defaults
