"""Shared state transitions for strict stateful runtime components."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ALB.contracts.lifecycle import LifecycleState as LifecycleState


class RuntimeLifecycle:
    """Track one-input/one-evaluation freshness and terminal failures.

    ``READY`` accepts a new input. ``RUNNING`` means that one validated input
    is latched and must be evaluated before replacement. A successful
    evaluation returns to ``READY`` with one readable output. Any exception
    during a mutating phase enters ``FAILED`` and requires an explicit reset.
    """

    def __init__(self, owner: str, *, input_label: str = "input") -> None:
        self._owner = owner
        self._input_label = input_label
        self._state = LifecycleState.NEW
        self._output_available = False

    @property
    def state(self) -> LifecycleState:
        """Return the current lifecycle state."""

        return self._state

    @property
    def is_valid(self) -> bool:
        """Return whether the runtime is initialized and not failed."""

        return self._state in {LifecycleState.READY, LifecycleState.RUNNING}

    def reset(self, *, output_available: bool = False) -> None:
        """Enter ``READY`` and optionally publish an initialization snapshot."""

        self._state = LifecycleState.READY
        self._output_available = output_available

    def require_input_slot(self) -> None:
        """Require a runtime that can accept a new input."""

        if self._state is LifecycleState.FAILED:
            raise RuntimeError(
                f"{self._owner} is failed; rebuild it or let its owner "
                "reinitialize it before reuse"
            )
        if self._state is LifecycleState.NEW:
            raise RuntimeError(
                f"{self._owner} is not initialized; construct it through its "
                "public builder"
            )
        if self._state is LifecycleState.RUNNING:
            raise RuntimeError(
                f"{self._owner} has a latched input that must be evaluated first"
            )

    def latch(self) -> None:
        """Mark one already validated input as pending evaluation."""

        self.require_input_slot()
        self._state = LifecycleState.RUNNING
        self._output_available = False

    @contextmanager
    def evaluation(self) -> Iterator[None]:
        """Guard one mutating evaluation and publish freshness on success."""

        if self._state is LifecycleState.FAILED:
            raise RuntimeError(
                f"{self._owner} is failed; rebuild it or let its owner "
                "reinitialize it before reuse"
            )
        if self._state is not LifecycleState.RUNNING:
            raise RuntimeError(
                f"a new {self._input_label} is required before evaluate()"
            )
        try:
            yield
        except BaseException:
            self.fail()
            raise
        self._state = LifecycleState.READY
        self._output_available = True

    def require_output(self) -> None:
        """Require a completed output for the current input generation."""

        if self._state is LifecycleState.FAILED:
            raise RuntimeError(
                f"{self._owner} is failed; rebuild it or let its owner "
                "reinitialize it before reuse"
            )
        if self._state is not LifecycleState.READY or not self._output_available:
            raise RuntimeError(
                f"{self._owner} output is unavailable until evaluate() completes"
            )

    def fail(self) -> None:
        """Invalidate all public output after a partial mutation."""

        self._state = LifecycleState.FAILED
        self._output_available = False
