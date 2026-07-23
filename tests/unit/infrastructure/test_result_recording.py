"""Tests for run-scoped result recording and canonical digests."""

import numpy as np
import pytest

from ALB.contracts import (
    ExpiredRecordKey,
    RecordConflictError,
    RecordDisposition,
    ResultBundle,
    RunCloseStatus,
    StepContext,
    UnsupportedResultValueError,
    bundle_digest,
)
from ALB.infrastructure import InMemoryResultRecorder, RingBufferResultRecorder


def _context(index: int) -> StepContext:
    return StepContext(index, index * 0.1, 0.1, "dimensional")


def _bundle(value=1.0) -> ResultBundle:
    return ResultBundle(
        {"force": np.array([value, -value]), "scalar": np.float64(value)},
        {"source": "test"},
    )


def test_bundle_digest_is_canonical_and_preserves_float_sign_bits() -> None:
    context = _context(0)
    assert bundle_digest(context, _bundle()) == bundle_digest(context, _bundle())
    positive = ResultBundle({"value": 0.0}, {})
    negative = ResultBundle({"value": -0.0}, {})
    assert bundle_digest(context, positive) != bundle_digest(context, negative)


@pytest.mark.parametrize(
    "value",
    [
        np.array([object()], dtype=object),
        np.array([np.nan]),
        {"bad": object()},
    ],
)
def test_bundle_digest_rejects_unsupported_values(value) -> None:
    with pytest.raises(UnsupportedResultValueError):
        bundle_digest(_context(0), ResultBundle({"value": value}, {}))


def test_in_memory_recorder_is_run_scoped_continuous_and_idempotent() -> None:
    recorder = InMemoryResultRecorder()
    recorder.begin_run("run-1")
    first = recorder.record(_context(0), _bundle(1.0))
    duplicate = recorder.record(_context(0), _bundle(1.0))
    assert first.disposition is RecordDisposition.RECORDED
    assert duplicate.disposition is RecordDisposition.IDEMPOTENT_DUPLICATE
    with pytest.raises(RecordConflictError):
        recorder.record(_context(0), _bundle(2.0))
    recorder.record(_context(1), _bundle(2.0))
    receipt = recorder.end_run("run-1")
    assert receipt.close_status is RunCloseStatus.COMPLETE
    assert receipt.record_count == 2
    with pytest.raises(RuntimeError, match="reopened"):
        recorder.begin_run("run-1")


def test_ring_buffer_expires_old_idempotency_keys() -> None:
    recorder = RingBufferResultRecorder(2)
    recorder.begin_run("bounded")
    for index in range(3):
        recorder.record(_context(index), _bundle(float(index + 1)))
    assert len(recorder.records) == 2
    with pytest.raises(ExpiredRecordKey):
        recorder.record(_context(0), _bundle(1.0))
