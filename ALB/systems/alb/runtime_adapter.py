"""Temporary strict runtime facade for pre-0.3 ALB implementations."""

from __future__ import annotations

from typing import Generic, TypeVar

from ALB.contracts import (
    BearingOutput,
    ConvergenceStatus,
    LifecycleState,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.core.lifecycle import RuntimeLifecycle


InputT = TypeVar("InputT")


class LegacyBearingRuntimeAdapter(Generic[InputT]):
    """Expose one legacy ALB through the strict runtime contract.

    This adapter is intentionally temporary for 0.3.x.  It executes the
    wrapped block exactly once during :meth:`evaluate`; :meth:`output` only
    reads the completed DTO.  Native ALB runtimes replace this adapter in the
    next implementation stage.
    """

    def __init__(self, block, implementation) -> None:
        self._block = block
        self._implementation = implementation
        self.unit_system = UnitSystem.coerce(block.unit_system)
        self.node_link = block.node_link
        self._lifecycle = RuntimeLifecycle(
            type(implementation).__name__,
            input_label="bearing input",
        )
        self._latest_output: BearingOutput | None = None
        self._latest_result: ResultBundle | None = None
        self._failure: ResultBundle | None = None
        self._convergence_status = ConvergenceStatus.pending(
            "runtime is not initialized"
        )

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the strict facade lifecycle state."""

        return self._lifecycle.state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return cached convergence without querying mutable solver state."""

        return self._convergence_status

    def init(self) -> None:
        """Reset the implementation and expose no stale result on failure."""

        self._lifecycle.fail()
        self._latest_output = None
        self._latest_result = None
        self._failure = None
        try:
            self._implementation.init()
        except BaseException as exc:
            self._failure = self._build_failure_snapshot(exc, "init")
            raise
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.reset()

    def input(self, dto: InputT) -> None:
        """Validate and latch one DTO without advancing numerical state."""

        self._lifecycle.require_input_slot()
        self._block.input(dto)
        self._latest_output = None
        self._latest_result = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.latch()

    def evaluate(self) -> None:
        """Execute the legacy implementation exactly once under failure sealing."""

        try:
            with self._lifecycle.evaluation():
                self._block.evaluate()
                output = self._block.output()
                self._latest_output = output
                block_status = getattr(self._block, "convergence_status", None)
                if isinstance(block_status, ConvergenceStatus):
                    self._convergence_status = block_status
                else:
                    completed = bool(self._implementation.calc_is_finished())
                    self._convergence_status = (
                        ConvergenceStatus(
                            0.0,
                            True,
                            message="legacy calculation finished",
                        )
                        if completed
                        else ConvergenceStatus.pending(
                            "legacy calculation is incomplete"
                        )
                    )
                self._latest_result = result_snapshot(
                    {"force": output.force},
                    {
                        "schema": "alb.bearing-runtime-result.v1",
                        "time": output.time,
                        "unit_system": output.unit_system.value,
                        "converged": self._convergence_status.converged,
                    },
                )
        except BaseException as exc:
            self._latest_output = None
            self._latest_result = None
            self._failure = self._build_failure_snapshot(exc, "evaluate")
            raise

    def output(self) -> BearingOutput:
        """Read the completed port output without numerical work."""

        self._lifecycle.require_output()
        assert self._latest_output is not None
        return self._latest_output

    def step(self, dto: InputT) -> BearingOutput:
        """Compose input, evaluation, and output without physical-step commit."""

        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> ResultBundle:
        """Return the complete current immutable result."""

        self._lifecycle.require_output()
        assert self._latest_result is not None
        return self._latest_result

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest sealed failure without reopening the runtime."""

        if self._failure is None:
            raise RuntimeError("no bearing runtime failure is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable state and convergence diagnostics."""

        return result_snapshot(
            {},
            {
                "schema": "alb.bearing-runtime-diagnostic.v1",
                "lifecycle_state": self.lifecycle_state.value,
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
                "converged": self._convergence_status.converged,
                "has_result": self._latest_result is not None,
                "has_failure": self._failure is not None,
            },
        )

    def _build_failure_snapshot(
        self,
        error: BaseException,
        phase: str,
    ) -> ResultBundle:
        return result_snapshot(
            {},
            {
                "schema": "alb.bearing-runtime-failure.v1",
                "phase": phase,
                "error_type": type(error).__name__,
                "message": str(error),
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
            },
        )


__all__ = ["LegacyBearingRuntimeAdapter"]
