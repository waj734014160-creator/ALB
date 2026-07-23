"""Integration tests for unique physical-step recording."""

import pytest

from ALB import StepContext
from ALB.workflows import StepCommitLedger


def test_workflow_commits_each_physical_step_once():
    ledger = StepCommitLedger()
    first = StepContext(0, 0.0, 0.01, "dimensional")
    second = StepContext(1, 0.01, 0.01, "dimensional")

    ledger.commit_step(first)
    with pytest.raises(RuntimeError, match="already"):
        ledger.commit_step(first)
    ledger.commit_step(second)

    assert ledger.last_context == second
    assert ledger.is_last_committed(second)


@pytest.mark.parametrize(
    ("context", "message"),
    [
        (StepContext(2, 0.01, 0.01, "dimensional"), "step_index"),
        (StepContext(1, 0.02, 0.01, "dimensional"), "increment"),
        (StepContext(1, 0.02, 0.02, "dimensional"), "dt cannot change"),
    ],
)
def test_workflow_rejects_step_gaps_time_drift_and_dt_changes(context, message):
    ledger = StepCommitLedger()
    first = StepContext(0, 0.0, 0.01, "dimensional")
    ledger.commit_step(first)

    with pytest.raises(RuntimeError, match=message):
        ledger.commit_step(context)

    assert ledger.last_context == first
