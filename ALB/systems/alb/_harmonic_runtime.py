"""Strict runtime failure boundary for the harmonic ALB implementation."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ALB.contracts.numeric import FloatArray
from ALB.core.validation import finite_real_array as _finite_real_array
from ALB.core.validation import finite_real_scalar as _finite_real_scalar


ComplexArray = npt.NDArray[np.complex128]


@dataclass(frozen=True, slots=True)
class HarmonicForceResult:
    """One validated force decomposition from the harmonic kernel."""

    stiffness: FloatArray
    damping: FloatArray
    spool: FloatArray
    total: FloatArray


class HarmonicForceEvaluator:
    """Pure harmonic force calculation separated from runtime orchestration."""

    def __init__(
        self,
        static_force: FloatArray,
        stiffness: FloatArray,
        damping: FloatArray,
        spool_transfer: ComplexArray,
    ) -> None:
        self._static_force = static_force.copy()
        self._stiffness = stiffness.copy()
        self._damping = damping.copy()
        self._spool_transfer = spool_transfer.copy()

    def evaluate(
        self,
        delta_position: FloatArray,
        velocity: FloatArray,
        delta_spool: FloatArray,
        spool_quadrature: FloatArray,
    ) -> HarmonicForceResult:
        """Return finite component and total forces without storing state."""

        with np.errstate(over="raise", invalid="raise"):
            stiffness_force = -self._stiffness @ delta_position
            damping_force = -self._damping @ velocity
            spool_force = (
                self._spool_transfer.real @ delta_spool
                + self._spool_transfer.imag @ spool_quadrature
            )
            total_force = (
                self._static_force
                + stiffness_force
                + damping_force
                + spool_force
            )
        return HarmonicForceResult(
            stiffness=finite_real_array(
                "stiffness force", stiffness_force, shape=(2,)
            ),
            damping=finite_real_array("damping force", damping_force, shape=(2,)),
            spool=finite_real_array("servovalve force", spool_force, shape=(2,)),
            total=finite_real_array("bearing force", total_force, shape=(2,)),
        )


def finite_real_array(
    name: str, value: object, *, shape: tuple[int, ...]
) -> FloatArray:
    """Apply the harmonic module's name-first array validation contract."""

    return _finite_real_array(value, name, shape=shape)


def finite_real_scalar(name: str, value: object) -> float:
    """Apply the harmonic module's name-first scalar validation contract."""

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
