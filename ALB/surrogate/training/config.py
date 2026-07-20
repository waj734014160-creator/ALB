# coding: utf-8
"""JSON configuration contract for ALB surrogate training runs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


ALBNN_BASE_INPUT_COLS = [
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
ALBNN_OUTPUT_COLS = ["fx", "fy"]


class TrainingConfigError(ValueError):
    """Raised when a training config is incomplete or inconsistent."""


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` recursively updated by ``updates``."""
    result = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _json_hash(payload: dict[str, Any]) -> str:
    """Return a stable SHA256 hash for a JSON-compatible payload."""
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _resolve_path(value: str | None, *, config_dir: Path | None) -> str | None:
    """Resolve a path relative to the config file directory when possible."""
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute() and config_dir is not None:
        path = config_dir / path
    return str(path.resolve())


def _resolve_runtime_path(value: str | None, *, cwd: Path) -> str | None:
    """Resolve a CLI-supplied runtime path relative to the current process cwd."""
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = cwd / path
    return str(path.resolve())


@dataclass(frozen=True)
class TrainingConfig:
    """Resolved JSON training configuration plus its original payload."""

    raw: dict[str, Any]
    resolved: dict[str, Any]
    config_path: Path | None = None
    config_hash: str | None = None
    resolved_config_hash: str | None = None

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> "TrainingConfig":
        """Load a config from disk and apply runtime overrides."""
        config_path = Path(path).resolve()
        with config_path.open("r", encoding="utf-8-sig") as file:
            raw = json.load(file)
        return cls.from_dict(raw, config_path=config_path, overrides=overrides)

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        config_path: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> "TrainingConfig":
        """Resolve a JSON-compatible training config dictionary."""
        if not isinstance(payload, dict):
            raise TrainingConfigError("Training config must be a JSON object")
        raw = deepcopy(payload)
        config_path_obj = Path(config_path).resolve() if config_path is not None else None
        merged = _deep_update(_defaults(), raw)
        if overrides:
            merged = _deep_update(merged, overrides)
        resolved = _resolve(merged, config_dir=config_path_obj.parent if config_path_obj else None)
        return cls(
            raw=raw,
            resolved=resolved,
            config_path=config_path_obj,
            config_hash=_json_hash(raw),
            resolved_config_hash=_json_hash(resolved),
        )

    @property
    def output_dir(self) -> Path:
        """Return the resolved training output directory."""
        value = self.resolved["run"].get("output_dir")
        if not value:
            raise TrainingConfigError("run.output_dir is required")
        return Path(value)

    def write_trace(self, output_dir: str | Path | None = None) -> None:
        """Write original and resolved config files into ``output_dir``."""
        target = Path(output_dir) if output_dir is not None else self.output_dir
        target.mkdir(parents=True, exist_ok=True)
        (target / "training_config.json").write_text(
            json.dumps(self.raw, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (target / "resolved_training_config.json").write_text(
            json.dumps(self.resolved, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def runtime_overrides(
    *,
    data: str | None = None,
    validation_data: str | None = None,
    output_dir: str | None = None,
    device: str | None = None,
    epochs: int | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Build a nested override dictionary from CLI runtime flags."""
    cwd_path = Path.cwd() if cwd is None else Path(cwd).resolve()
    overrides: dict[str, Any] = {}
    if data is not None:
        overrides.setdefault("data", {})["train_csv"] = _resolve_runtime_path(
            data, cwd=cwd_path
        )
    if validation_data is not None:
        overrides.setdefault("data", {})["validation_csv"] = _resolve_runtime_path(
            validation_data, cwd=cwd_path
        )
    if output_dir is not None:
        overrides.setdefault("run", {})["output_dir"] = _resolve_runtime_path(
            output_dir, cwd=cwd_path
        )
    if device is not None:
        overrides.setdefault("run", {})["device"] = device
    if epochs is not None:
        overrides.setdefault("training", {})["epochs"] = int(epochs)
    return overrides


def _defaults() -> dict[str, Any]:
    """Return default values for the v1 training schema."""
    return {
        "schema_version": 1,
        "run": {
            "run_id": None,
            "output_dir": None,
            "seed": 42,
            "torch_threads": 0,
            "device": "auto",
        },
        "data": {
            "train_csv": None,
            "validation_csv": None,
            "input_cols": list(ALBNN_BASE_INPUT_COLS),
            "target_cols": list(ALBNN_OUTPUT_COLS),
            "target_output": "cartesian",
            "valid_only": True,
            "test_size": 0.2,
        },
        "model": {
            "kind": "albnn_mlp",
            "architecture": [12, 128, 128, 64, 2],
            "activation": "gelu",
            "sine_omega0": 30.0,
            "use_layer_norm": False,
        },
        "scaler": {
            "input": [{"name": "input_identity", "transform": "identity", "columns": "all"}],
            "target": [{"name": "target_identity", "transform": "identity", "columns": "all"}],
        },
        "loss": {"type": "mse", "weights": {"type": "none"}, "huber_delta": 1.0},
        "optimizer": {"type": "adam", "lr": 5e-4, "weight_decay": 0.0},
        "training": {
            "batch_size": 512,
            "epochs": 50000,
            "patience": 2000,
            "val_interval": 1,
            "lr_scheduler": "none",
            "lr_plateau_factor": 0.5,
            "lr_plateau_patience": 1000,
            "min_lr": 1e-6,
        },
        "report": {
            "write_predictions": True,
            "write_loss_curve": True,
            "force_scale_n": 11200.0,
        },
    }


def _resolve(config: dict[str, Any], *, config_dir: Path | None) -> dict[str, Any]:
    """Validate and normalize a merged config."""
    resolved = deepcopy(config)
    if int(resolved.get("schema_version", 0)) != 1:
        raise TrainingConfigError("Only training schema_version=1 is supported")
    model_kind = str(resolved["model"].get("kind", "")).lower()
    if model_kind != "albnn_mlp":
        raise TrainingConfigError(
            "ALB.surrogate.training.AlbnnMlpTrainer only supports model.kind='albnn_mlp'; "
            f"got {resolved['model'].get('kind')!r}"
        )
    data = resolved["data"]
    run = resolved["run"]
    if not data.get("train_csv"):
        raise TrainingConfigError("data.train_csv is required")
    if not run.get("output_dir"):
        raise TrainingConfigError("run.output_dir is required")
    data["train_csv"] = _resolve_path(data["train_csv"], config_dir=config_dir)
    data["validation_csv"] = _resolve_path(data.get("validation_csv"), config_dir=config_dir)
    run["output_dir"] = _resolve_path(run["output_dir"], config_dir=config_dir)
    data["input_cols"] = _string_list(data.get("input_cols"), "data.input_cols")
    data["target_cols"] = _string_list(data.get("target_cols"), "data.target_cols")
    architecture = [int(value) for value in resolved["model"].get("architecture", [])]
    if len(architecture) < 2:
        raise TrainingConfigError("model.architecture must contain at least input and output widths")
    resolved["model"]["architecture"] = architecture
    return resolved


def _string_list(value: Any, name: str) -> list[str]:
    """Parse a list of strings or a comma-separated string."""
    if isinstance(value, str):
        result = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        result = [str(item) for item in value]
    else:
        raise TrainingConfigError(f"{name} must be a list or comma-separated string")
    if not result:
        raise TrainingConfigError(f"{name} cannot be empty")
    duplicates = sorted({item for item in result if result.count(item) > 1})
    if duplicates:
        raise TrainingConfigError(f"{name} contains duplicate columns: {duplicates}")
    return result
