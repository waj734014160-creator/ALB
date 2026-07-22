"""Exact regression for valid behavior surrounding fourth-review fixes."""

from pathlib import Path

import numpy as np

from tools.reference.generate_fourth_review_release_reference_v4 import (
    collect_reference_arrays,
)


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "refs" / "fourth_review_release_reference_v4.npz"


def test_fourth_review_valid_behavior_matches_v4_reference_exactly():
    """Preserved harmonic, enabled-control, and PID config arrays stay exact."""

    actual = collect_reference_arrays()
    with np.load(REFERENCE) as expected:
        assert set(actual) == set(expected.files)
        for name, value in actual.items():
            np.testing.assert_array_equal(value, expected[name], err_msg=name)
