"""Exact pre-0.3 reference for the complete bearing unit boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from tools.reference.generate_bearing_unit_boundary_reference_v1 import (
    collect_reference,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs" / "bearing_unit_boundary_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs" / "bearing_unit_boundary_reference_v1.npz"


def _sha256_array(value: np.ndarray) -> str:
    """Return the stable reference digest for one array."""

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def test_bearing_unit_boundary_matches_reference_exactly() -> None:
    """Protect time, motion, pressure, force, and residual scale semantics."""

    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    assert metadata["schema"] == "alb.bearing-unit-boundary-reference.v1"
    actual, contracts = collect_reference()
    assert contracts == metadata["contracts"]

    with np.load(REFERENCE_NPZ, allow_pickle=False) as frozen:
        assert set(actual) == set(frozen.files) == set(metadata["arrays"])
        for name in sorted(frozen.files):
            expected = frozen[name]
            descriptor = metadata["arrays"][name]
            assert list(expected.shape) == descriptor["shape"]
            assert str(expected.dtype) == descriptor["dtype"]
            assert _sha256_array(expected) == descriptor["sha256"]
            np.testing.assert_array_equal(actual[name], expected, err_msg=name)
