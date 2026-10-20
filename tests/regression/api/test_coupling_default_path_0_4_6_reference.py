"""Exact regression for the default coupling path frozen before ALB 0.4.6.

The reference was generated from the unmodified 0.4.5 source (``df7336f``).
Every case rebuilds the same inputs through the public API with default
settings, so it must keep the staggered integrator, one controller update per
step, and one shared time step bit-for-bit.

Cross-platform note: the reference records its numerical environment. To
re-check on another platform, regenerate a pair from ``df7336f`` with
``tools/reference/generate_coupling_default_path_0_4_6_reference.py --json
<file> --npz <file>`` and point ``ALB_COUPLING_DEFAULT_PATH_0_4_6_NPZ`` and
``ALB_COUPLING_DEFAULT_PATH_0_4_6_JSON`` at the local pair. The committed
reference itself is never regenerated to fit an implementation (ADR-0007,
rule 5).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from tools.reference.generate_coupling_default_path_0_4_6_reference import (
    CASES,
    JSON_PATH,
    NPZ_PATH,
    capture_case,
)


_REFERENCE = Path(
    os.environ.get("ALB_COUPLING_DEFAULT_PATH_0_4_6_NPZ", str(NPZ_PATH))
)
_REFERENCE_JSON = Path(
    os.environ.get("ALB_COUPLING_DEFAULT_PATH_0_4_6_JSON", str(JSON_PATH))
)


@pytest.mark.parametrize("case_name", tuple(CASES))
def test_default_coupling_path_matches_pre_0_4_6_reference_exactly(
    case_name: str,
) -> None:
    """Require every frozen array of one case to match bit-for-bit."""

    reference = np.load(_REFERENCE)
    _, actual = capture_case(case_name)
    expected_keys = sorted(
        key for key in reference.files if key.startswith(f"{case_name}.")
    )

    assert sorted(actual) == expected_keys
    for key in expected_keys:
        np.testing.assert_array_equal(actual[key], reference[key], err_msg=key)


@pytest.mark.parametrize(
    "case_name",
    tuple(name for name in CASES if name != "standalone_controllers"),
)
def test_default_coupling_result_metadata_is_unchanged(case_name: str) -> None:
    """Require the default-path result metadata keys and values to be frozen.

    New 0.4.6 metadata (integrator, control periods, time-step adjustment) is
    published only for ROS2 runs, configured control periods, or explicit
    initial states, so the default path keeps its 0.4.5 result contract.
    """

    reference = json.loads(_REFERENCE_JSON.read_text(encoding="utf-8"))
    metadata, _ = capture_case(case_name)
    actual = json.loads(json.dumps(metadata["result_metadata"]))

    assert actual == reference["cases"][case_name]["result_metadata"]
