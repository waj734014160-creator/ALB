"""Bound analysis services for user-facing bearings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, cast

import numpy as np
import numpy.typing as npt
from scipy.optimize import root  # type: ignore[import-untyped]

from ALB.contracts import ConvergenceStatus

from .errors import CalculationError
from .results import AnalysisResult

FloatArray = npt.NDArray[np.float64]


def _axis_pair(value: object, name: str) -> FloatArray:
    if np.iscomplexobj(cast(Any, value)):
        raise TypeError(f"{name} must be real")
    result = np.asarray(value, dtype=float)
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain two finite values")
    return result


@dataclass(frozen=True, slots=True)
class EllipseTrajectory:
    """Two-axis elliptical displacement path."""

    center: FloatArray
    semi_axes: FloatArray
    direction: str = "forward"
    phase: float = 0.0

    def __post_init__(self) -> None:
        center = _axis_pair(self.center, "center").copy()
        semi_axes = _axis_pair(self.semi_axes, "semi_axes").copy()
        if np.any(semi_axes <= 0.0):
            raise ValueError("semi_axes values must be > 0")
        if self.direction not in {"forward", "reverse"}:
            raise ValueError("direction must be forward or reverse")
        phase = float(self.phase)
        if not np.isfinite(phase):
            raise ValueError("phase must be finite")
        center.setflags(write=False)
        semi_axes.setflags(write=False)
        object.__setattr__(self, "center", center)
        object.__setattr__(self, "semi_axes", semi_axes)
        object.__setattr__(self, "phase", phase)

    def samples(
        self,
        time: Sequence[float],
        *,
        frequency_hz: float,
    ) -> tuple[FloatArray, FloatArray]:
        """Return displacement and velocity samples on the path."""

        times = np.asarray(time, dtype=float)
        if times.ndim != 1 or times.size == 0 or not np.all(np.isfinite(times)):
            raise ValueError("time must be a nonempty finite one-dimensional grid")
        frequency = float(frequency_hz)
        if not np.isfinite(frequency) or frequency <= 0.0:
            raise ValueError("frequency_hz must be finite and > 0")
        sign = 1.0 if self.direction == "forward" else -1.0
        omega = sign * 2.0 * np.pi * frequency
        angle = omega * times + self.phase
        displacement = np.column_stack(
            (
                self.center[0] + self.semi_axes[0] * np.cos(angle),
                self.center[1] + self.semi_axes[1] * np.sin(angle),
            )
        )
        velocity = np.column_stack(
            (
                -omega * self.semi_axes[0] * np.sin(angle),
                omega * self.semi_axes[1] * np.cos(angle),
            )
        )
        return cast(FloatArray, displacement), cast(FloatArray, velocity)


class BearingAnalysis:
    """Run analyses on fresh runtimes derived from one immutable config."""

    def __init__(self, bearing: Any) -> None:
        self._bearing = bearing

    def find_equilibrium(
        self,
        load: object,
        initial_displacement: object = (0.0, 0.0),
        options: Mapping[str, Any] | None = None,
    ) -> AnalysisResult:
        """Find the displacement whose bearing force balances ``load``."""

        target = _axis_pair(load, "load")
        initial = _axis_pair(initial_displacement, "initial_displacement")
        solver_options = dict(options or {})
        time = float(solver_options.pop("time", 0.0))

        def residual(displacement: FloatArray) -> FloatArray:
            candidate = self._bearing._fresh()
            result = candidate.calculate(
                displacement=displacement,
                velocity=(0.0, 0.0),
                time=time,
            )
            return cast(FloatArray, result.force + target)

        solved = root(residual, initial, options=solver_options)
        if not solved.success:
            raise CalculationError(
                f"equilibrium solve failed: {solved.message}"
            )
        final = self._bearing._fresh().calculate(
            displacement=solved.x,
            velocity=(0.0, 0.0),
            time=time,
        )
        return AnalysisResult(
            {
                "displacement": np.asarray(solved.x, dtype=float),
                "bearing_force": final.force,
                "load": target,
                "residual": final.force + target,
            },
            {
                "schema": "alb.equilibrium-result.v0.4",
                "success": True,
                "evaluations": int(solved.nfev),
                "message": str(solved.message),
                "unit_system": final.unit_system.value,
            },
            convergence=ConvergenceStatus(
                residual=float(np.linalg.norm(final.force + target)),
                converged=True,
                iterations=int(solved.nfev),
                message=str(solved.message),
            ),
        )

    def trace_orbit(
        self,
        trajectory: EllipseTrajectory,
        time_grid: Sequence[float],
        *,
        frequency_hz: float,
        spool: Sequence[Sequence[float]] | None = None,
    ) -> AnalysisResult:
        """Evaluate all samples of one explicit trajectory."""

        if not isinstance(trajectory, EllipseTrajectory):
            raise TypeError("trajectory must be EllipseTrajectory")
        time = np.asarray(time_grid, dtype=float)
        if (
            time.ndim != 1
            or time.size == 0
            or not np.all(np.isfinite(time))
            or np.any(np.diff(time) <= 0.0)
        ):
            raise ValueError("time_grid must be finite and strictly increasing")
        displacement, velocity = trajectory.samples(
            time.tolist(),
            frequency_hz=frequency_hz,
        )
        spool_array = None if spool is None else np.asarray(spool, dtype=float)
        if spool_array is not None and spool_array.shape != displacement.shape:
            raise ValueError("spool must have shape (steps, 2)")
        runtime = self._bearing._fresh()
        forces = []
        convergence = []
        for index, current_time in enumerate(time):
            result = runtime.calculate(
                displacement=displacement[index],
                velocity=velocity[index],
                time=float(current_time),
                spool=(
                    None
                    if spool_array is None
                    else spool_array[index]
                ),
            )
            forces.append(result.force)
            convergence.append(result.convergence)
        iterations = [
            item.iterations
            for item in convergence
            if item.iterations is not None
        ]
        return AnalysisResult(
            {
                "time": time,
                "displacement": displacement,
                "velocity": velocity,
                "force": np.asarray(forces, dtype=float),
            },
            {
                "schema": "alb.orbit-result.v0.4",
                "frequency_hz": float(frequency_hz),
                "direction": trajectory.direction,
                "unit_system": runtime.unit_system.value,
            },
            convergence=ConvergenceStatus(
                residual=max(item.residual for item in convergence),
                converged=all(item.converged for item in convergence),
                iterations=sum(iterations) if iterations else None,
                message="all trajectory samples completed",
            ),
        )

    def dynamic_coefficients(
        self,
        trajectory: EllipseTrajectory,
        time_grid: Sequence[float],
        *,
        frequency_hz: float,
        spool: Sequence[Sequence[float]] | None = None,
    ) -> AnalysisResult:
        """Fit local stiffness and damping from one orbit response."""

        orbit = self.trace_orbit(
            trajectory,
            time_grid,
            frequency_hz=frequency_hz,
            spool=spool,
        )
        displacement = np.asarray(orbit.values["displacement"], dtype=float)
        velocity = np.asarray(orbit.values["velocity"], dtype=float)
        force = np.asarray(orbit.values["force"], dtype=float)
        design = np.column_stack(
            (
                displacement - np.mean(displacement, axis=0),
                velocity - np.mean(velocity, axis=0),
            )
        )
        response = force - np.mean(force, axis=0)
        coefficients, _, rank, singular = np.linalg.lstsq(
            design,
            -response,
            rcond=None,
        )
        stiffness = coefficients[:2, :].T
        damping = coefficients[2:, :].T
        return AnalysisResult(
            {
                **dict(orbit.values),
                "stiffness": stiffness,
                "damping": damping,
                "singular_values": singular,
            },
            {
                **dict(orbit.metadata),
                "schema": "alb.dynamic-coefficients-result.v0.4",
                "rank": int(rank),
            },
            convergence=orbit.convergence,
        )

    def harmonic_linearize(
        self,
        operating_point: object,
        excitation_frequency: float,
        *,
        amplitude: object = (1.0e-6, 1.0e-6),
        points_per_cycle: int = 32,
    ) -> AnalysisResult:
        """Estimate a harmonic local model around one operating point."""

        if (
            isinstance(points_per_cycle, bool)
            or not isinstance(points_per_cycle, int)
            or points_per_cycle < 8
        ):
            raise ValueError("points_per_cycle must be an integer >= 8")
        frequency = float(excitation_frequency)
        if not np.isfinite(frequency) or frequency <= 0.0:
            raise ValueError("excitation_frequency must be finite and > 0")
        dt = float(self._bearing.config.spec["time_step"])
        period = 1.0 / frequency
        expected = period / points_per_cycle
        if not np.isclose(dt, expected, rtol=1.0e-9, atol=1.0e-12):
            raise ValueError(
                "bearing time_step must equal one harmonic sample interval"
            )
        time = np.arange(points_per_cycle, dtype=float) * dt
        trajectory = EllipseTrajectory(
            center=_axis_pair(operating_point, "operating_point"),
            semi_axes=_axis_pair(amplitude, "amplitude"),
        )
        result = self.dynamic_coefficients(
            trajectory,
            time.tolist(),
            frequency_hz=frequency,
        )
        return AnalysisResult(
            dict(result.values),
            {
                **dict(result.metadata),
                "schema": "alb.harmonic-linearization-result.v0.4",
                "excitation_frequency": frequency,
            },
            convergence=result.convergence,
        )


__all__ = ["BearingAnalysis", "EllipseTrajectory"]
