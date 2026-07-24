"""User-facing ALB 0.4 facade."""

from .analysis import BearingAnalysis, EllipseTrajectory, EquilibriumOptions
from .bearing import Bearing, bearing_from_file, build_bearing
from .config import BearingConfig, SCHEMA_VERSION, load_bearing_config
from .errors import (
    ALBError,
    BuildError,
    CalculationError,
    ConfigurationError,
    SimulationError,
)
from .results import AnalysisResult, BearingResult, SimulationResult
from .simulation import (
    BearingMount,
    HistoryPolicy,
    RotorBearingSimulation,
    SimulationConfig,
    build_simulation,
    load_simulation_config,
    simulation_from_file,
)


__all__ = [
    "ALBError",
    "AnalysisResult",
    "Bearing",
    "BearingAnalysis",
    "BearingConfig",
    "BearingMount",
    "BearingResult",
    "BuildError",
    "CalculationError",
    "ConfigurationError",
    "EllipseTrajectory",
    "EquilibriumOptions",
    "HistoryPolicy",
    "RotorBearingSimulation",
    "SCHEMA_VERSION",
    "SimulationError",
    "SimulationConfig",
    "SimulationResult",
    "bearing_from_file",
    "build_bearing",
    "build_simulation",
    "load_bearing_config",
    "load_simulation_config",
    "simulation_from_file",
]
