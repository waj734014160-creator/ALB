"""Analytic rotor plants and bearing test doubles for coupled integration tests.

None of these doubles needs a trained surrogate package. They implement the
native ``BearingRuntimeProtocol`` plus the optional side-effect-free hooks used
by the ROS2 integrator (``probe_force``, ``torch_force``, and the sampled
actuator contract).
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import numpy as np

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    DirectSpoolBearingInput,
    LifecycleState,
    StepContext,
    UnitSystem,
    ValveOutput,
    result_snapshot,
)


class SinglePlant:
    """One-node four-DOF mass-spring-damper plant in ROSS state ordering."""

    ndof = 4
    number_dof = 4

    def __init__(
        self,
        mass: float = 2.0,
        stiffness: float = 2.0e4,
        damping: float = 20.0,
    ) -> None:
        self.mass = float(mass)
        self.stiffness = float(stiffness)
        self.damping = float(damping)

    def _lti(self, speed: float) -> SimpleNamespace:
        del speed
        n = self.ndof
        mass = np.diag([self.mass, self.mass, 0.01, 0.01])
        stiffness = np.diag([self.stiffness, 1.3 * self.stiffness, 50.0, 50.0])
        damping = np.diag([self.damping, self.damping, 0.1, 0.1])
        inverse = np.linalg.inv(mass)
        return SimpleNamespace(
            A=np.block(
                [
                    [np.zeros((n, n)), np.eye(n)],
                    [-inverse @ stiffness, -inverse @ damping],
                ]
            ),
            B=np.vstack((np.zeros((n, n)), inverse)),
            C=np.eye(2 * n),
            D=np.zeros((2 * n, n)),
        )


ForceLaw = Callable[[np.ndarray, np.ndarray, np.ndarray | None], np.ndarray]


class AnalyticBearing:
    """Dimensional bearing whose force is an explicit function of the state.

    ``law(displacement, velocity, spool)`` returns ``[Fx, Fy]``. Every lifecycle
    evaluation and every ``probe_force`` call is counted. ``torch_law`` (same
    signature on tensors) enables automatic differentiation in ROS2.
    """

    input_dto_type: type = BearingInput
    unit_system = UnitSystem.DIMENSIONAL

    def __init__(
        self,
        law: ForceLaw,
        *,
        node_link: int = 0,
        torch_law: Callable[..., Any] | None = None,
    ) -> None:
        self.law = law
        self.node_link = node_link
        if torch_law is not None:
            self.torch_force = torch_law
        self.evaluations = 0
        self.probes = 0
        self._state = LifecycleState.NEW
        self._pending: Any = None
        self._output: BearingOutput | None = None

    @property
    def lifecycle_state(self) -> LifecycleState:
        return self._state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        return ConvergenceStatus(0.0, True)

    def _reset_for_owner(self) -> None:
        self._state = LifecycleState.READY
        self._pending = None
        self._output = None

    def _force(self, dto: Any) -> np.ndarray:
        bearing = dto.bearing if isinstance(dto, DirectSpoolBearingInput) else dto
        spool = dto.spool.spool if isinstance(dto, DirectSpoolBearingInput) else None
        return np.asarray(
            self.law(
                np.asarray(bearing.displacement, dtype=float),
                np.asarray(bearing.velocity, dtype=float),
                None if spool is None else np.asarray(spool, dtype=float),
            ),
            dtype=float,
        ).reshape(2)

    def input(self, dto: Any) -> None:
        self._pending = dto
        self._output = None
        self._state = LifecycleState.RUNNING

    def evaluate(self) -> None:
        dto = self._pending
        bearing = dto.bearing if isinstance(dto, DirectSpoolBearingInput) else dto
        self.evaluations += 1
        self._output = BearingOutput(self._force(dto), bearing.time, self.unit_system)
        self._state = LifecycleState.READY

    def output(self) -> BearingOutput:
        assert self._output is not None
        return self._output

    def step(self, dto: Any) -> BearingOutput:
        self.input(dto)
        self.evaluate()
        return self.output()

    def probe_force(self, dto: Any) -> np.ndarray:
        self.probes += 1
        return self._force(dto)

    def result_snapshot(self) -> Any:
        assert self._output is not None
        return result_snapshot({"force": self._output.force}, {"time": self._output.time})

    def failure_snapshot(self) -> Any:
        return result_snapshot({}, {})

    def diagnostic_snapshot(self) -> Any:
        return result_snapshot({}, {})


class DirectSpoolAnalyticBearing(AnalyticBearing):
    """Analytic bearing that takes an explicit spool command."""

    input_dto_type = DirectSpoolBearingInput


class LinearSpoolProvider:
    """Spool provider ``s = clip(-gain * x)`` recording every sample."""

    def __init__(self, gain: float) -> None:
        self.gain = float(gain)
        self.samples: list[float] = []
        self._output: ValveOutput | None = None
        self._pending: tuple[StepContext, BearingInput] | None = None

    def input(self, context: StepContext, bearing_input: BearingInput) -> None:
        self._pending = (context, bearing_input)

    def evaluate(self) -> None:
        assert self._pending is not None
        context, bearing_input = self._pending
        self.samples.append(context.time)
        spool = np.clip(-self.gain * np.asarray(bearing_input.displacement), -1.0, 1.0)
        self._output = ValveOutput(spool, context.time, UnitSystem.NONDIMENSIONAL)

    def output(self) -> ValveOutput:
        assert self._output is not None
        return self._output


class ActuatedAnalyticBearing(AnalyticBearing):
    """Analytic active bearing with a sampled P controller and lag valves.

    Each axis has a first-order valve ``tau * ds/dt = u - s`` and the force is
    ``law(displacement, velocity, spool)``. The controller command is
    ``u = -gain * x_measured`` and is sampled through
    ``sample_actuator_command``; the integrator owns the valve states.
    """

    def __init__(
        self,
        law: ForceLaw,
        *,
        gain: float,
        tau: float,
        control_steps: int,
        node_link: int = 0,
    ) -> None:
        super().__init__(law, node_link=node_link)
        self.gain = float(gain)
        self.tau = float(tau)
        self._control_steps = int(control_steps)
        self.samples: list[float] = []

    @property
    def control_steps_per_period(self) -> int:
        return self._control_steps

    def actuator_state_space(self) -> tuple[tuple[np.ndarray, ...], ...]:
        channel = (
            np.array([[-1.0 / self.tau]]),
            np.array([[1.0 / self.tau]]),
            np.array([[1.0]]),
            np.array([[0.0]]),
        )
        return (channel, tuple(item.copy() for item in channel))

    def sample_actuator_command(self, dto: BearingInput) -> np.ndarray:
        self.samples.append(dto.time)
        return np.clip(-self.gain * np.asarray(dto.displacement), -1.0, 1.0)

    def probe_force_with_spool(self, dto: BearingInput, spool: np.ndarray) -> np.ndarray:
        self.probes += 1
        return np.asarray(
            self.law(
                np.asarray(dto.displacement, dtype=float),
                np.asarray(dto.velocity, dtype=float),
                np.asarray(spool, dtype=float),
            ),
            dtype=float,
        ).reshape(2)


def linear_law(stiffness: float, damping: float) -> ForceLaw:
    """Return ``F = -k x - c v`` for a constant-coefficient bearing."""

    def law(displacement: np.ndarray, velocity: np.ndarray, spool: Any) -> np.ndarray:
        del spool
        return -stiffness * displacement - damping * velocity

    return law


def hardening_law(stiffness: float, damping: float, scale: float, alpha: float) -> ForceLaw:
    """Return ``F = -k0 (1 + alpha (r/scale)^2) x - c v``.

    The stiffness grows with the radial displacement ``r`` like a film
    bearing approaching the wall; ``scale`` plays the role of a clearance.
    """

    def law(displacement: np.ndarray, velocity: np.ndarray, spool: Any) -> np.ndarray:
        del spool
        ratio = float(displacement @ displacement) / scale**2
        return -stiffness * (1.0 + alpha * ratio) * displacement - damping * velocity

    return law


def hardening_torch_law(stiffness: float, damping: float, scale: float, alpha: float) -> Callable[..., Any]:
    """Return the torch version of :func:`hardening_law` for autodiff."""

    def law(displacement: Any, velocity: Any, spool: Any) -> Any:
        del spool
        ratio = (displacement * displacement).sum() / scale**2
        return -stiffness * (1.0 + alpha * ratio) * displacement - damping * velocity

    return law


def spool_law(stiffness: float, damping: float, spool_gain: float) -> ForceLaw:
    """Return ``F = -k x - c v + g * spool`` for actuated test bearings."""

    def law(displacement: np.ndarray, velocity: np.ndarray, spool: Any) -> np.ndarray:
        force = -stiffness * displacement - damping * velocity
        if spool is not None:
            force = force + spool_gain * np.asarray(spool, dtype=float)
        return force

    return law
