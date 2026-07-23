"""Failure-isolated dispatch for immutable runtime observer events."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from ALB.contracts import (
    ObserverFailure,
    RecordingRecovered,
    StepCompleted,
    StepObserverProtocol,
)


class ObserverDispatcher:
    """Dispatch observer events while retaining bounded sanitized failures."""

    def __init__(
        self,
        observers: Iterable[StepObserverProtocol] = (),
        *,
        failure_capacity: int = 16,
    ) -> None:
        if (
            isinstance(failure_capacity, bool)
            or not isinstance(failure_capacity, int)
            or failure_capacity < 1
        ):
            raise ValueError("failure_capacity must be a positive integer")
        self._observers = tuple(observers)
        self._failures: deque[ObserverFailure] = deque(maxlen=failure_capacity)

    @property
    def failures(self) -> tuple[ObserverFailure, ...]:
        """Return the bounded sanitized observer failure history."""

        return tuple(self._failures)

    def step_completed(self, event: StepCompleted) -> tuple[ObserverFailure, ...]:
        """Send a committed-step event once to every configured observer."""

        return self._dispatch("on_step_completed", event)

    def recording_recovered(
        self, event: RecordingRecovered
    ) -> tuple[ObserverFailure, ...]:
        """Send a record-recovery event without repeating StepCompleted."""

        return self._dispatch("on_recording_recovered", event)

    def _dispatch(self, method_name: str, event: object) -> tuple[ObserverFailure, ...]:
        current = []
        for observer in self._observers:
            try:
                getattr(observer, method_name)(event)
            except Exception as exc:
                failure = ObserverFailure(
                    observer_name=type(observer).__name__,
                    event_type=type(event).__name__,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
                self._failures.append(failure)
                current.append(failure)
        return tuple(current)


__all__ = ["ObserverDispatcher"]
