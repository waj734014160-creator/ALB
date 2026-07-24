"""Native bearing runtime for an ALBNN 0.4 package."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    DirectSpoolBearingInput,
    LifecycleState,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.contracts.numeric import finite_real_array
from ALB.core.diagnostics import sanitize_exception_message
from ALB.core.lifecycle import RuntimeLifecycle


class _SurrogateModelProtocol(Protocol):
    def input(self, *args: Any, **kwargs: Any) -> None: ...

    def output(self, *args: Any, **kwargs: Any) -> Any: ...


class SurrogateBearingRuntime:
    """Evaluate one packaged ALBNN through the bearing DTO lifecycle."""

    def __init__(
        self,
        model: _SurrogateModelProtocol,
        *,
        unit_system: UnitSystem | str,
        node_link: int | None,
        external_spool: bool,
        fixed_spool: object = (0.0, 0.0),
    ) -> None:
        self._model = model
        self.unit_system = UnitSystem.coerce(unit_system)
        self.node_link = node_link
        self.input_dto_type = (
            DirectSpoolBearingInput if external_spool else BearingInput
        )
        self._fixed_spool = finite_real_array(
            fixed_spool,
            "fixed spool",
            shape=(2,),
        )
        if np.any(np.abs(self._fixed_spool) > 1.0):
            raise ValueError("fixed spool values must be within [-1, 1]")
        self._lifecycle = RuntimeLifecycle(
            type(self).__name__,
            input_label="bearing input",
        )
        self._pending: BearingInput | DirectSpoolBearingInput | None = None
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
        """Return cached inference convergence."""

        return self._convergence

    def _reset_for_owner(self) -> None:
        """Reset only lifecycle caches; the packaged model is stateless."""

        self._lifecycle.fail()
        self._pending = None
        self._latest_output = None
        self._latest_result = None
        self._failure = None
        self._convergence = ConvergenceStatus.pending("input not evaluated")
        self._lifecycle.reset()

    def input(self, dto: Any) -> None:
        """Latch one ordinary or direct-spool DTO."""

        self._lifecycle.require_input_slot()
        if not isinstance(dto, self.input_dto_type):
            label = (
                "DirectSpoolBearingInput"
                if self.input_dto_type is DirectSpoolBearingInput
                else "BearingInput"
            )
            raise TypeError(f"surrogate input must be {label}")
        bearing = dto.bearing if isinstance(dto, DirectSpoolBearingInput) else dto
        if bearing.unit_system is not self.unit_system:
            raise ValueError("surrogate input unit_system does not match runtime")
        self._pending = dto
        self._latest_output = None
        self._latest_result = None
        self._convergence = ConvergenceStatus.pending("input not evaluated")
        self._lifecycle.latch()

    def evaluate(self) -> None:
        """Run exactly one restricted package inference."""

        dto = self._pending
        try:
            with self._lifecycle.evaluation():
                assert dto is not None
                bearing = (
                    dto.bearing
                    if isinstance(dto, DirectSpoolBearingInput)
                    else dto
                )
                spool = (
                    dto.spool.spool
                    if isinstance(dto, DirectSpoolBearingInput)
                    else self._fixed_spool
                )
                nodim = self.unit_system is UnitSystem.NONDIMENSIONAL
                self._model.input(
                    bearing.displacement,
                    bearing.velocity,
                    spool,
                    nodim=nodim,
                )
                force = finite_real_array(
                    self._model.output(nodim=nodim),
                    "surrogate force",
                ).reshape(-1)
                if force.shape != (2,):
                    raise ValueError(
                        "packaged surrogate force must contain two values"
                    )
                output = BearingOutput(
                    force,
                    bearing.time,
                    self.unit_system,
                )
                self._latest_output = output
                self._latest_result = result_snapshot(
                    {"force": force, "spool": spool},
                    {
                        "schema": "alb.surrogate-bearing-result.v0.4",
                        "time": bearing.time,
                        "unit_system": self.unit_system.value,
                        "external_spool": isinstance(
                            dto,
                            DirectSpoolBearingInput,
                        ),
                        "converged": True,
                    },
                )
                self._convergence = ConvergenceStatus(
                    0.0,
                    True,
                    message="surrogate inference completed",
                )
                self._pending = None
        except BaseException as exc:
            self._latest_output = None
            self._latest_result = None
            self._failure = result_snapshot(
                {},
                {
                    "schema": "alb.surrogate-bearing-failure.v0.4",
                    "phase": "evaluate",
                    "error_type": type(exc).__name__,
                    "message": sanitize_exception_message(exc),
                    "unit_system": self.unit_system.value,
                    "node_link": self.node_link,
                },
            )
            raise

    def output(self) -> BearingOutput:
        """Return the completed result without inference."""

        self._lifecycle.require_output()
        assert self._latest_output is not None
        return self._latest_output

    def step(self, dto: Any) -> BearingOutput:
        """Compose input, evaluate, and output."""

        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> ResultBundle:
        """Return the complete immutable inference result."""

        self._lifecycle.require_output()
        assert self._latest_result is not None
        return self._latest_result

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest sealed inference failure."""

        if self._failure is None:
            raise RuntimeError("no surrogate failure is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable lifecycle diagnostics."""

        return result_snapshot(
            {},
            {
                "schema": "alb.surrogate-bearing-diagnostic.v0.4",
                "lifecycle_state": self.lifecycle_state.value,
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
                "converged": self._convergence.converged,
                "has_result": self._latest_result is not None,
                "has_failure": self._failure is not None,
            },
        )


__all__ = ["SurrogateBearingRuntime"]
