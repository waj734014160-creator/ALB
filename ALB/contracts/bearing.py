"""Bearing-side contracts used by rotor coupling code."""

from typing import Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt

from .block import EvaluableBlock
from .ports import BearingInput, BearingOutput
from .types import UnitSystem


@runtime_checkable
class BearingProtocol(EvaluableBlock[BearingInput, BearingOutput], Protocol):
    """Standard two-axis bearing contract.

    A conforming dimensional bearing accepts ``uxy`` in metres, ``uxyt`` in
    metres per second, and returns a two-component force in newtons.  A
    nondimensional bearing uses the same call shape but declares a different
    ``unit_system`` and must not be passed directly to a dimensional rotor.
    """

    node_link: int
    unit_system: UnitSystem


@runtime_checkable
class BearingCoefficientProtocol(Protocol):
    """Optional local-linear coefficient capability."""

    @property
    def K(self) -> npt.NDArray[np.float64]:
        """Return the 2-by-2 stiffness matrix."""

    @property
    def C(self) -> npt.NDArray[np.float64]:
        """Return the 2-by-2 damping matrix."""

    @property
    def G_xv(self) -> npt.NDArray[np.complex128]:
        """Return the complex 2-by-2 spool-force transfer matrix."""
