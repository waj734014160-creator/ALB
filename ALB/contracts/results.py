"""Filesystem-independent result and artifact contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

import numpy as np


def _snapshot_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        array = value.copy()
        array.setflags(write=False)
        return array
    if isinstance(value, Mapping):
        return MappingProxyType({key: _snapshot_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_snapshot_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_snapshot_value(item) for item in value)
    return deepcopy(value)


@dataclass(frozen=True, slots=True)
class ResultBundle:
    """Immutable snapshot of numerical data and associated metadata."""

    values: Mapping[str, Any]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _snapshot_value(dict(self.values)))
        object.__setattr__(self, "metadata", _snapshot_value(dict(self.metadata)))


def result_snapshot(
    values: Mapping[str, Any], metadata: Mapping[str, Any] | None = None
) -> ResultBundle:
    """Create an immutable copy detached from mutable solver state."""

    return ResultBundle(values=values, metadata=metadata or {})


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """One persisted artifact with a caller-verifiable digest."""

    path: str
    media_type: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not self.path or Path(self.path).is_absolute():
            raise ValueError("artifact paths must be nonempty and relative")
        if not self.media_type:
            raise ValueError("media_type must be nonempty")
        digest = self.sha256.lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be nonnegative")
        object.__setattr__(self, "sha256", digest)


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    """Inspectable record returned by every artifact writer."""

    artifacts: tuple[ArtifactRecord, ...]
    created_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        try:
            datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("created_at must be an ISO-8601 timestamp") from exc

    @classmethod
    def now(cls, artifacts: Sequence[ArtifactRecord]) -> "ArtifactManifest":
        """Build a manifest using the current UTC timestamp."""

        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return cls(tuple(artifacts), created_at)


@runtime_checkable
class ArtifactWriterProtocol(Protocol):
    """Persistence boundary consumed by workflows, never by numerical kernels."""

    def write(self, bundle: ResultBundle, destination: Path) -> ArtifactManifest:
        """Persist a result bundle and return a verifiable manifest."""


@runtime_checkable
class ResultSnapshotProtocol(Protocol):
    """Read the most recent immutable numerical result."""

    def result_snapshot(self) -> ResultBundle:
        """Return a detached snapshot without advancing component state."""


@runtime_checkable
class ResultRecorderProtocol(Protocol):
    """Receive immutable results without exposing filesystem concerns."""

    def record(self, bundle: ResultBundle) -> None:
        """Record one completed bundle exactly once."""
