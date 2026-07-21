"""Validated DTOs for bearing, controller, valve, and rotor ports."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Any

import numpy as np
import numpy.typing as npt

from .types import UnitSystem


FloatArray = npt.NDArray[np.float64]


def _finite_time(value: Any) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise TypeError("time must be a real scalar")
    result = float(value)
    if not np.isfinite(result) or result < 0.0:
        raise ValueError("time must be finite and nonnegative")
    return result


def _finite_axis_vector(value: Any, name: str) -> FloatArray:
    array = np.asarray(value, dtype=float)
    if array.shape != (2,):
        raise ValueError(f"{name} must have shape (2,)")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    result = array.copy()
    result.setflags(write=False)
    return result


def _finite_node_axes(value: Any, name: str) -> FloatArray:
    array = np.asarray(value, dtype=float)
    if array.ndim == 1:
        if array.shape != (2,):
            raise ValueError(f"{name} must have shape (2,) or (n, 2)")
        array = array.reshape(1, 2)
    if array.ndim != 2 or array.shape[1] != 2 or array.shape[0] == 0:
        raise ValueError(f"{name} must have shape (2,) or (n, 2)")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    result = array.copy()
    result.setflags(write=False)
    return result


class _PortDto:
    """Shared helper for immutable unit-aware DTOs."""

    unit_system: UnitSystem
    time: float

    def _normalize_common(self) -> None:
        object.__setattr__(self, "unit_system", UnitSystem.coerce(self.unit_system))
        object.__setattr__(self, "time", _finite_time(self.time))


@dataclass(frozen=True, slots=True)
class BearingInput(_PortDto):
    """Two-axis bearing displacement and velocity at one time sample."""

    displacement: FloatArray
    velocity: FloatArray
    time: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        self._normalize_common()
        object.__setattr__(
            self, "displacement", _finite_axis_vector(self.displacement, "displacement")
        )
        object.__setattr__(self, "velocity", _finite_axis_vector(self.velocity, "velocity"))


@dataclass(frozen=True, slots=True)
class BearingOutput(_PortDto):
    """Two-axis bearing force produced for one input sample."""

    force: FloatArray
    time: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        self._normalize_common()
        object.__setattr__(self, "force", _finite_axis_vector(self.force, "force"))


@dataclass(frozen=True, slots=True)
class ControlInput(_PortDto):
    """Two-axis control error at one time sample."""

    error: FloatArray
    time: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        self._normalize_common()
        object.__setattr__(self, "error", _finite_axis_vector(self.error, "error"))


@dataclass(frozen=True, slots=True)
class ControlOutput(_PortDto):
    """Two-axis normalized control command."""

    command: FloatArray
    time: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        self._normalize_common()
        object.__setattr__(self, "command", _finite_axis_vector(self.command, "command"))


@dataclass(frozen=True, slots=True)
class ValveInput(_PortDto):
    """Two-axis valve command at one time sample."""

    command: FloatArray
    time: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        self._normalize_common()
        object.__setattr__(self, "command", _finite_axis_vector(self.command, "command"))


@dataclass(frozen=True, slots=True)
class ValveOutput(_PortDto):
    """Two-axis valve spool state at one time sample."""

    spool: FloatArray
    time: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        self._normalize_common()
        spool = _finite_axis_vector(self.spool, "spool")
        if np.any(np.abs(spool) > 1.0):
            raise ValueError("spool values must be within [-1, 1]")
        object.__setattr__(self, "spool", spool)


@dataclass(frozen=True, slots=True)
class RotorLoadInput(_PortDto):
    """Two-axis nodal loads supplied to a rotor advance operation."""

    force: FloatArray
    previous_force: FloatArray
    node_links: tuple[int, ...]
    time: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        self._normalize_common()
        force = _finite_node_axes(self.force, "force")
        previous_force = _finite_node_axes(self.previous_force, "previous_force")
        if force.shape != previous_force.shape:
            raise ValueError("force and previous_force must have the same shape")
        links = tuple(self.node_links)
        if len(links) != force.shape[0]:
            raise ValueError("node_links length must match the number of force rows")
        if any(
            isinstance(link, (bool, np.bool_))
            or not isinstance(link, (Integral, np.integer))
            or link < 0
            for link in links
        ):
            raise ValueError("node_links must contain nonnegative integers")
        object.__setattr__(self, "force", force)
        object.__setattr__(self, "previous_force", previous_force)
        object.__setattr__(self, "node_links", tuple(int(link) for link in links))


@dataclass(frozen=True, slots=True)
class RotorState(_PortDto):
    """Two-axis displacement and velocity for one or more rotor nodes."""

    displacement: FloatArray
    velocity: FloatArray
    time: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        self._normalize_common()
        displacement = _finite_node_axes(self.displacement, "displacement")
        velocity = _finite_node_axes(self.velocity, "velocity")
        if displacement.shape != velocity.shape:
            raise ValueError("displacement and velocity must have the same shape")
        object.__setattr__(self, "displacement", displacement)
        object.__setattr__(self, "velocity", velocity)
