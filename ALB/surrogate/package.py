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

# Inference symmetry modes accepted by ``load_albnn_package``. ``"package"``
# resolves to one of the two concrete modes from the package itself.
ALBNN_SYMMETRY_MODES = ("none", "c4", "package")

# Metadata key and accepted declaration names. ``c4_canonical_quadrant`` is the
# historical v0.2 marker (for example M0031); ``c4`` mirrors the config value.
_SYMMETRY_METADATA_KEY = "inference_symmetry"
_SYMMETRY_DECLARATIONS = {
    "none": "none",
    "c4": "c4",
    "c4_canonical_quadrant": "c4",
}
# Optional descriptive entries of a mapping-form C4 declaration. They must
# describe exactly what ``ALBNNC4Canonical`` implements.
_C4_DECLARATION_DETAILS = {
    "canonical_domain": "ex>=0, ey>=0",
    "rotated_input_pairs": [["ex", "ey"], ["vx", "vy"], ["sx", "sy"]],
    "restored_output_cols": ["fx", "fy"],
}
# Network inputs that remain correct after the C4 wrapper rotates (e, v, s).
# ``ALBNNC4Canonical`` rotates only the base vector pairs and does not
# recompute derived columns, so only rotation-invariant derived columns are safe.
_C4_SAFE_INPUT_COLS = frozenset(
    {
        "ex", "ey", "vx", "vy", "sx", "sy",
        "lambda_value", "beta_nondim", "lr", "cq0", "cq1", "cq2",
        "r", "v_norm", "s_norm",
        "e_dot_v", "e_dot_s", "s_dot_v", "ev_dot", "es_dot", "sv_dot", "v_dot_s",
        "lambda_over_lr",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _declared_symmetry(metadata: Mapping[str, Any]) -> str | None:
    """Return the concrete symmetry declared by package metadata, if any.

    ``inference_symmetry`` may be a declaration name or a mapping with a
    ``name`` entry plus the optional descriptive entries of the historical
    v0.2 marker. Absence returns ``None``; any malformed or unknown declaration
    raises instead of being treated as undeclared.
    """

    if _SYMMETRY_METADATA_KEY not in metadata:
        return None
    value = metadata[_SYMMETRY_METADATA_KEY]
    details: Mapping[str, Any] = {}
    if isinstance(value, Mapping):
        unknown = set(value) - {"name", *_C4_DECLARATION_DETAILS}
        if unknown:
            raise ValueError(
                f"metadata inference_symmetry has unknown entries: {sorted(unknown)}"
            )
        details = {key: item for key, item in value.items() if key != "name"}
        value = value.get("name")
    if not isinstance(value, str) or value not in _SYMMETRY_DECLARATIONS:
        raise ValueError(
            "metadata inference_symmetry must name one of "
            f"{sorted(_SYMMETRY_DECLARATIONS)}"
        )
    resolved = _SYMMETRY_DECLARATIONS[value]
    if details and resolved != "c4":
        raise ValueError(
            "metadata inference_symmetry details are valid only for C4"
        )
    for key, item in details.items():
        if item != _C4_DECLARATION_DETAILS[key]:
            raise ValueError(
                f"metadata inference_symmetry.{key} does not match the "
                f"implemented C4 mapping {_C4_DECLARATION_DETAILS[key]!r}"
            )
    return resolved


def _fitted_quadrant_i_only(scaler: object) -> bool:
    """Return whether an input scaler records ``ex, ey >= 0`` training minima.

    Only scalers that store per-column fitted minima (``data_min_`` aligned with
    ``scale_columns_`` or ``feature_names_in_``) can prove the domain. Any other
    scaler returns ``False``: its fitted domain is unknown, not quadrant-limited.
    """

    data_min = getattr(scaler, "data_min_", None)
    names = getattr(scaler, "scale_columns_", None)
    if names is None:
        names = getattr(scaler, "feature_names_in_", None)
    if data_min is None or names is None:
        return False
    names = [str(name) for name in names]
    try:
        minima = [float(value) for value in data_min]
    except (TypeError, ValueError):
        return False
    if len(minima) != len(names) or not {"ex", "ey"} <= set(names):
        return False
    return (
        minima[names.index("ex")] >= 0.0
        and minima[names.index("ey")] >= 0.0
    )


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
        a conflicting explicit schema is rejected. An optional
        ``inference_symmetry`` declaration (``"none"``, ``"c4"``, or the
        historical ``{"name": "c4_canonical_quadrant", ...}`` mapping) is
        validated here so packages trained only on ``ex, ey >= 0`` can declare
        C4 canonical-quadrant inference.

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
        If metadata conflicts with the 0.4 contract, declares an unsupported
        inference symmetry, or a scaler is invalid.
    """

    _declared_symmetry(metadata)
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
    symmetry: str = "none",
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
    symmetry
        Inference symmetry. ``"none"`` (default) returns the bare ``ALBNN``
        network exactly as stored. ``"c4"`` wraps it in ``ALBNNC4Canonical``,
        which rotates ``(e, v, s)`` into the ``ex, ey >= 0`` training quadrant
        and rotates the force back. ``"package"`` follows the metadata
        ``inference_symmetry`` declaration; an undeclared package resolves to
        ``"none"`` unless its input scaler records fitted ``ex`` and ``ey``
        minima ``>= 0``, which is rejected so the caller chooses explicitly.

    Returns
    -------
    Any
        Initialized ``ALBNN`` (or ``ALBNNC4Canonical``) inference object
        accepted by the surrogate bearing runtime.

    Raises
    ------
    FileNotFoundError
        If the package is incomplete.
    ValueError
        If digests, schemas, model type, checkpoint structure, scalers, or the
        symmetry declaration are invalid; if C4 is requested for an input
        contract containing rotation-dependent derived columns; or if
        ``symmetry="package"`` meets an undeclared quadrant-I-only package.
    ImportError
        If the ``surrogate`` extra, including Torch, is not installed.
    """

    if not isinstance(symmetry, str) or symmetry not in ALBNN_SYMMETRY_MODES:
        raise ValueError(
            f"symmetry must be one of {list(ALBNN_SYMMETRY_MODES)}"
        )
    package = open_model_package(path)
    import torch

    from .inference import ALBNN, ALBNNC4Canonical
    from .networks import net_from_checkpoint
    from .scaler_io import load_scaler

    metadata = json.loads(package.metadata.read_text(encoding="utf-8"))
    if metadata.get("model_type") != "albnn_mlp":
        raise ValueError(
            "ALB 0.4 deployment accepts only self-contained albnn_mlp packages"
        )
    input_scaler = load_scaler(package.input_scaler)
    # Resolve symmetry before loading weights. Explicit modes win over the
    # metadata declaration, mirroring the ``use_augment`` override, but the
    # declaration is always validated so malformed packages fail early.
    declared = _declared_symmetry(metadata)
    resolved = symmetry
    if symmetry == "package":
        if declared is not None:
            resolved = declared
        elif _fitted_quadrant_i_only(input_scaler):
            raise ValueError(
                "ALBNN package input scaler was fitted only on ex >= 0 and "
                "ey >= 0 but metadata declares no inference_symmetry; choose "
                "'c4' (canonical-quadrant inference) or 'none' (bare network) "
                "explicitly, e.g. spec.model_package.symmetry"
            )
        else:
            resolved = "none"
    if resolved == "c4":
        unsafe = sorted(
            set(metadata.get("input_cols") or ()) - _C4_SAFE_INPUT_COLS
        )
        if unsafe:
            raise ValueError(
                "C4 canonical inference does not support rotation-dependent "
                f"input columns: {unsafe}"
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
    model = ALBNN(
        net,
        input_scaler,
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
    if resolved == "c4":
        return ALBNNC4Canonical(model)
    return model


__all__ = [
    "ALBNN_SYMMETRY_MODES",
    "METADATA_SCHEMA",
    "MODEL_PACKAGE_SCHEMA",
    "ModelPackage",
    "create_model_package",
    "load_albnn_package",
    "open_model_package",
]
