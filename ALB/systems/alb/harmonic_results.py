"""Result persistence adapter for the harmonic ALB runtime."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from ALB.contracts import ArtifactManifest, ArtifactWriterProtocol
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode


def build_harmonic_save_tree(
    results: pd.DataFrame,
    coefficient_metadata: Mapping[str, object],
    path: str | Path,
    name: str,
    *,
    tofile: bool,
    writer: ArtifactWriterProtocol | None,
) -> SaveTreeNode | ArtifactManifest:
    """Build and optionally persist harmonic results and coefficient metadata."""

    coefficient_frame = pd.DataFrame([dict(coefficient_metadata)])
    payload = DataFrameResult(
        {name: results.copy(), f"{name}_configuration": coefficient_frame}
    )
    node = SaveTreeNode(str(path), payload)
    if tofile:
        return node.persist(writer, path)
    return node


__all__ = ["build_harmonic_save_tree"]
