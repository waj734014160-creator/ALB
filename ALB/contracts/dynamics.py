"""Rotor dynamics contracts."""

from collections.abc import Mapping, Sequence
from typing import Protocol, TypeAlias, runtime_checkable

import numpy.typing as npt

from .numeric import FloatArray
from .lifecycle import RuntimeLifecycleProtocol
from .types import UnitSystem


RotorStateMap: TypeAlias = Mapping[str, FloatArray]


@runtime_checkable
class RotorProtocol(RuntimeLifecycleProtocol, Protocol):
    """Explicit rotor runtime consumed by ``RsRotorBearingCouple``."""

    unit_system: UnitSystem | str

    def init(self, initial_state: npt.ArrayLike | None = None) -> None:
        """Reset rotor state and invalidate any pending force."""

    def input_force2node(
        self,
        time: float,
        force: npt.ArrayLike,
        node: int | Sequence[int],
        initial_state: npt.ArrayLike | None = None,
        *,
        force0: npt.ArrayLike | None = None,
    ) -> None:
        """Latch per-node force data without propagating the state."""

    def advance(self) -> FloatArray:
        """Advance exactly once from the currently latched load."""

    def current_state(
        self, node: int | Sequence[int] | None = None
    ) -> FloatArray | RotorStateMap:
        """Read the completed state without hidden propagation."""

    def output(
        self, node: int | Sequence[int] | None = None
    ) -> FloatArray | RotorStateMap:
        """Compatibility read alias for :meth:`current_state`."""
