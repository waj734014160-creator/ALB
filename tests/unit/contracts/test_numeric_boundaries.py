"""Property-style checks for shared real and finite numeric boundaries."""

from __future__ import annotations

import numpy as np
import pytest

from ALB.contracts.numeric import (
    finite_real_array,
    finite_real_scalar,
    finite_real_time,
    finite_real_vector,
)


@pytest.mark.parametrize(
    "value",
    [
        [0.0, 1.0],
        (0, 1),
        np.asarray([0, 1], dtype=np.int64),
        np.asarray([0.0, 1.0], dtype=np.float32),
    ],
)
def test_equivalent_real_inputs_normalize_to_owned_float64_vectors(value):
    vector = finite_real_vector(value, "sample", 2)

    np.testing.assert_array_equal(vector, [0.0, 1.0])
    assert vector.dtype == np.float64
    if isinstance(value, np.ndarray):
        assert not np.shares_memory(vector, value)


@pytest.mark.parametrize(
    "value",
    [
        [np.nan, 0.0],
        [np.inf, 0.0],
        [-np.inf, 0.0],
        [1.0 + 0.0j, 0.0],
        [1.0 + 1.0j, 0.0],
    ],
)
def test_all_nonfinite_or_complex_array_inputs_are_rejected(value):
    with pytest.raises(ValueError):
        finite_real_array(value, "sample")


@pytest.mark.parametrize("value", [True, np.bool_(False), "0.1", 1.0 + 0.0j])
def test_time_rejects_non_real_or_boolean_scalar_types(value):
    with pytest.raises(TypeError):
        finite_real_time(value)


def test_scalar_and_vector_validators_do_not_silently_change_shape():
    with pytest.raises(ValueError, match="one value"):
        finite_real_scalar([1.0, 2.0], "scalar")
    with pytest.raises(ValueError, match="exactly 2"):
        finite_real_vector([[1.0, 2.0], [3.0, 4.0]], "vector", 2)
