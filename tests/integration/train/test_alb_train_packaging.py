# coding: utf-8
"""Focused tests for surrogate training packaging and report lifecycle."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ALB.surrogate.training import AlbnnMlpTrainer
from ALB.surrogate.training import TrainingConfig
from ALB.surrogate.training import TrainingConfigError
from ALB.surrogate.training.reports import write_validation_predictions
from ALB.surrogate.training.runs import PACKAGED_ARTIFACT_NAMES


BASE_INPUT_COLS = [
    "ex",
    "ey",
    "vx",
    "vy",
    "sx",
    "sy",
    "lambda_value",
    "beta_nondim",
    "lr",
    "cq0",
    "cq1",
    "cq2",
]


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            [0.10, -0.20, 0.30, -0.10, 0.20, 0.40, 1.20, 0.05, 0.80, 2.0, 0.010, 0.0010, 0.15, -0.25, True],
            [-0.40, 0.10, -0.20, 0.50, -0.10, 0.30, 0.90, 0.15, 1.30, 4.0, 0.030, 0.0050, -0.45, 0.35, True],
            [0.25, 0.35, 0.10, 0.20, 0.60, -0.20, 1.80, 0.10, 2.10, 8.0, 0.060, 0.0120, 0.80, 0.40, True],
        ],
        columns=BASE_INPUT_COLS + ["fx", "fy", "valid"],
    )


def _config(tmp_path: Path, *, output_name: str, epochs: int = 2, patience: int = 10) -> dict:
    frame = _frame()
    train_csv = tmp_path / f"{output_name}_train.csv"
    val_csv = tmp_path / f"{output_name}_validation.csv"
    frame.to_csv(train_csv, index=False)
    frame.to_csv(val_csv, index=False)
    return {
        "schema_version": 1,
        "run": {
            "run_id": output_name,
            "output_dir": str(tmp_path / output_name),
            "seed": 7,
            "device": "cpu",
        },
        "data": {
            "train_csv": str(train_csv),
            "validation_csv": str(val_csv),
            "input_cols": BASE_INPUT_COLS,
            "target_cols": ["fx", "fy"],
            "valid_only": True,
        },
        "model": {
            "kind": "albnn_mlp",
            "architecture": [16, 8, 2],
            "activation": "gelu",
        },
        "scaler": {
            "input": [
                {
                    "name": "base_minmax",
                    "transform": "minmax",
                    "columns": "all",
                    "feature_range": [0, 1],
                },
                {"name": "scaled_evs", "transform": "scaled_evs"},
            ],
            "target": [
                {
                    "name": "force_standard",
                    "transform": "standard",
                    "columns": ["fx", "fy"],
                }
            ],
        },
        "training": {"epochs": epochs, "batch_size": 2, "patience": patience},
        "optimizer": {"type": "adamw", "lr": 0.001, "weight_decay": 0.0},
        "loss": {"type": "mse", "weights": {"type": "none"}},
    }


def _pre_run_path(path: Path, index: int = 1) -> Path:
    return path.with_name(f"{path.stem}.pre_run_{index}{path.suffix}")


def test_reused_output_dir_isolates_complete_old_package(tmp_path):
    config = _config(tmp_path, output_name="reuse")
    output_dir = Path(config["run"]["output_dir"])
    output_dir.mkdir(parents=True)
    for name in PACKAGED_ARTIFACT_NAMES:
        (output_dir / name).write_bytes(f"old package artifact: {name}".encode("utf-8"))

    AlbnnMlpTrainer(TrainingConfig.from_dict(config)).run()

    for name in PACKAGED_ARTIFACT_NAMES:
        current_path = output_dir / name
        archived_path = _pre_run_path(current_path)
        assert current_path.exists(), name
        assert archived_path.exists(), name
        assert archived_path.read_bytes() == f"old package artifact: {name}".encode("utf-8")


def test_invalid_run_does_not_isolate_existing_package(tmp_path):
    config = _config(tmp_path, output_name="invalid_target")
    output_dir = Path(config["run"]["output_dir"])
    output_dir.mkdir(parents=True)
    for name in PACKAGED_ARTIFACT_NAMES:
        (output_dir / name).write_bytes(f"old package artifact: {name}".encode("utf-8"))
    config["data"]["target_cols"] = ["fx"]

    with pytest.raises(TrainingConfigError, match="target_cols"):
        AlbnnMlpTrainer(TrainingConfig.from_dict(config)).run()

    for name in PACKAGED_ARTIFACT_NAMES:
        current_path = output_dir / name
        assert current_path.read_bytes() == f"old package artifact: {name}".encode("utf-8")
        assert not _pre_run_path(current_path).exists()


def test_nonfinite_validation_loss_uses_patience_checks(tmp_path, monkeypatch):
    config = _config(tmp_path, output_name="nan_validation", epochs=50, patience=2)
    calls = []

    def _nan_validation_loss(self, *args, **kwargs):
        calls.append(1)
        return float("nan")

    monkeypatch.setattr(AlbnnMlpTrainer, "_validation_loss", _nan_validation_loss)

    with pytest.raises(RuntimeError, match="did not produce a finite validation checkpoint"):
        AlbnnMlpTrainer(TrainingConfig.from_dict(config)).run()

    assert len(calls) == 2
    assert len(calls) < config["training"]["epochs"]


def test_validation_prediction_locator_columns_reject_generated_name_conflicts(tmp_path):
    locator = pd.DataFrame({"case_id": [1, 2], "true_fx": [10.0, 11.0]})

    with pytest.raises(ValueError, match="locator_frame columns conflict"):
        write_validation_predictions(
            tmp_path,
            np.array([[1.0, 2.0], [3.0, 4.0]]),
            np.array([[1.1, 2.2], [3.3, 4.4]]),
            ["fx", "fy"],
            locator_frame=locator,
        )

    assert not (tmp_path / "validation_predictions.csv").exists()
