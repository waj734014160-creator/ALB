"""Filesystem artifact writers implementing the public persistence protocol."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ALB.contracts.results import (
    ArtifactManifest,
    ArtifactRecord,
    ResultBundle,
)


class DirectoryArtifactWriter:
    """Write a result bundle to a directory and return content digests.

    Arrays are stored as ``.npy`` files, data frames as UTF-8 CSV files, and
    JSON-compatible values as JSON. The writer refuses to reuse a populated
    destination unless ``overwrite`` was explicitly enabled.
    """

    def __init__(self, *, overwrite: bool = False) -> None:
        self._overwrite = overwrite

    def write(self, bundle: ResultBundle, destination: Path) -> ArtifactManifest:
        """Persist ``bundle`` and return a caller-verifiable artifact manifest."""

        destination = Path(destination)
        if destination.exists() and any(destination.iterdir()) and not self._overwrite:
            raise FileExistsError(f"destination is not empty: {destination}")
        destination.mkdir(parents=True, exist_ok=True)

        records: list[ArtifactRecord] = []
        for key, value in bundle.values.items():
            records.extend(self._write_value(destination, str(key), value))
        records.extend(self._write_value(destination, "metadata", dict(bundle.metadata)))
        return ArtifactManifest.now(records)

    def _write_value(
        self,
        destination: Path,
        key: str,
        value: Any,
    ) -> list[ArtifactRecord]:
        safe_key = _safe_relative_stem(key)
        if isinstance(value, Mapping):
            records: list[ArtifactRecord] = []
            for child_key, child_value in value.items():
                records.extend(
                    self._write_value(
                        destination,
                        f"{safe_key}/{child_key}",
                        child_value,
                    )
                )
            return records
        if isinstance(value, np.ndarray):
            path = destination / f"{safe_key}.npy"
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, value, allow_pickle=False)
            return [_record(destination, path, "application/x-npy")]
        if isinstance(value, pd.DataFrame):
            path = destination / f"{safe_key}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            value.to_csv(path, encoding="utf-8")
            return [_record(destination, path, "text/csv")]

        path = destination / f"{safe_key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
        return [_record(destination, path, "application/json")]


def _safe_relative_stem(value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"artifact key is not a safe relative path: {value!r}")
    return path


def _record(root: Path, path: Path, media_type: str) -> ArtifactRecord:
    payload = path.read_bytes()
    return ArtifactRecord(
        path=path.relative_to(root).as_posix(),
        media_type=media_type,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"value of type {type(value).__name__} is not JSON serializable")
