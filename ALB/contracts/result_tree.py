"""Filesystem-independent structured result payloads used during migration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt
import pandas as pd

from .results import ArtifactManifest, ArtifactWriterProtocol, ResultBundle, result_snapshot

if TYPE_CHECKING:
    from ross import Rotor, TimeResponseResults  # type: ignore[import-untyped]


@dataclass
class DataFrameResult:
    """Named tabular results without any persistence behavior."""

    result: Mapping[str, pd.DataFrame]

    def __post_init__(self) -> None:
        invalid = [
            key for key, value in self.result.items() if not isinstance(value, pd.DataFrame)
        ]
        if invalid:
            raise TypeError(
                f"DataFrameResult values must be pandas DataFrame objects: {invalid}"
            )
        self.result = dict(self.result)

    def __getitem__(self, item: str) -> pd.DataFrame:
        return self.result[item]


@dataclass
class NpyResult:
    """Named NumPy array results without any persistence behavior."""

    result: Mapping[str, npt.NDArray[np.generic]]

    def __post_init__(self) -> None:
        invalid = [
            key for key, value in self.result.items() if not isinstance(value, np.ndarray)
        ]
        if invalid:
            raise TypeError(f"NpyResult values must be NumPy arrays: {invalid}")
        self.result = dict(self.result)

    def __getitem__(self, item: str) -> npt.NDArray[np.generic]:
        return self.result[item]


@dataclass
class RossRotorResult:
    """In-memory rotor response payload retained for workflow handoff."""

    t: Sequence[float] | npt.NDArray[np.generic]
    xout: Sequence[float] | npt.NDArray[np.generic]
    yout: Sequence[float] | npt.NDArray[np.generic]
    rotor_result: "TimeResponseResults"
    rotor: "Rotor"
    name: str


class SaveTreeNode:
    """A filesystem-independent tree of named numerical result payloads.

    The historical class mixed numerical result assembly with direct CSV, NPY,
    HTML, TOML, and pickle writes. In 0.2 the tree only describes data. A
    workflow may call :meth:`persist` with an injected writer and receives an
    inspectable :class:`ArtifactManifest`.
    """

    def __init__(
        self,
        path: str,
        data: Any,
        children: list["SaveTreeNode"] | None = None,
    ) -> None:
        self.path = str(path)
        self.data = data
        self.children: list[SaveTreeNode] = []
        self.parent: SaveTreeNode | None = None
        self.add_children(children or [])

    def add_child(self, child: "SaveTreeNode") -> None:
        child.parent = self
        self.children.append(child)

    def add_children(self, children: Sequence["SaveTreeNode"]) -> None:
        for child in children:
            self.add_child(child)

    def get_dir(self) -> dict[str, Any]:
        """Return the logical tree layout without accessing the filesystem."""

        if not self.children:
            return {self.path: None}
        return {
            self.path: {
                key: value
                for child in self.children
                for key, value in child.get_dir().items()
            }
        }

    def return_root(self) -> "SaveTreeNode":
        """Return the root node containing this node."""

        return self if self.parent is None else self.parent.return_root()

    def result_snapshot(self) -> ResultBundle:
        """Create an immutable result bundle suitable for an artifact writer."""

        return result_snapshot(
            _node_values(self),
            {
                "schema": "alb.result-tree.v1",
                "logical_root": _logical_name(self.path),
            },
        )

    def persist(
        self,
        writer: ArtifactWriterProtocol | None,
        destination: str | Path | None = None,
    ) -> ArtifactManifest:
        """Persist through an injected writer and return its artifact manifest."""

        if writer is None:
            raise RuntimeError(
                "persistence requires an injected ArtifactWriterProtocol; "
                "numerical modules do not write files directly in ALB 0.2"
            )
        target = Path(destination if destination is not None else self.path)
        return writer.write(self.result_snapshot(), target)


def _logical_name(value: str) -> str:
    normalized = value.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] or "result"


def _payload_values(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    if isinstance(data, ResultBundle):
        return {
            "values": dict(data.values),
            "metadata": dict(data.metadata),
        }
    if isinstance(data, (DataFrameResult, NpyResult)):
        return dict(data.result)
    if isinstance(data, RossRotorResult):
        return {
            f"{data.name}_t": np.asarray(data.t),
            f"{data.name}_xout": np.asarray(data.xout),
            f"{data.name}_yout": np.asarray(data.yout),
        }
    if isinstance(data, (list, tuple)):
        values: dict[str, Any] = {}
        for item in data:
            values.update(_payload_values(item))
        return values
    if isinstance(data, pd.DataFrame):
        return {"table": data}
    if isinstance(data, np.ndarray):
        return {"array": data}
    if isinstance(data, Mapping):
        return dict(data)
    if hasattr(data, "result_snapshot"):
        snapshot = data.result_snapshot()
        if not isinstance(snapshot, ResultBundle):
            raise TypeError("result_snapshot() must return ResultBundle")
        return dict(snapshot.values)
    raise TypeError(
        f"unsupported result-tree payload {type(data).__name__}; "
        "provide ResultBundle-compatible data"
    )


def _node_values(node: SaveTreeNode) -> dict[str, Any]:
    values = _payload_values(node.data)
    for child in node.children:
        child_name = _logical_name(child.path)
        if child_name in values:
            raise ValueError(f"duplicate result-tree key: {child_name}")
        values[child_name] = _node_values(child)
    return values
