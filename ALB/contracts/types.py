"""Primitive value objects shared by ALB public contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real

import numpy as np


class UnitSystem(str, Enum):
    """Unit system declared at every numerical integration boundary."""

    DIMENSIONAL = "dimensional"
    NONDIMENSIONAL = "nondimensional"

    @classmethod
    def coerce(cls, value: "UnitSystem | str") -> "UnitSystem":
        """Return a validated unit-system value."""

        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError as exc:
            raise ValueError(
                "unit_system must be 'dimensional' or 'nondimensional'"
            ) from exc


@dataclass(frozen=True, slots=True)
class StepContext:
    """Identity and timing information for one physical time step."""

    step_index: int
    time: float
    dt: float
    unit_system: UnitSystem

    def __post_init__(self) -> None:
        if isinstance(self.step_index, (bool, np.bool_)) or not isinstance(
            self.step_index, (Integral, np.integer)
        ):
            raise TypeError("step_index must be an integer")
        if self.step_index < 0:
            raise ValueError("step_index must be nonnegative")
        if isinstance(self.time, (bool, np.bool_)) or not isinstance(self.time, Real):
            raise TypeError("time must be a real scalar")
        if isinstance(self.dt, (bool, np.bool_)) or not isinstance(self.dt, Real):
            raise TypeError("dt must be a real scalar")
        time = float(self.time)
        dt = float(self.dt)
        if not np.isfinite(time) or time < 0.0:
            raise ValueError("time must be finite and nonnegative")
        if not np.isfinite(dt) or dt <= 0.0:
            raise ValueError("dt must be finite and positive")
        object.__setattr__(self, "step_index", int(self.step_index))
        object.__setattr__(self, "time", time)
        object.__setattr__(self, "dt", dt)
        object.__setattr__(self, "unit_system", UnitSystem.coerce(self.unit_system))

    @property
    def identity(self) -> tuple[int, float]:
        """Return the immutable identity used by step-commit ledgers."""

        return self.step_index, self.time
