"""Strict runtime contracts for controllers and servovalves."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ControllerProtocol(Protocol):
    """Native controller lifecycle consumed by ALB system assemblers."""

    def input(self, time: float, error: Any, *args: Any, **kwargs: Any) -> Any:
        """Validate and latch one controller sample without calculating."""

    def evaluate(self, *args: Any, **kwargs: Any) -> Any:
        """Advance the control law exactly once for the latched sample."""

    def output(self, *args: Any, **kwargs: Any) -> Any:
        """Return the completed command without advancing controller state."""


@runtime_checkable
class LegacyControllerProtocol(Protocol):
    """Deprecated controller shape whose ``output()`` still calculates."""

    def input(self, time: float, error: Any, *args: Any, **kwargs: Any) -> Any:
        """Accept one historical controller sample."""

    def output(self, *args: Any, **kwargs: Any) -> Any:
        """Calculate and return one historical command."""


@runtime_checkable
class ServoValveProtocol(Protocol):
    """Native servovalve lifecycle consumed by ALB system assemblers."""

    def input(self, time: float, command: Any, *args: Any, **kwargs: Any) -> Any:
        """Validate and latch one valve command without advancing state."""

    def evaluate(self, *args: Any, **kwargs: Any) -> Any:
        """Advance valve state exactly once for the latched command."""

    def output(self, *args: Any, **kwargs: Any) -> Any:
        """Return the completed spool state without advancing it."""
