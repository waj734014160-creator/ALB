"""Predictor-corrector partitioned coupling of a rotor and its bearings.

Added in ALB 0.4.7 as the optional ``integrator="predictor_corrector"``. The
default staggered integrator evaluates the bearing force at the previously
committed rotor state, so the force lags one step and the coupling is first
order. ROS2 removes the lag but needs side-effect-free forces and a Jacobian.
This scheme removes the lag while keeping the bearing a black box: no
derivatives, no model splitting, and bearings with internal memory (transient
thermal fields, controllers, valves) are supported.

One step ``n -> n+1`` with the notation of ADR-0010::

    L1   = L(t_{n+1})                                  external loads
    P^0  = 2 F_n - F_{n-1} ("linear") or F_n ("constant")
    k = 0, 1, ...
        x^k  = Prop(x_n, G_n, L1 + M P^k)              rotor trial (pure)
        F~^k = Trial(y(x^k); t_{n+1})                  bearing trial
        r^k  = F~^k - P^k                              interface residual (N)
        stop when ||r^k||_inf <= rtol max(||F~^k||_inf, f_ref) + atol
        otherwise P^{k+1} from the relaxation / acceleration rule
    P*      = F~^k                                     corrector force
    x_{n+1} = Prop(x_n, G_n, L1 + M P*)
    F_{n+1} = Commit(y(x_{n+1}); t_{n+1})              one lifecycle commit
    G_{n+1} = L1 + M F_{n+1}

``Prop`` is the exact first-order-hold rotor update of
``RossRotor._propagate_trial`` (the formulas of ``RossRotor._propagate``).
``M`` maps stacked bearing forces to the global load vector. ``f_ref`` is the
larger of ``||F_n||_inf`` and 1 N. The committed state and force are
consistent in the PECE sense: the force is recomputed at the corrected state.
``||F_{n+1} - P*||_inf`` is reported as the a-posteriori consistency residual.

A trial evaluates every bearing from its committed state without committing
anything. Side-effect-free bearings (``probe_force``: liquid film without a
thermal model, gas film, fixed-spool surrogate, multi-pad of such pads,
direct-spool bearings with an explicit spool) are probed. Stateful bearings
(thermal wrappers, active bearings with controller and valves, multi-pads
containing them) implement ``CheckpointableRuntimeProtocol``: the integrator
checkpoints them once per step, runs each trial through the normal
``input``/``evaluate``/``output`` lifecycle, and restores the checkpoint after
every trial. Internal memory is therefore advanced once per trial with the
trial input, and once more by the single commit; at convergence the memory
channel is consistent with the rotor instead of being frozen at ``t_n``. The
bearings are updated simultaneously (Jacobi) from one rotor trial state.

Convergence. Without relaxation the iteration converges when the one-step map
``P -> F~(y(x(P)))`` is a contraction, i.e. the spectral radius of
``dF/dy * dy/dP`` is below one. ``dy/dP`` comes from ``Bd1``: about
``h**2 / (6 m)`` for displacement and ``h / (2 m)`` for velocity, ``m`` being
the effective journal mass. Stiff and especially strongly damped films can
give a radius above one at practical steps; then plain iteration and PECE
diverge or become unstable and the derivative-free Aitken relaxation (Kuettler
and Wall, Comput. Mech. 2008, 43: 61-72) or the IQN-ILS quasi-Newton
acceleration (Degroote, Bathe and Vierendeels, Comput. Struct. 2009, 87:
793-801) must be used. See also Felippa, Park and Farhat (Comput. Methods
Appl. Mech. Eng. 2001, 190: 3247-3270) for partitioned analysis in general.

Spool providers. A direct-spool bearing receives its spool from a provider.
A provider implementing ``checkpoint()``/``restore()`` is called with every
trial input and rolled back with the bearing; any other provider is sampled
once per committed step and its spool is held over the next step's trials,
which makes the spool channel first order (as in ROS2).

Controllers inside active bearings are part of the black box. They count
committed evaluations, and trials are rolled back, so the controller still
runs exactly once every ``m`` commits. At a converged step the controller
samples the committed state at ``t_{n+1}``, the ROS2 sampling semantics.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
import math
from numbers import Integral, Real
from typing import Any, Literal
import warnings

import numpy as np
import numpy.typing as npt
from scipy.linalg import solve_triangular


FloatArray = npt.NDArray[np.float64]

PREDICTOR_CORRECTOR_MODES = ("iterate", "pece")
"""Iteration modes of :class:`PredictorCorrectorOptions`."""

PREDICTORS = ("linear", "constant")
"""Force predictors of :class:`PredictorCorrectorOptions`."""

RELAXATIONS = ("aitken", "iqn_ils", "constant", "none")
"""Interface-force update rules of :class:`PredictorCorrectorOptions`."""

NONCONVERGENCE_POLICIES = ("warn", "raise")
"""Accepted ``on_nonconvergence`` values."""

IQN_COLUMN_TOLERANCE = 1.0e-10
"""Relative ``|R_ii|`` threshold below which IQN-ILS drops a column."""

_REFERENCE_FORCE_FLOOR = 1.0
"""Lower bound (N) of the force scale ``f_ref`` in the relative tolerance."""


class CouplingIterationWarning(UserWarning):
    """The predictor-corrector interface iteration did not converge.

    Emitted once per run, at the first step that reaches
    ``PredictorCorrectorOptions.max_iterations`` without satisfying the
    interface tolerance when ``on_nonconvergence="warn"``. The step is still
    committed from the last iterate; the number of such steps and the largest
    final residual are reported in the run diagnostics and the result
    metadata (``predictor_corrector_diagnostics``).
    """


class CouplingIterationError(RuntimeError):
    """The interface iteration did not converge with ``on_nonconvergence="raise"``."""


class CouplingTrialError(RuntimeError):
    """A bearing raised during a predictor-corrector trial evaluation.

    The bearing has already been restored to its committed state when this
    error is raised; ``__cause__`` is the original exception.
    """


def _as_vector(value: Any) -> FloatArray:
    """Return ``value`` as a flat float64 array (no copy for float64 input)."""

    return np.asarray(value, dtype=np.float64).reshape(-1)


def _positive_finite(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")
    return result


def _nonnegative_finite(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and >= 0")
    return result


def _integer(value: object, name: str, minimum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (Integral, np.integer)
    ):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _choice(value: object, name: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{name} must be one of {', '.join(map(repr, choices))}")
    return value


@dataclass(frozen=True, slots=True)
class PredictorCorrectorOptions:
    """Configure the optional predictor-corrector coupled integrator.

    Parameters
    ----------
    mode
        ``"iterate"`` (default) iterates the interface force to the tolerance;
        ``"pece"`` performs exactly one trial and one commit per step
        (predict, evaluate, correct, evaluate) without a convergence check.
        In ``"pece"`` mode the relaxation, tolerance, iteration-limit, and
        non-convergence options are validated but not used.
    predictor
        ``"linear"`` (default) extrapolates ``P^0 = 2 F_n - F_{n-1}`` (``F_n``
        on the first step); ``"constant"`` uses ``P^0 = F_n``, the staggered
        first guess.
    relaxation
        Interface-force update between trials: ``"aitken"`` (default,
        dynamic Aitken relaxation), ``"iqn_ils"`` (interface quasi-Newton with
        inverse Jacobian from a least-squares model), ``"constant"``
        (``P + omega r``), or ``"none"`` (plain fixed point ``P = F~``).
        Plain iteration converges only when the one-step map is a
        contraction; stiff or strongly damped films need Aitken or IQN-ILS.
    omega
        Relaxation factor of ``"constant"`` and first-iteration factor of
        ``"aitken"`` (initial value of the first step, clipped to
        ``omega_bounds``) and ``"iqn_ils"``. Finite and > 0.
    omega_bounds
        ``(lower, upper)`` clipping range of the Aitken factor,
        ``0 < lower <= upper``.
    iqn_reuse_steps
        Number of previous steps whose IQN-ILS secant columns are reused
        (``0``, the default, uses only the current step).
    rtol, atol
        Convergence test ``||r||_inf <= rtol * max(||F~||_inf, f_ref) +
        atol`` with ``f_ref = max(||F_n||_inf, 1 N)``; ``atol`` is in N in the
        rotor domain. ``rtol`` should not be smaller than the relative
        tolerance of the bearing solver itself (about ``1e-6`` for FEM liquid
        films), otherwise solver noise prevents convergence.
    max_iterations
        Maximum number of trials per step in ``"iterate"`` mode (>= 1).
    on_nonconvergence
        ``"warn"`` (default) commits the last iterate, emits one
        :class:`CouplingIterationWarning` per run, and counts the step in the
        diagnostics; ``"raise"`` seals the step as a coupling failure
        (``CouplingIterationError``) and invalidates the runtime.
    """

    mode: Literal["iterate", "pece"] = "iterate"
    predictor: Literal["linear", "constant"] = "linear"
    relaxation: Literal["aitken", "iqn_ils", "constant", "none"] = "aitken"
    omega: float = 0.5
    omega_bounds: tuple[float, float] = (0.01, 1.5)
    iqn_reuse_steps: int = 0
    rtol: float = 1.0e-6
    atol: float = 1.0e-6
    max_iterations: int = 20
    on_nonconvergence: Literal["warn", "raise"] = "warn"

    def __post_init__(self) -> None:
        _choice(self.mode, "mode", PREDICTOR_CORRECTOR_MODES)
        _choice(self.predictor, "predictor", PREDICTORS)
        _choice(self.relaxation, "relaxation", RELAXATIONS)
        _choice(
            self.on_nonconvergence,
            "on_nonconvergence",
            NONCONVERGENCE_POLICIES,
        )
        object.__setattr__(self, "omega", _positive_finite(self.omega, "omega"))
        bounds = self.omega_bounds
        if (
            isinstance(bounds, (str, bytes))
            or not hasattr(bounds, "__len__")
            or len(bounds) != 2
        ):
            raise ValueError("omega_bounds must contain (lower, upper)")
        lower = _positive_finite(bounds[0], "omega_bounds[0]")
        upper = _positive_finite(bounds[1], "omega_bounds[1]")
        if lower > upper:
            raise ValueError("omega_bounds must satisfy lower <= upper")
        object.__setattr__(self, "omega_bounds", (lower, upper))
        object.__setattr__(
            self,
            "iqn_reuse_steps",
            _integer(self.iqn_reuse_steps, "iqn_reuse_steps", 0),
        )
        object.__setattr__(self, "rtol", _nonnegative_finite(self.rtol, "rtol"))
        object.__setattr__(self, "atol", _nonnegative_finite(self.atol, "atol"))
        if self.rtol == 0.0 and self.atol == 0.0:
            raise ValueError("rtol and atol must not both be zero")
        object.__setattr__(
            self,
            "max_iterations",
            _integer(self.max_iterations, "max_iterations", 1),
        )

    def to_dict(self) -> dict[str, object]:
        """Return primitive metadata describing these options.

        The mapping is stored in
        ``SimulationResult.metadata["predictor_corrector_options"]``.
        """

        return {
            "mode": self.mode,
            "predictor": self.predictor,
            "relaxation": self.relaxation,
            "omega": self.omega,
            "omega_bounds": self.omega_bounds,
            "iqn_reuse_steps": self.iqn_reuse_steps,
            "rtol": self.rtol,
            "atol": self.atol,
            "max_iterations": self.max_iterations,
            "on_nonconvergence": self.on_nonconvergence,
            "unused_in_pece": (
                (
                    "relaxation",
                    "omega",
                    "omega_bounds",
                    "iqn_reuse_steps",
                    "rtol",
                    "atol",
                    "max_iterations",
                    "on_nonconvergence",
                )
                if self.mode == "pece"
                else ()
            ),
        }


# ---------------------------------------------------------------------------
# Interface-force update rules
# ---------------------------------------------------------------------------


class FixedPointUpdate:
    """Plain (``omega = None``) or constant relaxation ``P + omega r``."""

    def __init__(self, omega: float | None = None) -> None:
        self.omega = None if omega is None else _positive_finite(omega, "omega")

    def begin_step(self) -> None:
        """Start a new coupled step."""

    def update(
        self,
        guess: FloatArray,
        trial: FloatArray,
        residual: FloatArray,
    ) -> FloatArray:
        """Return the next interface force from ``P^k``, ``F~^k``, ``r^k``."""

        if self.omega is None:
            return np.array(trial, dtype=float, copy=True)
        return _as_vector(
            np.asarray(guess, dtype=float)
            + self.omega * np.asarray(residual, dtype=float)
        )

    def end_step(self) -> None:
        """Finish the current step."""


class AitkenRelaxation:
    """Dynamic Aitken relaxation of a fixed-point interface iteration.

    ``P^{k+1} = P^k + omega_k r^k``. The first update of a step uses the
    factor carried over from the last update of the previous step (the
    configured ``omega``, clipped to ``bounds``, on the first step). Later
    updates use::

        omega_k = -omega_{k-1} * r_{k-1}^T (r_k - r_{k-1}) / ||r_k - r_{k-1}||^2

    clipped to ``bounds``. For a scalar affine map ``F~ = a P + b`` the second
    update lands on the fixed point when ``1 / (1 - a)`` lies inside the
    bounds. No derivative of the bearing force is needed.
    """

    def __init__(self, omega: float, bounds: tuple[float, float]) -> None:
        lower, upper = (float(bounds[0]), float(bounds[1]))
        if not 0.0 < lower <= upper or not math.isfinite(upper):
            raise ValueError("Aitken bounds must satisfy 0 < lower <= upper")
        self.bounds = (lower, upper)
        self.omega = self._clip(_positive_finite(omega, "omega"))
        self._previous_residual: FloatArray | None = None
        self.omega_min = math.inf
        self.omega_max = -math.inf

    def _clip(self, value: float) -> float:
        return float(min(max(value, self.bounds[0]), self.bounds[1]))

    def begin_step(self) -> None:
        """Forget the residual history; keep the carried factor."""

        self._previous_residual = None

    def update(
        self,
        guess: FloatArray,
        trial: FloatArray,
        residual: FloatArray,
    ) -> FloatArray:
        """Return ``P^{k+1}`` and remember ``r^k`` and ``omega_k``."""

        del trial
        current = np.asarray(residual, dtype=float).reshape(-1)
        omega = self.omega
        if self._previous_residual is not None:
            delta = current - self._previous_residual
            denominator = float(delta @ delta)
            if denominator > 0.0 and math.isfinite(denominator):
                candidate = -self.omega * float(
                    self._previous_residual @ delta
                ) / denominator
                if math.isfinite(candidate):
                    omega = self._clip(candidate)
        self.omega = omega
        self.omega_min = min(self.omega_min, omega)
        self.omega_max = max(self.omega_max, omega)
        self._previous_residual = current.copy()
        return _as_vector(np.asarray(guess, dtype=float).reshape(-1) + omega * current)

    def end_step(self) -> None:
        """Finish the current step; the last factor is carried over."""

        self._previous_residual = None

    def omega_range(self) -> tuple[float, float] | None:
        """Return ``(min, max)`` of the factors used, or ``None``."""

        if not math.isfinite(self.omega_min):
            return None
        return (self.omega_min, self.omega_max)


def _filtered_least_squares(
    matrix: FloatArray,
    rhs: FloatArray,
    tolerance: float,
) -> tuple[FloatArray, npt.NDArray[np.intp]] | None:
    """Solve ``min ||V c - rhs||`` dropping nearly dependent columns.

    Columns are ordered newest first. Repeatedly QR-factorize ``V`` and drop
    the first column ``i`` with ``|R_ii| < tolerance``. Returns ``(c, keep)``
    with the kept column indices, or ``None`` when no column survives.
    """

    keep = np.arange(matrix.shape[1])
    while keep.size:
        q, r = np.linalg.qr(matrix[:, keep], mode="reduced")
        diagonal = np.abs(np.diag(r))
        weak = np.flatnonzero(diagonal < tolerance)
        if weak.size == 0:
            coefficients = solve_triangular(r, q.T @ rhs)
            return np.asarray(coefficients, dtype=float), keep
        keep = np.delete(keep, int(weak[0]))
    return None


class IQNILSAccelerator:
    """Interface quasi-Newton acceleration with least-squares inverse Jacobian.

    The first update of a step is ``P^1 = P^0 + omega r^0``. For ``k >= 1``
    the secant columns ``V = [r^k - r^{k-1}, ..., r^1 - r^0]`` and
    ``W = [F~^k - F~^{k-1}, ..., F~^1 - F~^0]`` (newest first, optionally
    followed by the columns of ``reuse_steps`` previous steps) give
    ``c = argmin ||V c + r^k||`` by QR (columns with ``|R_ii| < 1e-10 ||r^k||``
    are dropped, at most ``dim(P)`` newest columns are kept) and
    ``P^{k+1} = F~^k + W c``. For an affine map the iteration terminates in
    at most ``dim(P) + 1`` updates.
    """

    def __init__(self, omega: float, reuse_steps: int = 0) -> None:
        self.omega = _positive_finite(omega, "omega")
        self.reuse_steps = _integer(reuse_steps, "reuse_steps", 0)
        self._residuals: list[FloatArray] = []
        self._trials: list[FloatArray] = []
        self._history: list[tuple[list[FloatArray], list[FloatArray]]] = []
        self.dropped_columns = 0

    def begin_step(self) -> None:
        """Start a new coupled step."""

        self._residuals = []
        self._trials = []

    def _current_columns(self) -> tuple[list[FloatArray], list[FloatArray]]:
        residuals, trials = self._residuals, self._trials
        count = len(residuals)
        v_columns = [
            residuals[index] - residuals[index - 1]
            for index in range(count - 1, 0, -1)
        ]
        w_columns = [
            trials[index] - trials[index - 1]
            for index in range(count - 1, 0, -1)
        ]
        return v_columns, w_columns

    def update(
        self,
        guess: FloatArray,
        trial: FloatArray,
        residual: FloatArray,
    ) -> FloatArray:
        """Return ``P^{k+1}`` from the secant model of this step."""

        current_residual = np.asarray(residual, dtype=float).reshape(-1).copy()
        current_trial = np.asarray(trial, dtype=float).reshape(-1).copy()
        self._residuals.append(current_residual)
        self._trials.append(current_trial)
        if len(self._residuals) == 1:
            return _as_vector(
                np.asarray(guess, dtype=float).reshape(-1)
                + self.omega * current_residual
            )
        v_columns, w_columns = self._current_columns()
        for old_v, old_w in self._history:
            v_columns.extend(old_v)
            w_columns.extend(old_w)
        size = current_residual.size
        v_columns = v_columns[:size]
        w_columns = w_columns[:size]
        v_matrix = np.column_stack(v_columns)
        w_matrix = np.column_stack(w_columns)
        tolerance = IQN_COLUMN_TOLERANCE * float(np.linalg.norm(current_residual))
        solved = _filtered_least_squares(v_matrix, -current_residual, tolerance)
        if solved is None:
            self.dropped_columns += len(v_columns)
            return _as_vector(
                np.asarray(guess, dtype=float).reshape(-1)
                + self.omega * current_residual
            )
        coefficients, keep = solved
        self.dropped_columns += len(v_columns) - int(keep.size)
        return _as_vector(current_trial + w_matrix[:, keep] @ coefficients)

    def end_step(self) -> None:
        """Store this step's secant columns for optional reuse."""

        if self.reuse_steps > 0:
            v_columns, w_columns = self._current_columns()
            if v_columns:
                self._history.insert(0, (v_columns, w_columns))
                del self._history[self.reuse_steps:]
        self._residuals = []
        self._trials = []


