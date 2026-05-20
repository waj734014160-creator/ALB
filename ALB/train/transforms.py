# coding: utf-8
"""Declarative column transform pipelines for ALB training configs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


class ColumnTransformError(ValueError):
    """Raised when a configured column transform cannot be applied."""


_DERIVED_TRANSFORMS = {"polar_pair", "dot_pair", "ratio", "scaled_evs"}


class MidpointMinMaxScaler:
    """Minmax scaler that maps constant columns to the feature-range midpoint.

    sklearn's ``MinMaxScaler`` maps fitted constant columns to the lower bound.
    Legacy ALBNN scalers mapped those columns to the midpoint, which matters for
    derived scaled-space features.  This top-level class is intentionally small
    and pickle-friendly so it can be stored in packaged training artifacts.
    """

    def __init__(self, feature_range: tuple[float, float] = (0.0, 1.0)):
        self.feature_range = tuple(float(value) for value in feature_range)
        self.feature_names_in_: np.ndarray | None = None
        self.n_features_in_: int | None = None
        self.data_min_: np.ndarray | None = None
        self.data_max_: np.ndarray | None = None
        self.data_range_: np.ndarray | None = None

    def fit(self, values):
        """Fit per-column min/max statistics."""
        arr = _as_2d_float(values)
        lo, hi = self.feature_range
        if hi <= lo:
            raise ColumnTransformError("minmax feature_range upper bound must exceed lower bound")
        self.n_features_in_ = int(arr.shape[1])
        if isinstance(values, pd.DataFrame):
            self.feature_names_in_ = np.asarray(list(values.columns), dtype=object)
        else:
            self.feature_names_in_ = None
        self.data_min_ = np.min(arr, axis=0)
        self.data_max_ = np.max(arr, axis=0)
        self.data_range_ = self.data_max_ - self.data_min_
        return self

    def transform(self, values):
        """Scale values, placing constant fitted columns at the midpoint."""
        self._require_fitted()
        arr = _as_2d_float(values)
        if arr.shape[1] != self.n_features_in_:
            raise ColumnTransformError(
                f"minmax expected {self.n_features_in_} features, got {arr.shape[1]}"
            )
        lo, hi = self.feature_range
        span = hi - lo
        safe_range = np.where(self.data_range_ > 0.0, self.data_range_, 1.0)
        scaled = (arr - self.data_min_) / safe_range
        scaled = scaled * span + lo
        zero_range = self.data_range_ <= 0.0
        if np.any(zero_range):
            scaled[:, zero_range] = 0.5 * (lo + hi)
        return scaled

    def fit_transform(self, values):
        """Fit statistics and return transformed values."""
        return self.fit(values).transform(values)

    def inverse_transform(self, values):
        """Invert minmax scaling, keeping fitted constant columns constant."""
        self._require_fitted()
        arr = _as_2d_float(values)
        if arr.shape[1] != self.n_features_in_:
            raise ColumnTransformError(
                f"minmax inverse expected {self.n_features_in_} features, got {arr.shape[1]}"
            )
        lo, hi = self.feature_range
        span = hi - lo
        safe_range = np.where(self.data_range_ > 0.0, self.data_range_, 1.0)
        restored = (arr - lo) / span
        restored = restored * safe_range + self.data_min_
        zero_range = self.data_range_ <= 0.0
        if np.any(zero_range):
            restored[:, zero_range] = self.data_min_[zero_range]
        return restored

    def _require_fitted(self) -> None:
        if self.data_min_ is None or self.data_range_ is None or self.n_features_in_ is None:
            raise ColumnTransformError("minmax scaler has not been fitted")


@dataclass
class _FittedStep:
    """Internal fitted transform state used by ``ColumnTransformPipeline``."""

    name: str
    transform: str
    columns: list[str]
    params: dict[str, Any]
    scaler: Any = None
    scaler2: Any = None


class ColumnTransformPipeline:
    """Apply JSON-configured transforms to pandas columns.

    The pipeline follows a simple rule: each step updates existing columns or
    appends derived columns, and the final frame column order becomes the model
    feature contract.  ``feature_names_in_`` and ``feature_names_out_`` mimic
    sklearn scaler attributes used by :mod:`ALB.nn` packaged inference.
    """

    def __init__(
        self,
        steps: list[dict[str, Any]] | None = None,
        *,
        allow_derived: bool = True,
        role: str = "input",
    ):
        self.steps = [dict(step) for step in (steps or [])]
        self.allow_derived = bool(allow_derived)
        self.role = str(role)
        self.fitted_steps_: list[_FittedStep] = []
        self.feature_names_in_: np.ndarray | None = None
        self.feature_names_out_: np.ndarray | None = None

    def fit(self, frame: pd.DataFrame):
        """Fit all configured non-derived transforms."""
        current = self._as_frame(frame).copy()
        self.feature_names_in_ = np.asarray(list(current.columns), dtype=object)
        self.fitted_steps_ = []
        fitted_names: set[str] = set()
        for step in self.steps:
            self._validate_source(step, fitted_names)
            current, fitted = self._fit_step(current, step)
            self.fitted_steps_.append(fitted)
            fitted_names.add(fitted.name)
        self.feature_names_out_ = np.asarray(list(current.columns), dtype=object)
        return self

    def transform(self, frame: pd.DataFrame):
        """Transform ``frame`` and return a numeric array."""
        current = self._as_frame(frame).copy()
        if self.feature_names_in_ is not None:
            missing = [col for col in self.feature_names_in_ if col not in current.columns]
            if missing:
                raise ColumnTransformError(f"Input frame is missing columns: {missing}")
            current = current[list(self.feature_names_in_)]
        for fitted in self.fitted_steps_:
            current = self._transform_step(current, fitted)
        return current.to_numpy(dtype=float)

    def fit_transform(self, frame: pd.DataFrame):
        """Fit the pipeline and return transformed values."""
        return self.fit(frame).transform(frame)

    def inverse_transform(self, values):
        """Invert transforms for pipelines that do not add derived columns."""
        frame = pd.DataFrame(
            np.asarray(values, dtype=float),
            columns=list(self.feature_names_out_),
        )
        for fitted in reversed(self.fitted_steps_):
            if fitted.transform in _DERIVED_TRANSFORMS:
                for col in fitted.params.get("outputs", []):
                    if col in frame.columns:
                        frame = frame.drop(columns=[col])
                continue
            frame = self._inverse_basic(frame, fitted)
        return frame[list(self.feature_names_in_)].to_numpy(dtype=float)

    def _as_frame(self, value) -> pd.DataFrame:
        if isinstance(value, pd.DataFrame):
            return value.copy()
        arr = np.asarray(value, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if self.feature_names_in_ is not None and arr.shape[1] == len(self.feature_names_in_):
            return pd.DataFrame(arr, columns=list(self.feature_names_in_))
        return pd.DataFrame(arr)

    def _fit_step(self, frame: pd.DataFrame, step: dict[str, Any]) -> tuple[pd.DataFrame, _FittedStep]:
        name = str(step.get("name") or step.get("transform"))
        transform = str(step.get("transform", "")).lower()
        if not transform:
            raise ColumnTransformError("Each transform step requires transform")
        columns = _select_columns(frame, step)
        params = dict(step)
        params.pop("name", None)
        params.pop("transform", None)
        scaler = None
        scaler2 = None
        updated = frame.copy()
        if transform == "identity":
            pass
        elif transform == "minmax":
            scaler = MidpointMinMaxScaler(
                feature_range=tuple(params.get("feature_range", (0.0, 1.0)))
            )
            updated.loc[:, columns] = scaler.fit_transform(frame[columns])
        elif transform == "standard":
            scaler = StandardScaler()
            updated.loc[:, columns] = scaler.fit_transform(frame[columns])
        elif transform == "standard_then_minmax":
            scaler = StandardScaler()
            scaler2 = MidpointMinMaxScaler(
                feature_range=tuple(params.get("feature_range", (0.0, 1.0)))
            )
            standardized = scaler.fit_transform(frame[columns])
            updated.loc[:, columns] = scaler2.fit_transform(standardized)
        elif transform in {"log1p", "signed_log1p", "asinh"}:
            updated.loc[:, columns] = _forward_nonlinear(
                frame[columns].to_numpy(dtype=float),
                transform,
                float(params.get("scale", 1.0)),
            )
        elif transform in _DERIVED_TRANSFORMS:
            if not self.allow_derived:
                raise ColumnTransformError(
                    f"{self.role} transform pipeline does not support derived-output "
                    f"step '{name}' ({transform}); model predictions cannot be "
                    "inverted to the configured target columns."
                )
            updated, params = _append_derived(updated, transform, params)
        else:
            raise ColumnTransformError(f"Unsupported transform: {transform}")
        return updated, _FittedStep(name, transform, columns, params, scaler, scaler2)

    def _transform_step(self, frame: pd.DataFrame, fitted: _FittedStep) -> pd.DataFrame:
        updated = frame.copy()
        columns = fitted.columns
        transform = fitted.transform
        if transform == "identity":
            return updated
        if transform == "minmax":
            updated.loc[:, columns] = fitted.scaler.transform(frame[columns])
        elif transform == "standard":
            updated.loc[:, columns] = fitted.scaler.transform(frame[columns])
        elif transform == "standard_then_minmax":
            standardized = fitted.scaler.transform(frame[columns])
            updated.loc[:, columns] = fitted.scaler2.transform(standardized)
        elif transform in {"log1p", "signed_log1p", "asinh"}:
            updated.loc[:, columns] = _forward_nonlinear(
                frame[columns].to_numpy(dtype=float),
                transform,
                float(fitted.params.get("scale", 1.0)),
            )
        elif transform in _DERIVED_TRANSFORMS:
            updated, _ = _append_derived(updated, transform, fitted.params)
        else:
            raise ColumnTransformError(f"Unsupported fitted transform: {transform}")
        return updated

    def _inverse_basic(self, frame: pd.DataFrame, fitted: _FittedStep) -> pd.DataFrame:
        updated = frame.copy()
        columns = fitted.columns
        transform = fitted.transform
        if transform == "identity":
            return updated
        if transform == "minmax":
            updated.loc[:, columns] = fitted.scaler.inverse_transform(frame[columns])
        elif transform == "standard":
            updated.loc[:, columns] = fitted.scaler.inverse_transform(frame[columns])
        elif transform == "standard_then_minmax":
            standardized = fitted.scaler2.inverse_transform(frame[columns])
            updated.loc[:, columns] = fitted.scaler.inverse_transform(standardized)
        elif transform in {"log1p", "signed_log1p", "asinh"}:
            updated.loc[:, columns] = _inverse_nonlinear(
                frame[columns].to_numpy(dtype=float),
                transform,
                float(fitted.params.get("scale", 1.0)),
            )
        else:
            raise ColumnTransformError(f"Cannot invert transform: {transform}")
        return updated

    def _validate_source(self, step: dict[str, Any], fitted_names: set[str]) -> None:
        """Validate derived-step source references against earlier fitted steps."""
        transform = str(step.get("transform", "")).lower()
        if transform not in _DERIVED_TRANSFORMS or "source" not in step:
            return
        source = str(step.get("source"))
        if source not in fitted_names:
            name = str(step.get("name") or step.get("transform"))
            raise ColumnTransformError(
                f"Derived transform step '{name}' references source '{source}', "
                "but that source step has not been fitted earlier in the pipeline."
            )


def _select_columns(frame: pd.DataFrame, step: dict[str, Any]) -> list[str]:
    """Select columns by names or integer indices."""
    if str(step.get("transform", "")).lower() in _DERIVED_TRANSFORMS:
        return []
    if step.get("columns") == "all":
        return list(frame.columns)
    if "columns" in step:
        columns = [str(col) for col in step["columns"]]
    elif "indices" in step:
        columns = [list(frame.columns)[int(idx)] for idx in step["indices"]]
    else:
        raise ColumnTransformError("Basic transform step requires columns or indices")
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ColumnTransformError(f"Transform references missing columns: {missing}")
    return columns


def _forward_nonlinear(values: np.ndarray, transform: str, scale: float) -> np.ndarray:
    """Apply a reversible scalar nonlinear transform."""
    if scale <= 0.0:
        raise ColumnTransformError("Nonlinear transform scale must be positive")
    if transform == "log1p":
        return np.log1p(values / scale)
    if transform == "signed_log1p":
        return np.sign(values) * np.log1p(np.abs(values) / scale)
    if transform == "asinh":
        return np.arcsinh(values / scale)
    raise ColumnTransformError(f"Unsupported nonlinear transform: {transform}")


def _inverse_nonlinear(values: np.ndarray, transform: str, scale: float) -> np.ndarray:
    """Invert a scalar nonlinear transform."""
    if transform == "log1p":
        return np.expm1(values) * scale
    if transform == "signed_log1p":
        return np.sign(values) * np.expm1(np.abs(values)) * scale
    if transform == "asinh":
        return np.sinh(values) * scale
    raise ColumnTransformError(f"Unsupported nonlinear transform: {transform}")


def _as_2d_float(values) -> np.ndarray:
    """Return values as a two-dimensional float array."""
    arr = values.to_numpy(dtype=float) if isinstance(values, pd.DataFrame) else np.asarray(values, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2:
        raise ColumnTransformError("Scaler values must be one- or two-dimensional")
    return arr


def _derived_outputs(
    frame: pd.DataFrame,
    params: dict[str, Any],
    *,
    default: list[str],
    expected_count: int,
    transform: str,
) -> list[str]:
    """Validate derived output names before appending columns."""
    if "output" in params:
        outputs = [params["output"]]
    else:
        outputs = params.get("outputs") or default
        if isinstance(outputs, str):
            outputs = [outputs]
    outputs = [str(item) for item in outputs]
    if len(outputs) != expected_count:
        raise ColumnTransformError(
            f"{transform} requires {expected_count} output column(s), got {len(outputs)}: {outputs}"
        )
    duplicates = sorted({item for item in outputs if outputs.count(item) > 1})
    if duplicates:
        raise ColumnTransformError(f"{transform} output columns contain duplicates: {duplicates}")
    collisions = [item for item in outputs if item in frame.columns]
    if collisions:
        raise ColumnTransformError(
            f"{transform} output columns would overwrite existing columns: {collisions}"
        )
    return outputs


def _append_derived(
    frame: pd.DataFrame,
    transform: str,
    params: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Append configured derived columns to ``frame``."""
    updated = frame.copy()
    params = dict(params)
    if transform == "polar_pair":
        x_col, y_col = _pair_columns(params, ("x_col", "y_col"))
        outputs = _derived_outputs(
            updated,
            params,
            default=["sin_theta", "cos_theta", "norm"],
            expected_count=3,
            transform=transform,
        )
        norm = np.hypot(updated[x_col].to_numpy(dtype=float), updated[y_col].to_numpy(dtype=float))
        safe = norm > 1e-12
        sin_values = np.zeros_like(norm)
        cos_values = np.ones_like(norm)
        sin_values[safe] = updated[y_col].to_numpy(dtype=float)[safe] / norm[safe]
        cos_values[safe] = updated[x_col].to_numpy(dtype=float)[safe] / norm[safe]
        for name, values in zip(outputs, (sin_values, cos_values, norm)):
            updated[str(name)] = values
        params["outputs"] = outputs
    elif transform == "dot_pair":
        left = params.get("left") or params.get("a")
        right = params.get("right") or params.get("b")
        outputs = _derived_outputs(
            updated,
            params,
            default=["dot"],
            expected_count=1,
            transform=transform,
        )
        output = outputs[0]
        if not left or not right or len(left) != 2 or len(right) != 2:
            raise ColumnTransformError("dot_pair requires left/right two-column lists")
        _require_columns(updated, list(left) + list(right))
        updated[output] = (
            updated[left[0]].to_numpy(dtype=float) * updated[right[0]].to_numpy(dtype=float)
            + updated[left[1]].to_numpy(dtype=float) * updated[right[1]].to_numpy(dtype=float)
        )
        params["outputs"] = outputs
    elif transform == "ratio":
        numerator = str(params.get("numerator"))
        denominator = str(params.get("denominator"))
        outputs = _derived_outputs(
            updated,
            params,
            default=["ratio"],
            expected_count=1,
            transform=transform,
        )
        output = outputs[0]
        _require_columns(updated, [numerator, denominator])
        floor = float(params.get("denominator_floor", 1e-12))
        updated[output] = updated[numerator].to_numpy(dtype=float) / np.clip(
            updated[denominator].to_numpy(dtype=float),
            floor,
            None,
        )
        params["outputs"] = outputs
    elif transform == "scaled_evs":
        outputs = _derived_outputs(
            updated,
            params,
            default=["evs_geom", "edotv", "edots", "sdotv"],
            expected_count=4,
            transform=transform,
        )
        _require_columns(updated, ["ex", "ey", "vx", "vy", "sx", "sy"])
        ex = updated["ex"].to_numpy(dtype=float)
        ey = updated["ey"].to_numpy(dtype=float)
        vx = updated["vx"].to_numpy(dtype=float)
        vy = updated["vy"].to_numpy(dtype=float)
        sx = updated["sx"].to_numpy(dtype=float)
        sy = updated["sy"].to_numpy(dtype=float)
        e_norm = np.hypot(ex, ey)
        v_norm = np.hypot(vx, vy)
        s_norm = np.hypot(sx, sy)
        values = [
            np.cbrt(np.clip(e_norm * v_norm * s_norm, 0.0, None)),
            ex * vx + ey * vy,
            ex * sx + ey * sy,
            sx * vx + sy * vy,
        ]
        for name, column_values in zip(outputs, values):
            updated[str(name)] = column_values
        params["outputs"] = outputs
    else:
        raise ColumnTransformError(f"Unsupported derived transform: {transform}")
    return updated, params


def _pair_columns(params: dict[str, Any], names: tuple[str, str]) -> tuple[str, str]:
    if "columns" in params and len(params["columns"]) == 2:
        return str(params["columns"][0]), str(params["columns"][1])
    first = params.get(names[0])
    second = params.get(names[1])
    if first is None or second is None:
        raise ColumnTransformError(f"Transform requires {names[0]} and {names[1]}")
    return str(first), str(second)


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ColumnTransformError(f"Derived transform is missing columns: {missing}")
