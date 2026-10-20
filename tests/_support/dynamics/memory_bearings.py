"""Black-box bearing test doubles with internal memory (ALB 0.4.7).

Both doubles evaluate everything inside the normal ``input`` / ``evaluate`` /
``output`` lifecycle and expose no ``probe_force``: the force is not a
side-effect-free function of the rotor state, so ROS2 rejects them, while the
predictor-corrector integrator trials them through ``checkpoint()`` and
``restore()``. Their tokens are plain tuples of the explicit state, which is
how explicit-state models (a thermal-memory MLP, an LSTM ``(h, c)``) are
expected to implement the protocol.

Instrumentation that must survive rollbacks (``lifecycle_evaluations``,
``controller_runs``) is kept outside the tokens on purpose.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    LifecycleState,
    UnitSystem,
    result_snapshot,
)


class _LifecycleDouble:
    """Strict-enough lifecycle shared by the memory doubles."""

    input_dto_type: type = BearingInput
    unit_system = UnitSystem.DIMENSIONAL
    probe_force = None

    def __init__(self, node_link: int = 0) -> None:
        self.node_link = node_link
        self._state = LifecycleState.NEW
        self._pending: BearingInput | None = None
        self._output: BearingOutput | None = None
        self._result: Any = None
        self.lifecycle_evaluations = 0

    @property
    def lifecycle_state(self) -> LifecycleState:
        return self._state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        return ConvergenceStatus(0.0, True)

    def input(self, dto: BearingInput) -> None:
        if self._state is not LifecycleState.READY:
            raise RuntimeError(f"{type(self).__name__} is not ready")
        if not isinstance(dto, BearingInput):
            raise TypeError("memory bearing input must be BearingInput")
        self._pending = dto
        self._output = None
        self._result = None
        self._state = LifecycleState.RUNNING

    def output(self) -> BearingOutput:
        if self._state is not LifecycleState.READY or self._output is None:
            raise RuntimeError("output is unavailable until evaluate() completes")
        return self._output

    def step(self, dto: BearingInput) -> BearingOutput:
        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> Any:
        if self._result is None:
            raise RuntimeError("no result is available")
        return self._result

    def failure_snapshot(self) -> Any:
        return result_snapshot({}, {})

    def diagnostic_snapshot(self) -> Any:
        return result_snapshot({}, {"lifecycle_state": self._state.value})

    def evaluate(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class MemoryAnalyticBearing(_LifecycleDouble):
    """Bearing whose stiffness relaxes towards an eccentricity equilibrium.

    ``F = -k(t) x - c v`` with ``tau dk/dt = k_eq(x) - k`` and the hardening
    equilibrium ``k_eq(x) = k0 (1 + alpha |x|^2 / scale^2)``. Every lifecycle
    evaluation at time ``t`` advances the memory from the committed state
    with the second-order exponential-trapezoid update::

        a = exp(-(t - t_c) / tau)
        k = a k_c + (1 - a) (u_c + k_eq(x)) / 2

    where ``(k_c, u_c, t_c)`` is the committed memory. The first evaluation
    starts at equilibrium. ``tau`` should be much larger than the step.
    ``history`` records ``(t, k)`` for every committed evaluation.
    """

    def __init__(
        self,
        *,
        stiffness: float,
        damping: float,
        scale: float,
        alpha: float,
        tau: float,
        node_link: int = 0,
        fail_above: float | None = None,
    ) -> None:
        super().__init__(node_link)
        self.stiffness = float(stiffness)
        self.damping = float(damping)
        self.scale = float(scale)
        self.alpha = float(alpha)
        self.tau = float(tau)
        self.fail_above = fail_above
        self._memory: tuple[float, float, float] | None = None
        self.history: list[tuple[float, float]] = []

    def equilibrium_stiffness(self, displacement: np.ndarray) -> float:
        ratio = float(displacement @ displacement) / self.scale**2
        return self.stiffness * (1.0 + self.alpha * ratio)

    def _reset_for_owner(self) -> None:
        self._state = LifecycleState.READY
        self._pending = None
        self._output = None
        self._result = None
        self._memory = None
        self.history = []

    def evaluate(self) -> None:
        dto = self._pending
        if self._state is not LifecycleState.RUNNING or dto is None:
            raise RuntimeError("a new bearing input is required before evaluate()")
        self.lifecycle_evaluations += 1
        displacement = np.asarray(dto.displacement, dtype=float)
        velocity = np.asarray(dto.velocity, dtype=float)
        if self.fail_above is not None and float(np.max(np.abs(displacement))) > self.fail_above:
            self._state = LifecycleState.FAILED
            raise RuntimeError("memory bearing left its admissible range")
        target = self.equilibrium_stiffness(displacement)
        if self._memory is None:
            stiffness = target
        else:
            committed, committed_target, committed_time = self._memory
            decay = math.exp(-(float(dto.time) - committed_time) / self.tau)
            stiffness = decay * committed + (1.0 - decay) * 0.5 * (
                committed_target + target
            )
        self._memory = (stiffness, target, float(dto.time))
        self.history.append((float(dto.time), stiffness))
        force = -stiffness * displacement - self.damping * velocity
        self._output = BearingOutput(force, dto.time, self.unit_system)
        self._result = result_snapshot(
            {"force": force, "stiffness": stiffness},
            {"time": dto.time},
        )
        self._pending = None
        self._state = LifecycleState.READY

    @property
    def memory(self) -> tuple[float, float, float] | None:
        """Return the committed ``(k, k_eq, t)`` memory."""

        return self._memory

    def checkpoint(self) -> object:
        """Copy the explicit memory and lifecycle state into a token."""

        return (
            self,
            self._state,
            self._pending,
            self._output,
            self._result,
            self._memory,
            len(self.history),
        )

    def restore(self, token: object) -> None:
        """Return to the state captured by :meth:`checkpoint`."""

        owner, state, pending, output, result, memory, length = token  # type: ignore[misc]
        if owner is not self:
            raise ValueError("checkpoint token belongs to another runtime")
        self._state = state
        self._pending = pending
        self._output = output
        self._result = result
        self._memory = memory
        del self.history[length:]


class SampledActiveAnalyticBearing(_LifecycleDouble):
    """Active bearing with an internal sampled controller and lag valves.

    Everything runs inside ``evaluate``, as in the native active bearing:

    * the controller ``u = clip(-gain x, -1, 1)`` runs when the evaluation
      counter is a multiple of ``control_steps`` and its command is held
      between samples (``samples`` lists the sample times);
    * each axis has a first-order valve ``tau ds/dt = u - s``. With
      ``valve_hold="first_order"`` (default, like the native servovalve) the
      valve input is interpolated linearly between evaluations, so a new
      command enters ramped over the step that ends at its sampling instant.
      ``valve_hold="zero_order"`` integrates the step with the command that
      was held during it, i.e. a new command acts from its sampling instant
      on (the exact sampled-data semantics). The first evaluation publishes
      ``s = 0``;
    * the force is ``-k x - c v + spool_gain s``.
    """

    def __init__(
        self,
        *,
        stiffness: float,
        damping: float,
        spool_gain: float,
        gain: float,
        tau: float,
        control_steps: int,
        node_link: int = 0,
        valve_hold: str = "first_order",
    ) -> None:
        super().__init__(node_link)
        if valve_hold not in {"first_order", "zero_order"}:
            raise ValueError("valve_hold must be 'first_order' or 'zero_order'")
        self.valve_hold = valve_hold
        self.stiffness = float(stiffness)
        self.damping = float(damping)
        self.spool_gain = float(spool_gain)
        self.gain = float(gain)
        self.tau = float(tau)
        self.control_steps = int(control_steps)
        self.controller_runs = 0
        self._reset_memory()

    def _reset_memory(self) -> None:
        self._counter = 0
        self._held: np.ndarray | None = None
        self._spool = np.zeros(2)
        self._valve_input = np.zeros(2)
        self._valve_time: float | None = None
        self.samples: list[float] = []

    def _reset_for_owner(self) -> None:
        self._state = LifecycleState.READY
        self._pending = None
        self._output = None
        self._result = None
        self._reset_memory()

    def evaluate(self) -> None:
        dto = self._pending
        if self._state is not LifecycleState.RUNNING or dto is None:
            raise RuntimeError("a new bearing input is required before evaluate()")
        self.lifecycle_evaluations += 1
        time = float(dto.time)
        displacement = np.asarray(dto.displacement, dtype=float)
        velocity = np.asarray(dto.velocity, dtype=float)
        sample = self._counter % self.control_steps == 0
        self._counter += 1
        if sample or self._held is None:
            self.controller_runs += 1
            self._held = np.clip(-self.gain * displacement, -1.0, 1.0)
            self.samples.append(time)
        command = self._held.copy()
        if self._valve_time is None:
            spool = np.zeros(2)
            previous_input = np.zeros(2)
        elif self.valve_hold == "zero_order":
            step = time - self._valve_time
            decay = math.exp(-step / self.tau)
            previous_input = self._valve_input
            spool = decay * self._spool + (1.0 - decay) * previous_input
        else:
            step = time - self._valve_time
            decay = math.exp(-step / self.tau)
            current_weight = 1.0 - self.tau / step * (1.0 - decay)
            previous_weight = (1.0 - decay) - current_weight
            previous_input = self._valve_input
            spool = (
                decay * self._spool
                + previous_weight * previous_input
                + current_weight * command
            )
        self._spool = spool
        self._valve_input = command
        self._valve_time = time
        force = (
            -self.stiffness * displacement
            - self.damping * velocity
            + self.spool_gain * spool
        )
        self._output = BearingOutput(force, dto.time, self.unit_system)
        self._result = result_snapshot(
            {"force": force, "spool": spool.copy(), "command": command},
            {"time": dto.time},
        )
        self._pending = None
        self._state = LifecycleState.READY

    @property
    def control_counter(self) -> int:
        """Return the number of committed evaluations seen by the controller."""

        return self._counter

    def checkpoint(self) -> object:
        """Copy the controller, valve, and lifecycle state into a token."""

        return (
            self,
            self._state,
            self._pending,
            self._output,
            self._result,
            self._counter,
            None if self._held is None else self._held.copy(),
            self._spool.copy(),
            self._valve_input.copy(),
            self._valve_time,
            len(self.samples),
        )

    def restore(self, token: object) -> None:
        """Return to the state captured by :meth:`checkpoint`."""

        (
            owner,
            state,
            pending,
            output,
            result,
            counter,
            held,
            spool,
            valve_input,
            valve_time,
            length,
        ) = token  # type: ignore[misc]
        if owner is not self:
            raise ValueError("checkpoint token belongs to another runtime")
        self._state = state
        self._pending = pending
        self._output = output
        self._result = result
        self._counter = counter
        self._held = None if held is None else held.copy()
        self._spool = spool.copy()
        self._valve_input = valve_input.copy()
        self._valve_time = valve_time
        del self.samples[length:]


__all__ = ["MemoryAnalyticBearing", "SampledActiveAnalyticBearing"]
