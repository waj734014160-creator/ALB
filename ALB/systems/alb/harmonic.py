"""Equation-derived harmonic linear ALB bearing for rotor coupling.

The model exposes the standard dimensional bearing interface used by
``RsRotorBearingCouple``.  Its K, C, and complex spool-force transfer are
loaded from an equation-linearization result; no trajectory differencing or
coefficient identification is performed at runtime.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from ALB.config import Moog2ndServoConfig, PIDConfig
from ALB.control.blocks import run_controller_step
from ALB.control.pid import PID
from ALB.core import BearingComponentBase
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode
from ALB.control.valve import moog_2nd_servovalve

from ._harmonic_runtime import RuntimeFailureGuard


BUILTIN_COEFFICIENT_RESOURCE = "data/alb_harmonic_linear_gamma1_50hz.json"


def _finite_vector(name: str, value: Any) -> np.ndarray:
    """Return a copied finite two-component float vector."""

    vector = np.asarray(value, dtype=float)
    if vector.shape != (2,):
        raise ValueError(f"{name} must have shape (2,)")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must contain only finite values")
    return vector.copy()


def _finite_matrix(name: str, value: Any, *, complex_values: bool) -> np.ndarray:
    """Return a copied finite 2 x 2 coefficient matrix."""

    dtype = complex if complex_values else float
    matrix = np.asarray(value, dtype=dtype)
    if matrix.shape != (2, 2):
        raise ValueError(f"{name} must have shape (2, 2)")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name} must contain only finite values")
    return matrix.copy()


def _positive_float(name: str, value: Any) -> float:
    """Return a finite positive scalar."""

    scalar = float(value)
    if not np.isfinite(scalar) or scalar <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")
    return scalar


def _complex_matrix_from_payload(name: str, payload: Mapping[str, Any]) -> np.ndarray:
    """Decode a complex matrix stored as separate real and imaginary arrays."""

    if not isinstance(payload, Mapping) or "real" not in payload or "imag" not in payload:
        raise ValueError(f"{name} must contain real and imag arrays")
    matrix = np.asarray(payload["real"], dtype=float) + 1j * np.asarray(
        payload["imag"], dtype=float
    )
    return _finite_matrix(name, matrix, complex_values=True)


@dataclass(frozen=True)
class ALBHarmonicCoefficients:
    r"""Dimensional local ALB coefficients at one strict harmonic base state.

    ``spool_transfer`` is the complex matrix
    :math:`G_{x_v}(\Omega_w)` in newtons per normalized spool displacement.
    The matrices are equation-derived inputs; this class only validates and
    stores them.
    """

    name: str
    static_force: np.ndarray
    stiffness: np.ndarray
    damping: np.ndarray
    spool_transfer: np.ndarray
    equilibrium_position: np.ndarray
    base_spool: np.ndarray
    clearance_m: float
    shaft_frequency_hz: float
    whirl_ratio: float
    source: str = ""

    def __post_init__(self) -> None:
        """Normalize arrays and reject incomplete coefficient contracts."""

        if not str(self.name).strip():
            raise ValueError("name must be non-empty")
        object.__setattr__(
            self, "static_force", _finite_vector("static_force", self.static_force)
        )
        object.__setattr__(
            self,
            "stiffness",
            _finite_matrix("stiffness", self.stiffness, complex_values=False),
        )
        object.__setattr__(
            self,
            "damping",
            _finite_matrix("damping", self.damping, complex_values=False),
        )
        object.__setattr__(
            self,
            "spool_transfer",
            _finite_matrix(
                "spool_transfer", self.spool_transfer, complex_values=True
            ),
        )
        object.__setattr__(
            self,
            "equilibrium_position",
            _finite_vector("equilibrium_position", self.equilibrium_position),
        )
        object.__setattr__(
            self, "base_spool", _finite_vector("base_spool", self.base_spool)
        )
        object.__setattr__(
            self, "clearance_m", _positive_float("clearance_m", self.clearance_m)
        )
        object.__setattr__(
            self,
            "shaft_frequency_hz",
            _positive_float("shaft_frequency_hz", self.shaft_frequency_hz),
        )
        whirl_ratio = float(self.whirl_ratio)
        if not np.isfinite(whirl_ratio) or whirl_ratio <= 0.0:
            raise ValueError("whirl_ratio must be finite and > 0")
        object.__setattr__(self, "whirl_ratio", whirl_ratio)
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "source", str(self.source))

    @property
    def whirl_frequency_hz(self) -> float:
        """Return the coefficient whirl frequency in hertz."""

        return self.whirl_ratio * self.shaft_frequency_hz

    @property
    def whirl_omega_rad_s(self) -> float:
        """Return the coefficient whirl angular frequency in radians per second."""

        return 2.0 * np.pi * self.whirl_frequency_hz

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ALBHarmonicCoefficients":
        """Load the stable ``alb.harmonic-linear.v1`` data contract."""

        if payload.get("schema") != "alb.harmonic-linear.v1":
            raise ValueError("Unsupported harmonic-linear coefficient schema")
        linearization = payload.get("linearization")
        if not isinstance(linearization, Mapping):
            raise ValueError("linearization must be an object")
        spool_transfer = _complex_matrix_from_payload(
            "G_xv_N_per_nondim",
            linearization["G_xv_N_per_nondim"],
        )
        return cls(
            name=str(payload["name"]),
            static_force=linearization["static_force_N"],
            stiffness=linearization["K_N_per_m"],
            damping=linearization["C_N_s_per_m"],
            spool_transfer=spool_transfer,
            equilibrium_position=linearization["equilibrium_position_m"],
            base_spool=linearization["base_spool_nondim"],
            clearance_m=linearization["clearance_m"],
            shaft_frequency_hz=linearization["shaft_frequency_hz"],
            whirl_ratio=linearization["whirl_ratio"],
            source=str(payload.get("coefficient_source", "")),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "ALBHarmonicCoefficients":
        """Load coefficients from a UTF-8 JSON file."""

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible coefficient representation."""

        return {
            "name": self.name,
            "source": self.source,
            "static_force_N": self.static_force.tolist(),
            "K_N_per_m": self.stiffness.tolist(),
            "C_N_s_per_m": self.damping.tolist(),
            "G_xv_N_per_nondim": {
                "real": self.spool_transfer.real.tolist(),
                "imag": self.spool_transfer.imag.tolist(),
            },
            "equilibrium_position_m": self.equilibrium_position.tolist(),
            "base_spool_nondim": self.base_spool.tolist(),
            "clearance_m": self.clearance_m,
            "shaft_frequency_hz": self.shaft_frequency_hz,
            "whirl_ratio": self.whirl_ratio,
            "whirl_frequency_hz": self.whirl_frequency_hz,
        }


