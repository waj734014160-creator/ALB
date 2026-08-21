"""Stable exceptions exposed by the ALB 0.4 user API."""

from __future__ import annotations

from ALB.contracts import ResultBundle


class ALBError(Exception):
    """Base class for failures raised through the stable user-facing API.

    Catch this type to handle all facade configuration, build, calculation, and
    simulation failures while allowing ordinary Python contract errors such as
    unrelated ``TypeError`` to remain distinct.
    """


class ConfigurationError(ALBError, ValueError):
    """A JSON5 document or immutable typed configuration is invalid.

    This includes unknown fields, invalid values, include/resource containment,
    cross-section constraints, and incompatible unit or time-step boundaries.
    """


class BuildError(ALBError, RuntimeError):
    """A validated bearing configuration could not be assembled into a runtime.

    Configuration errors retain their own type; this exception wraps unexpected
    assembly failures with the original exception as ``__cause__``.
    """


class CalculationError(ALBError, RuntimeError):
    """A bearing calculation or analysis failed after input acceptance.

    ``failure_snapshot`` may contain the last trusted values, convergence state,
    evaluation history, or matrix diagnostics. It is ``None`` when no safe
    snapshot could be produced.
    """

    def __init__(
        self,
        message: str,
        *,
        failure_snapshot: ResultBundle | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_snapshot = failure_snapshot


class SimulationError(ALBError, RuntimeError):
    """A coupled simulation failed at a defined commit or post-commit boundary.

    ``partial_result`` may expose every retained committed state, while
    ``failure_snapshot`` separates physical, history, recording, observer, and
    run-close completion. A failed physical step is never published as complete.
    """

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
