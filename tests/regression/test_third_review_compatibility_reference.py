"""Exact regression for valid behavior surrounding third-review fixes."""

from pathlib import Path

import numpy as np

from tools.reference.generate_third_review_compatibility_reference_v3 import (
    collect_reference_arrays,
)


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "refs" / "third_review_compatibility_reference_v3.npz"


def test_third_review_valid_behavior_matches_v3_reference_exactly():
    """All valid pre-fix controller, valve, config, and rotor arrays stay exact."""

    actual = collect_reference_arrays()
    with np.load(REFERENCE) as expected:
        assert set(actual) == set(expected.files)
        for name, value in actual.items():
            np.testing.assert_array_equal(value, expected[name], err_msg=name)
