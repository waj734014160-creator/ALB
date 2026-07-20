"""Shared structural contracts for ALB runtime components.

The contracts in this module intentionally describe small roles.  Numerical
models should compose these roles instead of inheriting one universal solver
interface whose ``input`` and ``output`` meanings vary by domain.
"""

from dataclasses import dataclass
from typing import Any, Iterator, Optional, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class SignalProtocol(Protocol):
    """Event propagation port exposed by runtime components."""

    signal: bool

    def add_child(self, child: "SignalProtocol") -> None:
        """Attach a child event port."""

    def lead_loop(self, attr: str) -> None:
        """Broadcast one true/false event cycle."""


@runtime_checkable
class LifecycleProtocol(Protocol):
    """Minimal initialization and completion contract."""

    signal: SignalProtocol

    def init(self, *args: Any, **kwargs: Any) -> Any:
        """Reset the component to its initial runtime state."""

    def calc_is_finished(self, *args: Any, **kwargs: Any) -> bool:
        """Return whether the current calculation is complete."""


@runtime_checkable
class PersistableProtocol(Protocol):
    """Persistence port used by coupled systems."""

    def save(
        self,
        tofile: bool = True,
        path: Optional[str] = None,
        name: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Return a save-tree node and optionally persist it."""


@runtime_checkable
class TimeGridProtocol(Protocol):
    """Time-grid shape consumed by transient solvers."""

    num: int

    @property
    def dt(self) -> float:
        """Return the constant time increment."""

    @property
    def t_list(self) -> np.ndarray:
        """Return all sample times, including the initial point."""

    def __iter__(self) -> Iterator[float]:
        """Iterate over sample times."""


@dataclass(frozen=True)
class ConvergenceStatus:
    """Unambiguous convergence result for new interfaces.

    Legacy ``calc_error`` methods currently return a mixture of booleans and
    residual scalars.  New code should expose this value without changing the
    legacy method until each numerical solver is migrated deliberately.
    """

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

        return cls(residual=np.finfo(float).max, converged=False, message=message)
