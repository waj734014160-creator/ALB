"""Strict runtime failure boundary for the harmonic ALB implementation."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from ALB.contracts.numeric import FloatArray
from ALB.core.validation import finite_real_array as _finite_real_array
from ALB.core.validation import finite_real_scalar as _finite_real_scalar


def finite_real_array(
    name: str, value: object, *, shape: tuple[int, ...]
) -> FloatArray:
    """Compatibility wrapper for the shared finite real-array validator."""

    return _finite_real_array(value, name, shape=shape)


def finite_real_scalar(name: str, value: object) -> float:
    """Compatibility wrapper for the shared finite real-scalar validator."""

    return float(_finite_real_scalar(value, name))


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
