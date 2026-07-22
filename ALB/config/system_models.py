"""Domain configuration models split from the historical monolith."""

from dataclasses import dataclass, field, fields
from typing import Optional, Union

import numpy as np

from .common_models import ConfigData
from .control_models import (
    FuzzyPIDConfig, Moog2ndServoConfig, PIDConfig, ServoConfig,
)
from .film_models import FPBConfig, NodimPadConfig
from .hydraulics_models import (
    NodimOrificeConfig, OrificeConfig, TankConfig,
)
from .thermal_models import ThermalConfig

def _select_alb_controller(config_dict: dict, default: Optional[str]) -> Optional[str]:
    """Resolve PID, FuzzyPID, or the explicit no-controller configuration."""

    if "controller" in config_dict:
        selected = config_dict["controller"]
    elif (
        "controller_config" in config_dict
        and config_dict["controller_config"] is None
    ):
        selected = None
    else:
        selected = default
    if selected is None or selected == "none":
        return None
    if selected not in {"PID", "FuzzyPID"}:
        raise ValueError("Controller must be 'PID', 'FuzzyPID', or 'none'")
    return selected

def _alb_controller_tag(controller_config: object) -> str:
    """Return the stable serialized discriminator for an ALB controller config."""

    if controller_config is None:
        return "none"
    if isinstance(controller_config, PIDConfig):
        return "PID"
    if isinstance(controller_config, FuzzyPIDConfig):
        return "FuzzyPID"
    raise TypeError(
        "controller_config must be PIDConfig, FuzzyPIDConfig, or None"
    )

def _build_alb_controller_config(
    config_dict: dict,
    selected_controller: Optional[str],
) -> Optional[Union["PIDConfig", "FuzzyPIDConfig"]]:
    """Build a tagged nested controller config without silently changing type."""

    payload_is_present = "controller_config" in config_dict
    payload = config_dict.get("controller_config")
    if selected_controller is None:
        if payload_is_present and payload is not None:
            raise ValueError(
                "controller='none' conflicts with a non-null controller_config"
            )
        return None

    controller_class = (
        PIDConfig if selected_controller == "PID" else FuzzyPIDConfig
    )
    other_class = (
        FuzzyPIDConfig if selected_controller == "PID" else PIDConfig
    )
    if payload_is_present:
        if payload is None:
            raise ValueError(
                f"controller='{selected_controller}' requires controller_config"
            )
        if isinstance(payload, other_class):
            raise ValueError(
                f"controller='{selected_controller}' conflicts with "
                f"{type(payload).__name__}"
            )
        if isinstance(payload, controller_class):
            return payload
        if isinstance(payload, dict):
            allowed = {config_field.name for config_field in fields(controller_class)}
            unknown = sorted(set(payload) - allowed)
            if unknown:
                raise ValueError(
                    f"Unknown {selected_controller} controller_config fields: {unknown}"
                )
            return controller_class(**payload)
        raise TypeError(
            "controller_config must be a matching config object, dictionary, or None"
        )

    # Historical flat task dictionaries remain permissive for migration only.
    return ConfigData.set_config(controller_class, config_dict)

