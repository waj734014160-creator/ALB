"""Shared structural contracts for ALB runtime components.

The contracts in this module intentionally describe small roles.  Numerical
models should compose these roles instead of inheriting one universal solver
interface whose ``input`` and ``output`` meanings vary by domain.
"""

from dataclasses import dataclass
from typing import Iterator, Optional, Protocol, TypeAlias, runtime_checkable

import numpy as np
import numpy.typing as npt


FloatArray: TypeAlias = npt.NDArray[np.float64]


@runtime_checkable
class TimeGridProtocol(Protocol):
    """Time-grid shape consumed by transient solvers."""

    num: int

    @property
    def dt(self) -> float:
        """Return the constant time increment."""

    @property
    def t_list(self) -> FloatArray:
        """Return all sample times, including the initial point."""

    def __iter__(self) -> Iterator[float]:
        """Iterate over sample times."""


@dataclass(frozen=True)
class ConvergenceStatus:
    """Unambiguous convergence result for strict runtime interfaces."""

    residual: float
    converged: bool
    iterations: Optional[int] = None
    message: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.residual, (bool, np.bool_)):
            raise TypeError("residual must be numeric, not boolean")
        if not isinstance(self.converged, (bool, np.bool_)):
            raise TypeError("converged must be boolean")
        residual = float(self.residual)
        if not np.isfinite(residual) or residual < 0.0:
            raise ValueError("residual must be a finite nonnegative scalar")
        if self.iterations is not None:
            if isinstance(self.iterations, (bool, np.bool_)) or not isinstance(
                self.iterations, (int, np.integer)
            ):
                raise TypeError("iterations must be an integer or None")
            if self.iterations < 0:
                raise ValueError("iterations must be nonnegative")
        object.__setattr__(self, "residual", residual)
        object.__setattr__(self, "converged", bool(self.converged))

    @classmethod
    def pending(cls, message: str = "") -> "ConvergenceStatus":
        """Return a standard local status before a numerical solve starts."""

        return cls(residual=float(np.finfo(float).max), converged=False, message=message)
