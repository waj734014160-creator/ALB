"""Exact regression for the new ALB 0.4.7 predictor-corrector behavior.

The reference was generated from the finished 0.4.7 implementation, not from
the pre-change source: it guards against silent changes of the new algorithm
(probe and checkpointed trials, PECE, Aitken and IQN-ILS updates, control
periods, held spool providers). The pre-change staggered behavior of the same
bearing families is frozen separately in
``refs/coupling_staggered_pre_0_4_7_reference_v1.*``.

Cross-platform note: point ``ALB_PREDICTOR_CORRECTOR_0_4_7_NPZ`` and
``ALB_PREDICTOR_CORRECTOR_0_4_7_JSON`` at a pair regenerated locally with
``tools/reference/generate_predictor_corrector_0_4_7_reference.py --json
<file> --npz <file>``. The committed pair is never regenerated to fit an
implementation (ADR-0007, rule 5).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from tools.reference.generate_predictor_corrector_0_4_7_reference import (
    CASES,
    JSON_PATH,
    NPZ_PATH,
    capture_case,
)


_REFERENCE = Path(
    os.environ.get("ALB_PREDICTOR_CORRECTOR_0_4_7_NPZ", str(NPZ_PATH))
)
_REFERENCE_JSON = Path(
    os.environ.get("ALB_PREDICTOR_CORRECTOR_0_4_7_JSON", str(JSON_PATH))
)


@pytest.mark.parametrize("case_name", tuple(CASES))
def test_predictor_corrector_matches_the_0_4_7_reference(case_name: str) -> None:
    """Require every frozen array and the case metadata bit for bit."""

    reference = np.load(_REFERENCE)
    payload = json.loads(_REFERENCE_JSON.read_text(encoding="utf-8"))
    metadata, actual = capture_case(case_name)
    expected_keys = sorted(
        key for key in reference.files if key.startswith(f"{case_name}.")
    )

    assert sorted(actual) == expected_keys
    for key in expected_keys:
        np.testing.assert_array_equal(actual[key], reference[key], err_msg=key)
    expected = dict(payload["cases"][case_name])
    expected.pop("arrays")
    assert json.loads(json.dumps(metadata)) == expected
