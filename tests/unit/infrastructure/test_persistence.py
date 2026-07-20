"""Tests for inspectable artifact manifests."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from ALB.contracts import result_snapshot
from ALB.infrastructure.persistence import DirectoryArtifactWriter


def test_directory_writer_returns_verified_manifest(tmp_path) -> None:
    bundle = result_snapshot(
        {
            "field": np.array([[1.0, 2.0]], dtype=np.float64),
            "history": pd.DataFrame({"residual": [1.0, 0.1]}),
            "summary": {"iterations": 2},
        },
        {"case": "small"},
    )

    manifest = DirectoryArtifactWriter().write(bundle, tmp_path / "artifacts")

    assert {record.path for record in manifest.artifacts} == {
        "field.npy",
        "history.csv",
        "summary/iterations.json",
        "metadata/case.json",
    }
    for record in manifest.artifacts:
        payload = (tmp_path / "artifacts" / record.path).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == record.sha256
        assert len(payload) == record.size_bytes


def test_directory_writer_refuses_populated_destination(tmp_path) -> None:
    destination = tmp_path / "artifacts"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        DirectoryArtifactWriter().write(result_snapshot({"value": 1}), destination)
