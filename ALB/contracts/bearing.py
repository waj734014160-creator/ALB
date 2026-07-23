"""Bearing-side computation and runtime contracts."""

from typing import Generic, Protocol, TypeVar, runtime_checkable

import numpy as np
import numpy.typing as npt

from .block import EvaluableBlock
from .lifecycle import LifecycleState
from .model import ConvergenceStatus
from .ports import BearingInput, BearingOutput, DirectSpoolBearingInput
from .results import ResultBundle
from .types import UnitSystem


InputT = TypeVar("InputT", contravariant=True)


@runtime_checkable
class BearingProtocol(EvaluableBlock[BearingInput, BearingOutput], Protocol):
    """Standard two-axis bearing computation port."""

    node_link: int | None
    unit_system: UnitSystem


@runtime_checkable
class BearingRuntimeProtocol(Protocol, Generic[InputT]):
    """Strict initialized bearing runtime with immutable diagnostic exits."""

    node_link: int | None
    unit_system: UnitSystem
    input_dto_type: type[InputT]

    def init(self) -> None:
        """Start a fresh runtime session after child initialization succeeds."""

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
    "DirectSpoolBearingRuntimeProtocol",
]
