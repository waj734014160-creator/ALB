"""Strict versioned configuration envelopes for ALB 0.3 runtimes."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, fields
from enum import Enum
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, cast

import numpy as np

from .control import FuzzyPIDConfig, Moog2ndServoConfig, PIDConfig, ServoConfig
from .film import FPBConfig, NodimPadConfig
from .hydraulics import NodimOrificeConfig, OrificeConfig, TankConfig
from .system import ALBConfig, NodimALBConfig
from .thermal import ThermalConfig


CURRENT_SCHEMA_VERSION = "0.3.0"
ConfigUnit: TypeAlias = Literal["dimensional", "nondimensional"]
CurrentConfig: TypeAlias = ALBConfig | NodimALBConfig


class ControlMode(str, Enum):
    """Explicitly select closed-loop, uncontrolled, or direct-spool input."""

    CONTROLLED = "controlled"
    NONE = "none"
    DIRECT_SPOOL = "direct_spool"

    @classmethod
    def coerce(cls, value: "ControlMode | str") -> "ControlMode":
        """Return one validated control mode."""

        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError as exc:
            raise ValueError(
                "control_mode must be 'controlled', 'none', or 'direct_spool'"
            ) from exc


def _primitive_value(value: Any) -> Any:
    """Convert current configuration values to JSON-compatible primitives."""

    if isinstance(value, np.ndarray):
        return [_primitive_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _primitive_value(value.item())
    if isinstance(value, Mapping):
        return {str(key): _primitive_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitive_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return deepcopy(value)


def _freeze_config_value(value: Any) -> Any:
    """Recursively freeze validated configuration content."""

    if isinstance(value, np.ndarray):
        array = value.copy()
        array.setflags(write=False)
        return array
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze_config_value(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_config_value(item) for item in value)
    return deepcopy(value)


def _field_names(config_type: type[Any]) -> set[str]:
    return {item.name for item in fields(config_type)}


def _require_known_fields(
    payload: Mapping[str, object],
    allowed: set[str],
    *,
    label: str,
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown {label} fields: {unknown}")


def _require_mapping(
    config: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"current ALB config requires '{key}' to be a mapping")
    return cast(Mapping[str, object], value)


def _validate_current_config_fields(
    config: Mapping[str, object],
    unit_system: ConfigUnit,
) -> None:
    """Reject unknown current-schema fields at every nested boundary."""

    config_type = ALBConfig if unit_system == "dimensional" else NodimALBConfig
    allowed = _field_names(config_type) | {"controller"}
    _require_known_fields(config, allowed, label="ALB config")
    required = {
        "pad_config",
        "servo_config",
        "orifice_config",
        "tank_config",
        "controller_config",
        "controller",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"current ALB config is missing nested fields: {missing}")

    pad_type = FPBConfig if unit_system == "dimensional" else NodimPadConfig
    orifice_type = (
        OrificeConfig if unit_system == "dimensional" else NodimOrificeConfig
    )
    pad = _require_mapping(config, "pad_config")
    servo = _require_mapping(config, "servo_config")
    orifice = _require_mapping(config, "orifice_config")
    tank = _require_mapping(config, "tank_config")
    _require_known_fields(pad, _field_names(pad_type), label="pad_config")
    _require_known_fields(
        servo,
        _field_names(ServoConfig) | _field_names(Moog2ndServoConfig),
        label="servo_config",
    )
    _require_known_fields(
        orifice,
        _field_names(orifice_type),
        label="orifice_config",
    )
    _require_known_fields(tank, _field_names(TankConfig), label="tank_config")

    thermal = pad.get("thermal_config")
    if thermal is not None:
        if not isinstance(thermal, Mapping):
            raise TypeError("thermal_config must be a mapping or null")
        _require_known_fields(
            cast(Mapping[str, object], thermal),
            _field_names(ThermalConfig),
            label="thermal_config",
        )

    controller_tag = config.get("controller")
    controller = config.get("controller_config")
    if controller_tag == "none":
        if controller is not None:
            raise ValueError(
                "controller='none' conflicts with a non-null controller_config"
            )
    elif controller_tag in {"PID", "FuzzyPID"}:
        if not isinstance(controller, Mapping):
            raise TypeError(
                f"controller='{controller_tag}' requires a mapping controller_config"
            )
        controller_type = (
            PIDConfig if controller_tag == "PID" else FuzzyPIDConfig
        )
        _require_known_fields(
            cast(Mapping[str, object], controller),
            _field_names(controller_type),
            label=f"{controller_tag} controller_config",
        )
    else:
        raise ValueError("controller must be 'PID', 'FuzzyPID', or 'none'")


def _validate_mode_config(
    control_mode: ControlMode,
    config: Mapping[str, object],
) -> None:
    """Require the explicit mode to agree with legacy implementation fields."""

    alb_kind = config.get("alb")
    controller = config.get("controller")
    controller_config = config.get("controller_config")
    if control_mode is ControlMode.DIRECT_SPOOL:
        if alb_kind != "ALBSV":
            raise ValueError("direct_spool control_mode requires alb='ALBSV'")
        if controller != "none" or controller_config is not None:
            raise ValueError(
                "direct_spool control_mode requires controller='none'"
            )
        return
    if alb_kind != "ALB":
        raise ValueError(
            f"{control_mode.value} control_mode requires alb='ALB'"
        )
    if control_mode is ControlMode.NONE:
        if controller != "none" or controller_config is not None:
            raise ValueError("none control_mode requires controller='none'")
        return
    if controller not in {"PID", "FuzzyPID"} or controller_config is None:
        raise ValueError(
            "controlled control_mode requires PID or FuzzyPID configuration"
        )


@dataclass(frozen=True, slots=True)
class ALBConfigEnvelope:
    """Validated, serializable current-schema ALB configuration."""

    schema_version: str
    kind: Literal["alb"]
    unit_system: ConfigUnit
    control_mode: ControlMode
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
        mode = ControlMode.coerce(self.control_mode)
        copied = deepcopy(dict(self.config))
        _validate_current_config_fields(copied, self.unit_system)
        _validate_mode_config(mode, copied)
        object.__setattr__(self, "control_mode", mode)
        object.__setattr__(self, "config", _freeze_config_value(copied))

    def to_dict(self) -> dict[str, object]:
        """Return a caller-owned JSON-compatible current-schema mapping."""

        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "unit_system": self.unit_system,
            "control_mode": self.control_mode.value,
            "config": _primitive_value(self.config),
        }


def _infer_control_mode(config: CurrentConfig) -> ControlMode:
    """Infer a mode only while wrapping an already typed legacy model."""

    if config.alb == "ALBSV":
        return ControlMode.DIRECT_SPOOL
    if config.controller_config is None:
        return ControlMode.NONE
    return ControlMode.CONTROLLED


def _current_config_envelope(
    config: CurrentConfig,
    *,
    control_mode: ControlMode | str | None = None,
) -> ALBConfigEnvelope:
    """Wrap one typed model in the internal 0.3 configuration envelope."""

    if isinstance(config, ALBConfig):
        unit_system: ConfigUnit = "dimensional"
    elif isinstance(config, NodimALBConfig):
        unit_system = "nondimensional"
    else:
        raise TypeError("config must be ALBConfig or NodimALBConfig")
    mode = (
        _infer_control_mode(config)
        if control_mode is None
        else ControlMode.coerce(control_mode)
    )
    return ALBConfigEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        kind="alb",
        unit_system=unit_system,
        control_mode=mode,
        config=cast(Mapping[str, object], config.to_dict()),
    )


def load_current_envelope(
    payload: Mapping[str, object],
) -> ALBConfigEnvelope:
    """Parse only the strict current envelope without materializing a model."""

    if not isinstance(payload, Mapping):
        raise TypeError("current configuration must be a mapping")
    allowed = {
        "schema_version",
        "kind",
        "unit_system",
        "control_mode",
        "config",
    }
    _require_known_fields(payload, allowed, label="configuration envelope")
    config_payload = payload.get("config")
    if not isinstance(config_payload, Mapping):
        raise TypeError("current configuration envelope requires a config mapping")
    return ALBConfigEnvelope(
        schema_version=str(payload.get("schema_version", "")),
        kind=cast(Literal["alb"], payload.get("kind")),
        unit_system=cast(ConfigUnit, payload.get("unit_system")),
        control_mode=ControlMode.coerce(
            cast(str, payload.get("control_mode", ""))
        ),
        config=cast(Mapping[str, object], config_payload),
    )


def materialize_current_config(envelope: ALBConfigEnvelope) -> CurrentConfig:
    """Construct one typed ALB model configuration from a strict envelope."""

    if not isinstance(envelope, ALBConfigEnvelope):
        raise TypeError("envelope must be ALBConfigEnvelope")
    normalized = cast(dict[str, object], _primitive_value(envelope.config))
    _validate_current_config_fields(normalized, envelope.unit_system)
    _validate_mode_config(envelope.control_mode, normalized)
    if envelope.unit_system == "dimensional":
        return cast(ALBConfig, ALBConfig.from_dict(normalized))
    return cast(NodimALBConfig, NodimALBConfig.from_dict(normalized))


def load_current_config(payload: Mapping[str, object]) -> CurrentConfig:
    """Parse and materialize only the strict current 0.3 envelope."""

    return materialize_current_config(load_current_envelope(payload))


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "ConfigUnit",
    "ControlMode",
    "CurrentConfig",
    "load_current_config",
]