@dataclass
class ALBConfig(ConfigData):
    """Configuration for the Active Lubricated Bearing (ALB) system."""

    pad_config: FPBConfig = field(default_factory=FPBConfig)
    servo_config: ServoConfig = field(default_factory=Moog2ndServoConfig)
    orifice_config: OrificeConfig = field(default_factory=OrificeConfig)
    tank_config: TankConfig = field(default_factory=TankConfig)
    controller_config: Optional[Union[PIDConfig, FuzzyPIDConfig]] = field(
        default_factory=PIDConfig
    )  # or FuzzyPIDConfig()
    dt: float = 6.667e-4
    node_link: np.int_ = None
    gxy: np.ndarray = field(default_factory=lambda: np.eye(2))
    gxyt: np.ndarray = field(default_factory=lambda: np.zeros((2, 2)))
    alb: str = "ALB"  # ALB or ALBSV
    servo: str = "moog_2nd"  # moog_2nd, moog, or static
    switch: bool = True  # Whether to enable control
    c: Optional[float] = None  # Optional displacement scale override.
    w: Optional[float] = None  # Optional speed scale override, rpm.

    @property
    def thermal_enabled(self) -> bool:
        """True when the pad-level thermal config is configured."""
        return self.pad_config.thermal_config is not None

    @property
    def thermal_config(self) -> Optional["ThermalConfig"]:
        """Forward ``pad_config.thermal_config`` for convenience."""
        return self.pad_config.thermal_config

    def to_dict(self) -> dict:
        """Serialize nested values with an explicit controller type tag."""

        data = super().to_dict()
        data["controller"] = _alb_controller_tag(self.controller_config)
        return data

    @classmethod
    def from_dict(cls, config_dict, controller: Optional[str] = "PID"):
        """
        Construct an ALBConfig instance correctly from a dictionary containing all parameters.
        :param controller: the type of the controller, PID or FuzzyPID
        :param config_dict: a dictionary containing all parameters
        """
        selected_controller = _select_alb_controller(config_dict, controller)

        alb = config_dict.get("alb", "ALB")
        if alb not in {"ALB", "ALBSV"}:
            raise ValueError("alb must be 'ALB' or 'ALBSV'")
        servo = config_dict.get("servo", "moog_2nd")
        if servo not in {"moog_2nd", "moog", "static"}:
            raise ValueError("servo must be 'moog_2nd', 'moog', or 'static'")

        # Prefer nested payloads emitted by to_dict(), while retaining the
        # historical flat task/config dictionary form.
        pad_payload = config_dict.get("pad_config")
        pad_config_instance = (
            pad_payload
            if isinstance(pad_payload, FPBConfig)
            else FPBConfig.from_dict(
                pad_payload if isinstance(pad_payload, dict) else config_dict
            )
        )
        servo_payload = config_dict.get("servo_config")
        if isinstance(servo_payload, ServoConfig):
            servo_config_instance = servo_payload
        elif isinstance(servo_payload, dict):
            servo_config_instance = Moog2ndServoConfig(**servo_payload)
        else:
            servo_config_data = Moog2ndServoConfig().to_dict()
            servo_config_data.update(
                {
                    key: config_dict[key]
                    for key in servo_config_data
                    if key in config_dict
                }
            )
            servo_config_instance = Moog2ndServoConfig(**servo_config_data)
        orifice_payload = config_dict.get("orifice_config")
        orifice_config_instance = (
            orifice_payload
            if isinstance(orifice_payload, OrificeConfig)
            else OrificeConfig(**orifice_payload)
            if isinstance(orifice_payload, dict)
            else cls.set_config(OrificeConfig, config_dict)
        )
        tank_payload = config_dict.get("tank_config")
        tank_config_instance = (
            tank_payload
            if isinstance(tank_payload, TankConfig)
            else TankConfig(**tank_payload)
            if isinstance(tank_payload, dict)
            else cls.set_config(TankConfig, config_dict)
        )
        controller_instance = _build_alb_controller_config(
            config_dict, selected_controller
        )

        # Extract fields that directly belong to ALBConfig
        direct_keys = [
            "dt",
            "node_link",
            "gxy",
            "gxyt",
            "alb",
            "servo",
            "switch",
            "c",
            "w",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }

        # Use the created instances and direct parameters to construct the final ALBConfig instance
        return cls(
            pad_config=pad_config_instance,
            servo_config=servo_config_instance,
            orifice_config=orifice_config_instance,
            tank_config=tank_config_instance,
            controller_config=controller_instance,
            **direct_args,
        )

    @classmethod
    def keys(cls):
        """Returns a list of all possible configuration keys."""
        keys = cls().to_dict().keys()
        # First, remove the keys of nested configurations
        keys = [
            key
            for key in keys
            if key
            not in [
                "pad_config",
                "servo_config",
                "orifice_config",
                "tank_config",
                "controller_config",
            ]
        ]
        keys.extend(cls().pad_config.to_dict().keys())
        keys.extend(cls().servo_config.to_dict().keys())
        keys.extend(cls().orifice_config.to_dict().keys())
        keys.extend(cls().tank_config.to_dict().keys())
        keys.extend(cls().controller_config.to_dict().keys())
        # Remove duplicates
        keys = list(set(keys))
        return keys

