"""Legacy flat JSON5 to ALB 0.2 configuration migration."""

from __future__ import annotations

import json
import warnings
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "0.2.0"

_DOMAIN_KEYS = {
    "time": {
        "mode",
        "freq",
        "cycles",
        "points_per_cycle",
        "dt",
        "steps",
        "n",
        "pt",
    },
    "film": {
        "r",
        "l",
        "c",
        "miu",
        "rho",
        "w",
        "x0",
        "lx",
        "lz",
        "nx",
        "nz",
        "bias",
        "coe",
        "reynold",
        "error_set",
        "max_iter",
        "damp",
        "lambda_value",
        "lr",
        "vf",
    },
    "hydraulics": {
        "position",
        "cq0",
        "cq1",
        "cq2",
        "ps",
        "p0",
        "q_leak",
        "tank_p",
    },
    "thermal": {
        "thermal_enabled",
        "thermal",
        "thermal_config",
        "transient_enabled",
        "args_nodim",
        "iter_method",
        "coupling",
        "miu0",
        "rho_lub",
        "cp_lub",
        "k_lub",
        "temperature_supply",
        "temperature_ambient",
    },
    "control": {
        "controller",
        "kp",
        "ki",
        "kd",
        "up",
        "down",
        "tw",
        "zeta",
        "tp3",
        "error_range",
        "delta_error_range",
        "rule_path",
        "sensor_angles",
    },
    "system": {
        "alb",
        "servo",
        "switch",
        "node_link",
        "gxy",
        "gxyt",
    },
    "surrogate": {
        "scaler_X",
        "scaler_y",
        "model",
        "metadata",
        "agent",
        "beta_nondim",
        "extra_inputs",
    },
}


@dataclass(frozen=True, slots=True)
class ConfigMigrationReport:
    """Summary of keys routed by a schema migration."""

    source_schema: str
    target_schema: str
    routed_keys: tuple[str, ...]
    unmapped_keys: tuple[str, ...]


def migrate_legacy_config(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], ConfigMigrationReport]:
    """Convert a legacy flat mapping without mutating the caller's data."""

    if not isinstance(payload, Mapping):
        raise TypeError("legacy configuration must be a mapping")
    source = deepcopy(dict(payload))
    if source.get("schema_version") == SCHEMA_VERSION:
        raise ValueError("configuration already declares schema_version 0.2.0")

    migrated: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    routed: set[str] = set()
    for domain, keys in _DOMAIN_KEYS.items():
        section = {key: source[key] for key in source if key in keys}
        if section:
            migrated[domain] = section
            routed.update(section)

    unmapped = {
        key: value
        for key, value in source.items()
        if key not in routed and key != "schema_version"
    }
    if unmapped:
        migrated["legacy_unmapped"] = unmapped

    report = ConfigMigrationReport(
        source_schema=str(source.get("schema_version", "legacy-flat")),
        target_schema=SCHEMA_VERSION,
        routed_keys=tuple(sorted(routed)),
        unmapped_keys=tuple(sorted(unmapped)),
    )
    return migrated, report


def migrate_config_file(
    source: Path | str,
    destination: Path | str,
    *,
    overwrite: bool = False,
) -> ConfigMigrationReport:
    """Read legacy JSON5 and save a separate UTF-8 ALB 0.2 JSON document."""

    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    if source_path == destination_path:
        raise ValueError("destination must differ from the legacy source")
    if destination_path.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {destination_path}")
    try:
        import json5  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "JSON5 migration requires the optional 'io' extra: pip install re-alb[io]"
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
            f"Legacy config is not UTF-8; decoded temporarily as "
            f"{fallback_encoding} and writing the migrated document as UTF-8.",
            UnicodeWarning,
            stacklevel=2,
        )
    payload = json5.loads(source_text)
    migrated, report = migrate_legacy_config(payload)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with destination_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(migrated, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return report
