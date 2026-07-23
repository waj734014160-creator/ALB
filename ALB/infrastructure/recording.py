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
        self._pending_keys: set[RecordKey] = set()

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
        self._pending_keys = set()
        return RunReceipt(run_id, None, 0, (), None, None)

    def record(self, context: StepContext, bundle: ResultBundle) -> RecordReceipt:
        if self._active_run is None:
            raise RuntimeError("begin_run() must be called before record()")
        key = RecordKey(self._active_run, context.step_index)
        try:
            digest = bundle_digest(context, bundle)
            existing = self._receipts.get(key)
            if existing is not None:
                if existing.digest != digest:
                    raise RecordConflictError(
                        "record key conflicts with existing digest"
                    )
                self._pending_keys.discard(key)
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
            self._pending_keys.discard(key)
        except Exception:
            if key not in self._receipts:
                self._pending_keys.add(key)
            raise
        return receipt

    def register_pending(self, key: RecordKey) -> None:
        """Register one missing record owned by the active run."""

        if self._active_run is None or key.run_id != self._active_run:
            raise RuntimeError("pending key does not belong to the active run")
        self._pending_keys.add(key)

    def resolve_pending(self, key: RecordKey) -> None:
        """Resolve one run-local pending key after successful recording."""

        if self._active_run is None or key.run_id != self._active_run:
            raise RuntimeError("pending key does not belong to the active run")
        self._pending_keys.discard(key)

    def end_run(
        self, run_id: str, *, allow_incomplete: bool = False
    ) -> RunReceipt:
        if run_id != self._active_run:
            raise RuntimeError("run_id is not the active recorder run")
        pending = tuple(
            sorted(self._pending_keys, key=lambda key: key.step_index)
        )
        if pending and not allow_incomplete:
            raise RuntimeError(
                "recorder run has pending records; recover them or use "
                "allow_incomplete=True"
            )
        indexes = [
            key.step_index for key in self._bundles if key.run_id == run_id
        ]
        receipt = RunReceipt(
            run_id,
            (
                RunCloseStatus.INCOMPLETE
                if pending
                else RunCloseStatus.COMPLETE
            ),
            len(indexes),
            pending,
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
        self._pending_keys: set[RecordKey] = set()
        self._active_run: str | None = None

    def begin_run(self, run_id: str) -> RunReceipt:
        receipt = self._recorder.begin_run(run_id)
        self._pending_keys = set()
        self._active_run = run_id
        return receipt

    def record(self, context: StepContext, bundle: ResultBundle) -> RecordReceipt:
        if self._active_run is None:
            raise RuntimeError("begin_run() must be called before record()")
        key = RecordKey(self._active_run, context.step_index)
        try:
            filtered = ResultBundle(
                {
                    name: value
                    for name, value in bundle.values.items()
                    if name in self._fields
                },
                bundle.metadata,
            )
            receipt = self._recorder.record(context, filtered)
        except Exception:
            self._pending_keys.add(key)
            raise
        self._pending_keys.discard(receipt.key)
        return receipt

    def end_run(
        self, run_id: str, *, allow_incomplete: bool = False
    ) -> RunReceipt:
        pending = tuple(
            sorted(self._pending_keys, key=lambda key: key.step_index)
        )
        if pending and not allow_incomplete:
            raise RuntimeError(
                "recorder run has pending records; recover them or use "
                "allow_incomplete=True"
            )
        receipt = self._recorder.end_run(
            run_id,
            allow_incomplete=allow_incomplete,
        )
        self._active_run = None
        return _merge_pending_receipt(receipt, pending)

    def register_pending(self, key: RecordKey) -> None:
        """Forward run-level pending accounting to the wrapped recorder."""

        if self._active_run is None or key.run_id != self._active_run:
            raise RuntimeError("pending key does not belong to the active run")
        self._pending_keys.add(key)

    def resolve_pending(self, key: RecordKey) -> None:
        """Forward pending recovery to the wrapped recorder."""

        if self._active_run is None or key.run_id != self._active_run:
            raise RuntimeError("pending key does not belong to the active run")
        self._pending_keys.discard(key)


class SamplingRecorder:
    """Forward records selected by an explicit deterministic predicate."""

    def __init__(
        self,
        recorder: ResultRecorderProtocol,
        predicate: Callable[[StepContext], bool],
    ) -> None:
        self._recorder = recorder
        self._predicate = predicate
        self._pending_keys: set[RecordKey] = set()
        self._active_run: str | None = None

    def begin_run(self, run_id: str) -> RunReceipt:
        receipt = self._recorder.begin_run(run_id)
        self._pending_keys = set()
        self._active_run = run_id
        return receipt

    def record(self, context: StepContext, bundle: ResultBundle) -> RecordReceipt:
        if self._active_run is None:
            raise RuntimeError("begin_run() must be called before record()")
        key = RecordKey(self._active_run, context.step_index)
        try:
            if not self._predicate(context):
                bundle = ResultBundle(
                    {},
                    {
                        "sampling_skipped": True,
                        "original_step_index": context.step_index,
                    },
                )
            receipt = self._recorder.record(context, bundle)
        except Exception:
            self._pending_keys.add(key)
            raise
        self._pending_keys.discard(receipt.key)
        return receipt

    def end_run(
        self, run_id: str, *, allow_incomplete: bool = False
    ) -> RunReceipt:
        pending = tuple(
            sorted(self._pending_keys, key=lambda key: key.step_index)
        )
        if pending and not allow_incomplete:
            raise RuntimeError(
                "recorder run has pending records; recover them or use "
                "allow_incomplete=True"
            )
        receipt = self._recorder.end_run(
            run_id,
            allow_incomplete=allow_incomplete,
        )
        self._active_run = None
        return _merge_pending_receipt(receipt, pending)

    def register_pending(self, key: RecordKey) -> None:
        """Forward run-level pending accounting to the wrapped recorder."""

        if self._active_run is None or key.run_id != self._active_run:
            raise RuntimeError("pending key does not belong to the active run")
        self._pending_keys.add(key)

    def resolve_pending(self, key: RecordKey) -> None:
        """Forward pending recovery to the wrapped recorder."""

        if self._active_run is None or key.run_id != self._active_run:
            raise RuntimeError("pending key does not belong to the active run")
        self._pending_keys.discard(key)


def _merge_pending_receipt(
    receipt: RunReceipt,
    additional: tuple[RecordKey, ...],
) -> RunReceipt:
    """Return one run receipt containing all unrecovered keys."""

    pending = tuple(
        sorted(
            {*receipt.pending_keys, *additional},
            key=lambda key: key.step_index,
        )
    )
    if not pending:
        return receipt
    return RunReceipt(
        receipt.run_id,
        RunCloseStatus.INCOMPLETE,
        receipt.record_count,
        pending,
        receipt.first_step_index,
        receipt.last_step_index,
    )


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
