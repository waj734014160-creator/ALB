"""Native bearing runtime for the gas-film numerical solver."""

from __future__ import annotations

from ALB.config.gas_models import GasConfig
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    LifecycleState,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.core.diagnostics import sanitize_exception_message
from ALB.core.lifecycle import RuntimeLifecycle
from ALB.core.validation import validate_bearing_output

from .solver import _GasFilmSolver


class GasFilmRuntime:
    """Expose the gas solver through the native immutable bearing contract."""

    input_dto_type = BearingInput
    unit_system = UnitSystem.DIMENSIONAL

    def __init__(self, config: GasConfig) -> None:
        if not isinstance(config, GasConfig):
            raise TypeError("config must be GasConfig")
        self._solver = _GasFilmSolver(config)
        self.node_link = config.node_link
        self._lifecycle = RuntimeLifecycle(
            type(self).__name__,
            input_label="bearing input",
        )
        self._pending_input: BearingInput | None = None
        self._latest_output: BearingOutput | None = None
        self._latest_result: ResultBundle | None = None
        self._failure: ResultBundle | None = None
        self._convergence = ConvergenceStatus.pending("input not evaluated")
        self._reset_for_owner()

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the current runtime state."""

        return self._lifecycle.state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return cached convergence without entering the solver."""

        return self._convergence

    def _reset_for_owner(self) -> None:
        """Reset numerical state for the facade or a composite owner."""

        self._lifecycle.fail()
        self._pending_input = None
        self._latest_output = None
        self._latest_result = None
        self._failure = None
        try:
            self._solver._reset_for_owner()  # type: ignore[no-untyped-call]
        except BaseException as exc:
            self._failure = self._failure_bundle(exc, "reset")
            raise
        self._convergence = ConvergenceStatus.pending("input not evaluated")
        self._lifecycle.reset()

    def input(self, dto: BearingInput) -> None:
        """Latch one dimensional bearing input."""

        self._lifecycle.require_input_slot()
        if not isinstance(dto, BearingInput):
            raise TypeError("gas-film input must be BearingInput")
        if dto.unit_system is not UnitSystem.DIMENSIONAL:
            raise ValueError("gas-film runtime requires dimensional input")
        self._pending_input = dto
        self._latest_output = None
        self._latest_result = None
        self._convergence = ConvergenceStatus.pending("input not evaluated")
        self._lifecycle.latch()

    def evaluate(self) -> None:
        """Run one gas-film pressure solve and publish a force snapshot."""

        dto = self._pending_input
        try:
            with self._lifecycle.evaluation():
                assert dto is not None
                self._solver.input(  # type: ignore[no-untyped-call]
                    dto.displacement,
                    dto.velocity,
                    t=dto.time,
                    nodim=False,
                )
                raw = self._solver.output(  # type: ignore[no-untyped-call]
                    nodim=False
                )
                force = validate_bearing_output(raw)
                output = BearingOutput(
                    force,
                    dto.time,
                    UnitSystem.DIMENSIONAL,
                )
                converged = bool(
                    self._solver.calc_is_finished()  # type: ignore[no-untyped-call]
                )
                self._convergence = (
                    ConvergenceStatus(
                        0.0,
                        True,
                        iterations=int(self._solver.final_iter) + 1,
                        message="gas-film calculation completed",
                    )
                    if converged
                    else ConvergenceStatus.pending(
                        "gas-film calculation did not converge"
                    )
                )
                self._latest_output = output
                self._latest_result = result_snapshot(
                    {
                        "force": output.force,
                        "pressure": self._solver.main_model.latest_result,
                    },
                    {
                        "schema": "alb.gas-film-result.v0.4",
                        "time": dto.time,
                        "unit_system": output.unit_system.value,
                        "converged": converged,
                    },
                )
                self._pending_input = None
        except BaseException as exc:
            self._latest_output = None
            self._latest_result = None
            self._failure = self._failure_bundle(exc, "evaluate")
            raise

    def output(self) -> BearingOutput:
        """Return the completed force without running the solver."""

        self._lifecycle.require_output()
        assert self._latest_output is not None
        return self._latest_output

    def step(self, dto: BearingInput) -> BearingOutput:
        """Compose input, evaluate, and output."""

        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> ResultBundle:
        """Return the complete current gas-film result."""

        self._lifecycle.require_output()
        assert self._latest_result is not None
        return self._latest_result

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest sealed gas-film failure."""

        if self._failure is None:
            raise RuntimeError("no gas-film failure is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable runtime diagnostics."""

        return result_snapshot(
            {},
            {
                "schema": "alb.gas-film-diagnostic.v0.4",
                "lifecycle_state": self.lifecycle_state.value,
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
                "converged": self._convergence.converged,
                "has_result": self._latest_result is not None,
                "has_failure": self._failure is not None,
            },
        )

    def _failure_bundle(
        self,
        error: BaseException,
        phase: str,
    ) -> ResultBundle:
        return result_snapshot(
            {},
            {
                "schema": "alb.gas-film-failure.v0.4",
                "phase": phase,
                "error_type": type(error).__name__,
                "message": sanitize_exception_message(error),
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
            },
        )


__all__ = ["GasFilmRuntime"]
