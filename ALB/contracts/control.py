"""Strict runtime contracts for controllers and servovalves."""

from typing import Protocol, runtime_checkable

import numpy.typing as npt

from .lifecycle import RuntimeLifecycleProtocol
from .numeric import FloatArray


@runtime_checkable
class ControllerProtocol(RuntimeLifecycleProtocol, Protocol):
    """Native controller lifecycle consumed by ALB system assemblers."""

    def input(self, time: float, error: npt.ArrayLike) -> None:
        """Validate and latch one controller sample without calculating."""

    def evaluate(self) -> FloatArray:
        """Advance the control law exactly once for the latched sample."""

    def output(self) -> FloatArray:
        """Return the completed command without advancing controller state."""


@runtime_checkable
class ServoValveProtocol(RuntimeLifecycleProtocol, Protocol):
    """Native servovalve lifecycle consumed by ALB system assemblers."""

    def input(self, time: float, command: npt.ArrayLike) -> None:
        """Validate and latch one valve command without advancing state."""

    def evaluate(self) -> FloatArray:
        """Advance valve state exactly once for the latched command."""

    def output(self) -> FloatArray:
        """Return the completed spool state without advancing it."""
