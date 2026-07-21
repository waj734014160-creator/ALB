"""Versioned ALBNN model-package validation and trusted loading."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


MODEL_PACKAGE_SCHEMA = "alb.surrogate-package.v0.2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ModelPackage:
    """Validated paths in one ALBNN 0.2 model package."""

    root: Path
    model: Path
    input_scaler: Path
    output_scaler: Path
    metadata: Path
    manifest: dict


def open_model_package(path: Path | str) -> ModelPackage:
    """Validate package schema, expected files, and SHA-256 digests."""

    root = Path(path).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"model package manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != MODEL_PACKAGE_SCHEMA:
        raise ValueError("unsupported ALBNN model package schema")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("model package artifacts must be a mapping")
    required = {
        "model": "model.pt",
        "input_scaler": "input_scaler.pkl",
        "output_scaler": "output_scaler.pkl",
        "metadata": "metadata.json",
    }
    resolved: dict[str, Path] = {}
    for role, expected_name in required.items():
        record = artifacts.get(role)
        if not isinstance(record, dict) or record.get("path") != expected_name:
            raise ValueError(f"invalid or missing package artifact role: {role}")
        artifact_path = root / expected_name
        if not artifact_path.is_file():
            raise FileNotFoundError(f"model package artifact is missing: {artifact_path}")
        if _sha256(artifact_path) != record.get("sha256"):
            raise ValueError(f"model package artifact digest mismatch: {role}")
        resolved[role] = artifact_path
    return ModelPackage(
        root=root,
        model=resolved["model"],
        input_scaler=resolved["input_scaler"],
        output_scaler=resolved["output_scaler"],
        metadata=resolved["metadata"],
        manifest=manifest,
    )


def load_albnn_package(
    path: Path | str,
    *,
    trust_pickle: bool = False,
    use_augment: bool | None = None,
    runtime_config: object | None = None,
):
    """Load a validated package only after explicit pickle trust consent.

    ``runtime_config`` may provide dimensional scales or fixed inference
    parameters. Package artifact paths always replace any paths on that object.
    """

    if not trust_pickle:
        raise PermissionError(
            "ALBNN scaler loading uses pickle; pass trust_pickle=True only for a trusted package"
        )
    package = open_model_package(path)
    from .inference import albnn

    values = {}
    if runtime_config is not None:
        try:
            values.update(vars(runtime_config))
        except TypeError as exc:
            raise TypeError(
                "runtime_config must expose instance attributes"
            ) from exc
    values.update(
        {
            "model": str(package.model),
            "scaler_X": str(package.input_scaler),
            "scaler_y": str(package.output_scaler),
            "metadata": str(package.metadata),
        }
    )
    config = SimpleNamespace(**values)
    return albnn(config, use_augment=use_augment)
