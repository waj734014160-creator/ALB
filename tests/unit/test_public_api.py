"""Tests for the friendly ALB 0.4 package root."""

import ALB


def test_package_root_exports_only_friendly_api():
    assert ALB.__version__ == "0.4.0"
    assert set(ALB.__all__) == {
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
    }
    for removed_name in ("ALB", "Signal", "ALBBuilder", "RsRotorBearingCouple"):
        assert not hasattr(ALB, removed_name)
