"""Run-scoped result recording contracts and canonical bundle digests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import struct
from typing import Any, Mapping, Protocol, runtime_checkable

import numpy as np

from .results import ResultBundle, _FrozenList
from .types import StepContext


DIGEST_ALGORITHM = "alb.result-bundle.sha256.v1"


class UnsupportedResultValueError(TypeError):
    """Raised when a value cannot participate in the v1 result digest."""


class RecordConflictError(RuntimeError):
    """Raised when one record key is reused with different content."""


class ExpiredRecordKey(RuntimeError):
    """Raised when a bounded recorder can no longer verify an old key."""


class StepRecordingStatus(str, Enum):
    """Closed status set for one committed physical step."""

    NOT_CONFIGURED = "not_configured"
    RECORDED = "recorded"
    PENDING = "pending"


class RunCloseStatus(str, Enum):
    """Closed status set for an explicitly ended recorder run."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class RecordDisposition(str, Enum):
    """Outcome of one idempotent record request."""

    RECORDED = "recorded"
    IDEMPOTENT_DUPLICATE = "idempotent_duplicate"


@dataclass(frozen=True, slots=True)
class RecordKey:
    """Unique run-scoped result key."""

    run_id: str
    step_index: int


@dataclass(frozen=True, slots=True)
class RecordReceipt:
    """Verifiable receipt for one result record."""

    key: RecordKey
    digest_algorithm: str
    digest: str
    disposition: RecordDisposition


@dataclass(frozen=True, slots=True)
class PendingRecord:
    """Immutable post-commit record request that may be retried safely."""

    run_id: str
    context: StepContext
    bundle: ResultBundle
    error_summary: str

    @property
    def key(self) -> RecordKey:
        """Return the idempotency key for the pending result."""

        return RecordKey(self.run_id, self.context.step_index)


@dataclass(frozen=True, slots=True)
class RunReceipt:
    """Summary returned when a recorder run starts or ends."""

    run_id: str
    close_status: RunCloseStatus | None
    record_count: int
    pending_keys: tuple[RecordKey, ...]
    first_step_index: int | None
    last_step_index: int | None


def validate_run_id(run_id: str) -> str:
    """Return a valid opaque run identifier."""

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a nonempty string")
    if any(unicodedata_category(character).startswith("C") for character in run_id):
        raise ValueError("run_id cannot contain Unicode control characters")
    return run_id


def unicodedata_category(character: str) -> str:
    """Defer the optional module lookup used by run identifier validation."""

    import unicodedata

    return unicodedata.category(character)


def _length_prefixed(payload: bytes) -> bytes:
    return struct.pack("<Q", len(payload)) + payload


def _encode_scalar(value: Any) -> bytes:
    if value is None:
        return b"N"
    if isinstance(value, np.generic):
        return _encode_scalar(value.item())
    if isinstance(value, bool):
        return b"B" + bytes((int(value),))
    if isinstance(value, int):
        payload = str(value).encode("ascii")
        return b"I" + _length_prefixed(payload)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsupportedResultValueError("floating result values must be finite")
        return b"F" + struct.pack("<d", value)
    if isinstance(value, complex):
        if not math.isfinite(value.real) or not math.isfinite(value.imag):
            raise UnsupportedResultValueError("complex result values must be finite")
        return b"C" + struct.pack("<dd", value.real, value.imag)
    if isinstance(value, str):
        return b"S" + _length_prefixed(value.encode("utf-8"))
    if isinstance(value, bytes):
        return b"Y" + _length_prefixed(value)
    raise UnsupportedResultValueError(
        f"unsupported result value type: {type(value).__name__}"
    )


def _validate_array_dtype(dtype: np.dtype[Any]) -> None:
    if dtype.hasobject:
        raise UnsupportedResultValueError("object dtype arrays are not recordable")
    if dtype.fields:
        for name in dtype.names or ():
            _validate_array_dtype(dtype.fields[name][0])
        return
    base = dtype.subdtype[0] if dtype.subdtype else dtype
    if base.kind not in "biufc":
        raise UnsupportedResultValueError(f"unsupported ndarray dtype: {dtype}")


def _encode_dtype(dtype: np.dtype[Any]) -> bytes:
    if dtype.fields:
        payload = []
        for name in dtype.names or ():
            field_dtype, offset = dtype.fields[name][:2]
            payload.append(
                _length_prefixed(name.encode("utf-8"))
                + struct.pack("<Q", offset)
                + _length_prefixed(_encode_dtype(field_dtype))
            )
        return b"R" + struct.pack("<Q", len(payload)) + b"".join(payload)
    if dtype.subdtype:
        base, shape = dtype.subdtype
        return (
            b"U"
            + _length_prefixed(_encode_dtype(base))
            + struct.pack("<Q", len(shape))
            + b"".join(struct.pack("<Q", item) for item in shape)
        )
    return b"D" + _length_prefixed(dtype.newbyteorder("<").str.encode("ascii"))


