"""Tests for failure-isolated immutable observer dispatch."""

from ALB.contracts import (
    ResultBundle,
    StepCompleted,
    StepContext,
    StepRecordingStatus,
)
from ALB.infrastructure import ObserverDispatcher


class _Observer:
    def __init__(self, fail: bool = False) -> None:
        self.events = []
        self.fail = fail

    def on_step_completed(self, event) -> None:
        self.events.append(event)
        if self.fail:
            raise RuntimeError("observer failed")

    def on_recording_recovered(self, event) -> None:
        self.events.append(event)


def test_dispatch_isolates_one_observer_failure() -> None:
    good = _Observer()
    bad = _Observer(fail=True)
    dispatcher = ObserverDispatcher((bad, good), failure_capacity=1)
    event = StepCompleted(
        "run",
        StepContext(0, 0.0, 0.1, "dimensional"),
        ResultBundle({"force": [1.0, 2.0]}, {}),
        StepRecordingStatus.NOT_CONFIGURED,
    )
    failures = dispatcher.step_completed(event)
    assert good.events == [event]
    assert bad.events == [event]
    assert failures[0].error_type == "RuntimeError"
    assert dispatcher.failures == failures
