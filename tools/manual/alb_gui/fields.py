"""Field extraction and multi-pad merge helpers for the ALB GUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass
class FieldMap:
    """Merged pad field on a full circumferential grid."""

    theta_deg: np.ndarray
    z: np.ndarray
    values: np.ndarray
    masked: bool = False


def _is_thermal_pad(pad) -> bool:
    return hasattr(pad, "post_process") and bool(
        getattr(getattr(pad, "post_process", None), "postprocess_result", None)
    )


def _field_from_pad(pad, field: str) -> np.ndarray:
    field = str(field).lower()
    if field == "temperature":
        if not _is_thermal_pad(pad):
            raise ValueError("Temperature field is only available for thermal pads")
        return np.asarray(pad.post_process.temperature_field, dtype=float)
    if field == "pressure" and _is_thermal_pad(pad):
        return np.asarray(pad.post_process.pressure_field, dtype=float)
    if field == "pressure":
        return np.asarray(pad.postprocess.p, dtype=float)
    raise ValueError("field must be 'pressure' or 'temperature'")


def _pad_interval(pad) -> tuple[float, float]:
    args = pad.main_model.args
    x0, x1 = np.asarray(args["x_lim"], dtype=float)
    return float(x0), float(x1)


def _pad_z_axis(pad, count: int) -> np.ndarray:
    args = getattr(pad.main_model, "args", {})
    z_lim = np.asarray(args.get("z_lim", [0.0, 1.0]), dtype=float)
    return np.linspace(float(z_lim[0]), float(z_lim[1]), int(count))


def _resample_z(values: np.ndarray, target_count: int) -> np.ndarray:
    if values.shape[1] == target_count:
        return values
    source_z = np.linspace(0.0, 1.0, values.shape[1])
    target_z = np.linspace(0.0, 1.0, target_count)
    out = np.empty((values.shape[0], target_count), dtype=float)
    for i in range(values.shape[0]):
        out[i] = np.interp(target_z, source_z, values[i])
    return out


def _inside_periodic_interval(theta: float, start: float, end: float):
    period = 2.0 * np.pi
    for shift in (-period, 0.0, period):
        candidate = theta + shift
        if start - 1e-12 <= candidate <= end + 1e-12:
            return candidate
    return None


def merge_pad_field(
    pads: Iterable,
    *,
    field: str,
    n_theta: int = 721,
    fill_value: float = 0.0,
    mask_gaps: bool = False,
) -> FieldMap:
    """Merge per-pad fields onto a full 0-360 degree display grid."""

    pads = list(pads)
    if not pads:
        raise ValueError("pads must not be empty")

    pad_fields = [(pad, _field_from_pad(pad, field)) for pad in pads]
    max_z = max(values.shape[1] for _, values in pad_fields)
    theta = np.linspace(0.0, 2.0 * np.pi, int(n_theta))
    z = _pad_z_axis(pads[0], max_z)
    merged = np.full((theta.size, max_z), float(fill_value), dtype=float)
    written = np.zeros(theta.size, dtype=bool)

    for pad, values in pad_fields:
        values = _resample_z(np.asarray(values, dtype=float), max_z)
        start, end = _pad_interval(pad)
        span = end - start
        if span <= 0:
            continue
        local_count = values.shape[0]
        for i, angle in enumerate(theta):
            unwrapped = _inside_periodic_interval(float(angle), start, end)
            if unwrapped is None:
                continue
            local = (unwrapped - start) / span
            local_index = int(round(local * (local_count - 1)))
            local_index = max(0, min(local_count - 1, local_index))
            merged[i] = values[local_index]
            written[i] = True

    if mask_gaps:
        merged = np.ma.array(merged, mask=np.repeat(~written[:, None], max_z, axis=1))
        return FieldMap(np.rad2deg(theta), z, merged, masked=True)
    return FieldMap(np.rad2deg(theta), z, merged, masked=False)


def pressure_map_from_pads(pads: Iterable) -> FieldMap:
    """Return a merged pressure field with zero-filled pad gaps."""

    return merge_pad_field(pads, field="pressure", fill_value=0.0, mask_gaps=False)


def temperature_map_from_pads(pads: Iterable) -> FieldMap | None:
    """Return a merged temperature field, or None when pads are not thermal."""

    pads = list(pads)
    if not pads or not all(_is_thermal_pad(pad) for pad in pads):
        return None
    return merge_pad_field(pads, field="temperature", fill_value=np.nan, mask_gaps=True)

