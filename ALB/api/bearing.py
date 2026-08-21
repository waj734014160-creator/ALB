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
from .errors import BuildError, CalculationError, ConfigurationError
from .results import BearingResult


class Bearing:
    """Stateful user facade over one validated native bearing runtime.

    Parameters
    ----------
    config
        Immutable :class:`BearingConfig` describing the family, unit system,
        time step, resources, and child models. Construction materializes a new
        runtime and does not perform a calculation.

    Notes
    -----
    Calls to :meth:`calculate` are sequential and must advance exactly by the
    configured ``time_step`` after the first sample. The facade retains only the
    latest stable :class:`BearingResult`; :meth:`reset` creates a fresh runtime
    without changing ``config``. Bound analysis services use isolated runtimes
    and do not replace ``latest_result``.

    Raises
    ------
    TypeError
        If ``config`` is not a :class:`BearingConfig`.
    ConfigurationError, BuildError
        If the validated specification cannot be materialized.
    """

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
        """Return the immutable source configuration used by this runtime.

        The returned object may be shared safely; use ``with_overrides`` to
        create a validated modified configuration rather than mutating it.
        """

        return self._config

    @property
    def unit_system(self) -> UnitSystem:
        """Return the unit system required by displacement, velocity, and force.

        Dimensional bearings accept displacement in m and velocity in m/s and
        return force in N. Nondimensional bearings use their configured scales.
        """

        return UnitSystem.coerce(self._config.unit_system)

    @property
    def latest_result(self) -> BearingResult:
        """Return the most recently completed result without hidden evaluation.

        Raises
        ------
        RuntimeError
            If :meth:`calculate` has not completed since construction or reset.
        """

        if self._latest_result is None:
            raise RuntimeError("no bearing result is available")
        return self._latest_result

    @property
    def analysis(self) -> BearingAnalysis:
        """Return state-isolated analysis services for this configuration.

        Each property access returns a lightweight :class:`BearingAnalysis` bound
        to this facade. Its operations build fresh runtimes and therefore leave
        the sequential calculation state and ``latest_result`` unchanged.
        """

        return BearingAnalysis(self)

    def _fresh(self) -> "Bearing":
        return Bearing(self._config)

    def reset(self) -> None:
        """Replace the native runtime and clear the latest result.

        The immutable configuration is preserved. The next calculation may use
        any finite starting time because the previous sequential time boundary is
        discarded.
        """

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
        """Evaluate and commit one sequential two-axis bearing sample.

        Parameters
        ----------
        displacement
            Finite ``(x, y)`` journal-center displacement. Dimensional bearings
            use m; nondimensional bearings use displacement normalized by their
            configured clearance scale.
        velocity
            Finite ``(vx, vy)`` center velocity in m/s or the corresponding
            nondimensional velocity. The default is zero.
        time
            Finite sample time in the configured local time unit. After the first
            successful sample it must equal the previous time plus ``time_step``.
        spool
            Optional finite normalized ``(sx, sy)`` valve command. It is required
            only for ``external_spool`` control and forbidden for all other modes.

        Returns
        -------
        BearingResult
            Immutable force, convergence, field outputs, and diagnostics. The
            same object becomes :attr:`latest_result` only after success.

        Raises
        ------
        TypeError, ValueError
            If array shapes, numeric values, time order, or spool ownership are
            invalid.
        CalculationError
            If the native step fails after accepting the input. When available,
            ``failure_snapshot`` preserves runtime diagnostics.
        """

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
        except Exception as exc:
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
        """Return an immutable diagnostic snapshot without advancing physics.

        Native runtimes may expose family-specific values. The fallback snapshot
        always records schema, family, unit system, and whether a result exists.
        """

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
    """Build a ready bearing facade from an immutable validated configuration.

    Parameters
    ----------
    config
        :class:`BearingConfig` containing the complete materialized specification
        and resource root.

    Returns
    -------
    Bearing
        Fresh facade with no calculation history.

    Raises
    ------
    TypeError
        If ``config`` is not :class:`BearingConfig`.
    ConfigurationError
        If a resource or cross-section configuration is invalid.
    BuildError
        If runtime assembly fails for another reason.
    """

    try:
        return Bearing(config)
    except (BuildError, ConfigurationError):
        raise
    except Exception as exc:
        raise BuildError(f"failed to build bearing: {exc}") from exc


def bearing_from_file(path: str | Path) -> Bearing:
    """Load one strict ALB 0.4 bearing document and build a fresh facade.

    Parameters
    ----------
    path
        UTF-8 JSON5 file with ``schema_version='0.4.0'`` and ``kind='bearing'``.
        Relative includes and resources remain contained below its directory.

    Returns
    -------
    Bearing
        Ready facade whose immutable config records the resolved source path.

    Raises
    ------
    ConfigurationError
        If the document, include graph, fields, values, or resources are invalid.
    ImportError
        If JSON5 support from the ``io`` extra is unavailable.
    BuildError
        If the validated configuration cannot be assembled.
    """

    return build_bearing(load_bearing_config(path))


__all__ = ["Bearing", "bearing_from_file", "build_bearing"]
