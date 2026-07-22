"""Result assembly and persistence adapters for ROSS rotor runtimes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import ross as rs  # type: ignore[import-untyped]

from ALB.contracts import ArtifactManifest, ArtifactWriterProtocol
from ALB.contracts.numeric import FloatArray
from ALB.contracts.result_tree import RossRotorResult, SaveTreeNode
from ALB.dynamics.rotor_layout import RotorDofLayout


def build_time_response_results(
    rotor: rs.Rotor,
    times: Sequence[float],
    outputs: Sequence[npt.ArrayLike],
    states: Sequence[npt.ArrayLike],
) -> object:
    """Build a detached ROSS time-response value from runtime histories."""

    return rs.TimeResponseResults(
        rotor,
        np.asarray(times, dtype=float),
        np.asarray(outputs),
        np.asarray(states),
    )


def extract_displacement_history(
    outputs: Sequence[npt.ArrayLike],
    layout: RotorDofLayout,
    node: int,
    ndof: int,
) -> FloatArray:
    """Return caller-owned x/y displacement history for one validated node."""

    x_index = layout.global_index(node, "x", ndof)
    y_index = layout.global_index(node, "y", ndof)
    return np.asarray(outputs, dtype=np.float64)[:, [x_index, y_index]].copy()


def build_rotor_save_tree(
    *,
    times: Sequence[float],
    states: Sequence[npt.ArrayLike],
    outputs: Sequence[npt.ArrayLike],
    response: object,
    rotor: rs.Rotor,
    path: str | Path,
    name: str,
    tofile: bool,
    writer: ArtifactWriterProtocol | None,
) -> SaveTreeNode | ArtifactManifest:
    """Build and optionally persist one rotor result tree."""

    result = RossRotorResult(
        np.asarray(times, dtype=np.float64),
        np.asarray(states),
        np.asarray(outputs),
        response,
        rotor,
        name=name,
    )
    node = SaveTreeNode(str(path), result)
    if tofile:
        return node.persist(writer, path)
    return node


__all__ = [
    "build_rotor_save_tree",
    "build_time_response_results",
    "extract_displacement_history",
]
