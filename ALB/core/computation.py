"""Reusable implementations of the strict computational-block lifecycle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class LatchedComputationalBlock(Generic[InputT, OutputT], ABC):
    """Implement input/output freshness while leaving numerical work explicit."""

    def __init__(self) -> None:
        self._latched_input: InputT | None = None
        self._completed_output: OutputT | None = None
        self._input_generation = 0
        self._output_generation = -1

    def input(self, dto: InputT) -> None:
        """Validate and latch input while invalidating the previous result."""

        self._latched_input = self._validate_input(dto)
        self._input_generation += 1
        self._completed_output = None
        self._output_generation = -1

    def output(self) -> OutputT:
        """Read a fresh completed result without computing or advancing state."""

        if (
            self._latched_input is None
            or self._completed_output is None
            or self._output_generation != self._input_generation
        ):
            raise RuntimeError("output is unavailable until the current input is computed")
        return self._completed_output

    def step(self, dto: InputT) -> OutputT:
        """Run one local computation without committing a physical time step."""

        self.input(dto)
        self._execute_latched()
        return self.output()

    def _require_input(self) -> InputT:
        if self._latched_input is None:
            raise RuntimeError("input must be latched before computation")
        return self._latched_input

    def _publish_output(self, result: OutputT) -> None:
        if self._latched_input is None:
            raise RuntimeError("cannot publish output without latched input")
        self._completed_output = result
        self._output_generation = self._input_generation

    def _validate_input(self, dto: InputT) -> InputT:
        return dto

    @abstractmethod
    def _execute_latched(self) -> None:
        """Invoke the domain-specific explicit computation method."""


class SolvingBlock(LatchedComputationalBlock[InputT, OutputT], ABC):
    """Base for blocks whose explicit operation is ``solve``."""

    @abstractmethod
    def solve(self) -> None:
        """Solve the currently latched input and publish an output."""

    def _execute_latched(self) -> None:
        self.solve()


class EvaluatingBlock(LatchedComputationalBlock[InputT, OutputT], ABC):
    """Base for blocks whose explicit operation is ``evaluate``."""

    @abstractmethod
    def evaluate(self) -> None:
        """Evaluate the currently latched input and publish an output."""

    def _execute_latched(self) -> None:
        self.evaluate()


class CommandComputingBlock(LatchedComputationalBlock[InputT, OutputT], ABC):
    """Base for blocks whose explicit operation computes a command."""

    @abstractmethod
    def compute_command(self) -> None:
        """Compute a command from the currently latched input."""

    def _execute_latched(self) -> None:
        self.compute_command()


class StateAdvancingBlock(LatchedComputationalBlock[InputT, OutputT], ABC):
    """Base for stateful blocks whose explicit operation is ``advance``."""

    @abstractmethod
    def advance(self) -> None:
        """Advance state from the currently latched input."""

    def _execute_latched(self) -> None:
        self.advance()
