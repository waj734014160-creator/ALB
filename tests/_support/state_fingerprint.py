"""Recursive state fingerprints for checkpoint/restore tests (ALB 0.4.7).

``state_fingerprint(obj)`` walks every attribute reachable from ``obj`` that is
owned by the ``ALB`` package (plus test doubles from ``tests``) and records a
stable digest per attribute path. Containers, NumPy arrays, sparse matrices,
and pandas frames are digested by value. Objects from third-party libraries
(SciPy factorizations, scikit-fem meshes, scikit-fuzzy simulations, torch
modules) are treated as opaque leaves identified only by type, because their
internal caches are not part of the bearing state contract.

Comparing the fingerprint before a checkpoint with the fingerprint after
``restore`` shows every attribute a trial evaluation left changed.
"""

from __future__ import annotations

from collections.abc import Mapping
import enum
import hashlib
import pickle
from types import MappingProxyType
from typing import Any

import numpy as np


_OWNED_PREFIXES = ("ALB.", "ALB", "tests.", "tools.")
_PRIMITIVES = (type(None), bool, int, float, complex, str, bytes)


def _digest(payload: bytes) -> str:
    return hashlib.sha1(payload).hexdigest()


def _owned(value: Any) -> bool:
    module = type(value).__module__ or ""
    return module.startswith(_OWNED_PREFIXES) and module != "builtins"


def _leaf(value: Any) -> Any:
    """Return a hashable digest for a value that is not walked further."""

    if isinstance(value, _PRIMITIVES):
        if isinstance(value, float) and value != value:
            return ("float", "nan")
        return (type(value).__name__, value)
    if isinstance(value, np.generic):
        return ("np", value.dtype.str, value.tobytes())
    if isinstance(value, np.ndarray):
        if value.dtype == object:
            return ("ndarray-object", value.shape, _digest(pickle.dumps(value.tolist())))
        return ("ndarray", value.shape, value.dtype.str, _digest(np.ascontiguousarray(value).tobytes()))
    try:
        import scipy.sparse as sparse

        if sparse.issparse(value):
            matrix = value.tocoo()
            return (
                "sparse",
                matrix.shape,
                _digest(matrix.row.tobytes() + matrix.col.tobytes() + matrix.data.tobytes()),
            )
    except ImportError:  # pragma: no cover - SciPy is a hard dependency
        pass
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            try:
                payload = pickle.dumps(
                    (
                        list(map(str, value.columns)),
                        list(map(str, value.dtypes)),
                        [
                            [_leaf(item) for item in value[column].tolist()]
                            for column in value.columns
                        ],
                    )
                )
            except Exception:  # pragma: no cover - defensive digest
                payload = repr(value).encode()
            return ("DataFrame", value.shape, _digest(payload))
    except ImportError:  # pragma: no cover - pandas is a hard dependency
        pass
    if isinstance(value, enum.Enum):
        return ("enum", type(value).__name__, repr(value.value))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(_leaf(item) for item in value))
    if isinstance(value, (dict, MappingProxyType)):
        return (
            "mapping",
            tuple(sorted((repr(key), _leaf(item)) for key, item in value.items())),
        )
    return ("opaque", type(value).__module__, type(value).__qualname__)


def _attributes(value: Any) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    if hasattr(value, "__dict__"):
        attributes.update(vars(value))
    for cls in type(value).__mro__:
        for name in getattr(cls, "__slots__", ()):
            if name in ("__dict__", "__weakref__") or name in attributes:
                continue
            try:
                attributes[name] = getattr(value, name)
            except AttributeError:
                continue
    return attributes


def state_fingerprint(root: Any) -> dict[str, Any]:
    """Return ``{attribute path: digest}`` for every reachable owned state."""

    result: dict[str, Any] = {}
    seen: dict[int, str] = {}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping) and not _owned(value):
            for key in sorted(value, key=repr):
                walk(value[key], f"{path}[{key!r}]")
            if not value:
                result[path] = ("mapping", ())
            return
        if isinstance(value, (list, tuple)) and not _owned(value):
            result[f"{path}#len"] = len(value)
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
            return
        if _owned(value) and not isinstance(value, enum.Enum):
            identity = id(value)
            if identity in seen:
                result[path] = ("ref", seen[identity])
                return
            seen[identity] = path
            for name, item in sorted(_attributes(value).items()):
                walk(item, f"{path}.{name}")
            return
        result[path] = _leaf(value)

    walk(root, "root")
    return result


def fingerprint_diff(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    ignore: tuple[str, ...] = (),
) -> list[str]:
    """Return attribute paths whose digest differs, minus ignored fragments."""

    changed = []
    for key in sorted(set(before) | set(after)):
        if any(fragment in key for fragment in ignore):
            continue
        if before.get(key, "<missing>") != after.get(key, "<missing>"):
            changed.append(key)
    return changed


__all__ = ["fingerprint_diff", "state_fingerprint"]
