"""Exact regression for the new 0.4.6 ROS2 and control-period behavior.

The reference is generated from the finished 0.4.6 implementation by
``tools/reference/generate_ros2_control_period_0_4_6_reference.py`` and pins
the new algorithms against silent changes (ADR-0007 rules 5 and 6, ADR-0009).
It records its numerical environment; other platforms may differ at round-off
level. ``ALB_ROS2_CONTROL_PERIOD_0_4_6_NPZ`` / ``..._JSON`` point the test at a
locally generated pair.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from tools.reference.generate_ros2_control_period_0_4_6_reference import (
    CASES,
    JSON_PATH,
    NPZ_PATH,
    capture_case,
)


_REFERENCE = Path(
    os.environ.get("ALB_ROS2_CONTROL_PERIOD_0_4_6_NPZ", str(NPZ_PATH))
)
_REFERENCE_JSON = Path(
    os.environ.get("ALB_ROS2_CONTROL_PERIOD_0_4_6_JSON", str(JSON_PATH))
)


@pytest.mark.parametrize("case_name", tuple(CASES))
def test_ros2_and_control_period_match_0_4_6_reference_exactly(
    case_name: str,
) -> None:
    """Require every frozen array and metadata entry of one case."""

    reference = np.load(_REFERENCE)
    reference_json = json.loads(_REFERENCE_JSON.read_text(encoding="utf-8"))
    metadata, actual = capture_case(case_name)
    expected_keys = sorted(
        key for key in reference.files if key.startswith(f"{case_name}.")
    )

    assert sorted(actual) == expected_keys
    for key in expected_keys:
        np.testing.assert_array_equal(actual[key], reference[key], err_msg=key)
    frozen = dict(reference_json["cases"][case_name])
    frozen.pop("arrays")
    assert json.loads(json.dumps(metadata)) == frozen
