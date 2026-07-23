"""Explicit one-way adapters from legacy flat ALB configuration mappings."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Literal

import numpy as np

from .schema import (
    ALBConfigEnvelope,
    CURRENT_SCHEMA_VERSION,
    ConfigUnit,
    ControlMode,
    current_config_envelope,
)
from .system import ALBConfig, NodimALBConfig


@dataclass(frozen=True, slots=True)
class LegacyALBMigrationReport:
    """Auditable description of one legacy-to-current conversion."""

    source_schema: str
    target_schema: str
    unit_system: ConfigUnit
    controller: str
    control_mode: str
    source_sha256: str


def _json_primitive(value):
    """Normalize legacy values solely for a stable migration digest."""

    if isinstance(value, np.ndarray):
        return [_json_primitive(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_primitive(value.item())
    if isinstance(value, Mapping):
        return {
            str(key): _json_primitive(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_primitive(item) for item in value]
    return value


def _source_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        _json_primitive(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def migrate_legacy_alb_config(
    payload: Mapping[str, object],
    *,
    unit_system: ConfigUnit = "dimensional",
    controller: Literal["PID", "FuzzyPID"] | None = "PID",
    control_mode: ControlMode | str | None = None,
) -> tuple[ALBConfigEnvelope, LegacyALBMigrationReport]:
    """Convert a legacy flat ALB mapping exactly once without mutating it."""

    if not isinstance(payload, Mapping):
        raise TypeError("legacy ALB configuration must be a mapping")
    source = deepcopy(dict(payload))
    if "schema_version" in source:
        raise ValueError(
            "versioned configurations must use load_current_config(); "
            "migration is one-way from unversioned legacy input"
        )
    if control_mode is None:
        if source.get("alb", "ALB") == "ALBSV":
            mode = ControlMode.DIRECT_SPOOL
        elif controller is None or source.get("controller") == "none":
            mode = ControlMode.NONE
        else:
            mode = ControlMode.CONTROLLED
    else:
        mode = ControlMode.coerce(control_mode)

    source["alb"] = (
        "ALBSV" if mode is ControlMode.DIRECT_SPOOL else "ALB"
    )
    selected_controller = (
        None
        if mode in {ControlMode.NONE, ControlMode.DIRECT_SPOOL}
        else controller
    )
    source["controller"] = (
        "none" if selected_controller is None else selected_controller
    )
    if selected_controller is None:
        source["controller_config"] = None

    if unit_system == "dimensional":
        model = ALBConfig.from_dict(source, controller=selected_controller)
    elif unit_system == "nondimensional":
        model = NodimALBConfig.from_dict(source, controller=selected_controller)
    else:
        raise ValueError(
            "unit_system must be 'dimensional' or 'nondimensional'"
        )
    envelope = current_config_envelope(model, control_mode=mode)
    controller_tag = envelope.config["controller"]
    report = LegacyALBMigrationReport(
        source_schema="legacy-flat",
        target_schema=CURRENT_SCHEMA_VERSION,
        unit_system=unit_system,
        controller=str(controller_tag),
        control_mode=mode.value,
        source_sha256=_source_digest(payload),
    )
    return envelope, report


__all__ = ["LegacyALBMigrationReport", "migrate_legacy_alb_config"]
