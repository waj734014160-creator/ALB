"""Explicit in-memory result recorders and bounded composable policies."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable

from ALB.contracts import (
    DIGEST_ALGORITHM,
    ExpiredRecordKey,
    RecordConflictError,
    RecordDisposition,
    RecordKey,
    RecordReceipt,
    ResultBundle,
    ResultRecorderProtocol,
    RunCloseStatus,
    RunReceipt,
    StepContext,
    bundle_digest,
)
from ALB.core.steps import StepCommitLedger


class InMemoryResultRecorder:
    """Store complete immutable result history for one active run."""

    def __init__(self) -> None:
        self._active_run: str | None = None
        self._closed_runs: set[str] = set()
        self._ledger = StepCommitLedger()
        self._bundles: OrderedDict[RecordKey, ResultBundle] = OrderedDict()
        self._receipts: dict[RecordKey, RecordReceipt] = {}

    @property
    def records(self) -> tuple[tuple[RecordKey, ResultBundle], ...]:
        """Return the ordered immutable record view."""

        return tuple(self._bundles.items())

    def begin_run(self, run_id: str) -> RunReceipt:
        from ALB.contracts.recording import validate_run_id

        run_id = validate_run_id(run_id)
        if self._active_run is not None:
            raise RuntimeError("a recorder run is already active")
        if run_id in self._closed_runs:
            raise RuntimeError("closed run_id cannot be reopened")
        self._active_run = run_id
        self._ledger = StepCommitLedger()
        return RunReceipt(run_id, None, 0, (), None, None)

    def record(self, context: StepContext, bundle: ResultBundle) -> RecordReceipt:
        if self._active_run is None:
            raise RuntimeError("begin_run() must be called before record()")
        key = RecordKey(self._active_run, context.step_index)
        digest = bundle_digest(context, bundle)
        existing = self._receipts.get(key)
        if existing is not None:
            if existing.digest != digest:
                raise RecordConflictError("record key conflicts with existing digest")
            return RecordReceipt(
                key,
                DIGEST_ALGORITHM,
                digest,
                RecordDisposition.IDEMPOTENT_DUPLICATE,
            )
        self._ledger.validate_next(context)
        receipt = RecordReceipt(
            key,
            DIGEST_ALGORITHM,
            digest,
            RecordDisposition.RECORDED,
        )
        self._ledger.commit_step(context)
        self._bundles[key] = bundle
        self._receipts[key] = receipt
        return receipt

    def end_run(
        self, run_id: str, *, allow_incomplete: bool = False
    ) -> RunReceipt:
        if run_id != self._active_run:
            raise RuntimeError("run_id is not the active recorder run")
        indexes = [
            key.step_index for key in self._bundles if key.run_id == run_id
        ]
        receipt = RunReceipt(
            run_id,
            RunCloseStatus.COMPLETE,
            len(indexes),
            (),
            indexes[0] if indexes else None,
            indexes[-1] if indexes else None,
        )
        self._closed_runs.add(run_id)
        self._active_run = None
        return receipt


class FieldFilteringRecorder:
    """Record selected top-level result fields through another recorder."""

    def __init__(
        self, recorder: ResultRecorderProtocol, fields: tuple[str, ...]
    ) -> None:
        self._recorder = recorder
        self._fields = frozenset(fields)

    def begin_run(self, run_id: str) -> RunReceipt:
        return self._recorder.begin_run(run_id)

    def record(self, context: StepContext, bundle: ResultBundle) -> RecordReceipt:
        filtered = ResultBundle(
            {key: value for key, value in bundle.values.items() if key in self._fields},
            bundle.metadata,
        )
        return self._recorder.record(context, filtered)

    def end_run(
        self, run_id: str, *, allow_incomplete: bool = False
    ) -> RunReceipt:
        return self._recorder.end_run(run_id, allow_incomplete=allow_incomplete)


class SamplingRecorder:
    """Forward records selected by an explicit deterministic predicate."""

    def __init__(
        self,
        recorder: ResultRecorderProtocol,
        predicate: Callable[[StepContext], bool],
    ) -> None:
        self._recorder = recorder
        self._predicate = predicate

    def begin_run(self, run_id: str) -> RunReceipt:
        return self._recorder.begin_run(run_id)

    def record(self, context: StepContext, bundle: ResultBundle) -> RecordReceipt:
        if not self._predicate(context):
            bundle = ResultBundle(
                {},
                {
                    "sampling_skipped": True,
                    "original_step_index": context.step_index,
                },
            )
        return self._recorder.record(context, bundle)

    def end_run(
        self, run_id: str, *, allow_incomplete: bool = False
    ) -> RunReceipt:
        return self._recorder.end_run(run_id, allow_incomplete=allow_incomplete)


class RingBufferResultRecorder(InMemoryResultRecorder):
    """Bound result data and idempotency receipts to a fixed window."""

    def __init__(self, capacity: int) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        super().__init__()
        self.idempotency_window = capacity
        self._expired_through: int | None = None

    def begin_run(self, run_id: str) -> RunReceipt:
        """Begin a run with a fresh run-local expiration boundary."""

        self._expired_through = None
        return super().begin_run(run_id)

    def record(self, context: StepContext, bundle: ResultBundle) -> RecordReceipt:
        if (
            self._expired_through is not None
            and context.step_index <= self._expired_through
        ):
            raise ExpiredRecordKey("record key has left the idempotency window")
        receipt = super().record(context, bundle)
        while len(self._bundles) > self.idempotency_window:
            key, _ = self._bundles.popitem(last=False)
            self._receipts.pop(key, None)
            self._expired_through = key.step_index
        return receipt


__all__ = [
    "FieldFilteringRecorder",
    "InMemoryResultRecorder",
    "RingBufferResultRecorder",
    "SamplingRecorder",
]
