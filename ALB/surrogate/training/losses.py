# coding: utf-8
"""Loss functions and weighting helpers for ALB surrogate training."""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch


def huber_values(error: torch.Tensor, delta: float) -> torch.Tensor:
    """Return elementwise Huber values using the conventional delta form."""
    delta_tensor = torch.as_tensor(float(delta), dtype=error.dtype, device=error.device)
    abs_error = torch.abs(error)
    return torch.where(
        abs_error <= delta_tensor,
        0.5 * error.pow(2),
        delta_tensor * (abs_error - 0.5 * delta_tensor),
    )


def sample_loss_values(
    pred: torch.Tensor,
    target: torch.Tensor,
    *,
    loss_type: str,
    huber_delta: float = 1.0,
) -> torch.Tensor:
    """Return one scalar loss per sample."""
    if loss_type == "mse":
        return (pred - target).pow(2).mean(dim=1)
    if loss_type == "huber":
        return huber_values(pred - target, huber_delta).mean(dim=1)
    raise ValueError(f"Unsupported loss type: {loss_type}")


def weighted_mean(values: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
    """Return a numerically stable weighted mean."""
    return (values * weights).sum() / weights.sum().clamp_min(1e-12)


def force_measure(frame: pd.DataFrame, target_cols: list[str], mode: str) -> np.ndarray:
    """Compute force magnitude from target columns for binning or weighting."""
    values = frame[target_cols].to_numpy(dtype=float)
    if values.shape[1] == 1:
        return np.abs(values[:, 0])
    if mode == "norm":
        return np.linalg.norm(values[:, :2], axis=1)
    if mode == "fmax":
        return np.max(np.abs(values[:, :2]), axis=1)
    raise ValueError(f"Unsupported force measure: {mode}")


def force_bin_ids(values: np.ndarray, bins: list[float]) -> np.ndarray:
    """Assign force magnitudes to adjacent bins."""
    edges = np.asarray(bins, dtype=float)
    if len(edges) < 2:
        raise ValueError("Force bins require at least two edges")
    if np.any(np.diff(edges) <= 0):
        raise ValueError("Force bins must be strictly increasing")
    ids = np.searchsorted(edges[1:], values, side="right")
    return np.clip(ids, 0, len(edges) - 2).astype(np.int64)


def loss_weights(
    frame: pd.DataFrame,
    target_cols: list[str],
    spec: dict,
) -> np.ndarray:
    """Build per-row loss weights from a JSON weight spec."""
    weight_type = str((spec or {}).get("type", "none"))
    if weight_type == "none":
        return np.ones(len(frame), dtype=np.float32)
    if weight_type == "force_bins":
        bins = [float(value) for value in spec["bins"]]
        weights = np.asarray(spec["weights"], dtype=np.float32)
        ids = force_bin_ids(
            force_measure(frame, target_cols, str(spec.get("measure", "norm"))),
            bins,
        )
        if len(weights) != len(bins) - 1:
            raise ValueError("force_bins weights must match len(bins)-1")
        return weights[ids].astype(np.float32)
    raise ValueError(f"Unsupported loss weight type: {weight_type}")
