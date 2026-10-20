"""Exact regression for stateful bearing families frozen before ALB 0.4.7.

The reference was generated from the unmodified 0.4.6 source (``9432c06``)
before the predictor-corrector integrator and the bearing checkpoint/restore
contract were added. Every case rebuilds the same inputs through the public
API with the default staggered integrator, so thermal, active, multi-pad, and
external-spool bearings must keep their staggered results bit-for-bit.

Cross-platform note: the reference records its numerical environment. To
re-check on another platform, regenerate a pair from ``9432c06`` with
``tools/reference/generate_coupling_staggered_pre_0_4_7_reference.py --json
<file> --npz <file>`` and point ``ALB_COUPLING_STAGGERED_PRE_0_4_7_NPZ`` and
``ALB_COUPLING_STAGGERED_PRE_0_4_7_JSON`` at the local pair. The committed
reference itself is never regenerated to fit an implementation (ADR-0007,
rule 5).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from tools.reference.generate_coupling_staggered_pre_0_4_7_reference import (
    CASES,
    JSON_PATH,
    NPZ_PATH,
    capture_case,
)


_REFERENCE = Path(
    os.environ.get("ALB_COUPLING_STAGGERED_PRE_0_4_7_NPZ", str(NPZ_PATH))
)
_REFERENCE_JSON = Path(
    os.environ.get("ALB_COUPLING_STAGGERED_PRE_0_4_7_JSON", str(JSON_PATH))
)


@pytest.mark.parametrize("case_name", tuple(CASES))
def test_staggered_stateful_families_match_pre_0_4_7_reference(
    case_name: str,
) -> None:
    """Require every frozen array and the result metadata of one case."""

    reference = np.load(_REFERENCE)
    payload = json.loads(_REFERENCE_JSON.read_text(encoding="utf-8"))
    metadata, actual = capture_case(case_name)
    expected_keys = sorted(
        key for key in reference.files if key.startswith(f"{case_name}.")
    )

    assert sorted(actual) == expected_keys
    for key in expected_keys:
        np.testing.assert_array_equal(actual[key], reference[key], err_msg=key)
    assert json.loads(json.dumps(metadata["result_metadata"])) == (
        payload["cases"][case_name]["result_metadata"]
    )
