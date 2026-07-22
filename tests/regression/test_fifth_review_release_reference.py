"""Exact regression for valid behavior surrounding fifth-review fixes."""

from pathlib import Path

import numpy as np

from tools.reference.generate_fifth_review_release_reference_v5 import (
    collect_reference_arrays,
)


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "refs" / "fifth_review_release_reference_v5.npz"


def test_fifth_review_valid_behavior_matches_v5_reference_exactly():
    """Preserved harmonic, controller-config, and constructor arrays stay exact."""

    actual = collect_reference_arrays()
    with np.load(REFERENCE) as expected:
        assert set(actual) == set(expected.files)
        for name, value in actual.items():
            np.testing.assert_array_equal(value, expected[name], err_msg=name)