def _load_builtin_payload() -> dict[str, Any]:
    """Load the packaged documented coefficient and runtime contract."""

    resource = resources.files("ALB.systems.alb").joinpath(
        BUILTIN_COEFFICIENT_RESOURCE
    )
    with resource.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def load_builtin_alb_harmonic_coefficients() -> ALBHarmonicCoefficients:
    """Return the packaged equation-derived 50 Hz, gamma=1 coefficient set."""

    return ALBHarmonicCoefficients.from_dict(_load_builtin_payload())


class ALBHarmonicLinear(BearingComponentBase):
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

    _RESULT_COLUMNS = [
        "t",
        "ux",
        "uy",
        "uxt",
        "uyt",
        "controller_u_x",
        "controller_u_y",
        "xv_x",
        "xv_y",
        "xv_quadrature_x",
        "xv_quadrature_y",
        "fk_x",
        "fk_y",
        "fc_x",
        "fc_y",
        "fxv_x",
        "fxv_y",
        "fx",
        "fy",
        "controller_saturated",
        "servovalve_saturated",
    ]

    def __init__(
        self,
        coefficients: ALBHarmonicCoefficients,
        *,
        node_link: int,
        servo_config: Moog2ndServoConfig,
        controller_config: PIDConfig | None = None,
        controller: Any | None = None,
        controller_factory: Callable[[], Any] | None = None,
        warmup_steps: int = 64,
        base_tolerance: float = 1.0e-8,
    ) -> None:
        """Create a rotor-couplable harmonic linear bearing.

        Parameters
        ----------
        coefficients:
            Equation-derived local force coefficients and strict base state.
        node_link:
            ROSS rotor node consumed by :class:`RsRotorBearingCouple`.
        controller_config:
            Project PID configuration. ``ki`` must be zero for the PD base.
            Supply exactly one of ``controller_config``, ``controller``, or
            ``controller_factory``.
        controller:
            Resettable controller instance. Its ``init()`` method is called on
            every bearing initialization.
        controller_factory:
            Factory used to create a fresh strict or legacy controller on
            every bearing initialization. This is the compatibility path for
            legacy controllers that do not expose ``init()``.
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
        controller_source_count = sum(
            source is not None
            for source in (controller_config, controller, controller_factory)
        )
        if controller_source_count != 1:
            raise ValueError(
                "provide exactly one of controller_config, controller, or "
                "controller_factory"
            )
        if controller_config is not None and not isinstance(
            controller_config, PIDConfig
        ):
            raise TypeError("controller_config must be PIDConfig or None")
        if controller_factory is not None and not callable(controller_factory):
            raise TypeError("controller_factory must be callable")
        if controller is not None:
            self._validate_controller(controller)
            if not callable(getattr(controller, "init", None)):
                raise TypeError(
                    "controller instances must provide init(); use "
                    "controller_factory for controllers without reset support"
                )
        if int(warmup_steps) < 2:
            raise ValueError("warmup_steps must be >= 2")

        super().__init__()
        self.coefficients = coefficients
        self.node_link = int(node_link)
        self.controller_config = (
            copy.deepcopy(controller_config) if controller_config is not None else None
        )
        self._controller_instance = controller
        self._controller_factory = controller_factory
        self.servo_config = copy.deepcopy(servo_config)
        self.warmup_steps = int(warmup_steps)
        self.base_tolerance = _positive_float("base_tolerance", base_tolerance)
        self.dt = _positive_float("servo_config.dt", servo_config.dt)
        if not np.isclose(self.dt, float(servo_config.dt), rtol=0.0, atol=1.0e-15):
            raise ValueError("controller and servovalve dt values must match")
        if controller_config is not None:
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
                raise ValueError("ALBHarmonicLinear requires a PD controller with ki=0")

        self.phase_step = coefficients.whirl_omega_rad_s * self.dt
        if not 0.0 < self.phase_step < np.pi:
            raise ValueError("dt must provide more than two samples per whirl cycle")
        self._phase_sine = float(np.sin(self.phase_step))
        self._phase_cosine = float(np.cos(self.phase_step))
        if abs(self._phase_sine) < 1.0e-10:
            raise ValueError("harmonic phase step is singular for quadrature recovery")

        self.controller: Any | None = None
        self.servovalves: list = []
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
        self._last_recorded_time: float | None = None
        self._has_input = False
        self._valid = False
        self._runtime_guard = RuntimeFailureGuard(self._invalidate_runtime)
        self.init()

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
    def fdxv(self) -> np.ndarray:
        """Return the complex spool coefficient under the legacy ALBLinear name."""

        return self.G_xv

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

    @property
    def results(self) -> pd.DataFrame:
        """Return completed results only while the runtime is valid."""

        self._require_valid("read results")
        return self._results

    def _require_valid(self, operation: str) -> None:
        """Reject state access after a failed runtime initialization."""

        if not self._valid:
            raise RuntimeError(
                f"Cannot {operation}: harmonic bearing runtime is invalid; "
                "call init() successfully before reuse"
            )

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
        self._last_recorded_time = None
        self._has_input = False

    def _invalidate_runtime(self) -> None:
        """Discard a partial controller/valve runtime and block state access."""

        self._valid = False
        self.controller = None
        self.servovalves = []
        self._reset_public_state()

    def _sensor_matrix(self) -> np.ndarray:
        """Return the project two-channel controller sensor projection."""

        if self.controller_config is None:
            raise RuntimeError("sensor projection is only defined for PID config")
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

        if self.controller_config is not None:
            controller = PID(copy.deepcopy(self.controller_config))
        elif self._controller_factory is not None:
            controller = self._controller_factory()
        else:
            controller = self._controller_instance
        self._validate_controller(controller)
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
        reset = getattr(controller, "init", None)
        if callable(reset):
            reset()
        self.controller = controller
        self.servovalves = [
            moog_2nd_servovalve(
                self.dt,
                delay=float(self.servo_config.delay),
                tw=float(self.servo_config.tw),
                zeta=float(self.servo_config.zeta),
            )
            for _ in range(2)
        ]
        for valve in self.servovalves:
            valve.init()

    @staticmethod
    def _scalar_output(value: Any) -> float:
        """Convert a finite scalar-like servovalve output to float."""

        output = np.asarray(value, dtype=float).reshape(-1)
        if output.size != 1:
            raise ValueError("Each servovalve must produce one scalar output")
        scalar = float(output[0])
        if not np.isfinite(scalar):
            raise ValueError("Each servovalve must produce a finite scalar output")
        return scalar

    def _advance_control(self, time_s: float, uxy: np.ndarray) -> None:
        """Advance the injected controller and two second-order Moog valves."""

        assert self.controller is not None
        with np.errstate(over="raise", invalid="raise"):
            normalized_position = uxy / self.coefficients.clearance_m
        normalized_position = _finite_vector(
            "normalized controller input", normalized_position
        )
        command = np.asarray(
            run_controller_step(
                self.controller,
                time_s,
                normalized_position,
            ),
            dtype=float,
        ).reshape(-1)
        if command.shape != (2,):
            raise ValueError("controller command must contain exactly two values")
        if not np.all(np.isfinite(command)):
            raise ValueError("controller command must contain only finite values")
        command = command.copy()
        spool = np.zeros(2, dtype=float)
        for axis, valve in enumerate(self.servovalves):
            valve.input(time_s, command[axis])
            spool[axis] = self._scalar_output(valve.output())
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
        if self.controller_config is not None:
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

    def init(self, *args, **kwargs) -> bool:
        """Initialize the runtime, exposing state only after complete success."""

        self._invalidate_runtime()
        self._results = pd.DataFrame(columns=self._RESULT_COLUMNS)
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
            self._last_recorded_time = None
            self._has_input = False
        except Exception:
            self._invalidate_runtime()
            raise
        self._valid = True
        return True

    def input(self, uxy, uxyt, t, *args, **kwargs) -> bool:
        """Accept dimensional rotor position and velocity for one coupling step."""

        self._require_valid("accept input")
        if kwargs.get("nodim", False):
            raise ValueError("ALBHarmonicLinear accepts dimensional bearing inputs")
        position = _finite_vector("uxy", uxy)
        velocity = _finite_vector("uxyt", uxyt)
        time_s = float(t)
        if not np.isfinite(time_s):
            raise ValueError("t must be finite")

        if self._last_time is not None:
            elapsed = time_s - self._last_time
            tolerance = max(1.0e-12, 1.0e-9 * self.dt)
            if abs(elapsed) <= tolerance:
                assert self._last_input is not None
                previous_position, previous_velocity = self._last_input
                if not (
                    np.allclose(position, previous_position, rtol=0.0, atol=1.0e-15)
                    and np.allclose(
                        velocity, previous_velocity, rtol=0.0, atol=1.0e-12
                    )
                ):
                    raise ValueError("Repeated timestamp received different bearing input")
                return True
            if not np.isclose(elapsed, self.dt, rtol=0.0, atol=tolerance):
                raise ValueError("Bearing input time step does not match configured dt")

        with self._runtime_guard.phase():
            self._advance_control(time_s, position)
            delta_spool = self.spool - self.coefficients.base_spool
            with np.errstate(over="raise", invalid="raise"):
                self.spool_quadrature = (
                    delta_spool * self._phase_cosine - self._previous_delta_spool
                ) / self._phase_sine
            if not np.all(np.isfinite(self.spool_quadrature)):
                raise FloatingPointError(
                    "servovalve quadrature must contain only finite values"
                )
            self._previous_delta_spool = delta_spool.copy()
            self.uxy = position
            self.uxyt = velocity
            self._last_time = time_s
            self._last_input = (position.copy(), velocity.copy())
            self._has_input = True
        return True

    def output(self, *args, **kwargs) -> dict[str, Any]:
        """Return total dimensional bearing force and component diagnostics."""

        self._require_valid("read output")
        if kwargs.get("nodim", False):
            raise ValueError("ALBHarmonicLinear only outputs dimensional force")
        if not self._has_input:
            raise RuntimeError("input() must be called before output()")
        with self._runtime_guard.phase():
            delta_position = self.uxy - self.coefficients.equilibrium_position
            delta_spool = self.spool - self.coefficients.base_spool
            with np.errstate(over="raise", invalid="raise"):
                self._force_stiffness = (
                    -self.coefficients.stiffness @ delta_position
                )
                self._force_damping = -self.coefficients.damping @ self.uxyt
                self._force_spool = (
                    self.coefficients.spool_transfer.real @ delta_spool
                    + self.coefficients.spool_transfer.imag
                    @ self.spool_quadrature
                )
                self.force = (
                    self.coefficients.static_force
                    + self._force_stiffness
                    + self._force_damping
                    + self._force_spool
                )
            runtime_vectors = {
                "stiffness force": self._force_stiffness,
                "damping force": self._force_damping,
                "servovalve force": self._force_spool,
                "bearing force": self.force,
            }
            for name, vector in runtime_vectors.items():
                if not np.all(np.isfinite(vector)):
                    raise FloatingPointError(
                        f"{name} must contain only finite values"
                    )
            self.signal.lead_loop("finish_signal")
            return {
                "force": self.force.copy(),
                "friction": 0.0,
                "force_stiffness": self._force_stiffness.copy(),
                "force_damping": self._force_damping.copy(),
                "force_spool": self._force_spool.copy(),
                "spool": self.spool.copy(),
                "spool_command": self.spool_command.copy(),
            }

    def finish_signal(self) -> None:
        """Record the latest completed coupling state once per timestamp."""

        self._require_valid("record results")
        if self._last_time is None or (
            self._last_recorded_time is not None
            and np.isclose(
                self._last_time,
                self._last_recorded_time,
                rtol=0.0,
                atol=max(1.0e-12, 1.0e-9 * self.dt),
            )
        ):
            return
        row = [
            self._last_time,
            self.uxy[0],
            self.uxy[1],
            self.uxyt[0],
            self.uxyt[1],
            self.spool_command[0],
            self.spool_command[1],
            self.spool[0],
            self.spool[1],
            self.spool_quadrature[0],
            self.spool_quadrature[1],
            self._force_stiffness[0],
            self._force_stiffness[1],
            self._force_damping[0],
            self._force_damping[1],
            self._force_spool[0],
            self._force_spool[1],
            self.force[0],
            self.force[1],
            self.controller_saturated,
            self.servovalve_saturated,
        ]
        self._results.loc[len(self._results)] = row
        self._last_recorded_time = self._last_time

    def calc_error(self, *args, **kwargs) -> bool:
        """Return true because this explicit local model has no inner iteration."""

        self._require_valid("read convergence status")
        return True

    def calc_is_finished(self, *args, **kwargs) -> bool:
        """Return true because one input/output evaluation completes the step."""

        self._require_valid("read completion status")
        return True

    def save(
        self,
        tofile: bool = True,
        path: str | Path | None = None,
        name: str | None = None,
        *args,
        **kwargs,
    ) -> SaveTreeNode:
        """Return or persist standard bearing results and coefficient metadata."""

        self._require_valid("save results")
        if path is None:
            path = "alb_harmonic_linear"
        if name is None:
            name = "bearing"
        coefficient_frame = pd.DataFrame(
            [
                {
                    "name": self.coefficients.name,
                    "source": self.coefficients.source,
                    "node_link": self.node_link,
                    "clearance_m": self.coefficients.clearance_m,
                    "shaft_frequency_hz": self.coefficients.shaft_frequency_hz,
                    "whirl_ratio": self.coefficients.whirl_ratio,
                    "whirl_frequency_hz": self.coefficients.whirl_frequency_hz,
                    "dt_s": self.dt,
                }
            ]
        )
        result = DataFrameResult(
            {name: self._results.copy(), f"{name}_configuration": coefficient_frame}
        )
        node = SaveTreeNode(str(path), result)
        if tofile:
            return node.persist(kwargs.get("writer"), path)
        return node


def alb_harmonic_linear(
    node_link: int,
    *,
    dt: float | None = None,
    warmup_steps: int | None = None,
    controller: Any | None = None,
    controller_factory: Callable[[], Any] | None = None,
) -> ALBHarmonicLinear:
    """Build the packaged documented harmonic-linear ALB bearing.

    The default artifact is the strict-base, thermal-inertia, gamma=1, 50 Hz
    equation result documented in ``docs/formula/alb_harmonic_linearization.md``.
    ``dt`` may be changed for a rotor time grid, subject to the narrowband
    sampling guard enforced by :class:`ALBHarmonicLinear`.
    """

    payload = _load_builtin_payload()
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
    injected_controller = controller is not None or controller_factory is not None
    return ALBHarmonicLinear(
        coefficients,
        node_link=node_link,
        servo_config=servo_config,
        controller_config=None if injected_controller else controller_config,
        controller=controller,
        controller_factory=controller_factory,
        warmup_steps=steps,
    )
