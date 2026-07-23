"""Deprecated observer bridge for external consumers of the legacy Signal tree."""

from __future__ import annotations

import warnings

from ALB.contracts import RecordingRecovered, StepCompleted
from ALB.core.events import Signal


class LegacySignalAdapter:
    """Translate committed-step events to the old callback signal.

    This 0.3.x compatibility surface is eligible for removal no earlier than
    0.4.0 after declared consumers reach zero.
    """

    def __init__(self, component) -> None:
        warnings.warn(
            "LegacySignalAdapter is deprecated; use StepObserverProtocol",
            DeprecationWarning,
            stacklevel=2,
        )
        self.signal = Signal(sys=component)

    def on_step_completed(self, event: StepCompleted) -> None:
        self.signal.lead_loop("finish_signal")

    def on_recording_recovered(self, event: RecordingRecovered) -> None:
        return None


__all__ = ["LegacySignalAdapter"]
