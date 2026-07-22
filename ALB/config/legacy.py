"""Explicit one-way adapters from legacy flat ALB configuration mappings."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from .schema import (
    ALBConfigEnvelope,
    CURRENT_SCHEMA_VERSION,
    ConfigUnit,
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


def migrate_legacy_alb_config(
    payload: Mapping[str, object],
    *,
    unit_system: ConfigUnit = "dimensional",
    controller: Literal["PID", "FuzzyPID"] | None = "PID",
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
    if unit_system == "dimensional":
        model = ALBConfig.from_dict(source, controller=controller)
    elif unit_system == "nondimensional":
        model = NodimALBConfig.from_dict(source, controller=controller)
    else:
        raise ValueError(
            "unit_system must be 'dimensional' or 'nondimensional'"
        )
    envelope = current_config_envelope(model)
    controller_tag = envelope.config["controller"]
    report = LegacyALBMigrationReport(
        source_schema="legacy-flat",
        target_schema=CURRENT_SCHEMA_VERSION,
        unit_system=unit_system,
        controller=str(controller_tag),
    )
    return envelope, report


__all__ = ["LegacyALBMigrationReport", "migrate_legacy_alb_config"]
