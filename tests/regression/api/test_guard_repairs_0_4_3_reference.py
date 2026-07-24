"""Exact valid-path regression contracts for the ALB 0.4.3 guards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from tools.reference.generate_alb_0_4_2_repair_reference_v1 import (
    _equilibrium_arrays,
    _facade_arrays,
)
from tools.reference.generate_alb_0_4_3_guard_reference_v1 import (
    _surrogate_arrays,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs/alb_0_4_3_guard_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs/alb_0_4_3_guard_reference_v1.npz"


def test_guard_repairs_preserve_valid_outputs_exactly() -> None:
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    assert metadata["schema"] == "alb.0.4.3-guard-reference.v1"
    assert (
        hashlib.sha256(REFERENCE_NPZ.read_bytes()).hexdigest()
        == metadata["npz_sha256"]
    )

    current_arrays: dict[str, np.ndarray] = {}
    current_cases: dict[str, object] = {}
    for name, build in (
        ("equilibrium", _equilibrium_arrays),
        ("facades", _facade_arrays),
        ("surrogate", _surrogate_arrays),
    ):
        case_metadata, arrays = build()
        current_cases[name] = case_metadata
        current_arrays.update(arrays)

    assert current_cases == metadata["cases"]
    with np.load(REFERENCE_NPZ, allow_pickle=False) as reference:
        assert set(reference.files) == set(current_arrays)
        for name, actual in current_arrays.items():
            np.testing.assert_array_equal(actual, reference[name])
