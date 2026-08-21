"""Strict pickle-free ALBNN 0.4 model packages."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .scaler_io import write_scaler


MODEL_PACKAGE_SCHEMA = "alb.surrogate-package.v0.4"
METADATA_SCHEMA = "alb.surrogate-metadata.v0.4"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ModelPackage:
    """Validated paths in one ALBNN 0.4 model package."""

    root: Path
    model: Path
    input_scaler: Path
    output_scaler: Path
    metadata: Path
    manifest: Mapping[str, Any]


def open_model_package(path: Path | str) -> ModelPackage:
    """Validate and describe one pickle-free ALBNN 0.4 package.

    Parameters
    ----------
    path
        Directory containing ``manifest.json`` and the four exact artifact roles:
        ``weights.pt``, two NPZ scalers, and ``metadata.json``.

    Returns
    -------
    ModelPackage
        Resolved artifact paths plus the validated manifest mapping.

    Raises
    ------
    FileNotFoundError
        If the manifest or any declared artifact is absent.
    ValueError
        If schemas, role names, relative file names, metadata, or SHA-256 digests
        do not match the ALBNN 0.4 package contract.
    """

    root = Path(path).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"model package manifest is missing: {manifest_path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("model package manifest must be a mapping")
    if manifest.get("schema") != MODEL_PACKAGE_SCHEMA:
        raise ValueError("unsupported ALBNN model package schema")
    if set(manifest) != {"schema", "artifacts"}:
        raise ValueError("model package manifest contains unknown fields")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("model package artifacts must be a mapping")
    required = {
        "model": "weights.pt",
        "input_scaler": "input_scaler.npz",
        "output_scaler": "output_scaler.npz",
        "metadata": "metadata.json",
    }
    if set(artifacts) != set(required):
        raise ValueError("model package artifact roles are not exact")
    resolved: dict[str, Path] = {}
    for role, expected_name in required.items():
        record = artifacts[role]
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "sha256"}
            or record.get("path") != expected_name
        ):
            raise ValueError(f"invalid package artifact role: {role}")
        artifact_path = root / expected_name
        if not artifact_path.is_file():
            raise FileNotFoundError(
                f"model package artifact is missing: {artifact_path}"
            )
        if _sha256(artifact_path) != record.get("sha256"):
            raise ValueError(f"model package artifact digest mismatch: {role}")
        resolved[role] = artifact_path
    metadata = json.loads(resolved["metadata"].read_text(encoding="utf-8"))
    if (
        not isinstance(metadata, dict)
        or metadata.get("schema") != METADATA_SCHEMA
    ):
        raise ValueError("unsupported ALBNN metadata schema")
    return ModelPackage(
        root=root,
        model=resolved["model"],
        input_scaler=resolved["input_scaler"],
        output_scaler=resolved["output_scaler"],
        metadata=resolved["metadata"],
        manifest=manifest,
    )


def create_model_package(
    path: Path | str,
    *,
    checkpoint: Path | str,
    input_scaler: object,
    output_scaler: object,
    metadata: Mapping[str, Any],
) -> ModelPackage:
    """Create one deployable package from trusted training artifacts.

    Parameters
    ----------
    path
        Destination directory. It may be absent or empty, but existing content is
        never overwritten.
    checkpoint
        Existing trusted Torch checkpoint copied to ``weights.pt``.
    input_scaler, output_scaler
        Fitted scaler objects accepted by ``write_scaler`` and serialized as NPZ.
    metadata
        Deployment metadata. Schema ``alb.surrogate-metadata.v0.4`` is inserted;
        a conflicting explicit schema is rejected.

    Returns
    -------
    ModelPackage
        Newly written package after a complete digest-validation pass.

    Raises
    ------
    FileExistsError
        If the destination directory contains files.
    FileNotFoundError
        If ``checkpoint`` does not exist.
    ValueError
        If metadata conflicts with the 0.4 contract or a scaler is invalid.
    """

    root = Path(path).resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"model package directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    source_model = Path(checkpoint).resolve()
    if not source_model.is_file():
        raise FileNotFoundError(f"checkpoint does not exist: {source_model}")
    model_path = root / "weights.pt"
    shutil.copyfile(source_model, model_path)
    input_path = write_scaler(input_scaler, root / "input_scaler.npz")
    output_path = write_scaler(output_scaler, root / "output_scaler.npz")
    metadata_payload = dict(metadata)
    metadata_payload.setdefault("model_type", "albnn_mlp")
    existing_schema = metadata_payload.get("schema")
    if existing_schema not in {None, METADATA_SCHEMA}:
        raise ValueError("metadata schema conflicts with ALBNN 0.4")
    metadata_payload["schema"] = METADATA_SCHEMA
    metadata_path = root / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths = {
        "model": model_path,
        "input_scaler": input_path,
        "output_scaler": output_path,
        "metadata": metadata_path,
    }
    manifest = {
        "schema": MODEL_PACKAGE_SCHEMA,
        "artifacts": {
            role: {
                "path": artifact.name,
                "sha256": _sha256(artifact),
            }
            for role, artifact in paths.items()
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return open_model_package(root)


def load_albnn_package(
    path: Path | str,
    *,
    use_augment: bool | None = None,
    runtime_parameters: Mapping[str, Any] | None = None,
) -> Any:
    """Load a digest-validated ALBNN package for CPU inference.

    Parameters
    ----------
    path
        Package directory accepted by ``open_model_package``.
    use_augment
        Optional runtime override for metadata ``use_augment``. ``None`` preserves
        the packaged value.
    runtime_parameters
        Optional mapping exposed as attributes on the inference runtime config.

    Returns
    -------
    Any
        Initialized ``ALBNN`` inference object accepted by the surrogate bearing
        runtime.

    Raises
    ------
    FileNotFoundError
        If the package is incomplete.
    ValueError
        If digests, schemas, model type, checkpoint structure, or scalers are
        invalid.
    ImportError
        If the ``surrogate`` extra, including Torch, is not installed.
    """

    package = open_model_package(path)
    import torch

    from .inference import ALBNN
    from .networks import net_from_checkpoint
    from .scaler_io import load_scaler

    metadata = json.loads(package.metadata.read_text(encoding="utf-8"))
    if metadata.get("model_type") != "albnn_mlp":
        raise ValueError(
            "ALB 0.4 deployment accepts only self-contained albnn_mlp packages"
        )
    checkpoint = torch.load(
        package.model,
        map_location=torch.device("cpu"),
        weights_only=True,
    )
    net = net_from_checkpoint(checkpoint)  # type: ignore[no-untyped-call]
    net.load_state_dict(checkpoint["model_state_dict"])
    parameters = dict(runtime_parameters or {})
    config = type("RuntimeParameters", (), parameters)()
    return ALBNN(
        net,
        load_scaler(package.input_scaler),
        load_scaler(package.output_scaler),
        config=config,
        input_cols=metadata.get("input_cols"),
        output_cols=metadata.get("output_cols"),
        use_augment=(
            bool(metadata.get("use_augment", False))
            if use_augment is None
            else bool(use_augment)
        ),
        feature_set=metadata.get("feature_set", "default"),
        target_output=metadata.get("target_output", "cartesian"),
    )


__all__ = [
    "METADATA_SCHEMA",
    "MODEL_PACKAGE_SCHEMA",
    "ModelPackage",
    "create_model_package",
    "load_albnn_package",
    "open_model_package",
]
