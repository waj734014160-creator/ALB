"""User-facing bearing facade and construction functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np

from ALB.contracts import (
    BearingInput,
    BearingRuntimeProtocol,
    DirectSpoolBearingInput,
    ResultBundle,
    UnitSystem,
    ValveOutput,
    result_snapshot,
)

from .analysis import BearingAnalysis
from .config import BearingConfig, load_bearing_config
from .errors import BuildError, CalculationError
from .results import BearingResult


class Bearing:
    """Simple stateful facade over one native bearing runtime."""

    __slots__ = ("_config", "_runtime", "_latest_result")

    def __init__(self, config: BearingConfig) -> None:
        if not isinstance(config, BearingConfig):
            raise TypeError("config must be BearingConfig")
        from .building import build_runtime

        self._config = config
        self._runtime = cast(
            BearingRuntimeProtocol[Any],
            build_runtime(config),
        )
        self._latest_result: BearingResult | None = None

    @property
    def config(self) -> BearingConfig:
        """Return the immutable source configuration."""

        return self._config

    @property
    def unit_system(self) -> UnitSystem:
        """Return the units expected by calculate()."""

        return UnitSystem.coerce(self._config.unit_system)

    @property
    def latest_result(self) -> BearingResult:
        """Return the latest result without calculation."""

        if self._latest_result is None:
            raise RuntimeError("no bearing result is available")
        return self._latest_result

    @property
    def analysis(self) -> BearingAnalysis:
        """Return analysis services bound to this immutable configuration."""

        return BearingAnalysis(self)

    def _fresh(self) -> "Bearing":
        return Bearing(self._config)

    def reset(self) -> None:
        """Start a fresh session without exposing implementation initialization."""

        from .building import build_runtime

        self._runtime = cast(
            BearingRuntimeProtocol[Any],
            build_runtime(self._config),
        )
        self._latest_result = None

    def calculate(
        self,
        *,
        displacement: object,
        velocity: object = (0.0, 0.0),
        time: float,
        spool: object | None = None,
    ) -> BearingResult:
        """Evaluate one sequential bearing sample."""

        input_value = BearingInput(
            displacement=np.asarray(displacement),
            velocity=np.asarray(velocity),
            time=time,
            unit_system=self.unit_system,
        )
        if self._latest_result is not None:
            expected = self._latest_result.time + float(
                self._config.spec["time_step"]
            )
            if not np.isclose(
                input_value.time,
                expected,
                rtol=1.0e-10,
                atol=1.0e-12,
            ):
                raise ValueError(
                    f"time must advance by time_step to {expected}"
                )
        mode = self._config.control_mode
        if mode == "external_spool":
            if spool is None:
                raise ValueError(
                    "external_spool control requires spool=(sx, sy)"
                )
            dto: Any = DirectSpoolBearingInput(
                input_value,
                ValveOutput(
                    spool=np.asarray(spool),
                    time=input_value.time,
                    unit_system=UnitSystem.NONDIMENSIONAL,
                ),
            )
        else:
            if spool is not None:
                raise ValueError(
                    "spool is accepted only by external_spool bearings"
                )
            dto = input_value
        try:
            output = self._runtime.step(dto)
            details = self._runtime.result_snapshot()
            convergence = self._runtime.convergence_status
        except BaseException as exc:
            snapshot: ResultBundle | None = None
            failure = getattr(self._runtime, "failure_snapshot", None)
            if callable(failure):
                try:
                    snapshot = failure()
                except Exception:
                    snapshot = None
            raise CalculationError(
                f"{self._config.family} calculation failed: {exc}",
                failure_snapshot=snapshot,
            ) from exc
        result = BearingResult(
            force=output.force,
            time=output.time,
            unit_system=output.unit_system,
            convergence=convergence,
            details=details,
        )
        self._latest_result = result
        return result

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable facade and runtime diagnostics."""

        diagnostic = getattr(self._runtime, "diagnostic_snapshot", None)
        if callable(diagnostic):
            return cast(ResultBundle, diagnostic())
        return result_snapshot(
            {},
            {
                "schema": "alb.bearing-diagnostic.v0.4",
                "family": self._config.family,
                "unit_system": self.unit_system.value,
                "has_result": self._latest_result is not None,
            },
        )


def build_bearing(config: BearingConfig) -> Bearing:
    """Build one ready user-facing bearing."""

    try:
        return Bearing(config)
    except BuildError:
        raise
    except Exception as exc:
        raise BuildError(f"failed to build bearing: {exc}") from exc


def bearing_from_file(path: str | Path) -> Bearing:
    """Load one strict 0.4 JSON5 document and build a ready bearing."""

    return build_bearing(load_bearing_config(path))


__all__ = ["Bearing", "bearing_from_file", "build_bearing"]
