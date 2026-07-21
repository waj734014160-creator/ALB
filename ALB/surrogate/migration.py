"""Non-destructive migration of legacy ALBNN artifacts into 0.2 packages."""

from __future__ import annotations

import hashlib
import json
import pickle
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .package import MODEL_PACKAGE_SCHEMA, open_model_package


_LEGACY_SCALER_NAMES = frozenset(
    {
        "AsinhTargetScaler",
        "ColumnSignedLog1pTargetScaler",
        "Cq2SigLogMinMaxScaler",
        "IdentityTargetScaler",
        "MinMaxCubeRootTargetScaler",
        "MinMaxWithScaledEvsFeaturesScaler",
        "MotionStandardParamDirectMinMaxScaler",
        "MotionStandardParamMinMaxScaler",
        "PolarMotionStandardParamMinMaxScaler",
        "SelectiveMinMaxScaler",
        "SelectiveStandardScaler",
        "SignedLog1pTargetScaler",
        "StandardTargetScaler",
        "StandardThenMinMaxScaler",
    }
)


class _LegacyAlbScalerUnpickler(pickle.Unpickler):
    """Remap only the retired ``ALB.nn`` scaler globals during migration."""

    def find_class(self, module: str, name: str):
        if module == "ALB.nn":
            if name not in _LEGACY_SCALER_NAMES:
                raise pickle.UnpicklingError(
                    f"unsupported legacy ALB.nn pickle global: {name}"
                )
            from . import scalers

            return getattr(scalers, name)
        return super().find_class(module, name)


def _load_legacy_scaler(path: Path):
    """Load one explicitly trusted scaler with the narrow legacy remap."""

    with path.open("rb") as stream:
        return _LegacyAlbScalerUnpickler(stream).load()


def _write_current_scaler(scaler, path: Path) -> None:
    """Serialize a migrated scaler using its current 0.2 module path."""

    with path.open("wb") as stream:
        pickle.dump(scaler, stream, protocol=pickle.HIGHEST_PROTOCOL)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ModelPackageMigrationReport:
    """Summary returned after a legacy artifact package migration."""

    destination: str
    source_digests: dict[str, str]
    package_digests: dict[str, str]


def migrate_legacy_model_package(
    model: Path | str,
    input_scaler: Path | str,
    output_scaler: Path | str,
    destination: Path | str,
    *,
    metadata: Path | str | None = None,
    overwrite: bool = False,
    trust_legacy_pickle: bool = False,
) -> ModelPackageMigrationReport:
    """Migrate trusted legacy artifacts without changing the source files.

    Pickle can execute arbitrary code while loading. The caller must therefore
    opt in explicitly for scaler files whose provenance has been verified. Old
    ``ALB.nn`` scaler globals are remapped to their 0.2 classes and reserialized
    so the resulting package no longer depends on the removed flat namespace.
    """

    sources = {
        "model": Path(model).resolve(),
        "input_scaler": Path(input_scaler).resolve(),
        "output_scaler": Path(output_scaler).resolve(),
    }
    for role, source in sources.items():
        if not source.is_file():
            raise FileNotFoundError(f"legacy {role} artifact is missing: {source}")
    metadata_source = Path(metadata).resolve() if metadata is not None else None
    if metadata_source is not None and not metadata_source.is_file():
        raise FileNotFoundError(
            f"legacy metadata artifact is missing: {metadata_source}"
        )
    if not trust_legacy_pickle:
        raise PermissionError(
            "legacy scaler migration uses pickle; pass trust_legacy_pickle=True "
            "only for trusted source artifacts"
        )

    migrated_scalers = {
        role: _load_legacy_scaler(sources[role])
        for role in ("input_scaler", "output_scaler")
    }

    root = Path(destination).resolve()
    outputs = {
        "model": root / "model.pt",
        "input_scaler": root / "input_scaler.pkl",
        "output_scaler": root / "output_scaler.pkl",
        "metadata": root / "metadata.json",
        "manifest": root / "manifest.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"destination package already contains: {existing[0]}")
    root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(sources["model"], outputs["model"])
    for role, scaler in migrated_scalers.items():
        _write_current_scaler(scaler, outputs[role])
    if metadata_source is None:
        metadata_payload = {
            "schema_version": "0.2.0",
            "migration": "legacy-artifact-layout",
        }
    else:
        metadata_payload = json.loads(metadata_source.read_text(encoding="utf-8"))
        metadata_payload["schema_version"] = "0.2.0"
    outputs["metadata"].write_text(
        json.dumps(metadata_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    package_digests = {
        role: _sha256(outputs[role])
        for role in ("model", "input_scaler", "output_scaler", "metadata")
    }
    manifest = {
        "schema": MODEL_PACKAGE_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pickle_trust_required": True,
        "artifacts": {
            role: {"path": outputs[role].name, "sha256": package_digests[role]}
            for role in package_digests
        },
    }
    outputs["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    open_model_package(root)
    return ModelPackageMigrationReport(
        destination=str(root),
        source_digests={role: _sha256(path) for role, path in sources.items()},
        package_digests=package_digests,
    )
