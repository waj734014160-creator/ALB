"""Exact successful-path contracts for the ALB 0.4.2 review repairs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from tools.reference.generate_alb_0_4_2_repair_reference_v1 import (
    BASELINE_COMMIT,
    _adapter_arrays,
    _equilibrium_arrays,
    _facade_arrays,
    _whirl_arrays,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs/alb_0_4_2_repair_contract_v1.json"
REFERENCE_NPZ = ROOT / "refs/alb_0_4_2_repair_contract_v1.npz"


@pytest.fixture(scope="module")
def reference_metadata() -> dict[str, object]:
    """Load immutable reference metadata."""

    return json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def reference_arrays() -> dict[str, np.ndarray]:
    """Load immutable reference arrays."""

    with np.load(REFERENCE_NPZ) as archive:
        return {name: archive[name].copy() for name in archive.files}


def test_reference_identity_and_shapes(
    reference_metadata: dict[str, object],
    reference_arrays: dict[str, np.ndarray],
) -> None:
    """Protect the baseline commit, archive digest, dtype, and shape."""

    assert reference_metadata["baseline_commit"] == BASELINE_COMMIT
    assert reference_metadata["npz_sha256"] == hashlib.sha256(
        REFERENCE_NPZ.read_bytes()
    ).hexdigest()
    manifest = reference_metadata["arrays"]
    assert isinstance(manifest, dict)
    assert set(manifest) == set(reference_arrays)
    for name, array in reference_arrays.items():
        item = manifest[name]
        assert isinstance(item, dict)
        assert item["shape"] == list(array.shape)
        assert item["dtype"] == str(array.dtype)


@pytest.mark.parametrize(
    ("case_name", "builder"),
    [
        ("equilibrium", _equilibrium_arrays),
        ("whirl", _whirl_arrays),
        ("unit_adapter", _adapter_arrays),
        ("facades", _facade_arrays),
    ],
)
def test_successful_paths_match_v0_4_1_exactly(
    case_name: str,
    builder: object,
    reference_metadata: dict[str, object],
    reference_arrays: dict[str, np.ndarray],
) -> None:
    """Reconstruct every frozen case and require exact outputs."""

    assert callable(builder)
    metadata, actual_arrays = builder()
    cases = reference_metadata["cases"]
    assert isinstance(cases, dict)
    assert metadata == cases[case_name]
    for name, actual in actual_arrays.items():
        np.testing.assert_array_equal(actual, reference_arrays[name])
