"""Pickle-free NPZ persistence for supported ALBNN scaler graphs."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt


Array = npt.NDArray[np.generic]


SCALER_SCHEMA = "alb.surrogate-scaler.v0.4"
_ALLOWED_CLASSES = {
    "ALB.surrogate.inference.AsinhTargetScaler",
    "ALB.surrogate.inference.ColumnSignedLog1pTargetScaler",
    "ALB.surrogate.inference.Cq2SigLogMinMaxScaler",
    "ALB.surrogate.inference.IdentityTargetScaler",
    "ALB.surrogate.inference.MinMaxCubeRootTargetScaler",
    "ALB.surrogate.inference.MinMaxWithScaledEvsFeaturesScaler",
    "ALB.surrogate.inference.MotionStandardParamDirectMinMaxScaler",
    "ALB.surrogate.inference.MotionStandardParamMinMaxScaler",
    "ALB.surrogate.inference.PolarMotionStandardParamMinMaxScaler",
    "ALB.surrogate.inference.SelectiveMinMaxScaler",
    "ALB.surrogate.inference.SelectiveStandardScaler",
    "ALB.surrogate.inference.SignedLog1pTargetScaler",
    "ALB.surrogate.inference.StandardTargetScaler",
    "ALB.surrogate.inference.StandardThenMinMaxScaler",
    "ALB.surrogate.training.transforms.MidpointMinMaxScaler",
    "ALB.surrogate.training.transforms.ColumnTransformPipeline",
    "ALB.surrogate.training.transforms._FittedStep",
    "sklearn.preprocessing._data.MinMaxScaler",
    "sklearn.preprocessing._data.RobustScaler",
    "sklearn.preprocessing._data.StandardScaler",
}


def _class_name(value: object) -> str:
    return f"{type(value).__module__}.{type(value).__qualname__}"


def _encode(
    value: Any,
    arrays: dict[str, Array],
    *,
    path: str,
) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (float, np.floating)):
        result = float(value)
        if not np.isfinite(result):
            raise ValueError(f"non-finite scaler state at {path}")
        return result
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            flat = value.reshape(-1).tolist()
            if not all(isinstance(item, str) for item in flat):
                raise TypeError(f"object scaler array is not string-only at {path}")
            return {
                "__string_array__": flat,
                "shape": list(value.shape),
            }
        key = f"array_{len(arrays):04d}"
        array = np.asarray(value)
        if np.issubdtype(array.dtype, np.number) and not np.all(
            np.isfinite(array)
        ):
            raise ValueError(f"non-finite scaler array at {path}")
        arrays[key] = array
        return {"__array__": key}
    if isinstance(value, tuple):
        return {
            "__tuple__": [
                _encode(item, arrays, path=f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        }
    if isinstance(value, list):
        return [
            _encode(item, arrays, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError(f"scaler state keys must be strings at {path}")
        return {
            key: _encode(item, arrays, path=f"{path}.{key}")
            for key, item in value.items()
        }
    class_name = _class_name(value)
    if class_name not in _ALLOWED_CLASSES:
        raise TypeError(f"unsupported scaler state type at {path}: {class_name}")
    try:
        state = vars(value)
    except TypeError as exc:
        raise TypeError(f"scaler object has no state at {path}") from exc
    return {
        "__object__": class_name,
        "state": _encode(dict(state), arrays, path=f"{path}.state"),
    }


def _decode(value: Any, arrays: dict[str, Array]) -> Any:
    if isinstance(value, list):
        return [_decode(item, arrays) for item in value]
    if not isinstance(value, dict):
        return value
    if "__array__" in value:
        return arrays[str(value["__array__"])].copy()
    if "__string_array__" in value:
        return np.asarray(value["__string_array__"], dtype=str).reshape(
            tuple(int(item) for item in value["shape"])
        )
    if "__tuple__" in value:
        return tuple(_decode(item, arrays) for item in value["__tuple__"])
    if "__object__" in value:
        class_name = str(value["__object__"])
        if class_name not in _ALLOWED_CLASSES:
            raise ValueError(f"unsupported scaler class: {class_name}")
        module_name, _, attribute = class_name.rpartition(".")
        cls = getattr(importlib.import_module(module_name), attribute)
        instance = cls.__new__(cls)
        state = _decode(value["state"], arrays)
        if not isinstance(state, dict):
            raise ValueError("serialized scaler object state must be a mapping")
        vars(instance).update(state)
        return instance
    return {key: _decode(item, arrays) for key, item in value.items()}


def write_scaler(scaler: object, path: str | Path) -> Path:
    """Write one allowlisted fitted scaler graph without pickle."""

    destination = Path(path)
    arrays: dict[str, Array] = {}
    graph = _encode(scaler, arrays, path="scaler")
    payload = {
        "schema": SCALER_SCHEMA,
        "graph": graph,
    }
    np.savez(
        destination,
        manifest=np.asarray(
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
        ),
        **arrays,
    )
    return destination


def load_scaler(path: str | Path) -> object:
    """Load one allowlisted fitted scaler graph with ``allow_pickle=False``."""

    source = Path(path)
    with np.load(source, allow_pickle=False) as archive:
        if "manifest" not in archive.files:
            raise ValueError("scaler NPZ manifest is missing")
        payload = json.loads(str(archive["manifest"].item()))
        if payload.get("schema") != SCALER_SCHEMA:
            raise ValueError("unsupported ALBNN scaler schema")
        arrays = {
            key: archive[key].copy()
            for key in archive.files
            if key != "manifest"
        }
    return _decode(payload.get("graph"), arrays)


__all__ = ["SCALER_SCHEMA", "load_scaler", "write_scaler"]
