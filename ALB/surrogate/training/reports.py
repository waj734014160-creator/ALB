# coding: utf-8
"""Report writers for ALB surrogate training runs."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def is_cartesian_force_schema(output_cols: list[str], target_output: str = "cartesian") -> bool:
    """Return whether reports can use two-channel Cartesian force semantics."""
    return str(target_output).lower() == "cartesian" and list(output_cols) == ["fx", "fy"]


def regression_metrics(
    y_true,
    y_pred,
    output_cols: list[str],
    *,
    target_output: str = "cartesian",
) -> dict[str, float]:
    """Return common regression metrics for each component and force norm."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    error = y_pred - y_true
    metrics: dict[str, float] = {}
    for idx, name in enumerate(output_cols):
        comp_error = error[:, idx]
        comp_true = y_true[:, idx]
        ss_res = float(np.sum(comp_error**2))
        ss_tot = float(np.sum((comp_true - np.mean(comp_true)) ** 2))
        metrics[f"rmse_{name}"] = float(np.sqrt(np.mean(comp_error**2)))
        metrics[f"mae_{name}"] = float(np.mean(np.abs(comp_error)))
        metrics[f"bias_{name}"] = float(np.mean(comp_error))
        metrics[f"r2_{name}"] = float(1.0 - ss_res / ss_tot) if ss_tot > 0.0 else float("nan")
    if is_cartesian_force_schema(output_cols, target_output=target_output):
        err_norm = np.linalg.norm(error[:, :2], axis=1)
        true_norm = np.linalg.norm(y_true[:, :2], axis=1)
        metrics["rmse_norm"] = float(np.sqrt(np.mean(err_norm**2)))
        metrics["mae_norm"] = float(np.mean(err_norm))
        metrics["mean_relative_norm_error"] = float(
            np.mean(err_norm / np.clip(true_norm, 1e-12, None))
        )
    return metrics


def write_json(path: str | Path, payload: dict) -> None:
    """Write a JSON object with stable formatting."""
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_loss_history(
    output_dir: str | Path,
    rows: list[dict[str, float | int]],
) -> Path:
    """Write per-epoch loss history CSV."""
    path = Path(output_dir) / "loss_history.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def write_loss_curve(output_dir: str | Path, rows: list[dict[str, float | int]]) -> Path:
    """Plot train and validation loss curves."""
    path = Path(output_dir) / "loss_curve.png"
    frame = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(9, 5))
    if "train_loss" in frame:
        ax.semilogy(frame["epoch"], frame["train_loss"], label="train")
    if "val_loss" in frame:
        val_frame = frame.dropna(subset=["val_loss"])
        if not val_frame.empty:
            ax.semilogy(val_frame["epoch"], val_frame["val_loss"], label="validation")
    ax.set_xlabel("epoch")
    ax.set_ylabel("loss")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def write_validation_predictions(
    output_dir: str | Path,
    y_true,
    y_pred,
    output_cols: list[str],
    *,
    locator_frame: pd.DataFrame | None = None,
    target_output: str = "cartesian",
) -> Path:
    """Write true/pred/error columns for validation predictions."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    reserved_columns = _validation_prediction_reserved_columns(
        output_cols,
        target_output=target_output,
    )
    data = {}
    if locator_frame is not None:
        loc = locator_frame.reset_index(drop=True)
        if len(loc) != len(y_true):
            raise ValueError("locator_frame length must match validation predictions")
        conflicts = [
            str(name)
            for name in loc.columns
            if _is_reserved_locator_column(str(name), reserved_columns)
        ]
        if conflicts:
            raise ValueError(
                "locator_frame columns conflict with generated validation "
                f"prediction columns: {conflicts}"
            )
        for name in loc.columns:
            data[str(name)] = loc[name].to_numpy()
    for idx, name in enumerate(output_cols):
        data[f"true_{name}"] = y_true[:, idx]
        data[f"pred_{name}"] = y_pred[:, idx]
        data[f"err_{name}"] = y_pred[:, idx] - y_true[:, idx]
    if is_cartesian_force_schema(output_cols, target_output=target_output):
        data["error_norm"] = np.linalg.norm(y_pred[:, :2] - y_true[:, :2], axis=1)
        data["true_force_norm"] = np.linalg.norm(y_true[:, :2], axis=1)
    path = Path(output_dir) / "validation_predictions.csv"
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def _validation_prediction_reserved_columns(
    output_cols: list[str],
    *,
    target_output: str,
) -> set[str]:
    """Return columns owned by the validation prediction writer."""
    reserved: set[str] = set()
    for name in output_cols:
        reserved.update({f"true_{name}", f"pred_{name}", f"err_{name}"})
    if is_cartesian_force_schema(output_cols, target_output=target_output):
        reserved.update({"error_norm", "true_force_norm"})
    return reserved


def _is_reserved_locator_column(name: str, reserved_columns: set[str]) -> bool:
    """Return whether a locator column would overlap report-owned schema."""
    return (
        name in reserved_columns
        or name == "error_norm"
        or name.startswith("true_")
        or name.startswith("pred_")
        or name.startswith("err_")
    )