def make_accelerator(options: PredictorCorrectorOptions) -> Any:
    """Return the update rule configured by ``options``."""

    if options.relaxation == "aitken":
        return AitkenRelaxation(options.omega, options.omega_bounds)
    if options.relaxation == "iqn_ils":
        return IQNILSAccelerator(options.omega, options.iqn_reuse_steps)
    if options.relaxation == "constant":
        return FixedPointUpdate(options.omega)
    return FixedPointUpdate(None)


# ---------------------------------------------------------------------------
# Bearing trials
# ---------------------------------------------------------------------------


class _BearingTrial:
    """Evaluate one bound bearing at a trial state without committing it.

    ``mode`` is ``"probe"`` for runtimes with a usable side-effect-free
    ``probe_force`` and ``"checkpoint"`` for runtimes implementing
    ``checkpoint()``/``restore()``. ``spool`` describes the spool source of a
    direct-spool bearing: ``"provider_checkpoint"`` (the provider is called
    with each trial input and rolled back) or ``"held_per_step"`` (the spool
    sampled at the last commit is held over the step).
    """

    def __init__(self, binding: Any) -> None:
        from ALB.contracts import DirectSpoolBearingInput, UnitSystem

        self.binding = binding
        bearing = binding.bearing
        self.bearing = bearing
        self.adapter = binding.unit_adapter
        self.bearing_unit = UnitSystem.coerce(bearing.unit_system)
        self.direct = bearing.input_dto_type is DirectSpoolBearingInput
        probe = getattr(bearing, "probe_force", None)
        probe_usable = callable(probe) and bool(
            getattr(bearing, "probe_force_supported", True)
        )
        checkpointable = callable(getattr(bearing, "checkpoint", None)) and (
            callable(getattr(bearing, "restore", None))
        )
        if probe_usable:
            self.mode = "probe"
        elif checkpointable:
            self.mode = "checkpoint"
        else:
            raise TypeError(
                f"{type(bearing).__name__} can neither evaluate force without "
                "side effects (probe_force) nor checkpoint and restore its "
                "state; use the staggered integrator"
            )
        self.provider = binding.spool_provider if self.direct else None
        self.spool_mode: str | None = None
        if self.direct:
            provider = self.provider
            if provider is None:
                raise TypeError("direct-spool bearing requires a spool provider")
            self.spool_mode = (
                "provider_checkpoint"
                if callable(getattr(provider, "checkpoint", None))
                and callable(getattr(provider, "restore", None))
                else "held_per_step"
            )
        self.held_spool: FloatArray | None = None
        self._token: object = None
        self._provider_token: object = None
        self.trials = 0

    # -- per-step bookkeeping ----------------------------------------------

    def begin_step(self) -> None:
        """Checkpoint the committed bearing and provider state once."""

        if self.mode == "checkpoint":
            self._token = self.bearing.checkpoint()
        if self.spool_mode == "provider_checkpoint":
            assert self.provider is not None
            self._provider_token = self.provider.checkpoint()

    def end_step(self) -> None:
        """Drop the step tokens before the commit evaluation."""

        self._token = None
        self._provider_token = None

    def sample_committed_spool(self) -> None:
        """Hold the spool published by the provider at the last commit."""

        if self.direct and self.provider is not None:
            self.held_spool = np.asarray(
                self.provider.output().spool,
                dtype=float,
            ).copy()

    # -- unit conversion ----------------------------------------------------

    def _global_input(self, displacement: FloatArray, velocity: FloatArray, time: float) -> Any:
        from ALB.contracts import BearingInput, UnitSystem

        return BearingInput(
            displacement=np.asarray(displacement, dtype=float).copy(),
            velocity=np.asarray(velocity, dtype=float).copy(),
            time=time,
            unit_system=UnitSystem.DIMENSIONAL,
        )

    def _rotor_force(self, force: Any, local_time: float) -> FloatArray:
        from ALB.contracts import BearingOutput

        if self.adapter is None:
            return np.asarray(force, dtype=float).reshape(2).copy()
        output = self.adapter.bearing_output_to_rotor(
            BearingOutput(
                np.asarray(force, dtype=float).reshape(2),
                local_time,
                self.bearing_unit,
            )
        )
        return np.asarray(output.force, dtype=float).reshape(2).copy()

    # -- spool ----------------------------------------------------------------

    def _trial_spool(self, context: Any, global_input: Any) -> FloatArray:
        from ALB.contracts import ValveOutput

        if self.spool_mode == "provider_checkpoint":
            provider = self.provider
            assert provider is not None
            token = self._provider_token
            if token is None:
                raise RuntimeError("spool provider was not checkpointed")
            try:
                provider.input(context, global_input)
                provider.evaluate()
                spool = provider.output()
                if not isinstance(spool, ValveOutput):
                    raise TypeError("spool provider output must be ValveOutput")
                if spool.time != context.time:
                    raise ValueError("spool command time must match global context")
                return np.asarray(spool.spool, dtype=float).copy()
            finally:
                provider.restore(token)
        if self.held_spool is None:
            raise RuntimeError("direct-spool provider has not been sampled")
        return self.held_spool.copy()

    # -- evaluation -----------------------------------------------------------

    def evaluate(
        self,
        displacement: FloatArray,
        velocity: FloatArray,
        context: Any,
    ) -> FloatArray:
        """Return the rotor-domain trial force at ``context.time``."""

        from ALB.contracts import (
            BearingOutput,
            DirectSpoolBearingInput,
            UnitSystem,
            ValveOutput,
        )

        global_input = self._global_input(displacement, velocity, context.time)
        adapter = self.adapter
        local_input = (
            adapter.rotor_input_to_bearing(global_input)
            if adapter is not None
            else global_input
        )
        spool = (
            self._trial_spool(context, global_input) if self.direct else None
        )
        self.trials += 1
        if self.mode == "probe":
            if spool is None:
                force = self.bearing.probe_force(local_input)
            else:
                force = self.bearing.probe_force(
                    DirectSpoolBearingInput(
                        local_input,
                        ValveOutput(spool, local_input.time, UnitSystem.NONDIMENSIONAL),
                    )
                )
            return self._rotor_force(force, local_input.time)
        dto: Any = local_input
        if spool is not None:
            global_direct = DirectSpoolBearingInput(
                global_input,
                ValveOutput(spool, context.time, UnitSystem.NONDIMENSIONAL),
            )
            dto = (
                adapter.rotor_direct_spool_to_bearing(global_direct)
                if adapter is not None
                else global_direct
            )
        token = self._token
        if token is None:
            raise RuntimeError("bearing was not checkpointed before a trial")
        bearing = self.bearing
        try:
            bearing.input(dto)
            bearing.evaluate()
            output = bearing.output()
            if not isinstance(output, BearingOutput):
                raise TypeError("native bearing output must be BearingOutput")
            if output.time != local_input.time:
                raise ValueError(
                    "bearing output time must match the local step context"
                )
            return self._rotor_force(output.force, output.time)
        finally:
            # Every trial starts from, and returns to, the committed state.
            bearing.restore(token)


