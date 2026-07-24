"""Friendly public boundary for ALB 0.4."""

from .api import (
    ALBError,
    AnalysisResult,
    Bearing,
    BearingAnalysis,
    BearingConfig,
    BearingMount,
    BearingResult,
    BuildError,
    CalculationError,
    ConfigurationError,
    EllipseTrajectory,
    EquilibriumOptions,
    HistoryPolicy,
    RotorBearingSimulation,
    SimulationConfig,
    SimulationError,
    SimulationResult,
    bearing_from_file,
    build_bearing,
    build_simulation,
    load_bearing_config,
    load_simulation_config,
    simulation_from_file,
)
from .contracts import UnitSystem


__version__ = "0.4.1"

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
    "SimulationConfig",
    "SimulationError",
    "SimulationResult",
    "UnitSystem",
    "__version__",
    "bearing_from_file",
    "build_bearing",
    "build_simulation",
    "load_bearing_config",
    "load_simulation_config",
    "simulation_from_file",
]