@dataclass
class NodimALBConfig(ConfigData):
    """Configuration for ALB models assembled from nondimensional inputs."""

    pad_config: NodimPadConfig = field(default_factory=NodimPadConfig)
    orifice_config: NodimOrificeConfig = field(default_factory=NodimOrificeConfig)
    servo_config: ServoConfig = field(default_factory=Moog2ndServoConfig)
    tank_config: TankConfig = field(default_factory=TankConfig)
    controller_config: Optional[Union[PIDConfig, FuzzyPIDConfig]] = field(
        default_factory=PIDConfig
    )
    dt: float = 6.667e-4
    node_link: np.int_ = None
    gxy: np.ndarray = field(default_factory=lambda: np.eye(2))
    gxyt: np.ndarray = field(default_factory=lambda: np.zeros((2, 2)))
    alb: str = "ALB"  # ALB or ALBSV
    servo: str = "moog_2nd"  # moog_2nd, moog, or static
    switch: bool = True

    @property
    def thermal_enabled(self) -> bool:
        return self.pad_config.thermal_config is not None

    @property
    def thermal_config(self) -> Optional[ThermalConfig]:
        return self.pad_config.thermal_config

    def to_dict(self) -> dict:
        """Serialize nested values with an explicit controller type tag."""

        data = super().to_dict()
        data["controller"] = _alb_controller_tag(self.controller_config)
        return data

    @classmethod
    def from_dict(cls, config_dict, controller: Optional[str] = "PID"):
        """Create a nodimensional ALB config from the flat task/config dictionary style."""
        selected_controller = _select_alb_controller(config_dict, controller)

        alb = config_dict.get("alb", "ALB")
        if alb not in {"ALB", "ALBSV"}:
            raise ValueError("alb must be 'ALB' or 'ALBSV'")
        servo = config_dict.get("servo", "moog_2nd")
        if servo not in {"moog_2nd", "moog", "static"}:
            raise ValueError("servo must be 'moog_2nd', 'moog', or 'static'")

        direct_keys = [
            "dt",
            "node_link",
            "gxy",
            "gxyt",
            "alb",
            "servo",
            "switch",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }
        pad_payload = config_dict.get("pad_config")
        pad_config_instance = (
            pad_payload
            if isinstance(pad_payload, NodimPadConfig)
            else NodimPadConfig.from_dict(
                pad_payload if isinstance(pad_payload, dict) else config_dict
            )
        )
        orifice_payload = config_dict.get("orifice_config")
        orifice_config_instance = (
            orifice_payload
            if isinstance(orifice_payload, NodimOrificeConfig)
            else NodimOrificeConfig.from_dict(
                orifice_payload if isinstance(orifice_payload, dict) else config_dict
            )
        )
        servo_payload = config_dict.get("servo_config")
        if isinstance(servo_payload, ServoConfig):
            servo_config_instance = servo_payload
        elif isinstance(servo_payload, dict):
            servo_config_instance = Moog2ndServoConfig(**servo_payload)
        else:
            servo_config_data = Moog2ndServoConfig().to_dict()
            servo_config_data.update(
                {
                    key: config_dict[key]
                    for key in servo_config_data
                    if key in config_dict
                }
            )
            servo_config_instance = Moog2ndServoConfig(**servo_config_data)
        tank_payload = config_dict.get("tank_config")
        tank_config_instance = (
            tank_payload
            if isinstance(tank_payload, TankConfig)
            else TankConfig(**tank_payload)
            if isinstance(tank_payload, dict)
            else cls.set_config(TankConfig, config_dict)
        )
        controller_instance = _build_alb_controller_config(
            config_dict, selected_controller
        )

        # Mirror ALBConfig.from_dict by rebuilding the nested nodim config
        # objects from a shared flat configuration payload.
        return cls(
            pad_config=pad_config_instance,
            orifice_config=orifice_config_instance,
            servo_config=servo_config_instance,
            tank_config=tank_config_instance,
            controller_config=controller_instance,
            **direct_args,
        )

__all__ = ['ALBConfig', 'NodimALBConfig']
