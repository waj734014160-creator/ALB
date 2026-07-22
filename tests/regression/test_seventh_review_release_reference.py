"""Exact regression for valid behavior surrounding seventh-review fixes."""

from pathlib import Path

import numpy as np

from tools.reference.generate_seventh_review_release_reference_v7 import (
    collect_reference_arrays,
)


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "refs" / "seventh_review_release_reference_v7.npz"


def test_seventh_review_valid_behavior_matches_v7_reference_exactly():
    """Successful real-valued behavior remains byte-exact after hardening."""

    actual = collect_reference_arrays()
    with np.load(REFERENCE) as expected:
        assert set(actual) == set(expected.files)
        for name, value in actual.items():
            np.testing.assert_array_equal(value, expected[name], err_msg=name)
