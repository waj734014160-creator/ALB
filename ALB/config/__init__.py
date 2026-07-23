"""Domain-grouped configuration contracts for ALB 0.3."""

from .common import ConfigData, ResolvedTimeGrid, TimeGridConfig
from .parameters import ParameterHub
from .control import (
    FuzzyPIDConfig,
    LQGConfig,
    Moog2ndServoConfig,
    PIDConfig,
    ServoConfig,
)
from .film import FPBConfig, HydConfig, NodimPadConfig
from .gas import GasConfig
from .hydraulics import CsoArgs, NodimOrificeConfig, OrificeConfig, TankConfig
from .surrogate import ALBNetConfig
from .system import ALBConfig, NodimALBConfig
from .thermal import ThermalConfig, build_thermal_config
from .schema import (
    ALBConfigEnvelope,
    CURRENT_SCHEMA_VERSION,
    ControlMode,
    CurrentConfig,
    current_config_envelope,
    load_current_config,
    load_current_envelope,
    materialize_current_config,
)
from .legacy import LegacyALBMigrationReport, migrate_legacy_alb_config

__all__ = [
    "ALBConfig",
    "ALBConfigEnvelope",
    "ALBNetConfig",
    "ConfigData",
    "ControlMode",
    "CurrentConfig",
    "CURRENT_SCHEMA_VERSION",
    "CsoArgs",
    "FPBConfig",
    "FuzzyPIDConfig",
    "GasConfig",
    "HydConfig",
    "LQGConfig",
    "LegacyALBMigrationReport",
    "Moog2ndServoConfig",
    "NodimALBConfig",
    "NodimOrificeConfig",
    "NodimPadConfig",
    "OrificeConfig",
    "ParameterHub",
    "PIDConfig",
    "ResolvedTimeGrid",
    "ServoConfig",
    "TankConfig",
    "ThermalConfig",
    "TimeGridConfig",
    "build_thermal_config",
    "current_config_envelope",
    "load_current_config",
    "load_current_envelope",
    "materialize_current_config",
    "migrate_legacy_alb_config",
]
