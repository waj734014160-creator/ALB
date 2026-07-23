"""Result recording and persistence adapters for rotor-bearing coupling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from ALB.contracts import (
    ArtifactManifest,
    ArtifactWriterProtocol,
    ResultBundle,
)
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode


def _component_result_node(
    component: Any,
    *,
    path: str,
    legacy_save_kwargs: dict[str, object],
) -> SaveTreeNode | None:
    """Build a node from the new snapshot protocol or a legacy save fallback."""

    snapshot_method = getattr(component, "result_snapshot", None)
    if callable(snapshot_method):
        snapshot = snapshot_method()
        if not isinstance(snapshot, ResultBundle):
            raise TypeError("component result_snapshot() must return ResultBundle")
        return SaveTreeNode(path, snapshot)
    save_method = getattr(component, "save", None)
    if callable(save_method):
        node = save_method(**legacy_save_kwargs)
        if not isinstance(node, SaveTreeNode):
            raise TypeError("legacy component save() must return SaveTreeNode")
        return node
    return None


def build_coupling_save_tree(
    results: Mapping[str, pd.DataFrame],
    rotor: Any,
    bearings: Sequence[Any],
    path: str | Path,
    name: str,
    *,
    tofile: bool,
    writer: ArtifactWriterProtocol | None,
) -> SaveTreeNode | ArtifactManifest:
    """Build and optionally persist one coupling result tree."""

    named_results = {f"{name}_{key}": data for key, data in results.items()}
    parent = SaveTreeNode(str(path), DataFrameResult(named_results))
    rotor_node = _component_result_node(
        rotor,
        path="rotor",
        legacy_save_kwargs={"tofile": False},
    )
    if rotor_node is not None:
        parent.add_child(rotor_node)
    for bearing in bearings:
        bearing_node = _component_result_node(
            bearing,
            path=f"{type(bearing).__name__}{bearing.node_link}",
            legacy_save_kwargs={
                "path": f"{type(bearing).__name__}{bearing.node_link}",
                "name": name,
                "tofile": False,
            },
        )
        if bearing_node is not None:
            parent.add_child(bearing_node)
    if tofile:
        return parent.persist(writer, path)
    return parent


__all__ = ["build_coupling_save_tree"]
