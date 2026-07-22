"""Result recording and persistence adapters for rotor-bearing coupling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from ALB.contracts import ArtifactManifest, ArtifactWriterProtocol
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode


class _SaveNodeProvider(Protocol):
    node_link: int

    def save(self, *args: Any, **kwargs: Any) -> SaveTreeNode:
        """Return a detached persistence-tree node."""


def build_coupling_save_tree(
    results: Mapping[str, pd.DataFrame],
    rotor: _SaveNodeProvider,
    bearings: Sequence[_SaveNodeProvider],
    path: str | Path,
    name: str,
    *,
    tofile: bool,
    writer: ArtifactWriterProtocol | None,
) -> SaveTreeNode | ArtifactManifest:
    """Build and optionally persist one coupling result tree."""

    named_results = {f"{name}_{key}": data for key, data in results.items()}
    parent = SaveTreeNode(str(path), DataFrameResult(named_results))
    parent.add_child(rotor.save(tofile=False))
    parent.add_children(
        [
            bearing.save(
                path=f"{type(bearing).__name__}{bearing.node_link}",
                name=name,
                tofile=False,
            )
            for bearing in bearings
        ]
    )
    if tofile:
        return parent.persist(writer, path)
    return parent


__all__ = ["build_coupling_save_tree"]
