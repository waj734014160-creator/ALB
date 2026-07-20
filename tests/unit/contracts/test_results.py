"""Tests for immutable result snapshots and artifact manifests."""

import numpy as np
import pytest

from ALB.contracts import ArtifactManifest, ArtifactRecord, result_snapshot


def test_result_snapshot_detaches_and_freezes_arrays():
    source = np.array([1.0, 2.0])
    bundle = result_snapshot({"force": source}, {"solver": "film"})
    source[0] = 9.0
    np.testing.assert_array_equal(bundle.values["force"], [1.0, 2.0])
    with pytest.raises(ValueError):
        bundle.values["force"][0] = 3.0


def test_artifact_manifest_is_verifiable():
    record = ArtifactRecord(
        path="results/force.npz",
        media_type="application/x-npz",
        sha256="0" * 64,
        size_bytes=12,
    )
    manifest = ArtifactManifest.now([record])
    assert manifest.artifacts == (record,)


def test_artifact_record_rejects_absolute_paths():
    with pytest.raises(ValueError, match="relative"):
        ArtifactRecord("C:/private/result.npz", "application/x-npz", "0" * 64, 1)
