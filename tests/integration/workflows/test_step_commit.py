"""Integration tests for unique physical-step recording."""

import pytest

from ALB import StepContext
from ALB.workflows import StepCommitLedger


def test_workflow_commits_each_physical_step_once():
    ledger = StepCommitLedger()
    recorded = []
    first = StepContext(0, 0.0, 0.01, "dimensional")
    second = StepContext(1, 0.01, 0.01, "dimensional")

    ledger.commit_step(first, recorded.append)
    with pytest.raises(RuntimeError, match="already"):
        ledger.commit_step(first, recorded.append)
    ledger.commit_step(second, recorded.append)

    assert recorded == [first, second]
    assert ledger.last_context == second
