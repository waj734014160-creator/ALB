"""Stable exceptions exposed by the ALB 0.4 user API."""

from __future__ import annotations

from ALB.contracts import ResultBundle


class ALBError(Exception):
    """Base class for failures raised through the user-facing API."""


class ConfigurationError(ALBError, ValueError):
    """A configuration document or typed configuration is invalid."""


class BuildError(ALBError, RuntimeError):
    """A validated configuration could not be assembled."""


class CalculationError(ALBError, RuntimeError):
    """A bearing calculation failed after the input was accepted."""

    def __init__(
        self,
        message: str,
        *,
        failure_snapshot: ResultBundle | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_snapshot = failure_snapshot


class SimulationError(ALBError, RuntimeError):
    """A coupled simulation failed without publishing a partial time step."""

    def __init__(
        self,
        message: str,
        *,
        partial_result: object | None = None,
    ) -> None:
        super().__init__(message)
        self.partial_result = partial_result
        self.failure_snapshot: ResultBundle | None = None


__all__ = [
    "ALBError",
    "BuildError",
    "CalculationError",
    "ConfigurationError",
    "SimulationError",
]
