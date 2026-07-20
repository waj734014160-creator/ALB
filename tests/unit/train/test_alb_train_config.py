# coding: utf-8
"""Tests for config-driven ALB surrogate training helpers."""

from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import torch

from ALB.surrogate.inference import albnn
from ALB.surrogate.training import AlbnnMlpTrainer
from ALB.surrogate.training import ColumnTransformPipeline
from ALB.surrogate.training import TrainingConfig
from ALB.surrogate.training.config import TrainingConfigError
from ALB.surrogate.training.data import load_frame
from ALB.surrogate.training.data import valid_mask
from ALB.surrogate.training.config import runtime_overrides
from ALB.surrogate.training.losses import huber_values
from ALB.surrogate.training.transforms import ColumnTransformError


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


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            [0.10, -0.20, 0.30, -0.10, 0.20, 0.40, 1.20, 0.05, 0.80, 2.0, 0.010, 0.0010, 0.15, -0.25, True],
            [-0.40, 0.10, -0.20, 0.50, -0.10, 0.30, 0.90, 0.15, 1.30, 4.0, 0.030, 0.0050, -0.45, 0.35, "true"],
            [0.25, 0.35, 0.10, 0.20, 0.60, -0.20, 1.80, 0.10, 2.10, 8.0, 0.060, 0.0120, 0.80, 0.40, 1],
            [-0.15, -0.25, 0.45, -0.35, -0.50, 0.15, 1.40, 0.08, 1.60, 6.0, 0.020, 0.0060, -0.20, -0.30, False],
        ],
        columns=BASE_INPUT_COLS + ["fx", "fy", "valid"],
    )


def _smoke_config(tmp_path, *, output_name: str = "model", training: dict | None = None) -> dict:
    frame = _sample_frame()
    train_csv = tmp_path / f"{output_name}_train.csv"
    val_csv = tmp_path / f"{output_name}_validation.csv"
    frame.iloc[:3].to_csv(train_csv, index=False)
    frame.iloc[:3].to_csv(val_csv, index=False)
    config = {
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
            "sine_omega0": 10.0,
        },
        "scaler": {
            "input": [
                {"name": "base_minmax", "transform": "minmax", "columns": "all", "feature_range": [0, 1]},
                {"name": "scaled_evs", "transform": "scaled_evs"},
            ],
            "target": [{"name": "force_standard", "transform": "standard", "columns": ["fx", "fy"]}],
        },
        "training": {"epochs": 2, "batch_size": 2, "patience": 10},
        "optimizer": {"type": "adamw", "lr": 0.001, "weight_decay": 0.0},
        "loss": {"type": "mse", "weights": {"type": "none"}},
    }
    if training:
        config["training"].update(training)
    return config


def _minimal_path_config(output_dir: str | Path = "json_model") -> dict:
    return {
        "schema_version": 1,
        "run": {"run_id": "cli_config_test", "output_dir": str(output_dir)},
        "data": {"train_csv": "json_train.csv", "validation_csv": "json_val.csv"},
        "training": {"epochs": 5},
    }


