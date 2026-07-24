"""Bound analysis services that preserve the established numerical methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, cast

import numpy as np
import numpy.typing as npt

from ALB.contracts import (
    BearingInput,
    ConvergenceStatus,
    DirectSpoolBearingInput,
    UnitSystem,
    ValveOutput,
    result_snapshot,
)
from ._analysis_numerics import (
    EquilibriumOutcome,
    EquilibriumSolver,
    aggregate_active_linearization,
    linearize_film_runtime,
)
from .errors import CalculationError
from .results import AnalysisResult


FloatArray = npt.NDArray[np.float64]
_FFT_RTOL = 1.0e-12
_MAX_DISPLACEMENT_CONDITION = 1.0 / np.sqrt(np.finfo(float).eps)


def _axis_pair(value: object, name: str) -> FloatArray:
    if np.iscomplexobj(cast(Any, value)):
        raise TypeError(f"{name} must be real")
    result = np.asarray(value, dtype=float)
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain two finite values")
    return result


def _positive_float(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a real number")
    result = float(cast(Any, value))
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")
    return result


@dataclass(frozen=True, slots=True)
class _WhirlGrid:
    """Validated coherent grid used by the established FFT identification."""

    time: FloatArray
    frequency_hz: float
    frequencies: FloatArray
    selected_index: int
    selected_frequency_hz: float
    nyquist_hz: float


def _validate_whirl_grid(
    time_grid: Sequence[float],
    frequency_hz: float,
) -> _WhirlGrid:
    """Reject grids that cannot represent the requested FFT coefficient."""

    if np.iscomplexobj(cast(Any, time_grid)):
        raise TypeError("time_grid must be real")
    time = np.asarray(time_grid, dtype=float)
    if time.ndim != 1 or not np.all(np.isfinite(time)):
        raise ValueError("time_grid must be a finite one-dimensional grid")
    if time.size < 2:
        raise ValueError("time_grid must contain at least two samples")
    delta = np.diff(time)
    if np.any(delta <= 0.0):
        raise ValueError("time_grid must be strictly increasing")
    dt = float(delta[0])
    float_info = np.finfo(np.float64)
    uniform_atol = (
        float(float_info.eps)
        * max(abs(dt), float(float_info.tiny))
        * 16.0
    )
    if not np.allclose(delta, dt, rtol=_FFT_RTOL, atol=uniform_atol):
        raise ValueError("time_grid must be uniform for FFT identification")
    requested = _positive_float(frequency_hz, "frequency_hz")
    frequencies = np.fft.rfftfreq(time.size, dt)
    nyquist = float(frequencies[-1])
    frequency_atol = abs(requested) * _FFT_RTOL
    if requested > nyquist and not np.isclose(
        requested,
        nyquist,
        rtol=_FFT_RTOL,
        atol=frequency_atol,
    ):
        raise CalculationError(
            "frequency_hz exceeds the FFT Nyquist frequency",
            failure_snapshot=result_snapshot(
                {
                    "time": time,
                    "fft_frequencies": frequencies,
                },
                {
                    "schema": "alb.dynamic-identification-failure.v0.4.2",
                    "failure_phase": "grid_validation",
                    "requested_frequency_hz": requested,
                    "selected_frequency_hz": nyquist,
                    "nyquist_hz": nyquist,
                },
            ),
        )
    selected_index = int(np.argmin(np.abs(frequencies - requested)))
    selected = float(frequencies[selected_index])
    if selected_index == 0 or not np.isclose(
        selected,
        requested,
        rtol=_FFT_RTOL,
        atol=frequency_atol,
    ):
        raise CalculationError(
            "frequency_hz must coincide with a non-DC FFT bin",
            failure_snapshot=result_snapshot(
                {
                    "time": time,
                    "fft_frequencies": frequencies,
                },
                {
                    "schema": "alb.dynamic-identification-failure.v0.4.2",
                    "failure_phase": "grid_validation",
                    "requested_frequency_hz": requested,
                    "selected_frequency_hz": selected,
                    "selected_frequency_index": selected_index,
                    "nyquist_hz": nyquist,
                },
            ),
        )
    return _WhirlGrid(
        time=time,
        frequency_hz=requested,
        frequencies=frequencies,
        selected_index=selected_index,
        selected_frequency_hz=selected,
        nyquist_hz=nyquist,
    )


@dataclass(frozen=True, slots=True)
class EquilibriumOptions:
    """Friendly immutable parameters for the established equilibrium solver."""

    max_iterations: int = 30
    relative_tolerance: float = 1.0e-4
    damping: float = 0.05
    jacobian_step: float = 1.0e-2
    fallback_stiffness: tuple[float, float] = (5.0, 5.0)
    stall_patience: int = 5
    stall_relative_tolerance: float = 0.0
    time: float = 0.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_iterations, (bool, np.bool_))
            or not isinstance(self.max_iterations, (int, np.integer))
            or int(self.max_iterations) < 1
        ):
            raise ValueError("max_iterations must be an integer >= 1")
        if (
            isinstance(self.stall_patience, (bool, np.bool_))
            or not isinstance(self.stall_patience, (int, np.integer))
            or int(self.stall_patience) < 0
        ):
            raise ValueError("stall_patience must be an integer >= 0")
        tolerance = _positive_float(
            self.relative_tolerance,
            "relative_tolerance",
        )
        damping = _positive_float(self.damping, "damping")
        jacobian_step = _positive_float(
            self.jacobian_step,
            "jacobian_step",
        )
        stiffness = _axis_pair(
            self.fallback_stiffness,
            "fallback_stiffness",
        )
        if np.any(stiffness <= 0.0):
            raise ValueError("fallback_stiffness values must be > 0")
        stall_tolerance = float(self.stall_relative_tolerance)
        if (
            not np.isfinite(stall_tolerance)
            or stall_tolerance < 0.0
            or stall_tolerance >= 1.0
        ):
            raise ValueError(
                "stall_relative_tolerance must be finite and in [0, 1)"
            )
        time = float(self.time)
        if not np.isfinite(time):
            raise ValueError("time must be finite")
        stiffness_tuple = (float(stiffness[0]), float(stiffness[1]))
        object.__setattr__(self, "max_iterations", int(self.max_iterations))
        object.__setattr__(self, "relative_tolerance", tolerance)
        object.__setattr__(self, "damping", damping)
        object.__setattr__(self, "jacobian_step", jacobian_step)
        object.__setattr__(self, "fallback_stiffness", stiffness_tuple)
        object.__setattr__(self, "stall_patience", int(self.stall_patience))
        object.__setattr__(
            self,
            "stall_relative_tolerance",
            stall_tolerance,
        )
        object.__setattr__(self, "time", time)


@dataclass(frozen=True, slots=True)
class EllipseTrajectory:
    """Two-axis ellipse with separate temporal phase and spatial orientation."""

    center: FloatArray
    semi_axes: FloatArray
    direction: str = "forward"
    phase: float = 0.0
    orientation_rad: float = 0.0

    def __post_init__(self) -> None:
        center = _axis_pair(self.center, "center").copy()
        semi_axes = _axis_pair(self.semi_axes, "semi_axes").copy()
        if np.any(semi_axes <= 0.0):
            raise ValueError("semi_axes values must be > 0")
        if self.direction not in {"forward", "reverse"}:
            raise ValueError("direction must be forward or reverse")
        phase = float(self.phase)
        orientation = float(self.orientation_rad)
        if not np.isfinite(phase):
            raise ValueError("phase must be finite")
        if not np.isfinite(orientation):
            raise ValueError("orientation_rad must be finite")
        center.setflags(write=False)
        semi_axes.setflags(write=False)
        object.__setattr__(self, "center", center)
        object.__setattr__(self, "semi_axes", semi_axes)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "orientation_rad", orientation)

    def with_direction(self, direction: str) -> "EllipseTrajectory":
        """Return the same geometry traversed in the requested direction."""

        return EllipseTrajectory(
            self.center,
            self.semi_axes,
            direction=direction,
            phase=self.phase,
            orientation_rad=self.orientation_rad,
        )

    def samples(
        self,
        time: Sequence[float],
        *,
        frequency_hz: float,
    ) -> tuple[FloatArray, FloatArray]:
        """Return displacement and velocity samples on the rotated ellipse."""

        times = np.asarray(time, dtype=float)
        if times.ndim != 1 or times.size == 0 or not np.all(np.isfinite(times)):
            raise ValueError("time must be a nonempty finite one-dimensional grid")
        frequency = _positive_float(frequency_hz, "frequency_hz")
        signed_frequency = (
            frequency if self.direction == "forward" else -frequency
        )
        omega = 2.0 * np.pi * signed_frequency
        angle = 2.0 * np.pi * signed_frequency * times + self.phase
        cosine = np.cos(self.orientation_rad)
        sine = np.sin(self.orientation_rad)
        axis_x = self.semi_axes[0]
        axis_y = self.semi_axes[1]
        displacement = np.column_stack(
            (
                axis_x * np.cos(angle) * cosine
                - axis_y * np.sin(angle) * sine
                + self.center[0],
                axis_x * np.cos(angle) * sine
                + axis_y * np.sin(angle) * cosine
                + self.center[1],
            )
        )
        velocity = np.column_stack(
            (
                -omega
                * (
                    axis_x * np.sin(angle) * cosine
                    + axis_y * np.cos(angle) * sine
                ),
                -omega
                * (
                    axis_x * np.sin(angle) * sine
                    - axis_y * np.cos(angle) * cosine
                ),
            )
        )
        return cast(FloatArray, displacement), cast(FloatArray, velocity)


class BearingAnalysis:
    """Run state-isolated analyses derived from one immutable bearing config."""

    def __init__(self, bearing: Any) -> None:
        self._bearing = bearing

    def _new_runtime(self) -> Any:
        from .building import build_runtime

        return build_runtime(self._bearing.config)

    def _run_runtime(
        self,
        runtime: Any,
        *,
        displacement: FloatArray,
        time: float,
        spool: FloatArray | None = None,
        static: bool = False,
    ) -> tuple[FloatArray, ConvergenceStatus]:
        unit_system = UnitSystem.coerce(self._bearing.config.unit_system)
        bearing_input = BearingInput(
            displacement,
            np.zeros(2),
            time,
            unit_system,
        )
        mode = self._bearing.config.control_mode
        if mode == "external_spool":
            if spool is None:
                raise CalculationError(
                    "external_spool analysis requires a normalized base spool"
                )
            dto: Any = DirectSpoolBearingInput(
                bearing_input,
                ValveOutput(
                    spool,
                    time,
                    UnitSystem.NONDIMENSIONAL,
                ),
            )
            output = runtime.step(dto)
        else:
            if spool is not None:
                raise CalculationError(
                    "spool is accepted only for external_spool analysis"
                )
            if static and callable(
                evaluate_static := getattr(runtime, "evaluate_static", None)
            ):
                runtime.input(bearing_input)
                evaluate_static()
                output = runtime.output()
            else:
                output = runtime.step(bearing_input)
        return (
            np.asarray(output.force, dtype=float),
            runtime.convergence_status,
        )

    def _equilibrium_scales(self) -> tuple[float, float]:
        config = self._bearing.config
        if config.unit_system == "nondimensional":
            return 1.0, 1.0
        if config.family not in {
            "active_lubricated",
            "liquid_film",
            "gas_film",
        }:
            raise CalculationError(
                "find_equilibrium requires a film bearing with explicit scales"
            )
        if config.family == "gas_film":
            from ALB.config.gas_models import GasConfig
            from .building import _GAS_FILM_MAP, _translate

            film = config.spec["film"]
            gas_config = GasConfig(**_translate(film, _GAS_FILM_MAP))
            pressure = float(gas_config.pa)
            clearance = float(gas_config.c)
            radius = float(gas_config.r)
            length = float(gas_config.l)
        else:
            from .building import _dimensional_pad

            film_config = _dimensional_pad(
                config,
                active=config.family == "active_lubricated",
            )
            pressure = float(film_config.ps)
            clearance = float(film_config.c)
            radius = float(film_config.r)
            length = float(film_config.l)
        return clearance, pressure * length * radius / 2.0

    @staticmethod
    def _equilibrium_values(
        outcome: EquilibriumOutcome,
        *,
        displacement_scale: float,
        force_scale: float,
        load: FloatArray,
    ) -> dict[str, Any]:
        return {
            "displacement": outcome.coordinate * displacement_scale,
            "bearing_force": outcome.force * force_scale,
            "load": load,
            "residual": (outcome.force * force_scale) + load,
            "evaluation_displacement": np.asarray(
                [
                    item.coordinate * displacement_scale
                    for item in outcome.evaluations
                ],
                dtype=float,
            ),
            "evaluation_force": np.asarray(
                [item.force * force_scale for item in outcome.evaluations],
                dtype=float,
            ),
            "evaluation_relative_residual": np.asarray(
                [item.residual for item in outcome.evaluations],
                dtype=float,
            ),
            "evaluation_inner_converged": np.asarray(
                [item.inner_converged for item in outcome.evaluations],
                dtype=bool,
            ),
        }

    def find_equilibrium(
        self,
        load: object,
        initial_displacement: object = (0.0, 0.0),
        options: EquilibriumOptions = EquilibriumOptions(),
    ) -> AnalysisResult:
        """Find load balance with the established damped Newton algorithm."""

        if not isinstance(options, EquilibriumOptions):
            raise TypeError("options must be EquilibriumOptions")
        if self._bearing.config.control_mode == "external_spool":
            raise CalculationError(
                "find_equilibrium does not infer an external spool; "
                "use a controlled/uncontrolled bearing configuration"
            )
        target = _axis_pair(load, "load")
        if bool(np.all(target == 0.0)):
            raise ValueError(
                "find_equilibrium requires a nonzero load because "
                "relative_tolerance is normalized by load magnitude"
            )
        initial = _axis_pair(
            initial_displacement,
            "initial_displacement",
        )
        displacement_scale, force_scale = self._equilibrium_scales()
        runtime = self._new_runtime()
        trusted_coordinates: list[FloatArray] = []
        trusted_forces: list[FloatArray] = []
        trusted_residuals: list[float] = []
        normalized_load = target / force_scale

        def reset_iteration() -> None:
            reset = getattr(runtime, "_reset_for_owner", None)
            if not callable(reset):
                raise CalculationError(
                    "bearing runtime does not support isolated equilibrium reset"
                )
            reset()

        def evaluate_force(
            coordinate: FloatArray,
        ) -> tuple[FloatArray, bool]:
            try:
                force, convergence = self._run_runtime(
                    runtime,
                    displacement=coordinate * displacement_scale,
                    time=options.time,
                    static=True,
                )
            except BaseException as exc:
                raise CalculationError(
                    "equilibrium inner calculation raised an exception",
                    failure_snapshot=result_snapshot(
                        {
                            "last_trusted_displacement": np.asarray(
                                trusted_coordinates[-1:]
                            )
                            * displacement_scale,
                            "last_trusted_force": np.asarray(
                                trusted_forces[-1:]
                            )
                            * force_scale,
                            "last_trusted_relative_residual": np.asarray(
                                trusted_residuals[-1:]
                            ),
                            "failed_displacement": (
                                coordinate * displacement_scale
                            ),
                            "evaluation_displacement": np.asarray(
                                trusted_coordinates
                            )
                            * displacement_scale,
                            "evaluation_force": np.asarray(trusted_forces)
                            * force_scale,
                            "evaluation_relative_residual": np.asarray(
                                trusted_residuals
                            ),
                        },
                        {
                            "schema": "alb.equilibrium-failure.v0.4.1",
                            "stop_reason": "inner_exception",
                            "inner_converged": False,
                            "exception_type": type(exc).__name__,
                        },
                    ),
                ) from exc
            normalized_force = force / force_scale
            load_norm = float(np.linalg.norm(normalized_load))
            residual = (
                float(
                    np.linalg.norm(normalized_load + normalized_force)
                    / load_norm
                )
                if load_norm > 0.0
                else 0.0
            )
            trusted_coordinates.append(coordinate.copy())
            trusted_forces.append(normalized_force.copy())
            trusted_residuals.append(residual)
            return normalized_force, convergence.converged

        solver = EquilibriumSolver(
            stiffness=np.asarray(options.fallback_stiffness, dtype=float),
            max_iterations=options.max_iterations,
            tolerance=options.relative_tolerance,
            damping=options.damping,
            jacobian_step=options.jacobian_step,
            stall_patience=options.stall_patience,
            stall_relative_tolerance=options.stall_relative_tolerance,
        )
        outcome = solver.run(
            load=normalized_load,
            initial_coordinate=initial / displacement_scale,
            evaluate_force=evaluate_force,
            reset_iteration=reset_iteration,
        )
        values = self._equilibrium_values(
            outcome,
            displacement_scale=displacement_scale,
            force_scale=force_scale,
            load=target,
        )
        metadata = {
            "schema": "alb.equilibrium-result.v0.4.1",
            "success": outcome.converged,
            "evaluations": len(outcome.evaluations),
            "stop_reason": outcome.stop_reason,
            "inner_converged": outcome.inner_converged,
            "unit_system": self._bearing.config.unit_system,
        }
        if not outcome.converged:
            raise CalculationError(
                f"equilibrium solve failed: {outcome.stop_reason}",
                failure_snapshot=result_snapshot(values, metadata),
            )
        return AnalysisResult(
            values,
            metadata,
            convergence=ConvergenceStatus(
                residual=outcome.residual,
                converged=True,
                iterations=outcome.iterations,
                message=outcome.stop_reason,
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
        """Evaluate every sample of one explicit trajectory exactly once."""

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
                "sample_converged": np.asarray(
                    [item.converged for item in convergence],
                    dtype=bool,
                ),
                "sample_residual": np.asarray(
                    [item.residual for item in convergence],
                    dtype=float,
                ),
                "sample_iterations": np.asarray(
                    [
                        -1 if item.iterations is None else item.iterations
                        for item in convergence
                    ],
                    dtype=int,
                ),
            },
            {
                "schema": "alb.orbit-result.v0.4.1",
                "frequency_hz": float(frequency_hz),
                "direction": trajectory.direction,
                "phase": trajectory.phase,
                "orientation_rad": trajectory.orientation_rad,
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
        """Identify K and C on one coherent FFT grid.

        The public boundary validates grid coherence and the forward/reverse
        displacement matrix before invoking the established ``recognize_kc``
        equations. Valid inputs therefore retain the prior numerical method.
        """

        if not isinstance(trajectory, EllipseTrajectory):
            raise TypeError("trajectory must be EllipseTrajectory")
        grid = _validate_whirl_grid(time_grid, frequency_hz)
        validated_time = grid.time.tolist()
        forward = self.trace_orbit(
            trajectory.with_direction("forward"),
            validated_time,
            frequency_hz=grid.frequency_hz,
            spool=spool,
        )
        reverse = self.trace_orbit(
            trajectory.with_direction("reverse"),
            validated_time,
            frequency_hz=grid.frequency_hz,
            spool=spool,
        )
        if not forward.convergence.converged or not reverse.convergence.converged:
            raise CalculationError(
                "dynamic coefficient identification requires every orbit "
                "sample to converge",
                failure_snapshot=result_snapshot(
                    {
                        "forward": dict(forward.values),
                        "reverse": dict(reverse.values),
                    },
                    {
                        "schema": "alb.dynamic-coefficients-failure.v0.4.1",
                        "forward_converged": forward.convergence.converged,
                        "reverse_converged": reverse.convergence.converged,
                    },
                ),
            )
        time = np.asarray(forward.values["time"], dtype=float)
        forward_displacement = np.asarray(
            forward.values["displacement"],
            dtype=float,
        )
        reverse_displacement = np.asarray(
            reverse.values["displacement"],
            dtype=float,
        )
        forward_force = np.asarray(forward.values["force"], dtype=float)
        reverse_force = np.asarray(reverse.values["force"], dtype=float)
        from ALB.dynamics.identification import recognize_kc, recognize_z

        forward_amplitude = recognize_z(
            time,
            grid.frequency_hz,
            forward_displacement.T,
        )
        reverse_amplitude = recognize_z(
            time,
            grid.frequency_hz,
            reverse_displacement.T,
        )
        displacement_matrix = np.asarray(
            [forward_amplitude[1], reverse_amplitude[1]]
        ).T
        matrix_is_finite = bool(
            np.all(np.isfinite(displacement_matrix.real))
            and np.all(np.isfinite(displacement_matrix.imag))
        )
        try:
            rank = (
                int(np.linalg.matrix_rank(displacement_matrix))
                if matrix_is_finite
                else 0
            )
            condition = (
                float(np.linalg.cond(displacement_matrix))
                if matrix_is_finite
                else np.inf
            )
        except np.linalg.LinAlgError as exc:
            raise CalculationError(
                "dynamic coefficient displacement matrix diagnostics failed",
                failure_snapshot=result_snapshot(
                    {
                        "time": time,
                        "forward_displacement": forward_displacement,
                        "forward_velocity": forward.values["velocity"],
                        "forward_force": forward_force,
                        "reverse_displacement": reverse_displacement,
                        "reverse_velocity": reverse.values["velocity"],
                        "reverse_force": reverse_force,
                        "displacement_matrix_real": displacement_matrix.real,
                        "displacement_matrix_imag": displacement_matrix.imag,
                    },
                    {
                        "schema": (
                            "alb.dynamic-identification-failure.v0.4.2"
                        ),
                        "failure_phase": "matrix_diagnostics",
                        "requested_frequency_hz": grid.frequency_hz,
                        "selected_frequency_hz": (
                            grid.selected_frequency_hz
                        ),
                        "nyquist_hz": grid.nyquist_hz,
                        "exception_type": type(exc).__name__,
                    },
                ),
            ) from exc
        if (
            not matrix_is_finite
            or rank < 2
            or not np.isfinite(condition)
            or condition > _MAX_DISPLACEMENT_CONDITION
        ):
            raise CalculationError(
                "dynamic coefficient displacement matrix is singular or "
                "ill-conditioned",
                failure_snapshot=result_snapshot(
                    {
                        "time": time,
                        "forward_displacement": forward_displacement,
                        "forward_velocity": forward.values["velocity"],
                        "forward_force": forward_force,
                        "reverse_displacement": reverse_displacement,
                        "reverse_velocity": reverse.values["velocity"],
                        "reverse_force": reverse_force,
                        "displacement_matrix_real": displacement_matrix.real,
                        "displacement_matrix_imag": displacement_matrix.imag,
                    },
                    {
                        "schema": (
                            "alb.dynamic-identification-failure.v0.4.2"
                        ),
                        "failure_phase": "matrix_validation",
                        "requested_frequency_hz": grid.frequency_hz,
                        "selected_frequency_hz": (
                            grid.selected_frequency_hz
                        ),
                        "nyquist_hz": grid.nyquist_hz,
                        "displacement_rank": rank,
                        "displacement_condition_number": condition,
                        "maximum_condition_number": (
                            _MAX_DISPLACEMENT_CONDITION
                        ),
                    },
                ),
            )

        try:
            identified = recognize_kc(
                time,
                grid.frequency_hz,
                forward_displacement.T,
                -forward_force.T,
                reverse_displacement.T,
                -reverse_force.T,
            )
        except (FloatingPointError, np.linalg.LinAlgError, ValueError) as exc:
            raise CalculationError(
                "dynamic coefficient matrix inversion failed",
                failure_snapshot=result_snapshot(
                    {
                        "time": time,
                        "forward_displacement": forward_displacement,
                        "forward_force": forward_force,
                        "reverse_displacement": reverse_displacement,
                        "reverse_force": reverse_force,
                        "displacement_matrix_real": displacement_matrix.real,
                        "displacement_matrix_imag": displacement_matrix.imag,
                    },
                    {
                        "schema": (
                            "alb.dynamic-identification-failure.v0.4.2"
                        ),
                        "failure_phase": "matrix_inversion",
                        "requested_frequency_hz": grid.frequency_hz,
                        "selected_frequency_hz": (
                            grid.selected_frequency_hz
                        ),
                        "nyquist_hz": grid.nyquist_hz,
                        "displacement_rank": rank,
                        "displacement_condition_number": condition,
                        "exception_type": type(exc).__name__,
                    },
                ),
            ) from exc
        primary = forward if trajectory.direction == "forward" else reverse
        iterations = [
            item
            for item in (
                forward.convergence.iterations,
                reverse.convergence.iterations,
            )
            if item is not None
        ]
        return AnalysisResult(
            {
                **dict(primary.values),
                "forward_time": forward.values["time"],
                "forward_displacement": forward_displacement,
                "forward_velocity": forward.values["velocity"],
                "forward_force": forward_force,
                "forward_converged": forward.values["sample_converged"],
                "forward_residual": forward.values["sample_residual"],
                "forward_iterations": forward.values["sample_iterations"],
                "reverse_time": reverse.values["time"],
                "reverse_displacement": reverse_displacement,
                "reverse_velocity": reverse.values["velocity"],
                "reverse_force": reverse_force,
                "reverse_converged": reverse.values["sample_converged"],
                "reverse_residual": reverse.values["sample_residual"],
                "reverse_iterations": reverse.values["sample_iterations"],
                "transfer_real": np.asarray(identified["h"].real),
                "transfer_imag": np.asarray(identified["h"].imag),
                "stiffness": np.asarray(identified["k"]),
                "damping": np.asarray(identified["c"]),
            },
            {
                **dict(primary.metadata),
                "schema": "alb.dynamic-coefficients-result.v0.4.1",
                "method": "forward_reverse_whirl_fft",
            },
            convergence=ConvergenceStatus(
                residual=max(
                    forward.convergence.residual,
                    reverse.convergence.residual,
                ),
                converged=True,
                iterations=sum(iterations) if iterations else None,
                message="forward and reverse whirl samples converged",
            ),
        )

    def harmonic_linearize(
        self,
        operating_point: object,
        excitation_frequency: float,
        *,
        spool: object | None = None,
    ) -> AnalysisResult:
        """Linearize with the established pressure-equation derivative method."""

        config = self._bearing.config
        if config.unit_system != "dimensional" or config.family not in {
            "active_lubricated",
            "liquid_film",
        }:
            raise CalculationError(
                "harmonic_linearize supports only verified dimensional "
                "liquid_film and active_lubricated bearings"
            )
        if config.spec.get("thermal") is not None:
            raise CalculationError(
                "harmonic_linearize does not support an enabled thermal wrapper"
            )
        frequency = _positive_float(
            excitation_frequency,
            "excitation_frequency",
        )
        point = _axis_pair(operating_point, "operating_point")
        spool_value = None if spool is None else _axis_pair(spool, "spool")
        runtime = self._new_runtime()
        force, convergence = self._run_runtime(
            runtime,
            displacement=point,
            time=0.0,
            spool=spool_value,
            static=config.family == "active_lubricated",
        )
        if not convergence.converged:
            raise CalculationError(
                "harmonic linearization requires a converged static point",
                failure_snapshot=runtime.result_snapshot(),
            )

        values: dict[str, Any] = {
            "operating_point": point,
            "static_force": force,
        }
        if config.family == "liquid_film":
            try:
                stiffness, damping = linearize_film_runtime(runtime)
            except Exception as exc:
                raise CalculationError(
                    f"liquid-film harmonic linearization failed: {exc}",
                    failure_snapshot=runtime.result_snapshot(),
                ) from exc
        else:
            pads = tuple(runtime._pads)
            try:
                (
                    stiffness,
                    damping,
                    spool_jacobian,
                    pad_stiffness,
                    pad_damping,
                ) = aggregate_active_linearization(pads)
            except (TypeError, ValueError, np.linalg.LinAlgError) as exc:
                raise CalculationError(
                    f"active harmonic linearization is unsupported: {exc}",
                    failure_snapshot=runtime.result_snapshot(),
                ) from exc
            base_spool = np.asarray(
                (
                    spool_value
                    if config.control_mode == "external_spool"
                    else [valve.xv for valve in runtime.static_sv]
                ),
                dtype=float,
            )
            if not np.all(np.isfinite(spool_jacobian)):
                raise CalculationError(
                    "active harmonic linearization produced a non-finite "
                    "spool Jacobian",
                    failure_snapshot=runtime.result_snapshot(),
                )
            values.update(
                {
                    "base_spool": base_spool,
                    "spool_jacobian": spool_jacobian,
                    "pad_stiffness": pad_stiffness,
                    "pad_damping": pad_damping,
                }
            )
        if not np.all(np.isfinite(stiffness)) or not np.all(
            np.isfinite(damping)
        ):
            raise CalculationError(
                "harmonic linearization produced non-finite coefficients",
                failure_snapshot=runtime.result_snapshot(),
            )
        omega = 2.0 * np.pi * frequency
        values.update(
            {
                "stiffness": stiffness,
                "damping": damping,
                "dynamic_stiffness_real": stiffness,
                "dynamic_stiffness_imag": omega * damping,
            }
        )
        return AnalysisResult(
            values,
            {
                "schema": "alb.harmonic-linearization-result.v0.4.1",
                "method": "pressure_equation_derivative",
                "excitation_frequency": frequency,
                "force_convention": "delta_f=-(K+i*omega*C)*delta_u",
                "unit_system": config.unit_system,
            },
            convergence=convergence,
        )


__all__ = [
    "BearingAnalysis",
    "EllipseTrajectory",
    "EquilibriumOptions",
]
