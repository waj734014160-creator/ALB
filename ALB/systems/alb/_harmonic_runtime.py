"""Strict runtime failure boundary for the harmonic ALB implementation."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager


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
