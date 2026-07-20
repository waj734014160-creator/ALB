"""Tests for the filesystem-independent result-tree compatibility contract."""

from __future__ import annotations

import pandas as pd
import pytest

from ALB.contracts import ArtifactManifest, DataFrameResult, SaveTreeNode
from ALB.infrastructure.persistence import DirectoryArtifactWriter


def test_result_tree_requires_an_injected_writer(tmp_path) -> None:
    tree = SaveTreeNode(
        "bearing",
        DataFrameResult({"force": pd.DataFrame({"fx": [1.0], "fy": [-2.0]})}),
    )

    with pytest.raises(RuntimeError, match="injected ArtifactWriterProtocol"):
        tree.persist(None, tmp_path / "result")


def test_result_tree_persistence_returns_manifest(tmp_path) -> None:
    tree = SaveTreeNode(
        "bearing",
        DataFrameResult({"force": pd.DataFrame({"fx": [1.0], "fy": [-2.0]})}),
    )

    manifest = tree.persist(DirectoryArtifactWriter(), tmp_path / "result")

    assert isinstance(manifest, ArtifactManifest)
    assert {artifact.path for artifact in manifest.artifacts} == {
        "force.csv",
        "metadata/logical_root.json",
        "metadata/schema.json",
    }
