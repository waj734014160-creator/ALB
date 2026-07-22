"""Versioned configuration envelopes for current ALB models."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .system import ALBConfig, NodimALBConfig


CURRENT_SCHEMA_VERSION = "0.2.0"
ConfigUnit: TypeAlias = Literal["dimensional", "nondimensional"]
CurrentConfig: TypeAlias = ALBConfig | NodimALBConfig


@dataclass(frozen=True, slots=True)
class ALBConfigEnvelope:
    """Validated current-schema envelope detached from legacy parsing."""

    schema_version: str
    kind: Literal["alb"]
    unit_system: ConfigUnit
    config: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CURRENT_SCHEMA_VERSION!r}"
            )
        if self.kind != "alb":
            raise ValueError("kind must be 'alb'")
        if self.unit_system not in {"dimensional", "nondimensional"}:
            raise ValueError(
                "unit_system must be 'dimensional' or 'nondimensional'"
            )
        required = {
            "pad_config",
            "servo_config",
            "orifice_config",
            "tank_config",
            "controller_config",
            "controller",
        }
        missing = sorted(required - set(self.config))
        if missing:
            raise ValueError(f"current ALB config is missing nested fields: {missing}")

    def to_dict(self) -> dict[str, object]:
        """Return a caller-owned current-schema mapping."""

        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "unit_system": self.unit_system,
            "config": deepcopy(dict(self.config)),
        }


def current_config_envelope(config: CurrentConfig) -> ALBConfigEnvelope:
    """Wrap one current model in an explicit versioned envelope."""

    if isinstance(config, ALBConfig):
        unit_system: ConfigUnit = "dimensional"
    elif isinstance(config, NodimALBConfig):
        unit_system = "nondimensional"
    else:
        raise TypeError("config must be ALBConfig or NodimALBConfig")
    return ALBConfigEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        kind="alb",
        unit_system=unit_system,
        config=cast(Mapping[str, object], config.to_dict()),
    )


def load_current_config(payload: Mapping[str, object]) -> CurrentConfig:
    """Load only the current nested schema; legacy flat inputs are rejected."""

    if not isinstance(payload, Mapping):
        raise TypeError("current configuration must be a mapping")
    allowed = {"schema_version", "kind", "unit_system", "config"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown current configuration envelope fields: {unknown}")
    config_payload = payload.get("config")
    if not isinstance(config_payload, Mapping):
        raise TypeError("current configuration envelope requires a config mapping")
    envelope = ALBConfigEnvelope(
        schema_version=str(payload.get("schema_version", "")),
        kind=cast(Literal["alb"], payload.get("kind")),
        unit_system=cast(ConfigUnit, payload.get("unit_system")),
        config=config_payload,
    )
    normalized = deepcopy(dict(envelope.config))
    if envelope.unit_system == "dimensional":
        return ALBConfig.from_dict(normalized)
    return NodimALBConfig.from_dict(normalized)


__all__ = [
    "ALBConfigEnvelope",
    "CURRENT_SCHEMA_VERSION",
    "ConfigUnit",
    "CurrentConfig",
    "current_config_envelope",
    "load_current_config",
]
