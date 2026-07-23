"""Exact pre-0.3 reference for ALB runtime and coupling migration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from tools.reference.generate_alb_runtime_transition_reference_v1 import (
    collect_reference,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs" / "alb_runtime_transition_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs" / "alb_runtime_transition_reference_v1.npz"


def _sha256_array(value: np.ndarray) -> str:
    """Return the reference byte digest for one contiguous array."""

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def test_alb_runtime_transition_reference_matches_exactly() -> None:
    """Protect numerics while lifecycle, history, and units are reworked."""

    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    assert metadata["schema"] == "alb.runtime-transition-reference.v1"
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

        np.testing.assert_array_equal(
            frozen["raw.force"],
            frozen["block.force"],
        )
        np.testing.assert_array_equal(
            frozen["raw.signal_history"],
            frozen["block.signal_history"],
        )
