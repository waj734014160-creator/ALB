# coding: utf-8
"""Trainer classes for config-driven ALB surrogate training."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.utils.data import TensorDataset

from ALB.surrogate.networks import Net
from ALB.surrogate.package import create_model_package

from .config import TrainingConfig
from .config import TrainingConfigError
from .data import train_validation_frames
from .losses import loss_weights
from .losses import sample_loss_values
from .losses import weighted_mean
from .reports import regression_metrics
from .reports import write_json
from .reports import write_loss_curve
from .reports import write_loss_history
from .reports import write_validation_predictions
from .transforms import ColumnTransformPipeline


PACKAGED_ARTIFACT_NAMES = (
    "model_package",
    "validation_summary.json",
    "validation_predictions.csv",
    "loss_history.csv",
    "loss_curve.png",
)


@dataclass
class TrainingResult:
    """Summary returned by a completed training run."""

    output_dir: Path
    best_epoch: int
    best_val_loss: float
    metrics: dict[str, float]


@dataclass
class FitResult:
    """Internal summary of checkpoint-producing training."""

    history: list[dict[str, float | int | bool | None]]
    best_epoch: int
    best_val_loss: float
    wrote_best: bool


class TrainingRun:
    """Base lifecycle for config-driven training runs."""

    trainer_kind = "base"

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.resolved = config.resolved
        self.output_dir = config.output_dir

    def write_config_only(self) -> None:
        """Write config trace files without starting training."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.write_trace(self.output_dir)

    def run(self) -> TrainingResult:
        """Execute the configured training run."""
        raise NotImplementedError


