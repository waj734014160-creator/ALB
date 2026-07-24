"""Internal equation-derived harmonic bearing runtime."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np

from ALB.config import Moog2ndServoConfig, PIDConfig
from ALB.control.blocks import run_controller_step, run_valve_step
from ALB.control.pid import PID
from ALB.core import LifecycleState, RuntimeLifecycle
from ALB.core.diagnostics import sanitize_exception_message
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    ControllerProtocol,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.control.valve import moog_2nd_servovalve

from ._harmonic_runtime import (
    HarmonicForceEvaluator,
    RuntimeFailureGuard,
    finite_real_array,
    finite_real_scalar,
)
from .harmonic_coefficients import (
    ALBHarmonicCoefficients,
    finite_vector,
    load_builtin_alb_harmonic_coefficients,
    load_builtin_payload,
    positive_float,
)


class _HarmonicBearingRuntime:
    r"""Standard bearing-interface wrapper for harmonic linear ALB coefficients.

    The returned force follows

    ``F = F0 - K dx - C xdot + Re(G_xv) dxv + Im(G_xv) qv``.

    ``qv`` is :math:`\dot{x}_v/\Omega_w` reconstructed by the exact sampled
    single-frequency identity

    ``qv[k] = (dxv[k] cos(Omega_w dt) - dxv[k-1]) / sin(Omega_w dt)``.

    This is a phase relation, not a finite-difference coefficient estimate.
    Consequently, the wrapper is a narrowband local model around the stored
    whirl frequency.  Broadband transients require a frequency-dependent or
    state-space fluid model.
    """

    input_dto_type = BearingInput

    unit_system = UnitSystem.DIMENSIONAL

    def __init__(
        self,
        coefficients: ALBHarmonicCoefficients,
        *,
        node_link: int,
        servo_config: Moog2ndServoConfig,
        controller_config: PIDConfig | None = None,
        warmup_steps: int = 64,
        base_tolerance: float = 1.0e-8,
    ) -> None:
        """Create a rotor-couplable harmonic linear bearing.

        Parameters
        ----------
        coefficients:
            Equation-derived local force coefficients and strict base state.
        node_link:
            Rotor node consumed by the owning simulation.
        controller_config:
            Project PID configuration. ``ki`` must be zero for the PD base.
            Required controller configuration.
        servo_config:
            Project second-order Moog configuration.
        warmup_steps:
            Constant-base steps used to settle controller and valve states.
        base_tolerance:
            Maximum accepted absolute spool error after warm-up.
        """

        if not isinstance(coefficients, ALBHarmonicCoefficients):
            raise TypeError("coefficients must be ALBHarmonicCoefficients")
        if isinstance(node_link, bool) or not isinstance(node_link, (int, np.integer)):
            raise TypeError("node_link must be an integer")
        if not isinstance(servo_config, Moog2ndServoConfig):
            raise TypeError("servo_config must be Moog2ndServoConfig")
        if not isinstance(controller_config, PIDConfig):
            raise TypeError("controller_config must be PIDConfig")
        if int(warmup_steps) < 2:
            raise ValueError("warmup_steps must be >= 2")

        super().__init__()
        self.coefficients = coefficients
        self.node_link = int(node_link)
        self.controller_config = copy.deepcopy(controller_config)
        self.servo_config = copy.deepcopy(servo_config)
        self.warmup_steps = int(warmup_steps)
        self.base_tolerance = positive_float("base_tolerance", base_tolerance)
        self.dt = positive_float("servo_config.dt", servo_config.dt)
        if not np.isclose(self.dt, float(servo_config.dt), rtol=0.0, atol=1.0e-15):
            raise ValueError("controller and servovalve dt values must match")
        if not np.isclose(
            float(controller_config.dt), self.dt, rtol=0.0, atol=1.0e-15
        ):
            raise ValueError("controller and servovalve dt values must match")
        if not np.isclose(
            float(controller_config.freq),
            coefficients.shaft_frequency_hz,
            rtol=0.0,
            atol=1.0e-12,
        ):
            raise ValueError(
                "controller frequency must match coefficient shaft frequency"
            )
        if not np.isclose(
            float(controller_config.ki), 0.0, rtol=0.0, atol=0.0
        ):
            raise ValueError("harmonic runtime requires a PD controller with ki=0")

        self.phase_step = coefficients.whirl_omega_rad_s * self.dt
        if not 0.0 < self.phase_step < np.pi:
            raise ValueError("dt must provide more than two samples per whirl cycle")
        self._phase_sine = float(np.sin(self.phase_step))
        self._phase_cosine = float(np.cos(self.phase_step))
        if abs(self._phase_sine) < 1.0e-10:
            raise ValueError("harmonic phase step is singular for quadrature recovery")

        self._force_evaluator = HarmonicForceEvaluator(
            coefficients.static_force,
            coefficients.stiffness,
            coefficients.damping,
            coefficients.spool_transfer,
        )

        self._controller: Any | None = None
        self._servovalves: list = []
        self.static_force = coefficients.static_force.copy()
        self.uxy0 = coefficients.equilibrium_position.copy()
        self.xv0 = coefficients.base_spool.copy()
        self.force = coefficients.static_force.copy()
        self.uxy = coefficients.equilibrium_position.copy()
        self.uxyt = np.zeros(2, dtype=float)
        self.spool_command = coefficients.base_spool.copy()
        self.spool = coefficients.base_spool.copy()
        self.spool_quadrature = np.zeros(2, dtype=float)
        self.controller_saturated = False
        self.servovalve_saturated = False
        self.warmup_audit: dict[str, Any] = {}
        self._force_stiffness = np.zeros(2, dtype=float)
        self._force_damping = np.zeros(2, dtype=float)
        self._force_spool = np.zeros(2, dtype=float)
        self._previous_delta_spool = np.zeros(2, dtype=float)
        self._last_time: float | None = None
        self._last_input: tuple[np.ndarray, np.ndarray] | None = None
        self._pending_input: BearingInput | None = None
        self._has_input = False
        self._lifecycle = RuntimeLifecycle(
            "harmonic bearing", input_label="bearing input"
        )
        self._last_output: BearingOutput | None = None
        self._latest_result: ResultBundle | None = None
        self._failure: ResultBundle | None = None
        self._convergence_status = ConvergenceStatus.pending(
            "runtime is not initialized"
        )
        self._runtime_guard = RuntimeFailureGuard(self._invalidate_runtime)
        self._reset_for_owner()

    @property
    def K(self) -> np.ndarray:
        """Return a copy of the dimensional stiffness matrix."""

        return self.coefficients.stiffness.copy()

    @property
    def C(self) -> np.ndarray:
        """Return a copy of the dimensional damping matrix."""

        return self.coefficients.damping.copy()

    @property
    def G_xv(self) -> np.ndarray:
        """Return a copy of the complex normalized-spool force transfer."""

        return self.coefficients.spool_transfer.copy()

    @property
    def xv(self) -> np.ndarray:
        """Return the current normalized spool state."""

        self._require_valid("read xv")
        return self.spool.copy()

    @property
    def t(self) -> float | None:
        """Return the latest public coupling timestamp."""

        self._require_valid("read t")
        return self._last_time

    def _require_valid(self, operation: str) -> None:
        """Reject state access after a failed runtime initialization."""

        if not self._lifecycle.is_valid:
            raise RuntimeError(
                f"Cannot {operation}: harmonic bearing runtime is invalid; "
                "rebuild it or let its owner reinitialize it before reuse"
            )

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the shared harmonic runtime state."""

        return self._lifecycle.state

    def _reset_public_state(self) -> None:
        """Reset public snapshots to a deterministic non-computed base state."""

        self.force = self.coefficients.static_force.copy()
        self.uxy = self.coefficients.equilibrium_position.copy()
        self.uxyt = np.zeros(2, dtype=float)
        self.spool_command = self.coefficients.base_spool.copy()
        self.spool = self.coefficients.base_spool.copy()
        self.spool_quadrature = np.zeros(2, dtype=float)
        self.controller_saturated = False
        self.servovalve_saturated = False
        self.warmup_audit = {}
        self._force_stiffness = np.zeros(2, dtype=float)
        self._force_damping = np.zeros(2, dtype=float)
        self._force_spool = np.zeros(2, dtype=float)
        self._previous_delta_spool = np.zeros(2, dtype=float)
        self._last_time = None
        self._last_input = None
        self._pending_input = None
        self._has_input = False
        self._last_output = None
        self._latest_result = None

    def _invalidate_runtime(self) -> None:
        """Discard a partial controller/valve runtime and block state access."""

        self._lifecycle.fail()
        self._controller = None
        self._servovalves = []
        self._reset_public_state()

    def _sensor_matrix(self) -> np.ndarray:
        """Return the project two-channel controller sensor projection."""

        angles = np.deg2rad(
            np.asarray(self.controller_config.sensor_angles, dtype=float)
        )
        if angles.shape != (2,):
            raise ValueError("controller sensor_angles must contain two values")
        return np.column_stack((np.cos(angles), np.sin(angles)))

    @staticmethod
    def _validate_controller(controller: Any) -> None:
        """Validate the minimum controller integration contract."""

        for method_name in ("input", "output"):
            if not callable(getattr(controller, method_name, None)):
                raise TypeError(f"controller must provide {method_name}()")

    def _build_runtime(self) -> None:
        """Create or reset controller and valve instances deterministically."""

        controller = PID(copy.deepcopy(self.controller_config))
        self._validate_controller(controller)
        if not isinstance(controller, ControllerProtocol):
            raise TypeError("controller must satisfy ControllerProtocol")
        controller_dt = getattr(controller, "dt", None)
        if controller_dt is not None and not np.isclose(
            float(controller_dt), self.dt, rtol=0.0, atol=1.0e-15
        ):
            raise ValueError("controller and servovalve dt values must match")
        controller_freq = getattr(controller, "freq", None)
        if controller_freq is not None and not np.isclose(
            float(controller_freq),
            self.coefficients.shaft_frequency_hz,
            rtol=0.0,
            atol=1.0e-12,
        ):
            raise ValueError("controller frequency must match coefficient shaft frequency")
        controller._reset_for_owner()
        self._controller = controller
        self._servovalves = [
            moog_2nd_servovalve(
                self.dt,
                delay=float(self.servo_config.delay),
                tw=float(self.servo_config.tw),
                zeta=float(self.servo_config.zeta),
            )
            for _ in range(2)
        ]
        for valve in self._servovalves:
            valve._reset_for_owner()

    @staticmethod
    def _scalar_output(value: Any) -> float:
        """Convert a finite scalar-like servovalve output to float."""

        return finite_real_scalar("servovalve output", value)

    def _advance_control(self, time_s: float, uxy: np.ndarray) -> None:
        """Advance the injected controller and two second-order Moog valves."""

        assert self._controller is not None
        with np.errstate(over="raise", invalid="raise"):
            normalized_position = uxy / self.coefficients.clearance_m
        normalized_position = finite_vector(
            "normalized controller input", normalized_position
        )
        command = finite_real_array(
            "controller command",
            run_controller_step(
                self._controller,
                time_s,
                normalized_position,
            ),
            shape=(2,),
        )
        spool = np.zeros(2, dtype=float)
        for axis, valve in enumerate(self._servovalves):
            spool[axis] = self._scalar_output(
                run_valve_step(valve, time_s, command[axis])
            )
        self.spool_command = command
        self.spool = spool
        self.controller_saturated = bool(
            np.any(np.abs(command) >= 1.0 - 1.0e-12)
        )
        self.servovalve_saturated = bool(
            np.any(np.abs(spool) >= 1.0 - 1.0e-12)
        )

    def _warm_strict_base(self) -> None:
        """Settle controller and valve states at the coefficient base."""

        base_position = self.coefficients.equilibrium_position
        expected_command = self.coefficients.base_spool.copy()
        expected_command = float(self.controller_config.kp) * (
            self._sensor_matrix()
            @ (base_position / self.coefficients.clearance_m)
        )
        if not np.allclose(
            expected_command,
            self.coefficients.base_spool,
            rtol=0.0,
            atol=1.0e-12,
        ):
            raise ValueError(
                "PD static command does not match the coefficient base spool"
            )
        for step in range(self.warmup_steps):
            time_s = -(self.warmup_steps - step) * self.dt
            self._advance_control(time_s, base_position)
        if not np.allclose(
            self.spool_command,
            self.coefficients.base_spool,
            rtol=0.0,
            atol=self.base_tolerance,
        ):
            raise RuntimeError(
                "Controller warm-up did not reach the coefficient base command"
            )
        error = self.spool - self.coefficients.base_spool
        if not np.allclose(
            self.spool,
            self.coefficients.base_spool,
            rtol=0.0,
            atol=self.base_tolerance,
        ):
            raise RuntimeError(
                "Servovalve warm-up did not reach the coefficient base spool"
            )
        self.warmup_audit = {
            "expected_command": expected_command.copy(),
            "actual_command": self.spool_command.copy(),
            "base_spool": self.coefficients.base_spool.copy(),
            "actual_spool": self.spool.copy(),
            "spool_error": error.copy(),
            "steps": self.warmup_steps,
            "duration_s": self.warmup_steps * self.dt,
        }

    def _reset_for_owner(self) -> None:
        """Reset the runtime when requested by its owning analysis."""

        self._invalidate_runtime()
        try:
            self._build_runtime()
            self._warm_strict_base()
            self.force = self.coefficients.static_force.copy()
            self.uxy = self.coefficients.equilibrium_position.copy()
            self.uxyt = np.zeros(2, dtype=float)
            self.spool_quadrature = np.zeros(2, dtype=float)
            self._force_stiffness = np.zeros(2, dtype=float)
            self._force_damping = np.zeros(2, dtype=float)
            self._force_spool = np.zeros(2, dtype=float)
            self._previous_delta_spool = self.spool - self.coefficients.base_spool
            self._last_time = None
            self._last_input = None
            self._pending_input = None
            self._has_input = False
        except Exception as exc:
            self._failure = self._build_failure_snapshot(exc, "reset")
            self._invalidate_runtime()
            raise
        self._failure = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.reset()

    def input(self, dto: BearingInput) -> None:
        """Validate and latch one dimensional sample without advancing control."""

        self._require_valid("accept input")
        self._lifecycle.require_input_slot()
        if not isinstance(dto, BearingInput):
            raise TypeError("harmonic bearing input must be BearingInput")
        if dto.unit_system is not UnitSystem.DIMENSIONAL:
            raise ValueError("harmonic runtime requires dimensional input")
        if self._last_time is not None:
            elapsed = dto.time - self._last_time
            tolerance = max(1.0e-12, 1.0e-9 * self.dt)
            if not np.isclose(elapsed, self.dt, rtol=0.0, atol=tolerance):
                raise ValueError(
                    "Bearing input time step does not match configured dt"
                )
        self._pending_input = dto
        self._last_output = None
        self._latest_result = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.latch()

    def evaluate(self) -> None:
        """Advance control and evaluate harmonic force exactly once."""

        self._require_valid("evaluate input")
        assert self._pending_input is not None
        dto = self._pending_input
        try:
            with self._runtime_guard.phase(), self._lifecycle.evaluation():
                position = dto.displacement
                velocity = dto.velocity
                time_s = dto.time
                self._advance_control(time_s, position)
                delta_spool = self.spool - self.coefficients.base_spool
                with np.errstate(over="raise", invalid="raise"):
                    spool_quadrature = (
                        delta_spool * self._phase_cosine
                        - self._previous_delta_spool
                    ) / self._phase_sine
                spool_quadrature = finite_real_array(
                    "servovalve quadrature",
                    spool_quadrature,
                    shape=(2,),
                )
                delta_position = (
                    position - self.coefficients.equilibrium_position
                )
                evaluated = self._force_evaluator.evaluate(
                    delta_position,
                    velocity,
                    delta_spool,
                    spool_quadrature,
                )
                output = BearingOutput(
                    evaluated.total,
                    time_s,
                    UnitSystem.DIMENSIONAL,
                )
                self.spool_quadrature = spool_quadrature
                self._previous_delta_spool = delta_spool.copy()
                self.uxy = position
                self.uxyt = velocity
                self._last_time = time_s
                self._last_input = (position.copy(), velocity.copy())
                self._has_input = True
                self._force_stiffness = evaluated.stiffness
                self._force_damping = evaluated.damping
                self._force_spool = evaluated.spool
                self.force = evaluated.total
                self._last_output = output
                self._latest_result = result_snapshot(
                    {
                        "force": output.force,
                        "friction": 0.0,
                        "force_stiffness": self._force_stiffness,
                        "force_damping": self._force_damping,
                        "force_spool": self._force_spool,
                        "spool": self.spool,
                        "spool_command": self.spool_command,
                    },
                    {
                        "schema": "alb.harmonic-bearing-result.v1",
                        "time": time_s,
                        "unit_system": UnitSystem.DIMENSIONAL.value,
                        "converged": True,
                    },
                )
                self._convergence_status = ConvergenceStatus(
                    0.0,
                    True,
                    message="harmonic evaluation completed",
                )
                self._pending_input = None
        except BaseException as exc:
            self._failure = self._build_failure_snapshot(exc, "evaluate")
            raise

    def output(self) -> BearingOutput:
        """Read the completed harmonic force without numerical work."""

        self._require_valid("read output")
        self._lifecycle.require_output()
        assert self._last_output is not None
        return self._last_output

    def step(self, dto: BearingInput) -> BearingOutput:
        """Compose input, evaluate, and output without committing a step."""

        self.input(dto)
        self.evaluate()
        return self.output()

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return cached harmonic convergence without computation."""

        return self._convergence_status

    def result_snapshot(self) -> ResultBundle:
        """Return the complete immutable harmonic result."""

        self._require_valid("read result")
        self._lifecycle.require_output()
        assert self._latest_result is not None
        return self._latest_result

    def _build_failure_snapshot(
        self,
        error: BaseException,
        phase: str,
    ) -> ResultBundle:
        return result_snapshot(
            {},
            {
                "schema": "alb.harmonic-bearing-failure.v1",
                "phase": phase,
                "error_type": type(error).__name__,
                "message": sanitize_exception_message(error),
                "unit_system": UnitSystem.DIMENSIONAL.value,
                "node_link": self.node_link,
            },
        )

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest sealed harmonic failure."""

        if self._failure is None:
            raise RuntimeError("no harmonic runtime failure is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable harmonic lifecycle diagnostics."""

        return result_snapshot(
            {},
            {
                "schema": "alb.harmonic-bearing-diagnostic.v1",
                "lifecycle_state": self.lifecycle_state.value,
                "unit_system": UnitSystem.DIMENSIONAL.value,
                "node_link": self.node_link,
                "converged": self._convergence_status.converged,
                "has_result": self._latest_result is not None,
                "has_failure": self._failure is not None,
            },
        )

def _build_harmonic_runtime(
    node_link: int,
    *,
    dt: float | None = None,
    warmup_steps: int | None = None,
) -> _HarmonicBearingRuntime:
    """Build the packaged documented harmonic-linear ALB bearing.

    The default artifact is the strict-base, thermal-inertia, gamma=1, 50 Hz
    equation result documented in ``docs/formula/alb_harmonic_linearization.md``.
    ``dt`` may be changed for a rotor time grid, subject to the narrowband
    sampling guard enforced by the internal runtime.
    """

    payload = load_builtin_payload()
    coefficients = ALBHarmonicCoefficients.from_dict(payload)
    runtime = payload["recommended_runtime"]
    runtime_dt = float(runtime["dt_s"] if dt is None else dt)
    controller_payload = runtime["controller"]
    servo_payload = runtime["servovalve"]
    controller_config = PIDConfig(
        dt=runtime_dt,
        kp=float(controller_payload["kp"]),
        ki=float(controller_payload["ki"]),
        kd=float(controller_payload["kd"]),
        freq=float(controller_payload["frequency_hz"]),
        sensor_angles=np.asarray(
            controller_payload["sensor_angles_deg"], dtype=float
        ),
    )
    servo_config = Moog2ndServoConfig(
        dt=runtime_dt,
        tw=float(servo_payload["tw_s"]),
        zeta=float(servo_payload["zeta"]),
        delay=float(servo_payload.get("delay_s", 0.0)),
    )
    steps = int(
        runtime["warmup_steps"] if warmup_steps is None else warmup_steps
    )
    return _HarmonicBearingRuntime(
        coefficients,
        node_link=node_link,
        servo_config=servo_config,
        controller_config=controller_config,
        warmup_steps=steps,
    )
