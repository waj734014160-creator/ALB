"""Strict runtime failure boundary for the harmonic ALB implementation."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, cast, TypeAlias

import numpy as np
from numpy.typing import NDArray


FloatArray: TypeAlias = NDArray[np.float64]


def finite_real_array(
    name: str,
    value: Any,
    *,
    shape: tuple[int, ...],
) -> FloatArray:
    """Return a copied finite real array without silently dropping imaginary data."""

    raw = np.asarray(value)
    if np.iscomplexobj(raw):
        raise ValueError(f"{name} must be real; complex values are not supported")
    try:
        array = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain real numeric values") from exc
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return cast(FloatArray, array.copy())


def finite_real_scalar(name: str, value: Any) -> float:
    """Return one finite real scalar without implicit complex-to-real conversion."""

    raw = np.asarray(value)
    if np.iscomplexobj(raw):
        raise ValueError(f"{name} must be real; complex values are not supported")
    try:
        flattened = np.asarray(raw, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain one real numeric value") from exc
    if flattened.size != 1:
        raise ValueError(f"{name} must contain exactly one value")
    if not np.isfinite(flattened[0]):
        raise ValueError(f"{name} must be finite")
    return float(flattened[0])


class RuntimeFailureGuard:
    """Invalidate a stateful runtime whenever an advancing phase raises.

    The guard deliberately does not attempt to roll back opaque controller or
    valve objects. Instead, it guarantees that a partially advanced runtime
    cannot be observed or retried until its owner completes a fresh reset.
    """

    def __init__(self, invalidate: Callable[[], None]) -> None:
        self._invalidate = invalidate

    @contextmanager
    def phase(self) -> Iterator[None]:
        """Run one stateful phase and invalidate the owner on any exception."""

        try:
            yield
        except BaseException:
            self._invalidate()
            raise
