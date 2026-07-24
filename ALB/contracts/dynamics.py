"""Rotor dynamics contracts."""

from collections.abc import Mapping, Sequence
from typing import Protocol, TypeAlias, runtime_checkable

import numpy.typing as npt

from .numeric import FloatArray
from .lifecycle import RuntimeLifecycleProtocol
from .types import UnitSystem
from .ports import RotorLoadInput


RotorStateMap: TypeAlias = Mapping[str, FloatArray]


@runtime_checkable
class RotorProtocol(RuntimeLifecycleProtocol, Protocol):
    """Explicit rotor runtime consumed by the simulation step runtime."""

    unit_system: UnitSystem | str

    def _reset_for_owner(
        self,
        initial_state: npt.ArrayLike | None = None,
    ) -> None:
        """Reset rotor state for its owning simulation runtime."""

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

    def input_load(self, value: RotorLoadInput) -> None:
        """Latch the standard nodal-load DTO without advancing."""

    def advance(self) -> FloatArray:
        """Advance exactly once from the currently latched load."""

    def current_state(
        self, node: int | Sequence[int] | None = None
    ) -> FloatArray | RotorStateMap:
        """Read the completed state without hidden propagation."""

    def output(
        self, node: int | Sequence[int] | None = None
    ) -> FloatArray | RotorStateMap:
        """Read the completed rotor state without advancing."""