# ---------------------------------------------------------------------------
# Coupled integrator
# ---------------------------------------------------------------------------


def _load_vector(load: Any, time: float) -> FloatArray:
    """Evaluate one rotor excitation without logging side effects."""

    evaluate = getattr(load, "force_at", None)
    return np.asarray(evaluate(time) if callable(evaluate) else load(time), dtype=float)


def _inf_norm(values: FloatArray) -> float:
    return float(np.max(np.abs(values))) if values.size else 0.0


class PredictorCorrectorCouplingIntegrator:
    """Advance a rotor and its bearings with predictor-corrector coupling.

    The integrator owns the committed rotor state ``x_n``, the committed
    bearing forces ``F_n`` (and ``F_{n-1}`` for the linear predictor), and the
    committed global load vector ``G_n``. Rotor trials use the pure hook
    ``rotor._propagate_trial``; the committed state is published by the caller
    through ``rotor._commit_integrated_state``. Bearing commits go through the
    caller's ``commit_bearing(index, displacement, velocity)`` callback, the
    same lifecycle path as the staggered integrator (including spool
    providers).
    """

    def __init__(
        self,
        rotor: Any,
        bindings: tuple[Any, ...],
        loads: list[Any],
        load_node_links: Any,
        time_step: float,
        options: PredictorCorrectorOptions | None,
    ) -> None:
        self.rotor = rotor
        self.bindings = tuple(bindings)
        self.options = options if options is not None else PredictorCorrectorOptions()
        if not isinstance(self.options, PredictorCorrectorOptions):
            raise TypeError("options must be PredictorCorrectorOptions or None")
        self.time_step = _positive_finite(time_step, "time_step")
        for name in ("_propagate_trial", "_node_state_indices", "_node_force_vector"):
            if not callable(getattr(rotor, name, None)):
                raise TypeError(
                    f"predictor_corrector requires the rotor owner hook {name}"
                )
        self._loads = list(loads)
        self._load_node_links = [
            int(value) for value in np.asarray(load_node_links).reshape(-1)
        ]
        self._bearing_nodes = [int(binding.node_link) for binding in self.bindings]
        displacement_idx, velocity_idx = rotor._node_state_indices(self._bearing_nodes)
        self._displacement_idx = np.asarray(displacement_idx, dtype=np.int64)
        self._velocity_idx = np.asarray(velocity_idx, dtype=np.int64)
        self._bearing_map = self._force_map(self._bearing_nodes)
        self.trials = tuple(_BearingTrial(binding) for binding in self.bindings)
        self._accelerator = make_accelerator(self.options)
        self._state: FloatArray | None = None
        self._global_force: FloatArray | None = None
        self._forces: FloatArray | None = None
        self._previous_forces: FloatArray | None = None
        self._warned = False
        self._reset_counters()

    # -- helpers ------------------------------------------------------------

    def _reset_counters(self) -> None:
        self.steps = 0
        self.trial_iterations = 0
        self.commits = 0
        self.iteration_histogram: Counter[int] = Counter()
        self.nonconverged_steps = 0
        self.max_final_residual = 0.0
        self.max_consistency_residual = 0.0
        self._ratio_sum = 0.0
        self._ratio_count = 0
        self._ratio_max = 0.0

    def _force_map(self, nodes: list[int]) -> FloatArray:
        """Return the linear map from stacked node forces to the load vector."""

        count = len(nodes)
        columns = []
        for index in range(2 * count):
            unit = np.zeros((count, 2))
            unit[index // 2, index % 2] = 1.0
            columns.append(
                np.asarray(self.rotor._node_force_vector(unit, nodes), dtype=float)
            )
        return np.column_stack(columns)

    def _load_force(self, time: float) -> tuple[FloatArray, FloatArray]:
        """Return stacked external node loads and their global load vector."""

        if not self._loads:
            return np.zeros((0, 2)), np.zeros(self._bearing_map.shape[0])
        stacked = np.vstack([_load_vector(load, time) for load in self._loads])
        return stacked, np.asarray(
            self.rotor._node_force_vector(stacked, self._load_node_links),
            dtype=float,
        )

    def _kinematics(self, state: FloatArray, index: int) -> tuple[FloatArray, FloatArray]:
        return (
            state[self._displacement_idx[index]].copy(),
            state[self._velocity_idx[index]].copy(),
        )

    def _propagate(self, global_force: FloatArray) -> FloatArray:
        assert self._state is not None and self._global_force is not None
        state = np.asarray(
            self.rotor._propagate_trial(
                self._state,
                self._global_force,
                global_force,
            ),
            dtype=float,
        )
        if not np.all(np.isfinite(state)):
            raise FloatingPointError(
                "predictor_corrector rotor trial produced a non-finite state"
            )
        return state

    def _commit_forces(
        self,
        state: FloatArray,
        commit_bearing: Callable[[int, FloatArray, FloatArray], FloatArray],
    ) -> FloatArray:
        forces = []
        for index, trial in enumerate(self.trials):
            displacement, velocity = self._kinematics(state, index)
            forces.append(
                np.asarray(
                    commit_bearing(index, displacement, velocity),
                    dtype=float,
                ).reshape(2)
            )
            trial.sample_committed_spool()
        committed = np.vstack(forces)
        if not np.all(np.isfinite(committed)):
            raise FloatingPointError(
                "predictor_corrector committed a non-finite bearing force"
            )
        self.commits += 1
        return committed

    def _trial_forces(self, state: FloatArray, context: Any, iteration: int) -> FloatArray:
        forces = []
        for index, trial in enumerate(self.trials):
            displacement, velocity = self._kinematics(state, index)
            try:
                force = trial.evaluate(displacement, velocity, context)
            except Exception as exc:
                raise CouplingTrialError(
                    f"predictor_corrector trial {iteration} of bearing {index} "
                    f"failed at time {context.time!r}; the bearing was restored "
                    f"to its committed state: {type(exc).__name__}"
                ) from exc
            forces.append(force)
        stacked = np.concatenate(forces)
        if not np.all(np.isfinite(stacked)):
            raise FloatingPointError(
                "predictor_corrector trial produced a non-finite bearing force"
            )
        return stacked

    # -- lifecycle ----------------------------------------------------------

    def reset(
        self,
        initial_time: float,
        commit_bearing: Callable[[int, FloatArray, FloatArray], FloatArray],
    ) -> FloatArray:
        """Commit the step-zero forces at the rotor's current state.

        Returns the committed bearing forces with shape ``(n, 2)``.
        """

        state = np.asarray(self.rotor.current_state(), dtype=float).reshape(-1).copy()
        self._state = state
        self._previous_forces = None
        self._warned = False
        self._reset_counters()
        for trial in self.trials:
            trial.held_spool = None
            trial.trials = 0
        _, load_vector = self._load_force(float(initial_time))
        forces = self._commit_forces(state, commit_bearing)
        self._forces = forces.reshape(-1).copy()
        self._global_force = load_vector + self._bearing_map @ self._forces
        return forces

    def _predict(self) -> FloatArray:
        assert self._forces is not None
        if self.options.predictor == "linear" and self._previous_forces is not None:
            return 2.0 * self._forces - self._previous_forces
        return self._forces.copy()

    def _converged(self, residual: FloatArray, trial: FloatArray, reference: float) -> bool:
        options = self.options
        return _inf_norm(residual) <= options.rtol * max(
            _inf_norm(trial), reference
        ) + options.atol

    def advance(
        self,
        context: Any,
        commit_bearing: Callable[[int, FloatArray, FloatArray], FloatArray],
    ) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
        """Advance one step to ``context.time`` and commit every bearing once.

        Returns ``(rotor_state, bearing_forces, load_forces, global_force)``
        at the committed time; the rotor itself is committed by the caller.
        """

        if self._state is None or self._forces is None or self._global_force is None:
            raise RuntimeError("predictor_corrector integrator has not been reset")
        options = self.options
        time = float(context.time)
        load_forces, load_vector = self._load_force(time)
        reference = max(_inf_norm(self._forces), _REFERENCE_FORCE_FLOOR)
        guess = self._predict()
        accelerator = self._accelerator
        iterate = options.mode == "iterate"
        converged = not iterate
        iterations = 0
        previous_norm: float | None = None
        trial_force = guess
        residual = np.zeros_like(guess)
        try:
            for trial in self.trials:
                trial.begin_step()
            accelerator.begin_step()
            while True:
                state = self._propagate(load_vector + self._bearing_map @ guess)
                trial_force = self._trial_forces(state, context, iterations)
                iterations += 1
                residual = trial_force - guess
                norm = _inf_norm(residual)
                if previous_norm is not None and previous_norm > 0.0:
                    # Successive residual ratios estimate the contraction
                    # factor of the (relaxed) interface iteration.
                    ratio = norm / previous_norm
                    self._ratio_sum += ratio
                    self._ratio_count += 1
                    self._ratio_max = max(self._ratio_max, ratio)
                previous_norm = norm
                if not iterate:
                    break
                if self._converged(residual, trial_force, reference):
                    converged = True
                    break
                if iterations >= options.max_iterations:
                    break
                guess = np.asarray(
                    accelerator.update(guess, trial_force, residual),
                    dtype=float,
                ).reshape(-1)
                if not np.all(np.isfinite(guess)):
                    raise FloatingPointError(
                        "predictor_corrector interface update is non-finite"
                    )
        finally:
            for trial in self.trials:
                trial.end_step()
            accelerator.end_step()
        self.trial_iterations += iterations
        self.iteration_histogram[iterations] += 1
        final_residual = _inf_norm(residual)
        self.max_final_residual = max(self.max_final_residual, final_residual)
        if not converged:
            message = (
                "predictor_corrector interface iteration did not converge in "
                f"{iterations} trial(s) at time {time!r}; final residual "
                f"{final_residual:.6g} N"
            )
            if options.on_nonconvergence == "raise":
                raise CouplingIterationError(message)
            self.nonconverged_steps += 1
            if not self._warned:
                self._warned = True
                warnings.warn(
                    CouplingIterationWarning(
                        message
                        + "; the last iterate is committed and further "
                        "non-converged steps are only counted in the "
                        "diagnostics"
                    ),
                    stacklevel=2,
                )
        corrector = trial_force
        next_state = self._propagate(load_vector + self._bearing_map @ corrector)
        committed = self._commit_forces(next_state, commit_bearing)
        flat = committed.reshape(-1).copy()
        self.max_consistency_residual = max(
            self.max_consistency_residual,
            _inf_norm(flat - corrector),
        )
        global_force = load_vector + self._bearing_map @ flat
        self._previous_forces = self._forces
        self._forces = flat
        self._state = next_state.copy()
        self._global_force = global_force
        self.steps += 1
        return next_state.copy(), committed, load_forces, global_force.copy()

    def diagnostics(self) -> dict[str, object]:
        """Return primitive iteration and evaluation counters."""

        steps = self.steps
        counts = sorted(self.iteration_histogram.items())
        ratio_count = self._ratio_count
        omega_range = (
            self._accelerator.omega_range()
            if isinstance(self._accelerator, AitkenRelaxation)
            else None
        )
        bearings = len(self.trials)
        return {
            "integrator": "predictor_corrector",
            "steps": steps,
            "trial_iterations": self.trial_iterations,
            "trial_evaluations": self.trial_iterations * bearings,
            "commits": self.commits,
            "commit_evaluations": self.commits * bearings,
            "iterations_per_step": {
                "mean": (self.trial_iterations / steps) if steps else 0.0,
                "max": max((count for count, _ in counts), default=0),
                # ((trials, steps), ...) sorted by the number of trials.
                "histogram": tuple(
                    (int(count), int(number)) for count, number in counts
                ),
            },
            "nonconverged_steps": self.nonconverged_steps,
            "max_final_residual": self.max_final_residual,
            "max_consistency_residual": self.max_consistency_residual,
            "residual_ratio": {
                "mean": (self._ratio_sum / ratio_count) if ratio_count else None,
                "max": self._ratio_max if ratio_count else None,
                "count": ratio_count,
            },
            "aitken_omega_range": omega_range,
            "trial_modes": tuple(trial.mode for trial in self.trials),
            "spool_trials": tuple(trial.spool_mode for trial in self.trials),
            "options": self.options.to_dict(),
        }


__all__ = [
    "AitkenRelaxation",
    "CouplingIterationError",
    "CouplingIterationWarning",
    "CouplingTrialError",
    "FixedPointUpdate",
    "IQNILSAccelerator",
    "PredictorCorrectorCouplingIntegrator",
    "PredictorCorrectorOptions",
    "make_accelerator",
]
