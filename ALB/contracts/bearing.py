"""Bearing-side contracts used by rotor coupling code."""

from typing import Any, Literal, Mapping, Protocol, runtime_checkable

import numpy as np

from .model import PersistableProtocol, SignalProtocol


UnitSystem = Literal["dimensional", "nondimensional", "unspecified"]


@runtime_checkable
class BearingProtocol(PersistableProtocol, Protocol):
    """Standard two-axis bearing contract.

    A conforming dimensional bearing accepts ``uxy`` in metres, ``uxyt`` in
    metres per second, and returns a two-component force in newtons.  A
    nondimensional bearing uses the same call shape but declares a different
    ``unit_system`` and must not be passed directly to a dimensional rotor.
    """

    node_link: int
    signal: SignalProtocol
    unit_system: UnitSystem

    @property
    def results(self) -> Any:
        """Return the component result store."""

    def init(self, *args: Any, **kwargs: Any) -> Any:
        """Reset bearing state."""

    def input(
        self,
        uxy: np.ndarray,
        uxyt: np.ndarray,
        t: float,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Accept one rotor state sample."""

    def output(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        """Return a mapping containing a finite two-component ``force``."""

    def calc_is_finished(self, *args: Any, **kwargs: Any) -> bool:
        """Return whether the bearing evaluation is complete."""


@runtime_checkable
class BearingCoefficientProtocol(Protocol):
    """Optional local-linear coefficient capability."""

    @property
    def K(self) -> np.ndarray:
        """Return the 2-by-2 stiffness matrix."""

    @property
    def C(self) -> np.ndarray:
        """Return the 2-by-2 damping matrix."""

    @property
    def G_xv(self) -> np.ndarray:
        """Return the complex 2-by-2 spool-force transfer matrix."""
