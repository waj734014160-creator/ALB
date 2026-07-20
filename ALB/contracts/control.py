"""Controller and servovalve contracts."""

from typing import Any, Protocol, runtime_checkable

from .model import PersistableProtocol, SignalProtocol


@runtime_checkable
class ControllerProtocol(PersistableProtocol, Protocol):
    """Controller role independent of its control law."""

    signal: SignalProtocol

    def init(self, *args: Any, **kwargs: Any) -> Any:
        """Reset controller state."""

    def input(self, t: float, error: Any, *args: Any, **kwargs: Any) -> Any:
        """Accept one timestamped error sample."""

    def output(self, *args: Any, **kwargs: Any) -> Any:
        """Return the current controller command."""


@runtime_checkable
class ServoValveProtocol(PersistableProtocol, Protocol):
    """Servovalve dynamic role."""

    signal: SignalProtocol

    def init(self, *args: Any, **kwargs: Any) -> Any:
        """Reset valve state."""

    def input(self, t: float, command: Any, *args: Any, **kwargs: Any) -> Any:
        """Accept one timestamped valve command."""

    def output(self, *args: Any, **kwargs: Any) -> Any:
        """Return the current valve state or flow output."""

    def calc_is_finished(self, *args: Any, **kwargs: Any) -> bool:
        """Return whether the valve evaluation is complete."""
