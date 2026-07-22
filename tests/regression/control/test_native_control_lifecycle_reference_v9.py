"""Exact regression for native LQG, repetitive, and servovalve lifecycles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from tools.reference.generate_native_control_lifecycle_reference_v9 import (
    collect_reference_arrays,
)


ROOT = Path(__file__).resolve().parents[3]
REF_JSON = ROOT / "refs/native_control_lifecycle_reference_v9.json"
REF_NPZ = ROOT / "refs/native_control_lifecycle_reference_v9.npz"


def _array_sha256(value: np.ndarray) -> str:
    """Return the reference-format digest for one array."""

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def test_native_control_trajectories_match_pre_migration_reference_exactly():
    """Lifecycle separation must not alter any frozen numerical trajectory."""

    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    actual = collect_reference_arrays()
    with np.load(REF_NPZ, allow_pickle=False) as expected:
        assert set(actual) == set(expected.files) == set(metadata["arrays"])
        for name, value in actual.items():
            np.testing.assert_array_equal(value, expected[name], err_msg=name)
            assert list(value.shape) == metadata["arrays"][name]["shape"]
            assert str(value.dtype) == metadata["arrays"][name]["dtype"]
            assert _array_sha256(value) == metadata["arrays"][name]["sha256"]
