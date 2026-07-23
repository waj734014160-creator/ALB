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
from ALB.core.diagnostics import sanitize_exception_message


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

        current = []
        for observer in self._observers:
            try:
                observer.on_step_completed(event)
            except Exception as exc:
                current.append(self._record_failure(observer, event, exc))
        return tuple(current)

    def recording_recovered(
        self, event: RecordingRecovered
    ) -> tuple[ObserverFailure, ...]:
        """Send a record-recovery event without repeating StepCompleted."""

        current = []
        for observer in self._observers:
            try:
                observer.on_recording_recovered(event)
            except Exception as exc:
                current.append(self._record_failure(observer, event, exc))
        return tuple(current)

    def _record_failure(
        self,
        observer: StepObserverProtocol,
        event: StepCompleted | RecordingRecovered,
        error: Exception,
    ) -> ObserverFailure:
        """Store one bounded sanitized observer diagnostic."""

        failure = ObserverFailure(
            observer_name=type(observer).__name__,
            event_type=type(event).__name__,
            error_type=type(error).__name__,
            message=sanitize_exception_message(error),
        )
        self._failures.append(failure)
        return failure


__all__ = ["ObserverDispatcher"]
