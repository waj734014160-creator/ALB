"""Dependency-free numeric validation shared by DTO and runtime boundaries."""

from __future__ import annotations

from numbers import Real
from typing import Any, TypeAlias

import numpy as np
import numpy.typing as npt


FloatArray: TypeAlias = npt.NDArray[np.float64]


def finite_real_array(
    value: Any,
    name: str,
    *,
    shape: tuple[int, ...] | None = None,
) -> FloatArray:
    """Return a copied finite real array without discarding imaginary parts."""

    raw = np.asarray(value)
    if np.iscomplexobj(raw):
        raise ValueError(f"{name} must be real; complex values are not supported")
    try:
        array = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain real numeric values") from exc
    if shape is not None and array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array.copy()


def finite_real_vector(value: Any, name: str, size: int) -> FloatArray:
    """Return a finite one-dimensional real vector with an exact size."""

    vector = finite_real_array(value, name).reshape(-1)
    if vector.shape != (size,):
        raise ValueError(f"{name} must contain exactly {size} values")
    return vector


def finite_real_scalar(value: Any, name: str) -> float:
    """Return one finite real scalar without implicit complex conversion."""

    flattened = finite_real_array(value, name).reshape(-1)
    if flattened.size != 1:
        raise ValueError(f"{name} must contain exactly one value")
    return float(flattened[0])


def finite_real_time(
    value: Any,
    name: str = "time",
    *,
    nonnegative: bool = True,
) -> float:
    """Return a finite non-boolean real timestamp with an optional lower bound."""

    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real scalar")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if nonnegative and result < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return result
