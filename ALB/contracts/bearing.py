"""Bearing-side computation and runtime contracts."""

from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

import numpy as np
import numpy.typing as npt

from .block import EvaluableBlock
from .lifecycle import LifecycleState
from .model import ConvergenceStatus
from .ports import (
    BearingInput,
    BearingOutput,
    DirectSpoolBearingInput,
    ValveOutput,
)
from .results import ResultBundle
from .types import StepContext, UnitSystem

InputT = TypeVar("InputT")


@runtime_checkable
class BearingProtocol(EvaluableBlock[BearingInput, BearingOutput], Protocol):
    """Standard two-axis bearing computation port."""

    node_link: int | None
    unit_system: UnitSystem


@runtime_checkable
class BearingRuntimeProtocol(Protocol, Generic[InputT]):
    """Strict auto-initialized bearing runtime with immutable diagnostics."""

    node_link: int | None
    unit_system: UnitSystem
    input_dto_type: type[InputT]

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the current runtime state without advancing computation."""

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return the most recent local convergence status."""

    def input(self, dto: InputT) -> None:
        """Validate and latch one input while invalidating prior output."""

    def evaluate(self) -> None:
        """Evaluate the latched input exactly once."""

    def output(self) -> BearingOutput:
        """Read the current completed port output without computation."""

    def step(self, dto: InputT) -> BearingOutput:
        """Compose input, evaluation, and output without committing time."""

    def result_snapshot(self) -> ResultBundle:
        """Return the complete current immutable numerical result."""

    def failure_snapshot(self) -> ResultBundle:
        """Return the most recent sealed numerical failure diagnostic."""

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable runtime diagnostics for normal or failed state."""


@runtime_checkable
class DirectSpoolBearingRuntimeProtocol(
    BearingRuntimeProtocol[DirectSpoolBearingInput],
    Protocol,
):
    """Strict runtime whose input explicitly includes normalized spool state."""


@runtime_checkable
class SpoolCommandProviderProtocol(Protocol):
    """Produce one time-aligned normalized spool command for a coupled bearing."""

    def input(self, context: "StepContext", bearing_input: BearingInput) -> None:
        """Latch the global step and current rotor-domain bearing state."""

    def evaluate(self) -> None:
        """Compute one spool command."""

    def output(self) -> ValveOutput:
        """Read the completed normalized spool command."""


@runtime_checkable
class BearingUnitAdapterProtocol(Protocol):
    """Convert rotor-domain bearing ports through an explicit scale set."""

    scales: Any

    def rotor_context_to_bearing(self, context: StepContext) -> StepContext:
        """Return the bearing-local step context."""

    def rotor_input_to_bearing(self, value: BearingInput) -> BearingInput:
        """Convert a rotor-domain bearing input."""

    def rotor_direct_spool_to_bearing(
        self, value: DirectSpoolBearingInput
    ) -> DirectSpoolBearingInput:
        """Convert direct-spool state while preserving normalized spool."""

    def bearing_output_to_rotor(self, value: BearingOutput) -> BearingOutput:
        """Convert bearing force back to the rotor domain."""


@runtime_checkable
class ForceProbeProtocol(Protocol):
    """Bearing runtime that can evaluate force without side effects.

    ``probe_force`` returns the two-component force for one bearing-local DTO
    (``BearingInput`` or, for direct-spool runtimes, ``DirectSpoolBearingInput``)
    in the runtime's own units. It must not publish lifecycle output, replace
    the latest committed result, or advance any time-integrated state, so a
    coupled integrator may call it at intermediate stage states (ROS2).
    Solver scratch buffers may be overwritten.
    """

    def probe_force(self, dto: Any) -> npt.NDArray[np.float64]:
        """Return the force for ``dto`` without committing anything."""


@runtime_checkable
class SampledActuatorBearingProtocol(Protocol):
    """Active bearing exposing its sampled controller and actuator dynamics.

    A coupled integrator that owns the actuator states uses these hooks: it
    samples the controller every ``control_steps_per_period`` steps, holds the
    returned command, integrates each actuator channel's continuous
    state-space model (bearing-local time units), and evaluates the bearing
    force for the resulting spool opening without side effects.
    """

    @property
    def control_steps_per_period(self) -> int:
        """Return the simulation steps per controller sample."""

    def actuator_state_space(
        self,
    ) -> tuple[
        tuple[
            npt.NDArray[np.float64],
            npt.NDArray[np.float64],
            npt.NDArray[np.float64],
            npt.NDArray[np.float64],
        ],
        ...,
    ]:
        """Return continuous ``(A, B, C, D)`` for every actuator channel."""

    def sample_actuator_command(
        self,
        dto: BearingInput,
    ) -> npt.NDArray[np.float64]:
        """Run the controller once for the measured state; return the command."""

    def probe_force_with_spool(
        self,
        dto: BearingInput,
        spool: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        """Return the force for an explicit spool opening without side effects."""


@runtime_checkable
class BearingCoefficientProtocol(Protocol):
    """Optional local-linear coefficient capability."""

    @property
    def K(self) -> npt.NDArray[np.float64]:
        """Return the 2-by-2 stiffness matrix."""

    @property
    def C(self) -> npt.NDArray[np.float64]:
        """Return the 2-by-2 damping matrix."""

    @property
    def G_xv(self) -> npt.NDArray[np.complex128]:
        """Return the complex 2-by-2 spool-force transfer matrix."""


__all__ = [
    "BearingCoefficientProtocol",
    "BearingProtocol",
    "BearingRuntimeProtocol",
    "BearingUnitAdapterProtocol",
    "DirectSpoolBearingRuntimeProtocol",
    "ForceProbeProtocol",
    "SampledActuatorBearingProtocol",
    "SpoolCommandProviderProtocol",
]