class AlbnnMlpTrainer(TrainingRun):
    """Train a standard ALBNN MLP from a v1 JSON training config."""

    trainer_kind = "albnn_mlp"

    def run(self) -> TrainingResult:
        """Train, evaluate, and package a config-driven ALBNN MLP."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.write_trace(self.output_dir)
        self._configure_torch()

        data_cfg = self.resolved["data"]
        run_cfg = self.resolved["run"]
        model_cfg = self.resolved["model"]
        training_cfg = self.resolved["training"]
        loss_cfg = self.resolved["loss"]
        self._validate_target_contract(data_cfg)

        train_frame, val_frame = train_validation_frames(
            data_cfg["train_csv"],
            data_cfg.get("validation_csv"),
            input_cols=data_cfg["input_cols"],
            target_cols=data_cfg["target_cols"],
            valid_only=bool(data_cfg.get("valid_only", True)),
            test_size=float(data_cfg.get("test_size", 0.2)),
            seed=int(run_cfg.get("seed", 42)),
        )

        x_train_frame = train_frame[data_cfg["input_cols"]].copy()
        x_val_frame = val_frame[data_cfg["input_cols"]].copy()
        y_train_frame = train_frame[data_cfg["target_cols"]].copy()
        y_val_frame = val_frame[data_cfg["target_cols"]].copy()

        scaler_x = ColumnTransformPipeline(self.resolved["scaler"]["input"])
        scaler_y = ColumnTransformPipeline(
            self.resolved["scaler"]["target"],
            allow_derived=False,
            role="target",
        )
        x_train = scaler_x.fit_transform(x_train_frame).astype(np.float32)
        x_val = scaler_x.transform(x_val_frame).astype(np.float32)
        y_train = scaler_y.fit_transform(y_train_frame).astype(np.float32)
        y_val = scaler_y.transform(y_val_frame).astype(np.float32)

        architecture = [int(value) for value in model_cfg["architecture"]]
        if architecture[0] != x_train.shape[1]:
            raise TrainingConfigError(
                f"model.architecture input width {architecture[0]} does not match "
                f"transformed input width {x_train.shape[1]}"
            )
        if architecture[-1] != y_train.shape[1]:
            raise TrainingConfigError(
                f"model.architecture output width {architecture[-1]} does not match "
                f"transformed target width {y_train.shape[1]}"
            )

        device = self._device()
        net = Net(
            architecture,
            activation=str(model_cfg.get("activation", "gelu")),
            sine_omega0=float(model_cfg.get("sine_omega0", 30.0)),
            use_layer_norm=bool(model_cfg.get("use_layer_norm", False)),
        ).to(device)
        optimizer = self._optimizer(net)
        scheduler = self._scheduler(optimizer)

        train_weights = loss_weights(
            train_frame,
            data_cfg["target_cols"],
            loss_cfg.get("weights", {"type": "none"}),
        )
        val_weights = loss_weights(
            val_frame,
            data_cfg["target_cols"],
            loss_cfg.get("weights", {"type": "none"}),
        )

        self._isolate_existing_packaged_artifacts()
        fit = self._fit(
            net,
            optimizer,
            scheduler,
            x_train,
            y_train,
            train_weights,
            x_val,
            y_val,
            val_weights,
            loss_type=str(loss_cfg.get("type", "mse")),
            huber_delta=float(loss_cfg.get("huber_delta", 1.0)),
            epochs=int(training_cfg.get("epochs", 50000)),
            batch_size=int(training_cfg.get("batch_size", 512)),
            patience=int(training_cfg.get("patience", 2000)),
            val_interval=int(training_cfg.get("val_interval", 1)),
            device=device,
        )
        if not fit.wrote_best:
            raise RuntimeError(
                "Training did not produce a finite validation checkpoint for this run; "
                "refusing to publish a stale deployment package"
            )

        checkpoint = _load_checkpoint(self.output_dir / "best_albnn.pth", device)
        net.load_state_dict(checkpoint["model_state_dict"])
        y_pred = self._predict(net, x_val, scaler_y, data_cfg["target_cols"], device)
        y_true = y_val_frame.to_numpy(dtype=float)
        metrics = regression_metrics(
            y_true,
            y_pred,
            data_cfg["target_cols"],
            target_output=str(data_cfg.get("target_output", "cartesian")),
        )
        self._write_artifacts(
            net=net,
            architecture=architecture,
            scaler_x=scaler_x,
            scaler_y=scaler_y,
            history=fit.history,
            metrics=metrics,
            y_true=y_true,
            y_pred=y_pred,
            train_frame=train_frame,
            val_frame=val_frame,
        )
        return TrainingResult(
            output_dir=self.output_dir,
            best_epoch=int(fit.best_epoch),
            best_val_loss=float(fit.best_val_loss),
            metrics=metrics,
        )

    def _isolate_existing_packaged_artifacts(self) -> None:
        """Move existing packaged outputs aside before a new training run."""
        existing = [
            self.output_dir / "best_albnn.pth",
            *(self.output_dir / name for name in PACKAGED_ARTIFACT_NAMES),
        ]
        existing = [path for path in existing if path.exists()]
        if not existing:
            return
        for index in range(1, 1000):
            candidates = [_pre_run_artifact_path(path, index) for path in existing]
            if not any(candidate.exists() for candidate in candidates):
                for path, candidate in zip(existing, candidates):
                    path.replace(candidate)
                return
        raise RuntimeError(f"Could not isolate existing packaged artifacts: {self.output_dir}")

    def _validate_target_contract(self, data_cfg: dict[str, Any]) -> None:
        """Fail fast for target schemas not implemented by the generic MLP trainer."""
        target_output = str(data_cfg.get("target_output", "cartesian")).lower()
        if target_output != "cartesian":
            raise TrainingConfigError(
                "ALB.surrogate.training generic MLP currently supports only "
                "data.target_output='cartesian' with target_cols=['fx', 'fy']; "
                f"got target_output={data_cfg.get('target_output')!r}"
            )
        if list(data_cfg.get("target_cols", [])) != ["fx", "fy"]:
            raise TrainingConfigError(
                "ALB.surrogate.training generic MLP supports only direct Cartesian "
                "target_cols=['fx', 'fy']"
            )

    def _configure_torch(self) -> None:
        threads = int(self.resolved["run"].get("torch_threads", 0))
        if threads > 0:
            torch.set_num_threads(threads)
        torch.manual_seed(int(self.resolved["run"].get("seed", 42)))
        np.random.seed(int(self.resolved["run"].get("seed", 42)))

    def _device(self) -> torch.device:
        requested = str(self.resolved["run"].get("device", "auto")).lower()
        if requested == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(requested)

    def _optimizer(self, net: Net):
        cfg = self.resolved["optimizer"]
        name = str(cfg.get("type", "adam")).lower()
        lr = float(cfg.get("lr", 5e-4))
        weight_decay = float(cfg.get("weight_decay", 0.0))
        if name == "adam":
            return optim.Adam(net.parameters(), lr=lr, weight_decay=weight_decay)
        if name == "adamw":
            return optim.AdamW(net.parameters(), lr=lr, weight_decay=weight_decay)
        raise TrainingConfigError(f"Unsupported optimizer: {name}")

    def _scheduler(self, optimizer):
        cfg = self.resolved["training"]
        name = str(cfg.get("lr_scheduler", "none")).lower()
        if name == "none":
            return None
        if name == "plateau":
            return optim.lr_scheduler.ReduceLROnPlateau(
                optimizer,
                mode="min",
                factor=float(cfg.get("lr_plateau_factor", 0.5)),
                patience=int(cfg.get("lr_plateau_patience", 1000)),
                min_lr=float(cfg.get("min_lr", 1e-6)),
            )
        raise TrainingConfigError(f"Unsupported lr_scheduler: {name}")

    def _fit(
        self,
        net: Net,
        optimizer,
        scheduler,
        x_train: np.ndarray,
        y_train: np.ndarray,
        train_weights: np.ndarray,
        x_val: np.ndarray,
        y_val: np.ndarray,
        val_weights: np.ndarray,
        *,
        loss_type: str,
        huber_delta: float,
        epochs: int,
        batch_size: int,
        patience: int,
        val_interval: int,
        device: torch.device,
    ) -> FitResult:
        if int(val_interval) < 1:
            raise TrainingConfigError("training.val_interval must be >= 1")
        if int(patience) < 1:
            raise TrainingConfigError("training.patience must be >= 1 validation check")
        dataset = TensorDataset(
            torch.tensor(x_train, dtype=torch.float32),
            torch.tensor(y_train, dtype=torch.float32),
            torch.tensor(train_weights, dtype=torch.float32),
        )
        generator = torch.Generator()
        generator.manual_seed(int(self.resolved["run"].get("seed", 42)))
        loader = DataLoader(
            dataset,
            batch_size=int(batch_size),
            shuffle=True,
            generator=generator,
        )
        x_val_t = torch.tensor(x_val, dtype=torch.float32, device=device)
        y_val_t = torch.tensor(y_val, dtype=torch.float32, device=device)
        val_weights_t = torch.tensor(val_weights, dtype=torch.float32, device=device)

        best_val = float("inf")
        best_epoch = 0
        checks_without_improvement = 0
        history: list[dict[str, float | int | bool | None]] = []
        best_path = self.output_dir / "best_albnn.pth"
        for epoch in range(1, int(epochs) + 1):
            net.train()
            train_total = 0.0
            train_weight_total = 0.0
            for xb, yb, wb in loader:
                xb = xb.to(device)
                yb = yb.to(device)
                wb = wb.to(device)
                pred = net(xb)
                values = sample_loss_values(
                    pred,
                    yb,
                    loss_type=loss_type,
                    huber_delta=huber_delta,
                )
                loss = weighted_mean(values, wb)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                train_total += float((values.detach() * wb).sum().item())
                train_weight_total += float(wb.sum().item())
            train_loss = train_total / max(train_weight_total, 1e-12)
            val_checked = epoch == 1 or epoch % int(val_interval) == 0
            val_loss: float | None = None
            if val_checked:
                val_loss = self._validation_loss(
                    net,
                    x_val_t,
                    y_val_t,
                    val_weights_t,
                    loss_type=loss_type,
                    huber_delta=huber_delta,
                )
                if scheduler is not None:
                    scheduler.step(val_loss)
                if np.isfinite(val_loss) and val_loss < best_val:
                    best_val = val_loss
                    best_epoch = epoch
                    checks_without_improvement = 0
                    _save_checkpoint(net, best_path, self.resolved["model"]["architecture"])
                else:
                    checks_without_improvement += 1
            else:
                val_loss = None
            history.append(
                {
                    "epoch": int(epoch),
                    "train_loss": float(train_loss),
                    "val_loss": None if val_loss is None else float(val_loss),
                    "val_checked": bool(val_checked),
                    "best_val_loss": None if not np.isfinite(best_val) else float(best_val),
                    "lr": float(optimizer.param_groups[0]["lr"]),
                }
            )
            if checks_without_improvement >= int(patience):
                break
        return FitResult(
            history=history,
            best_epoch=int(best_epoch),
            best_val_loss=float(best_val),
            wrote_best=bool(best_path.exists() and best_epoch > 0 and np.isfinite(best_val)),
        )

    def _validation_loss(
        self,
        net: Net,
        x_val: torch.Tensor,
        y_val: torch.Tensor,
        weights: torch.Tensor,
        *,
        loss_type: str,
        huber_delta: float,
    ) -> float:
        net.eval()
        with torch.no_grad():
            values = sample_loss_values(
                net(x_val),
                y_val,
                loss_type=loss_type,
                huber_delta=huber_delta,
            )
            return float(weighted_mean(values, weights).item())

    def _predict(
        self,
        net: Net,
        x_scaled: np.ndarray,
        scaler_y: ColumnTransformPipeline,
        output_cols: list[str],
        device: torch.device,
    ) -> np.ndarray:
        net.eval()
        with torch.no_grad():
            pred = net(torch.tensor(x_scaled, dtype=torch.float32, device=device))
        pred_np = pred.detach().cpu().numpy()
        pred_frame = pd.DataFrame(pred_np, columns=output_cols)
        return scaler_y.inverse_transform(pred_frame)

    def _write_artifacts(
        self,
        *,
        net: Net,
        architecture: list[int],
        scaler_x: ColumnTransformPipeline,
        scaler_y: ColumnTransformPipeline,
        history: list[dict[str, float | int | bool | None]],
        metrics: dict[str, float],
        y_true: np.ndarray,
        y_pred: np.ndarray,
        train_frame: pd.DataFrame,
        val_frame: pd.DataFrame,
    ) -> None:
        data_cfg = self.resolved["data"]
        report_cfg = self.resolved["report"]
        checkpoint = self.output_dir / "best_albnn.pth"
        _save_checkpoint(net, checkpoint, architecture)
        write_loss_history(self.output_dir, history)
        if report_cfg.get("write_loss_curve", True):
            write_loss_curve(self.output_dir, history)
        if report_cfg.get("write_predictions", True):
            write_validation_predictions(
                self.output_dir,
                y_true,
                y_pred,
                data_cfg["target_cols"],
                locator_frame=val_frame[data_cfg["input_cols"]],
                target_output=str(data_cfg.get("target_output", "cartesian")),
            )
        write_json(self.output_dir / "validation_summary.json", metrics)
        metadata = {
            "model_type": "albnn_mlp",
            "trainer": self.trainer_kind,
            "config_path": str(self.config.config_path) if self.config.config_path else None,
            "config_hash": self.config.config_hash,
            "resolved_config_hash": self.config.resolved_config_hash,
            "run_id": self.resolved["run"].get("run_id"),
            "data": data_cfg["train_csv"],
            "validation_data": data_cfg.get("validation_csv"),
            "train_rows": int(len(train_frame)),
            "validation_rows": int(len(val_frame)),
            "input_cols": data_cfg["input_cols"],
            "output_cols": data_cfg["target_cols"],
            "target_output": data_cfg.get("target_output", "cartesian"),
            "use_augment": False,
            "feature_set": "config_pipeline",
            "architecture": architecture,
            "activation": self.resolved["model"].get("activation", "gelu"),
            "sine_omega0": float(self.resolved["model"].get("sine_omega0", 30.0)),
            "use_layer_norm": bool(self.resolved["model"].get("use_layer_norm", False)),
            "scaler": "config_pipeline",
            "training_config": "training_config.json",
            "resolved_training_config": "resolved_training_config.json",
            "metrics": metrics,
        }
        create_model_package(
            self.output_dir / "model_package",
            checkpoint=checkpoint,
            input_scaler=scaler_x,
            output_scaler=scaler_y,
            metadata=metadata,
        )
        checkpoint.unlink()


class AlbnnExpertTrainer(AlbnnMlpTrainer):
    """Config-driven trainer for materialized expert-style ALBNN targets."""

    trainer_kind = "albnn_expert"


class AlbnnResidualTrainer(AlbnnMlpTrainer):
    """Config-driven trainer for materialized residual ALBNN targets."""

    trainer_kind = "albnn_residual"


def _save_checkpoint(net: Net, path: Path, architecture: list[int]) -> None:
    """Save a checkpoint compatible with ``ALB.surrogate.networks.net_from_checkpoint``."""
    torch.save(
        {
            "model_state_dict": net.state_dict(),
            "architecture": list(architecture),
            "activation": getattr(net, "activation", "gelu"),
            "sine_omega0": float(getattr(net, "sine_omega0", 30.0)),
            "use_layer_norm": bool(getattr(net, "use_layer_norm", False)),
        },
        path,
    )


def _pre_run_artifact_path(path: Path, index: int) -> Path:
    """Return the archive path for a package artifact from an earlier run."""
    return path.with_name(f"{path.stem}.pre_run_{index}{path.suffix}")


def _load_checkpoint(path: Path, device: torch.device) -> dict[str, Any]:
    return torch.load(path, map_location=device, weights_only=True)