def _encode_array(value: np.ndarray[Any, Any]) -> bytes:
    _validate_array_dtype(value.dtype)
    if value.dtype.fields:
        dtype_payload = _encode_dtype(value.dtype)
        data_payload = b"".join(
            _length_prefixed(_encode_array(np.asarray(value[name])))
            for name in value.dtype.names or ()
        )
    else:
        if value.dtype.kind in "fc" and not np.all(np.isfinite(value)):
            raise UnsupportedResultValueError("floating ndarray values must be finite")
        canonical_dtype = value.dtype.newbyteorder("<")
        canonical = np.ascontiguousarray(value, dtype=canonical_dtype)
        dtype_payload = canonical_dtype.str.encode("ascii")
        data_payload = canonical.tobytes(order="C")
    shape = b"".join(struct.pack("<Q", dimension) for dimension in value.shape)
    return (
        b"A"
        + _length_prefixed(dtype_payload)
        + struct.pack("<Q", value.ndim)
        + shape
        + _length_prefixed(data_payload)
    )


def _encode_value(value: Any) -> bytes:
    if isinstance(value, np.ndarray):
        return _encode_array(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise UnsupportedResultValueError("result mapping keys must be strings")
        payload = []
        for key in sorted(value, key=lambda item: item.encode("utf-8")):
            payload.append(
                _length_prefixed(key.encode("utf-8")) + _encode_value(value[key])
            )
        return b"M" + struct.pack("<Q", len(payload)) + b"".join(payload)
    if isinstance(value, _FrozenList):
        return b"L" + struct.pack("<Q", len(value)) + b"".join(
            _encode_value(item) for item in value
        )
    if isinstance(value, tuple):
        return b"T" + struct.pack("<Q", len(value)) + b"".join(
            _encode_value(item) for item in value
        )
    if isinstance(value, list):
        return b"L" + struct.pack("<Q", len(value)) + b"".join(
            _encode_value(item) for item in value
        )
    return _encode_scalar(value)


def validate_recordable_bundle(bundle: ResultBundle) -> None:
    """Reject values outside the versioned recorder value domain."""

    if not isinstance(bundle, ResultBundle):
        raise TypeError("bundle must be ResultBundle")
    _encode_value(bundle.values)
    _encode_value(bundle.metadata)


def bundle_digest(context: StepContext, bundle: ResultBundle) -> str:
    """Return the canonical SHA-256 digest for one contextual result."""

    validate_recordable_bundle(bundle)
    context_payload = {
        "step_index": context.step_index,
        "time": context.time,
        "dt": context.dt,
        "unit_system": context.unit_system.value,
    }
    digest = hashlib.sha256()
    digest.update(DIGEST_ALGORITHM.encode("utf-8"))
    digest.update(_encode_value(context_payload))
    digest.update(_encode_value(bundle.values))
    digest.update(_encode_value(bundle.metadata))
    return digest.hexdigest()


@runtime_checkable
class ResultRecorderProtocol(Protocol):
    """Record immutable step results inside one explicit active run."""

    def begin_run(self, run_id: str) -> RunReceipt:
        """Begin the only active run."""

    def record(self, context: StepContext, bundle: ResultBundle) -> RecordReceipt:
        """Record one continuous step idempotently."""

    def end_run(
        self, run_id: str, *, allow_incomplete: bool = False
    ) -> RunReceipt:
        """Close the active run and return its final receipt."""


@runtime_checkable
class PendingAwareResultRecorderProtocol(ResultRecorderProtocol, Protocol):
    """Recorder capability for run-level pending-record accounting."""

    def register_pending(self, key: RecordKey) -> None:
        """Register one committed result that has not been recorded."""

    def resolve_pending(self, key: RecordKey) -> None:
        """Remove one pending key after an idempotent record succeeds."""


__all__ = [
    "DIGEST_ALGORITHM",
    "ExpiredRecordKey",
    "PendingRecord",
    "PendingAwareResultRecorderProtocol",
    "RecordConflictError",
    "RecordDisposition",
    "RecordKey",
    "RecordReceipt",
    "ResultRecorderProtocol",
    "RunCloseStatus",
    "RunReceipt",
    "StepRecordingStatus",
    "UnsupportedResultValueError",
    "bundle_digest",
    "validate_recordable_bundle",
    "validate_run_id",
]
