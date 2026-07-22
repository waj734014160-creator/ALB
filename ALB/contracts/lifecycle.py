"""State contracts shared by strict runtime components."""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable


class LifecycleState(str, Enum):
    """Stable states for initialized, advancing, and failed runtimes."""

    NEW = "new"
    READY = "ready"
    RUNNING = "running"
    FAILED = "failed"


@runtime_checkable
class RuntimeLifecycleProtocol(Protocol):
    """Expose the observable state of a strict runtime component."""

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the current runtime state without mutating the component."""
