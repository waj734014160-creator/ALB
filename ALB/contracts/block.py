"""Generic Simulink-style computational block contracts."""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar, runtime_checkable


InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


@runtime_checkable
class ComputationalBlock(Protocol, Generic[InputT, OutputT]):
    """Latch input, execute explicitly, and expose only completed output."""

    def input(self, dto: InputT) -> None:
        """Validate and latch input while invalidating any previous output."""

    def output(self) -> OutputT:
        """Return the completed result or raise when it is stale or missing."""

    def step(self, dto: InputT) -> OutputT:
        """Compose input, explicit computation, and output without committing time."""


@runtime_checkable
class SolvableBlock(ComputationalBlock[InputT, OutputT], Protocol):
    """Computational block whose explicit operation is ``solve``."""

    def solve(self) -> None:
        """Solve the currently latched input and publish a result."""


@runtime_checkable
class EvaluableBlock(ComputationalBlock[InputT, OutputT], Protocol):
    """Computational block whose explicit operation is ``evaluate``."""

    def evaluate(self) -> None:
        """Evaluate the currently latched input and publish a result."""


@runtime_checkable
class CommandBlock(ComputationalBlock[InputT, OutputT], Protocol):
    """Computational block whose explicit operation computes a command."""

    def compute_command(self) -> None:
        """Compute a command from the currently latched input."""


@runtime_checkable
class AdvancingBlock(ComputationalBlock[InputT, OutputT], Protocol):
    """Stateful block whose explicit operation advances internal state."""

    def advance(self) -> None:
        """Advance from the currently latched input and publish the new state."""