def _load_train_albnn_module():
    script = (
        Path(__file__).resolve().parents[3].parent
        / "SURROGATE_TRAIN"
        / "run"
        / "train"
        / "train_albnn.py"
    )
    spec = importlib.util.spec_from_file_location("test_train_albnn_cli", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        if exc.name == "ALB.nn":
            pytest.skip("read-only SURROGATE_TRAIN trainer still imports ALB.nn")
        raise
    return module


def test_cli_path_overrides_resolve_relative_to_cwd(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    config_path = config_dir / "training.json"
    config_path.write_text(json.dumps(_minimal_path_config()), encoding="utf-8")

    json_only = TrainingConfig.from_file(config_path)
    assert json_only.resolved["data"]["train_csv"] == str(
        (config_dir / "json_train.csv").resolve()
    )

    monkeypatch.chdir(cwd)
    config = TrainingConfig.from_file(
        config_path,
        overrides=runtime_overrides(
            data="cli_train.csv",
            validation_data="cli_val.csv",
            output_dir="cli_model",
        ),
    )

    assert config.resolved["data"]["train_csv"] == str((cwd / "cli_train.csv").resolve())
    assert config.resolved["data"]["validation_csv"] == str(
        (cwd / "cli_val.csv").resolve()
    )
    assert config.resolved["run"]["output_dir"] == str((cwd / "cli_model").resolve())
    assert config.config_hash != config.resolved_config_hash


def test_config_rejects_non_mlp_model_kind(tmp_path):
    config = _minimal_path_config(tmp_path / "model")
    config["model"] = {"kind": "albnn_expert"}

    with pytest.raises(TrainingConfigError, match="model.kind='albnn_mlp'"):
        TrainingConfig.from_dict(config)


def test_config_cli_epochs_equals_override_writes_resolved_config(
    tmp_path, monkeypatch
):
    module = _load_train_albnn_module()
    config_path = tmp_path / "training.json"
    output_dir = tmp_path / "model"
    config_path.write_text(
        json.dumps(_minimal_path_config(output_dir)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_albnn.py",
            "--config",
            str(config_path),
            "--dry_run_config",
            "--epochs=10",
        ],
    )

    module.main()

    resolved = json.loads(
        (output_dir / "resolved_training_config.json").read_text(encoding="utf-8")
    )
    assert resolved["training"]["epochs"] == 10


def test_config_cli_unsupported_legacy_override_fails_fast(
    tmp_path, monkeypatch, capsys
):
    module = _load_train_albnn_module()
    config_path = tmp_path / "training.json"
    output_dir = tmp_path / "model"
    config_path.write_text(
        json.dumps(_minimal_path_config(output_dir)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_albnn.py",
            "--config",
            str(config_path),
            "--dry_run_config",
            "--lr",
            "0.1",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 2
    assert not (output_dir / "resolved_training_config.json").exists()
    assert "unsupported explicit option(s): --lr" in capsys.readouterr().err


def test_dry_run_config_without_config_fails_before_legacy_training(
    tmp_path, monkeypatch, capsys
):
    module = _load_train_albnn_module()
    output_dir = tmp_path / "legacy_model"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_albnn.py",
            "--dry_run_config",
            "--data",
            str(tmp_path / "train.csv"),
            "--output_dir",
            str(output_dir),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 2
    assert not output_dir.exists()
    assert "--dry_run_config requires --config" in capsys.readouterr().err


def test_legacy_device_without_config_fails_before_training(
    tmp_path, monkeypatch, capsys
):
    module = _load_train_albnn_module()
    output_dir = tmp_path / "legacy_model"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_albnn.py",
            "--device",
            "cpu",
            "--data",
            str(tmp_path / "train.csv"),
            "--output_dir",
            str(output_dir),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 2
    assert not output_dir.exists()
    assert "--device is only supported with --config" in capsys.readouterr().err


def test_column_transform_pipeline_matches_scaled_evs_reference():
    ref_dir = Path(__file__).resolve().parents[3] / "refs"
    summary = json.loads((ref_dir / "alb_train_reference_v1.json").read_text(encoding="utf-8"))
    arrays = np.load(ref_dir / "alb_train_reference_v1.npz")
    frame = _sample_frame()
    valid_frame = frame[valid_mask(frame)].reset_index(drop=True)

    pipeline = ColumnTransformPipeline(
        [
            {"name": "base_minmax", "transform": "minmax", "columns": "all", "feature_range": [0, 1]},
            {
                "name": "scaled_evs",
                "transform": "scaled_evs",
                "source": "base_minmax",
                "outputs": ["evs_geom", "edotv", "edots", "sdotv"],
            },
        ]
    )
    transformed = pipeline.fit_transform(valid_frame[BASE_INPUT_COLS])

    assert list(pipeline.feature_names_out_) == summary["x_frame_columns"] + [
        "evs_geom",
        "edotv",
        "edots",
        "sdotv",
    ]
    np.testing.assert_allclose(transformed, arrays["x_scaled"], rtol=1e-6, atol=1e-8)


def test_minmax_constant_column_maps_to_midpoint_and_inverse_roundtrips():
    frame = pd.DataFrame({"constant": [3.0, 3.0, 3.0], "varying": [1.0, 2.0, 5.0]})
    pipeline = ColumnTransformPipeline(
        [{"name": "minmax", "transform": "minmax", "columns": "all", "feature_range": [-1, 1]}]
    )

    transformed = pipeline.fit_transform(frame)
    reloaded = pickle.loads(pickle.dumps(pipeline))
    transformed_after_pickle = reloaded.transform(frame)
    recovered = reloaded.inverse_transform(
        pd.DataFrame(transformed_after_pickle, columns=list(reloaded.feature_names_out_))
    )

    np.testing.assert_allclose(transformed[:, 0], np.zeros(len(frame)), rtol=0.0, atol=0.0)
    np.testing.assert_allclose(transformed_after_pickle, transformed, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(recovered, frame.to_numpy(dtype=float), rtol=0.0, atol=1e-12)


def test_scaled_evs_uses_midpoint_for_constant_minmax_columns():
    frame = pd.DataFrame(
        {
            "ex": [2.0, 2.0],
            "ey": [-1.0, -1.0],
            "vx": [4.0, 4.0],
            "vy": [5.0, 5.0],
            "sx": [0.25, 0.25],
            "sy": [0.75, 0.75],
        }
    )
    pipeline = ColumnTransformPipeline(
        [
            {"name": "minmax", "transform": "minmax", "columns": "all", "feature_range": [0, 1]},
            {"name": "scaled_evs", "transform": "scaled_evs"},
        ]
    )

    transformed = pipeline.fit_transform(frame)
    feature_names = list(pipeline.feature_names_out_)
    derived = transformed[:, [feature_names.index(name) for name in ["evs_geom", "edotv", "edots", "sdotv"]]]
    expected = np.asarray([[np.sqrt(0.5), 0.5, 0.5, 0.5]] * len(frame))

    np.testing.assert_allclose(transformed[:, : len(frame.columns)], 0.5, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(derived, expected, rtol=1e-12, atol=1e-12)


def test_derived_outputs_fail_on_conflict_or_count_mismatch():
    frame = _sample_frame().iloc[:2].copy()
    frame["evs_geom"] = 0.0
    with pytest.raises(ColumnTransformError, match="overwrite existing columns"):
        ColumnTransformPipeline([{"name": "scaled_evs", "transform": "scaled_evs"}]).fit(frame)

    with pytest.raises(ColumnTransformError, match="requires 4 output"):
        ColumnTransformPipeline(
            [{"name": "scaled_evs", "transform": "scaled_evs", "outputs": ["only_one"]}]
        ).fit(_sample_frame().iloc[:2][BASE_INPUT_COLS])


def test_target_pipeline_rejects_derived_outputs_at_fit_time():
    target = pd.DataFrame({"fx": [1.0, 2.0], "fy": [3.0, 4.0]})
    pipeline = ColumnTransformPipeline(
        [
            {
                "name": "target_ratio",
                "transform": "ratio",
                "numerator": "fx",
                "denominator": "fy",
                "output": "force_ratio",
            }
        ],
        allow_derived=False,
        role="target",
    )

    with pytest.raises(ColumnTransformError, match="target transform pipeline.*derived-output"):
        pipeline.fit(target)


def test_target_pipeline_inverse_roundtrip_and_huber_reference():
    frame = _sample_frame()
    valid_frame = frame[valid_mask(frame)].reset_index(drop=True)
    target = valid_frame[["fx", "fy"]]
    pipeline = ColumnTransformPipeline(
        [{"name": "force_standard", "transform": "standard", "columns": ["fx", "fy"]}]
    )
    transformed = pipeline.fit_transform(target)
    recovered = pipeline.inverse_transform(pd.DataFrame(transformed, columns=["fx", "fy"]))
    np.testing.assert_allclose(recovered, target.to_numpy(dtype=float), rtol=0.0, atol=1e-12)

    arrays = np.load(Path(__file__).resolve().parents[3] / "refs" / "alb_train_reference_v1.npz")
    import torch

    values = huber_values(
        torch.tensor([[0.01, -0.02], [0.03, 0.01], [-0.02, 0.04]], dtype=torch.float32),
        0.03,
    ).mean(dim=1).numpy()
    np.testing.assert_allclose(values, arrays["huber_values"], rtol=1e-6, atol=1e-8)


def test_load_frame_filters_nonfinite_inputs_and_targets(tmp_path):
    frame = _sample_frame()
    frame.loc[1, "ex"] = np.nan
    frame.loc[2, "fx"] = np.inf
    csv_path = tmp_path / "train.csv"
    frame.to_csv(csv_path, index=False)

    valid_only = load_frame(
        str(csv_path),
        input_cols=BASE_INPUT_COLS,
        target_cols=["fx", "fy"],
        valid_only=True,
    )
    all_valid_flags = load_frame(
        str(csv_path),
        input_cols=BASE_INPUT_COLS,
        target_cols=["fx", "fy"],
        valid_only=False,
    )

    assert len(valid_only) == 1
    assert valid_only.iloc[0]["ex"] == pytest.approx(0.10)
    assert len(all_valid_flags) == 2
    assert valid_mask(all_valid_flags).tolist() == [True, False]


def test_config_trainer_smoke(tmp_path):
    config = _smoke_config(tmp_path, output_name="model")
    output_dir = Path(config["run"]["output_dir"])
    result = AlbnnMlpTrainer(TrainingConfig.from_dict(config)).run()

    assert result.output_dir == output_dir
    assert (output_dir / "best_albnn.pth").exists()
    assert (output_dir / "scaler_X.pkl").exists()
    assert (output_dir / "resolved_training_config.json").exists()
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["scaler"] == "config_pipeline"
    assert metadata["architecture"][0] == 16
    predictions = pd.read_csv(output_dir / "validation_predictions.csv")
    assert set(BASE_INPUT_COLS).issubset(predictions.columns)
    assert {"error_norm", "true_force_norm"}.issubset(predictions.columns)
    packaged = albnn(
        SimpleNamespace(
            model=str(output_dir / "best_albnn.pth"),
            scaler_X=str(output_dir / "scaler_X.pkl"),
            scaler_y=str(output_dir / "scaler_y.pkl"),
            metadata=str(output_dir / "metadata.json"),
        )
    )
    inference_frame = _sample_frame().iloc[:1][BASE_INPUT_COLS]
    packaged_pred = packaged.predict_nondim(inference_frame)
    assert packaged_pred.shape == (1, 2)
    assert np.isfinite(packaged_pred).all()
    assert list(packaged.scaler_X.feature_names_in_) == BASE_INPUT_COLS
    assert "evs_geom" in list(packaged.scaler_X.feature_names_out_)


def test_stale_best_checkpoint_is_not_packaged_when_no_current_best(tmp_path, monkeypatch):
    config = _smoke_config(tmp_path, output_name="stale")
    output_dir = Path(config["run"]["output_dir"])
    output_dir.mkdir(parents=True)
    torch.save({"model_state_dict": {}, "architecture": [1, 1]}, output_dir / "best_albnn.pth")

    def _nan_validation_loss(self, *args, **kwargs):
        return float("nan")

    monkeypatch.setattr(AlbnnMlpTrainer, "_validation_loss", _nan_validation_loss)
    with pytest.raises(RuntimeError, match="did not produce a finite validation checkpoint"):
        AlbnnMlpTrainer(TrainingConfig.from_dict(config)).run()

    assert not (output_dir / "best_albnn.pth").exists()
    assert (output_dir / "best_albnn.pre_run_1.pth").exists()
    assert not (output_dir / "metadata.json").exists()


def test_val_interval_history_and_patience_use_validation_checks(tmp_path, monkeypatch):
    config = _smoke_config(
        tmp_path,
        output_name="interval",
        training={"epochs": 10, "batch_size": 2, "patience": 2, "val_interval": 3},
    )
    losses = iter([1.0, 1.1, 1.2])

    def _validation_loss_sequence(self, *args, **kwargs):
        return next(losses)

    monkeypatch.setattr(AlbnnMlpTrainer, "_validation_loss", _validation_loss_sequence)
    result = AlbnnMlpTrainer(TrainingConfig.from_dict(config)).run()

    assert result.best_epoch == 1
    output_dir = Path(config["run"]["output_dir"])
    history = pd.read_csv(output_dir / "loss_history.csv")
    assert history["epoch"].tolist() == [1, 2, 3, 4, 5, 6]
    assert history.loc[history["val_checked"], "epoch"].tolist() == [1, 3, 6]
    assert history.loc[~history["val_checked"], "val_loss"].isna().all()
    assert history["best_val_loss"].dropna().iloc[-1] == pytest.approx(1.0)


def test_unsupported_target_output_fails_fast(tmp_path):
    config = _smoke_config(tmp_path, output_name="force_polar")
    config["data"]["target_output"] = "force_polar"

    with pytest.raises(TrainingConfigError, match="target_output='cartesian'"):
        AlbnnMlpTrainer(TrainingConfig.from_dict(config)).run()

    assert not (Path(config["run"]["output_dir"]) / "metadata.json").exists()


def test_trainer_rejects_target_derived_transform_before_training(tmp_path):
    config = _smoke_config(tmp_path, output_name="target_derived")
    config["scaler"]["target"] = [
        {
            "name": "target_ratio",
            "transform": "ratio",
            "numerator": "fx",
            "denominator": "fy",
            "output": "force_ratio",
        }
    ]
    config["model"]["architecture"] = [16, 8, 1]

    with pytest.raises(ColumnTransformError, match="target transform pipeline.*derived-output"):
        AlbnnMlpTrainer(TrainingConfig.from_dict(config)).run()

    assert not (Path(config["run"]["output_dir"]) / "metadata.json").exists()
