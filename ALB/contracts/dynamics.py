"""Rotor dynamics contracts."""

from collections.abc import Mapping, Sequence
from typing import Protocol, TypeAlias, runtime_checkable

import numpy.typing as npt

from .lifecycle import RuntimeLifecycleProtocol
from .numeric import FloatArray, finite_real_array
from .ports import RotorLoadInput
from .types import UnitSystem

RotorStateMap: TypeAlias = Mapping[str, FloatArray]


def _validate_coupled_rotor_output(
    value: object,
    node_count: int,
    *,
    label: str = "rotor output",
) -> dict[str, FloatArray]:
    """Return one validated dimensional two-axis rotor state mapping.

    Coupling requests explicit rotor nodes, so both displacement and velocity
    must have one two-axis row per requested node. The general rotor protocol
    remains able to return a flat full-system state when no nodes are supplied.
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping with uxy and uxyt fields")
    if isinstance(node_count, bool) or not isinstance(node_count, int):
        raise TypeError("node_count must be an integer")
    if node_count < 1:
        raise ValueError("node_count must be positive")
    missing = [field for field in ("uxy", "uxyt") if field not in value]
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing}")
    expected_shape = (node_count, 2)
    displacement = finite_real_array(
        value["uxy"],
        f"{label}.uxy",
        shape=expected_shape,
    )
    velocity = finite_real_array(
        value["uxyt"],
        f"{label}.uxyt",
        shape=expected_shape,
    )
    return {"uxy": displacement, "uxyt": velocity}


@runtime_checkable
class RotorProtocol(RuntimeLifecycleProtocol, Protocol):
    """Explicit rotor runtime consumed by the simulation step runtime."""

    unit_system: UnitSystem | str

    @property
    def dt(self) -> float:
        """Return the immutable rotor integration time step."""

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
