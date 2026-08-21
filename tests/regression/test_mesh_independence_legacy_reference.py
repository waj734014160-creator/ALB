"""Exact regression guard for the pre-explicit-mesh pressure/thermal path."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ALB.api import BearingConfig
from tools.reference.generate_mesh_independence_legacy_reference_v1 import (
    SPOOL_CASES,
    _run_case,
)


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_JSON = ROOT / "refs" / "mesh_independence_legacy_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs" / "mesh_independence_legacy_reference_v1.npz"


def test_legacy_pressure_thermal_path_is_elementwise_exact():
    """Keep every frozen legacy array unchanged when mesh fields are absent."""

    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    config = BearingConfig(metadata["derived_spec"])
    with np.load(REFERENCE_NPZ) as expected:
        for case_id, spool in SPOOL_CASES.items():
            arrays, _ = _run_case(config, spool)
            for name, actual in arrays.items():
                np.testing.assert_array_equal(actual, expected[f"{case_id}.{name}"])
