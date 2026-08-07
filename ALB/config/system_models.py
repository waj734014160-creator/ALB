"""Domain configuration models split from the historical monolith."""

from dataclasses import dataclass, field
from numbers import Integral, Real
from typing import Optional, Union

import numpy as np

from .common_models import ConfigData
from .control_models import (
    FuzzyPIDConfig,
    PIDConfig,
    SecondOrderServoConfig,
    TransferFunctionServoConfig,
)
from .film_models import FPBConfig, NodimPadConfig
from .hydraulics_models import (
    NodimOrificeConfig, OrificeConfig, TankConfig,
)
from .thermal_models import ThermalConfig


def _finite_matrix(value, name: str) -> np.ndarray:
    """Normalize one finite 2-by-2 ALB gain matrix."""

    array = np.asarray(value)
    if np.iscomplexobj(array):
        raise TypeError(f"{name} must be real")
    try:
        result = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a real numeric matrix") from exc
    if result.shape != (2, 2):
        raise ValueError(f"{name} must have shape (2, 2)")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    return result.copy()


def _normalize_alb_common(config) -> None:
    """Validate fields shared by dimensional and nondimensional ALB configs."""

    if isinstance(config.dt, bool) or not isinstance(config.dt, Real):
        raise TypeError("dt must be a real number")
    config.dt = float(config.dt)
    if not np.isfinite(config.dt) or config.dt <= 0.0:
        raise ValueError("dt must be finite and > 0")
    if config.node_link is not None:
        if isinstance(config.node_link, (bool, np.bool_)) or not isinstance(
            config.node_link, (Integral, np.integer)
        ):
            raise TypeError("node_link must be an integer or None")
        if int(config.node_link) < 0:
            raise ValueError("node_link must be nonnegative")
        config.node_link = int(config.node_link)
    config.gxy = _finite_matrix(config.gxy, "gxy")
    config.gxyt = _finite_matrix(config.gxyt, "gxyt")
    if config.control_mode not in {
        "pid",
        "fuzzy_pid",
        "uncontrolled",
        "external_spool",
    }:
        raise ValueError("control_mode is invalid")
    if not isinstance(
        config.servo_config,
        (SecondOrderServoConfig, TransferFunctionServoConfig),
    ):
        raise TypeError(
            "servo_config must be SecondOrderServoConfig or "
            "TransferFunctionServoConfig"
        )
    if config.control_mode in {"uncontrolled", "external_spool"}:
        if config.controller_config is not None:
            raise ValueError(
                f"{config.control_mode} requires controller_config=None"
            )
    elif config.controller_config is None:
        raise ValueError(f"{config.control_mode} requires controller_config")


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

@dataclass
class ALBConfig(ConfigData):
    """Configuration for the Active Lubricated Bearing (ALB) system."""

    pad_config: FPBConfig = field(default_factory=FPBConfig)
    servo_config: Union[
        SecondOrderServoConfig,
        TransferFunctionServoConfig,
    ] = field(default_factory=SecondOrderServoConfig)
    orifice_config: OrificeConfig = field(default_factory=OrificeConfig)
    tank_config: TankConfig = field(default_factory=TankConfig)
    controller_config: Optional[Union[PIDConfig, FuzzyPIDConfig]] = field(
        default_factory=PIDConfig
    )  # or FuzzyPIDConfig()
    dt: float = 6.667e-4
    node_link: np.int_ = None
    gxy: np.ndarray = field(default_factory=lambda: np.eye(2))
    gxyt: np.ndarray = field(default_factory=lambda: np.zeros((2, 2)))
    control_mode: str = "pid"
    c: Optional[float] = None  # Optional displacement scale override.
    w: Optional[float] = None  # Optional speed scale override, rpm.

    def __post_init__(self) -> None:
        _normalize_alb_common(self)
        for name in ("c", "w"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real number or None")
            normalized = float(value)
            if not np.isfinite(normalized) or normalized <= 0.0:
                raise ValueError(f"{name} must be finite and > 0")
            setattr(self, name, normalized)

    @property
    def thermal_config(self) -> Optional["ThermalConfig"]:
        """Forward ``pad_config.thermal_config`` for convenience."""
        return self.pad_config.thermal_config

    @property
    def valve_model(self) -> str:
        """Return the model discriminator derived from ``servo_config``."""

        if isinstance(self.servo_config, SecondOrderServoConfig):
            return "second_order"
        return "transfer_function"

    def to_dict(self) -> dict:
        """Serialize nested values with an explicit controller type tag."""

        data = super().to_dict()
        data["controller"] = _alb_controller_tag(self.controller_config)
        return data

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
    servo_config: Union[
        SecondOrderServoConfig,
        TransferFunctionServoConfig,
    ] = field(default_factory=SecondOrderServoConfig)
    tank_config: TankConfig = field(default_factory=TankConfig)
    controller_config: Optional[Union[PIDConfig, FuzzyPIDConfig]] = field(
        default_factory=PIDConfig
    )
    dt: float = 6.667e-4
    node_link: np.int_ = None
    gxy: np.ndarray = field(default_factory=lambda: np.eye(2))
    gxyt: np.ndarray = field(default_factory=lambda: np.zeros((2, 2)))
    control_mode: str = "pid"

    def __post_init__(self) -> None:
        _normalize_alb_common(self)

    @property
    def thermal_config(self) -> Optional[ThermalConfig]:
        return self.pad_config.thermal_config

    @property
    def valve_model(self) -> str:
        """Return the model discriminator derived from ``servo_config``."""

        if isinstance(self.servo_config, SecondOrderServoConfig):
            return "second_order"
        return "transfer_function"

    def to_dict(self) -> dict:
        """Serialize nested values with an explicit controller type tag."""

        data = super().to_dict()
        data["controller"] = _alb_controller_tag(self.controller_config)
        return data

__all__ = ['ALBConfig', 'NodimALBConfig']
