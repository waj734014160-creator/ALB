"""Exact regression for valid behavior surrounding sixth-review fixes."""

from pathlib import Path

import numpy as np

from tools.reference.generate_sixth_review_runtime_reference_v6 import (
    collect_reference_arrays,
)


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "refs" / "sixth_review_runtime_reference_v6.npz"


def test_sixth_review_valid_behavior_matches_v6_reference_exactly():
    """Successful harmonic and adjacent valid arrays remain byte-exact."""

    actual = collect_reference_arrays()
    with np.load(REFERENCE) as expected:
        assert set(actual) == set(expected.files)
        for name, value in actual.items():
            np.testing.assert_array_equal(value, expected[name], err_msg=name)
