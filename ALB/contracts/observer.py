"""Immutable physical-step observer events and failure diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .recording import (
    PendingRecord,
    RecordReceipt,
    RecordKey,
    StepRecordingStatus,
)
from .results import ResultBundle
from .types import StepContext


@dataclass(frozen=True, slots=True)
class StepCompleted:
    """One committed physical-step event."""

    run_id: str
    context: StepContext
    bundle: ResultBundle
    recording_status: StepRecordingStatus
    record_receipt: RecordReceipt | None = None
    pending_record: PendingRecord | None = None


@dataclass(frozen=True, slots=True)
class RecordingRecovered:
    """Notification that one pending record was persisted without recomputation."""

    run_id: str
    key: RecordKey
    receipt: RecordReceipt


@dataclass(frozen=True, slots=True)
class ObserverFailure:
    """Sanitized failure produced by one observer invocation."""

    observer_name: str
    event_type: str
    error_type: str
    message: str


@runtime_checkable
class StepObserverProtocol(Protocol):
    """Receive immutable post-commit events."""

    def on_step_completed(self, event: StepCompleted) -> None:
        """Observe one committed physical step."""

    def on_recording_recovered(self, event: RecordingRecovered) -> None:
        """Observe successful recovery of one pending record."""


__all__ = [
    "ObserverFailure",
    "RecordingRecovered",
    "StepCompleted",
    "StepObserverProtocol",
]
