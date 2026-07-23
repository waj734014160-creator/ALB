"""Non-destructive legacy JSON5 migration into the strict ALB 0.3 schema."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any, Literal
import warnings

from .legacy import migrate_legacy_alb_config
from .schema import ConfigUnit, ControlMode


@dataclass(frozen=True, slots=True)
class ConfigMigrationReport:
    """Auditable source, target, mode, and digest details."""

    source_schema: str
    target_schema: str
    unit_system: ConfigUnit
    controller: str
    control_mode: str
    source_sha256: str
    output_sha256: str | None = None


def migrate_legacy_config(
    payload: Mapping[str, Any],
    *,
    unit_system: ConfigUnit = "dimensional",
    controller: Literal["PID", "FuzzyPID"] | None = "PID",
    control_mode: ControlMode | str | None = None,
) -> tuple[dict[str, object], ConfigMigrationReport]:
    """Convert one unversioned ALB mapping to a strict current envelope."""

    envelope, legacy_report = migrate_legacy_alb_config(
        payload,
        unit_system=unit_system,
        controller=controller,
        control_mode=control_mode,
    )
    report = ConfigMigrationReport(
        source_schema=legacy_report.source_schema,
        target_schema=legacy_report.target_schema,
        unit_system=legacy_report.unit_system,
        controller=legacy_report.controller,
        control_mode=legacy_report.control_mode,
        source_sha256=legacy_report.source_sha256,
    )
    return envelope.to_dict(), report


def _read_legacy_json5(source_path: Path) -> Mapping[str, Any]:
    """Read UTF-8 JSON5, explicitly warning on legacy GBK/CP936 fallback."""

    try:
        import json5  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "JSON5 migration requires the optional 'io' extra: "
            "pip install re-alb[io]"
        ) from exc

    try:
        source_text = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as utf8_error:
        source_bytes = source_path.read_bytes()
        source_text = None
        fallback_encoding = None
        for encoding in ("gbk", "cp936"):
            try:
                source_text = source_bytes.decode(encoding)
                fallback_encoding = encoding
                break
            except UnicodeDecodeError:
                continue
        if source_text is None or fallback_encoding is None:
            raise utf8_error
        warnings.warn(
            "Legacy config is not UTF-8; decoded temporarily as "
            f"{fallback_encoding} and writing the migrated document as UTF-8.",
            UnicodeWarning,
            stacklevel=2,
        )
    payload = json5.loads(source_text)
    if not isinstance(payload, Mapping):
        raise TypeError("legacy JSON5 root must be an object")
    return payload


def migrate_config_file(
    source: Path | str,
    destination: Path | str,
    *,
    unit_system: ConfigUnit = "dimensional",
    controller: Literal["PID", "FuzzyPID"] | None = "PID",
    control_mode: ControlMode | str | None = None,
    overwrite: bool = False,
) -> ConfigMigrationReport:
    """Save a separate UTF-8 0.3 envelope while preserving the source file."""

    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    if source_path == destination_path:
        raise ValueError("destination must differ from the legacy source")
    if destination_path.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {destination_path}")

    payload = _read_legacy_json5(source_path)
    migrated, report = migrate_legacy_config(
        payload,
        unit_system=unit_system,
        controller=controller,
        control_mode=control_mode,
    )
    encoded = (
        json.dumps(migrated, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(encoded)
    return replace(
        report,
        output_sha256=hashlib.sha256(encoded).hexdigest(),
    )


__all__ = [
    "ConfigMigrationReport",
    "migrate_config_file",
    "migrate_legacy_config",
]
