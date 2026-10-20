"""Two-stage Rosenbrock-W (ROS2) integration core for coupled simulations.

The method follows Verwer, Spee, Blom and Hundsdorfer (SIAM J. Sci. Comput.,
1999, 20(4): 1456-1480). For ``dz/dt = f(z, t)`` one step of size ``h`` is::

    W = I - gamma * h * J,  gamma = 1 + 1 / sqrt(2)
    W k1 = f(z_j, t_j)
    W k2 = f(z_j + h * k1, t_j + h) - 2 * k1
    z_{j+1} = z_j + h * (1.5 * k1 + 0.5 * k2)

The scheme is second order for any matrix ``J`` (W-method property: the terms
containing ``J`` cancel at order ``h**2``). With ``J`` equal to the exact
Jacobian it is L-stable with stability function
``R(z) = (1 + (1 - 2 gamma) z) / (1 - gamma z)**2``. Explicit time dependence
is evaluated at ``t_j`` and ``t_j + h``; it acts like an extra state with a
zero Jacobian column and therefore keeps order two.

``J`` is frozen by default, so ``W`` is LU-factorized once per configuration
and every step costs two right-hand-side evaluations and two triangular
solves. A frozen ``J`` only changes the stability margin, not the order. For a
scalar model the scheme stays stable while the true stiffness remains within
about seven times the frozen value; contacts close to the bearing wall reduce
the margin most, which is why an optional refresh policy is provided.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from numbers import Integral, Real
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from scipy.linalg import lu_factor, lu_solve


FloatArray = npt.NDArray[np.float64]
RightHandSide = Callable[[FloatArray, float], FloatArray]

ROS2_GAMMA = 1.0 + 1.0 / math.sqrt(2.0)
"""Diagonal coefficient ``gamma = 1 + 1/sqrt(2)`` of the L-stable ROS2 method."""

INTEGRATORS = ("staggered", "ros2")
"""Coupled-simulation integrators accepted by ``SimulationConfig``."""


def ros2_stability_function(z: complex) -> complex:
    """Return the ROS2 amplification factor for ``y' = lambda y`` and exact J.

    ``z`` is ``lambda * h``. The factor tends to zero for ``|z| -> infinity``
    in the left half plane (L-stability).
    """

    gamma = ROS2_GAMMA
    return (1.0 + (1.0 - 2.0 * gamma) * z) / (1.0 - gamma * z) ** 2


def _positive_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")
    return result


@dataclass(frozen=True, slots=True)
class Ros2Options:
    """Configure the optional ROS2 coupled integrator.

    Parameters
    ----------
    jacobian_refresh
        ``None`` (default) freezes ``J`` for the whole run. A positive integer
        ``N`` recomputes ``J`` and refactorizes ``W`` at the committed state
        after every ``N`` steps. ``"control_period"`` refreshes at every
        controller sampling instant. Refreshing never changes the order of
        accuracy, only the stability margin and the cost.
    jacobian_state
        Optional state at which the initial ``J`` is evaluated, for example a
        static equilibrium obtained with the existing equilibrium analysis.
        Either the complete rotor state (ROSS ``[q, dq/dt]`` ordering; the
        actuator states of active bearings are then taken as zero) or the
        complete coupled state ``[rotor state, actuator states]``. ``None``
        uses the simulation initial state. Controller commands are the ones
        sampled at the initial state. Packaged surrogates have a
        square-root-type stiffness singularity at the centred journal, so an
        off-centre ``jacobian_state`` gives them a better frozen ``J``.
    relative_step, displacement_step, velocity_step, spool_step
        Central-difference steps used when a bearing cannot provide an
        automatic-differentiation force. Each perturbation is
        ``max(relative_step * |value|, floor)`` with the floor given in rotor
        units: metres for displacement, metres per second for velocity, and
        normalized spool units for spool opening. The defaults (``1e-3``,
        ``1e-7`` m, ``1e-4`` m/s and ``1e-3``) keep the stencil about three
        orders of magnitude below typical clearances (tens of micrometres),
        so truncation error is negligible, while staying well above the
        iterative noise of film and restrictor solves (the restrictor
        coupling stops at a relative tolerance of ``1e-3``, which can change
        the stopping iteration between the two stencil points). ``J`` only
        affects the stability margin, never the order of accuracy of a
        W-method.
    """

    jacobian_refresh: int | Literal["control_period"] | None = None
    jacobian_state: Any = None
    relative_step: float = 1.0e-3
    displacement_step: float = 1.0e-7
    velocity_step: float = 1.0e-4
    spool_step: float = 1.0e-3

    def __post_init__(self) -> None:
        refresh = self.jacobian_refresh
        if refresh is not None and refresh != "control_period":
            if (
                isinstance(refresh, (bool, np.bool_))
                or not isinstance(refresh, (Integral, np.integer))
                or int(refresh) < 1
            ):
                raise ValueError(
                    "jacobian_refresh must be None, a positive integer, or "
                    "'control_period'"
                )
            object.__setattr__(self, "jacobian_refresh", int(refresh))
        if self.jacobian_state is not None:
            state = np.array(self.jacobian_state, dtype=float, copy=True)
            if state.ndim != 1 or state.size == 0:
                raise ValueError("jacobian_state must be a nonempty vector")
            if not np.all(np.isfinite(state)):
                raise ValueError("jacobian_state must contain finite values")
            state.setflags(write=False)
            object.__setattr__(self, "jacobian_state", state)
        for name in (
            "relative_step",
            "displacement_step",
            "velocity_step",
            "spool_step",
        ):
            object.__setattr__(
                self,
                name,
                _positive_float(getattr(self, name), name),
            )

    def to_dict(self) -> dict[str, object]:
        """Return primitive metadata describing these options."""

        return {
            "jacobian_refresh": self.jacobian_refresh,
            "jacobian_state": (
                None
                if self.jacobian_state is None
                else "user-supplied"
            ),
            "relative_step": self.relative_step,
            "displacement_step": self.displacement_step,
            "velocity_step": self.velocity_step,
            "spool_step": self.spool_step,
        }


class Ros2Stepper:
    """Advance ``dz/dt = f(z, t)`` with the frozen-Jacobian ROS2 scheme.

    The stepper owns only the LU factorization of ``W = I - gamma h J``.
    Callers supply ``f(z_j, t_j)`` separately when it is already known (for
    example from the previous committed state) so that each step needs a
    single new right-hand-side evaluation for the second stage.
    """

    def __init__(self, time_step: float, jacobian: npt.ArrayLike) -> None:
        self._h = _positive_float(time_step, "time_step")
        self._lu: Any = None
        self._size = 0
        self.factorizations = 0
        self.set_jacobian(jacobian)

    @property
    def time_step(self) -> float:
        """Return the fixed step ``h``."""

        return self._h

    @property
    def size(self) -> int:
        """Return the state dimension."""

        return self._size

    def set_jacobian(self, jacobian: npt.ArrayLike) -> None:
        """Factorize ``W = I - gamma h J`` for a new frozen ``J``."""

        matrix = np.asarray(jacobian, dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError("ROS2 Jacobian must be a square matrix")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("ROS2 Jacobian must contain finite values")
        size = int(matrix.shape[0])
        w_matrix = np.eye(size) - ROS2_GAMMA * self._h * matrix
        self._lu = lu_factor(w_matrix, check_finite=True)
        self._size = size
        self.factorizations += 1

    def _solve(self, rhs: FloatArray) -> FloatArray:
        return np.asarray(lu_solve(self._lu, rhs, check_finite=True), dtype=float)

    def step(
        self,
        rhs: RightHandSide,
        time: float,
        state: npt.ArrayLike,
        rhs_at_state: npt.ArrayLike | None = None,
    ) -> FloatArray:
        """Return ``z_{j+1}`` from ``z_j`` at ``t_j``.

        ``rhs_at_state`` is ``f(z_j, t_j)``; it is evaluated here when omitted.
        """

        z = np.asarray(state, dtype=float).reshape(-1)
        if z.shape != (self._size,):
            raise ValueError("ROS2 state dimension does not match the Jacobian")
        h = self._h
        f0 = (
            np.asarray(rhs(z, time), dtype=float).reshape(-1)
            if rhs_at_state is None
            else np.asarray(rhs_at_state, dtype=float).reshape(-1)
        )
        k1 = self._solve(f0)
        f1 = np.asarray(rhs(z + h * k1, time + h), dtype=float).reshape(-1)
        k2 = self._solve(f1 - 2.0 * k1)
        return z + h * (1.5 * k1 + 0.5 * k2)


# ---------------------------------------------------------------------------
# Coupled rotor-bearing integration
# ---------------------------------------------------------------------------


class Ros2StageError(RuntimeError):
    """A ROS2 intermediate-stage bearing force could not be evaluated."""


def _central_difference(
    function: Callable[[FloatArray], FloatArray],
    point: FloatArray,
    floor: float,
    relative: float,
    *,
    lower: float | None = None,
    upper: float | None = None,
) -> FloatArray:
    """Return ``d function / d point`` (2 x n) by central differences.

    Each component uses ``delta = max(relative * |value|, floor)``. Optional
    bounds (spool opening in ``[-1, 1]``) shrink the stencil to stay inside
    the admissible interval, degrading to a one-sided difference at a bound.
    """

    base = np.asarray(point, dtype=float).reshape(-1)
    columns = []
    for index, value in enumerate(base):
        delta = max(relative * abs(float(value)), floor)
        plus = float(value) + delta
        minus = float(value) - delta
        if upper is not None:
            plus = min(plus, upper)
        if lower is not None:
            minus = max(minus, lower)
        if plus <= minus:
            columns.append(np.zeros(2))
            continue
        forward = base.copy()
        backward = base.copy()
        forward[index] = plus
        backward[index] = minus
        columns.append(
            (np.asarray(function(forward), dtype=float).reshape(2)
             - np.asarray(function(backward), dtype=float).reshape(2))
            / (plus - minus)
        )
    return np.column_stack(columns) if columns else np.zeros((2, 0))


class _BindingForceModel:
    """Evaluate one coupled bearing in the dimensional rotor domain.

    Three runtime kinds are supported:

    * ``pure``: the runtime implements ``ForceProbeProtocol`` for
      ``BearingInput`` (liquid film without thermal state, gas film, fixed-spool
      surrogate, multi-pad of such pads);
    * ``direct_spool``: the runtime takes ``DirectSpoolBearingInput`` and
      implements ``ForceProbeProtocol``; the spool comes from the binding's
      provider, sampled once per step at the committed state and held over the
      step (zero-order hold);
    * ``actuated``: the runtime implements ``SampledActuatorBearingProtocol``
      (active bearings with internal controller and servovalves); the valve
      states are integrated in the coupled state and the controller is
      sampled every ``control_steps_per_period`` steps with its command held.

    Any other runtime raises ``TypeError`` because ROS2 must evaluate forces at
    intermediate stage states without side effects.
    """

    def __init__(self, binding: Any, global_time_step: float) -> None:
        from ALB.contracts import (
            DirectSpoolBearingInput,
            ForceProbeProtocol,
            SampledActuatorBearingProtocol,
            StepContext,
            UnitSystem,
        )

        self.binding = binding
        bearing = binding.bearing
        self.bearing = bearing
        self.adapter = binding.unit_adapter
        self.bearing_unit = UnitSystem.coerce(bearing.unit_system)
        if self.adapter is None:
            self.time_scale = 1.0
        else:
            local = self.adapter.rotor_context_to_bearing(
                StepContext(0, 0.0, global_time_step, UnitSystem.DIMENSIONAL)
            )
            self.time_scale = float(local.dt) / float(global_time_step)
        self.channels: tuple[tuple[FloatArray, ...], ...] = ()
        self.state_count = 0
        self.control_steps = 1
        if bearing.input_dto_type is DirectSpoolBearingInput:
            if not isinstance(bearing, ForceProbeProtocol):
                raise TypeError(
                    f"{type(bearing).__name__} cannot evaluate direct-spool "
                    "force without side effects; use the staggered integrator"
                )
            self.kind = "direct_spool"
        elif isinstance(bearing, SampledActuatorBearingProtocol):
            self.kind = "actuated"
            channels = []
            for a, b, c, d in bearing.actuator_state_space():
                a = np.asarray(a, dtype=float)
                b = np.asarray(b, dtype=float)
                c = np.asarray(c, dtype=float)
                d = np.asarray(d, dtype=float)
                states = a.shape[0] if a.ndim == 2 else -1
                if (
                    a.shape != (states, states)
                    or b.shape != (states, 1)
                    or c.shape != (1, states)
                    or d.shape != (1, 1)
                ):
                    raise ValueError(
                        "ROS2 supports SISO actuator channels with 2-D "
                        "state-space matrices only"
                    )
                channels.append((a, b, c, d))
            self.channels = tuple(channels)
            self.state_count = int(sum(item[0].shape[0] for item in channels))
            self.control_steps = int(bearing.control_steps_per_period)
            if self.control_steps < 1:
                raise ValueError("control_steps_per_period must be >= 1")
        elif isinstance(bearing, ForceProbeProtocol):
            self.kind = "pure"
        else:
            raise TypeError(
                f"{type(bearing).__name__} cannot evaluate force without side "
                "effects (for example a thermal model with internal state); "
                "use the staggered integrator"
            )
        self.command = np.zeros(len(self.channels))
        self.held_spool: FloatArray | None = None
        self.torch_force = getattr(bearing, "torch_force", None)

    # -- unit conversion ---------------------------------------------------

    def _local_input(self, displacement: FloatArray, velocity: FloatArray, time: float) -> Any:
        from ALB.contracts import BearingInput, UnitSystem

        global_input = BearingInput(
            displacement=np.asarray(displacement, dtype=float).copy(),
            velocity=np.asarray(velocity, dtype=float).copy(),
            time=time,
            unit_system=UnitSystem.DIMENSIONAL,
        )
        if self.adapter is None:
            return global_input
        return self.adapter.rotor_input_to_bearing(global_input)

    def _rotor_force(self, local_force: FloatArray, local_time: float) -> FloatArray:
        from ALB.contracts import BearingOutput

        if self.adapter is None:
            return np.asarray(local_force, dtype=float).reshape(2)
        output = self.adapter.bearing_output_to_rotor(
            BearingOutput(
                np.asarray(local_force, dtype=float).reshape(2),
                local_time,
                self.bearing_unit,
            )
        )
        return np.asarray(output.force, dtype=float).reshape(2)

    # -- actuator dynamics -------------------------------------------------

    def spool(self, actuator_state: FloatArray) -> FloatArray:
        """Return the clipped spool opening of every actuator channel."""

        values = []
        offset = 0
        for (a, _, c, d), command in zip(self.channels, self.command):
            size = a.shape[0]
            state = actuator_state[offset:offset + size]
            offset += size
            values.append(float((c @ state)[0] + d[0, 0] * command))
        return np.clip(np.asarray(values, dtype=float), -1.0, 1.0)

    def spool_jacobian(self, actuator_state: FloatArray) -> FloatArray:
        """Return ``d spool / d actuator_state`` (zero where clipped)."""

        rows = np.zeros((len(self.channels), self.state_count))
        unclipped = self.spool(actuator_state)
        offset = 0
        for row, ((a, _, c, _), value) in enumerate(zip(self.channels, unclipped)):
            size = a.shape[0]
            if abs(value) < 1.0:
                rows[row, offset:offset + size] = c[0]
            offset += size
        return rows

    def actuator_derivative(self, actuator_state: FloatArray) -> FloatArray:
        """Return ``d xi / dt`` in global time for the held command."""

        derivatives = []
        offset = 0
        for (a, b, _, _), command in zip(self.channels, self.command):
            size = a.shape[0]
            state = actuator_state[offset:offset + size]
            offset += size
            derivatives.append(self.time_scale * (a @ state + b[:, 0] * command))
        return np.concatenate(derivatives) if derivatives else np.zeros(0)

    def actuator_matrix(self) -> FloatArray:
        """Return ``d (d xi / dt) / d xi`` in global time."""

        matrix = np.zeros((self.state_count, self.state_count))
        offset = 0
        for a, _, _, _ in self.channels:
            size = a.shape[0]
            matrix[offset:offset + size, offset:offset + size] = self.time_scale * a
            offset += size
        return matrix

    # -- sampling ------------------------------------------------------------

    def sample(
        self,
        displacement: FloatArray,
        velocity: FloatArray,
        time: float,
        step_index: int,
    ) -> bool:
        """Sample the controller when ``step_index`` is a control instant."""

        if self.kind != "actuated" or step_index % self.control_steps != 0:
            return False
        command = self.bearing.sample_actuator_command(
            self._local_input(displacement, velocity, time)
        )
        command = np.asarray(command, dtype=float).reshape(-1)
        if command.shape != (len(self.channels),):
            raise ValueError("actuator command must contain one value per channel")
        self.command = np.clip(command, -1.0, 1.0)
        return True

    # -- force evaluation ----------------------------------------------------

    def probe(
        self,
        displacement: FloatArray,
        velocity: FloatArray,
        time: float,
        actuator_state: FloatArray,
        spool: FloatArray | None = None,
    ) -> FloatArray:
        """Return the side-effect-free bearing force in the rotor domain."""

        from ALB.contracts import DirectSpoolBearingInput, UnitSystem, ValveOutput

        local = self._local_input(displacement, velocity, time)
        if self.kind == "pure":
            force = self.bearing.probe_force(local)
        elif self.kind == "direct_spool":
            if self.held_spool is None:
                raise RuntimeError("direct-spool provider has not been sampled")
            force = self.bearing.probe_force(
                DirectSpoolBearingInput(
                    local,
                    ValveOutput(self.held_spool, local.time, UnitSystem.NONDIMENSIONAL),
                )
            )
        else:
            values = self.spool(actuator_state) if spool is None else spool
            force = self.bearing.probe_force_with_spool(local, values)
        return self._rotor_force(force, local.time)

    def force_jacobian(
        self,
        displacement: FloatArray,
        velocity: FloatArray,
        time: float,
        actuator_state: FloatArray,
        options: Ros2Options,
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Return ``dF/d(x, y)``, ``dF/d(vx, vy)``, and ``dF/d actuator state``.

        Automatic differentiation is used when the runtime exposes
        ``torch_force(displacement, velocity, spool)`` returning a
        differentiable tensor in bearing-local units; otherwise central
        differences with the steps documented in :class:`Ros2Options`.
        """

        displacement = np.asarray(displacement, dtype=float).reshape(2)
        velocity = np.asarray(velocity, dtype=float).reshape(2)
        spool = (
            self.spool(actuator_state)
            if self.kind == "actuated"
            else None
        )
        blocks = None
        if callable(self.torch_force):
            blocks = self._autodiff_jacobian(displacement, velocity, time, spool)
            if not all(np.all(np.isfinite(block)) for block in blocks):
                # Feature maps such as sqrt(|x|) are not differentiable at the
                # centred journal; fall back to central differences there.
                blocks = None
        if blocks is not None:
            k_x, k_v, k_s = blocks
        else:
            k_x = _central_difference(
                lambda value: self.probe(value, velocity, time, actuator_state, spool),
                displacement,
                options.displacement_step,
                options.relative_step,
            )
            k_v = _central_difference(
                lambda value: self.probe(displacement, value, time, actuator_state, spool),
                velocity,
                options.velocity_step,
                options.relative_step,
            )
            if self.kind == "actuated":
                assert spool is not None
                k_s = _central_difference(
                    lambda value: self.probe(
                        displacement, velocity, time, actuator_state, value
                    ),
                    spool,
                    options.spool_step,
                    options.relative_step,
                    lower=-1.0,
                    upper=1.0,
                )
            else:
                k_s = np.zeros((2, 0))
        k_xi = (
            k_s @ self.spool_jacobian(actuator_state)
            if self.kind == "actuated"
            else np.zeros((2, 0))
        )
        return k_x, k_v, k_xi

    def _autodiff_jacobian(
        self,
        displacement: FloatArray,
        velocity: FloatArray,
        time: float,
        spool: FloatArray | None,
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Differentiate ``torch_force`` in local units and map to the rotor."""

        import torch

        local = self._local_input(displacement, velocity, time)
        x_scale, v_scale, f_scale = 1.0, 1.0, 1.0
        if self.adapter is not None:
            scales = self.adapter.scales
            x_scale = float(scales.Sx)
            v_scale = float(scales.Sv)
            f_scale = float(scales.Sf)
        held = None
        if self.kind == "direct_spool":
            held = torch.as_tensor(self.held_spool, dtype=torch.float64)
        local_spool = (
            torch.as_tensor(spool, dtype=torch.float64)
            if spool is not None
            else held
        )

        def force(x: Any, v: Any, s: Any) -> Any:
            return self.torch_force(x, v, s)

        x0 = torch.as_tensor(np.asarray(local.displacement), dtype=torch.float64)
        v0 = torch.as_tensor(np.asarray(local.velocity), dtype=torch.float64)
        if spool is not None:
            jac_x, jac_v, jac_s = torch.func.jacrev(force, argnums=(0, 1, 2))(
                x0, v0, local_spool
            )
            k_s = f_scale * jac_s.detach().cpu().numpy().reshape(2, -1)
        else:
            jac_x, jac_v = torch.func.jacrev(
                lambda x, v: force(x, v, local_spool), argnums=(0, 1)
            )(x0, v0)
            k_s = np.zeros((2, 0))
        k_x = (f_scale / x_scale) * jac_x.detach().cpu().numpy().reshape(2, 2)
        k_v = (f_scale / v_scale) * jac_v.detach().cpu().numpy().reshape(2, 2)
        return k_x, k_v, k_s


def _load_vector(load: Any, time: float) -> FloatArray:
    """Evaluate one rotor excitation without logging side effects."""

    evaluate = getattr(load, "force_at", None)
    return np.asarray(evaluate(time) if callable(evaluate) else load(time), dtype=float)


class Ros2CouplingIntegrator:
    """Integrate a rotor and its bearings as one ROS2 system.

    The coupled state is ``z = [x, xi]``: the continuous ROSS rotor state
    ``x = [q, dq/dt]`` followed by the actuator (servovalve) states ``xi`` of
    every actuated bearing. The right-hand side is::

        dx/dt  = A x + B g(t, z)
        dxi/dt = time_scale * (A_v xi + B_v u_k)

    where ``g`` maps load and bearing forces to the global load vector and the
    bearing forces are evaluated synchronously from the current ``z`` (no
    one-step lag). Controller commands ``u_k`` are sampled at the committed
    state every ``m`` steps and held (zero-order hold); the controller never
    enters the Jacobian.

    Each step evaluates the right-hand side twice: once at the ROS2 second
    stage and once at the committed state, which is reused as the first stage
    of the next step (sampling happens before that evaluation, so the cached
    value always uses the command held over the next step).
    """

    def __init__(
        self,
        rotor: Any,
        bindings: tuple[Any, ...],
        loads: list[Any],
        load_node_links: Any,
        time_step: float,
        options: Ros2Options | None,
    ) -> None:
        self.rotor = rotor
        self.bindings = bindings
        self.options = options if options is not None else Ros2Options()
        self.time_step = _positive_float(time_step, "time_step")
        a, b, _, _ = rotor._continuous_system()
        self._a = np.asarray(a, dtype=float)
        self._b = np.asarray(b, dtype=float)
        self._rotor_states = int(self._a.shape[0])
        self._loads = list(loads)
        self._load_node_links = [int(value) for value in np.asarray(load_node_links).reshape(-1)]
        self._bearing_nodes = [int(binding.node_link) for binding in bindings]
        self.models = tuple(
            _BindingForceModel(binding, self.time_step) for binding in bindings
        )
        displacement_idx, velocity_idx = rotor._node_state_indices(self._bearing_nodes)
        self._displacement_idx = np.asarray(displacement_idx, dtype=np.int64)
        self._velocity_idx = np.asarray(velocity_idx, dtype=np.int64)
        self._bearing_map = self._force_map(self._bearing_nodes)
        offsets = []
        offset = self._rotor_states
        for model in self.models:
            offsets.append(slice(offset, offset + model.state_count))
            offset += model.state_count
        self._slices = tuple(offsets)
        self.size = offset
        self._stepper: Ros2Stepper | None = None
        self._state: FloatArray | None = None
        self._time: float | None = None
        self._rhs_cache: FloatArray | None = None
        self._last_sampled = False
        self._steps = 0
        self.rhs_evaluations = 0
        self.jacobian_evaluations = 0

    # -- assembly helpers ----------------------------------------------------

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
            return np.zeros((0, 2)), np.zeros(self._b.shape[1])
        stacked = np.vstack([_load_vector(load, time) for load in self._loads])
        return stacked, np.asarray(
            self.rotor._node_force_vector(stacked, self._load_node_links),
            dtype=float,
        )

    def _node_kinematics(self, state: FloatArray, index: int) -> tuple[FloatArray, FloatArray]:
        rotor_state = state[: self._rotor_states]
        return (
            rotor_state[self._displacement_idx[index]].copy(),
            rotor_state[self._velocity_idx[index]].copy(),
        )

    def _assemble(
        self,
        state: FloatArray,
        bearing_forces: FloatArray,
        load_vector: FloatArray,
    ) -> FloatArray:
        rotor_state = state[: self._rotor_states]
        global_force = load_vector + self._bearing_map @ bearing_forces.reshape(-1)
        parts = [self._a @ rotor_state + self._b @ global_force]
        for model, part in zip(self.models, self._slices):
            if model.state_count:
                parts.append(model.actuator_derivative(state[part]))
        return np.concatenate(parts)

    def _stage_rhs(self, state: FloatArray, time: float, load_vector: FloatArray) -> FloatArray:
        """Evaluate ``f(z, t)`` with side-effect-free bearing probes."""

        forces = []
        for index, (model, part) in enumerate(zip(self.models, self._slices)):
            displacement, velocity = self._node_kinematics(state, index)
            try:
                forces.append(model.probe(displacement, velocity, time, state[part]))
            except Exception as exc:
                raise Ros2StageError(
                    f"ROS2 stage-2 force evaluation of bearing {index} failed "
                    f"at the predicted state (displacement {displacement!r}) "
                    f"and time {time!r}: {exc}. A frozen Jacobian may "
                    "underestimate the stiffness near the bearing wall; use "
                    "a smaller time_step or Ros2Options.jacobian_refresh"
                ) from exc
        self.rhs_evaluations += 1
        return self._assemble(state, np.vstack(forces), load_vector)

    # -- Jacobian --------------------------------------------------------------

    def jacobian(self, state: FloatArray, time: float) -> FloatArray:
        """Assemble ``df/dz`` from local bearing derivative blocks."""

        size = self.size
        n = self._rotor_states
        matrix = np.zeros((size, size))
        stiffness = np.zeros((self._b.shape[1], n))
        for index, (model, part) in enumerate(zip(self.models, self._slices)):
            displacement, velocity = self._node_kinematics(state, index)
            k_x, k_v, k_xi = model.force_jacobian(
                displacement, velocity, time, state[part], self.options
            )
            mapping = self._bearing_map[:, 2 * index:2 * index + 2]
            selector_x = np.zeros((2, n))
            selector_v = np.zeros((2, n))
            selector_x[np.arange(2), self._displacement_idx[index]] = 1.0
            selector_v[np.arange(2), self._velocity_idx[index]] = 1.0
            stiffness += mapping @ (k_x @ selector_x + k_v @ selector_v)
            if model.state_count:
                matrix[:n, part] = self._b @ mapping @ k_xi
                matrix[part, part] = model.actuator_matrix()
        matrix[:n, :n] = self._a + self._b @ stiffness
        self.jacobian_evaluations += 1
        return matrix

    # -- lifecycle -------------------------------------------------------------

    def reset(
        self,
        initial_time: float,
        commit_bearing: Callable[[int, FloatArray, FloatArray], FloatArray],
    ) -> FloatArray:
        """Sample controllers, commit step-zero forces, and factorize ``W``.

        ``commit_bearing(index, displacement, velocity)`` evaluates and
        commits one pure or direct-spool bearing through its normal lifecycle
        (the same path as the staggered integrator) and returns the rotor-domain
        force. It returns the committed bearing forces with shape ``(n, 2)``.
        """

        rotor_state = np.asarray(self.rotor.current_state(), dtype=float).reshape(-1)
        if rotor_state.shape != (self._rotor_states,):
            raise ValueError("rotor state does not match the continuous system")
        state = np.concatenate([rotor_state, np.zeros(self.size - self._rotor_states)])
        for model in self.models:
            model.command = np.zeros(len(model.channels))
            model.held_spool = None
        self._state = state
        self._time = float(initial_time)
        self._steps = 0
        _, load_vector = self._load_force(self._time)
        forces = self._commit_forces(
            state, self._time, 0, commit_bearing, load_vector
        )
        jacobian_state = state
        if self.options.jacobian_state is not None:
            supplied = np.asarray(self.options.jacobian_state, dtype=float)
            if supplied.shape == (self._rotor_states,):
                jacobian_state = np.concatenate(
                    [supplied, np.zeros(self.size - self._rotor_states)]
                )
            elif supplied.shape == (self.size,):
                jacobian_state = supplied.copy()
            else:
                raise ValueError(
                    "Ros2Options.jacobian_state must contain the rotor state "
                    f"({self._rotor_states} values) or the coupled state "
                    f"({self.size} values)"
                )
        self._stepper = Ros2Stepper(
            self.time_step,
            self.jacobian(jacobian_state, self._time),
        )
        return forces

    def _commit_forces(
        self,
        state: FloatArray,
        time: float,
        step_index: int,
        commit_bearing: Callable[[int, FloatArray, FloatArray], FloatArray],
        load_vector: FloatArray,
    ) -> FloatArray:
        """Sample due controllers, commit forces at ``state``, cache ``f``."""

        sampled = False
        forces = []
        for index, (model, part) in enumerate(zip(self.models, self._slices)):
            displacement, velocity = self._node_kinematics(state, index)
            sampled = model.sample(displacement, velocity, time, step_index) or sampled
            if model.kind == "actuated":
                forces.append(model.probe(displacement, velocity, time, state[part]))
            else:
                forces.append(
                    np.asarray(
                        commit_bearing(index, displacement, velocity),
                        dtype=float,
                    ).reshape(2)
                )
                if model.kind == "direct_spool":
                    provider = model.binding.spool_provider
                    model.held_spool = np.asarray(
                        provider.output().spool, dtype=float
                    ).copy()
        bearing_forces = np.vstack(forces)
        self.rhs_evaluations += 1
        self._rhs_cache = self._assemble(state, bearing_forces, load_vector)
        self._last_sampled = sampled
        return bearing_forces

    def advance(
        self,
        time: float,
        step_index: int,
        commit_bearing: Callable[[int, FloatArray, FloatArray], FloatArray],
    ) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
        """Advance one ROS2 step to ``time`` and commit the new state.

        Returns ``(rotor_state, bearing_forces, load_forces, load_vector)`` at
        the committed time; the rotor itself is committed by the caller.
        """

        if self._stepper is None or self._state is None or self._time is None:
            raise RuntimeError("ROS2 integrator has not been reset")
        start_time = self._time
        stage_time = float(time)
        load_forces, stage_load_vector = self._load_force(stage_time)

        def rhs(state: FloatArray, current: float) -> FloatArray:
            del current
            return self._stage_rhs(state, stage_time, stage_load_vector)

        next_state = self._stepper.step(
            rhs,
            start_time,
            self._state,
            rhs_at_state=self._rhs_cache,
        )
        if not np.all(np.isfinite(next_state)):
            raise FloatingPointError("ROS2 step produced a non-finite state")
        bearing_forces = self._commit_forces(
            next_state, stage_time, step_index, commit_bearing, stage_load_vector
        )
        self._state = next_state
        self._time = stage_time
        self._steps += 1
        refresh = self.options.jacobian_refresh
        if (
            isinstance(refresh, int) and self._steps % refresh == 0
        ) or (refresh == "control_period" and self._last_sampled):
            self._stepper.set_jacobian(self.jacobian(next_state, stage_time))
        global_force = (
            stage_load_vector + self._bearing_map @ bearing_forces.reshape(-1)
        )
        return (
            next_state[: self._rotor_states].copy(),
            bearing_forces,
            load_forces,
            global_force,
        )

    def diagnostics(self) -> dict[str, object]:
        """Return primitive integration counters for diagnostics."""

        return {
            "integrator": "ros2",
            "state_size": self.size,
            "actuator_states": self.size - self._rotor_states,
            "rhs_evaluations": self.rhs_evaluations,
            "jacobian_evaluations": self.jacobian_evaluations,
            "w_factorizations": (
                0 if self._stepper is None else self._stepper.factorizations
            ),
            "control_steps_per_period": tuple(
                model.control_steps for model in self.models
            ),
            "options": self.options.to_dict(),
        }


__all__ = [
    "INTEGRATORS",
    "ROS2_GAMMA",
    "Ros2CouplingIntegrator",
    "Ros2Options",
    "Ros2StageError",
    "Ros2Stepper",
    "ros2_stability_function",
]
