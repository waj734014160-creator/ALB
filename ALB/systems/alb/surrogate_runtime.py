"""Strict bearing runtime backed by an ALBNN inference model."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    LifecycleState,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode
from ALB.contracts.numeric import finite_real_array
from ALB.core.component import BaseSimpleModel
from ALB.core.lifecycle import RuntimeLifecycle

if TYPE_CHECKING:
    from ALB.surrogate.inference import ALBNet


class _SpoolState:
    """Minimal explicit spool state used by existing ALB assembly wiring."""

    def __init__(self) -> None:
        self.xv = 0.0

    def input(self, xv) -> None:
        self.xv = float(xv)

    def output(self) -> None:
        return None


class ALBNNAgent(BaseSimpleModel):
    """Evaluate one ALBNN force sample with strict input/output semantics."""

    input_dto_type = BearingInput
    def __init__(
        self,
        net: "ALBNet",
        agent: str | None = None,
        *,
        unit_system: UnitSystem | str = UnitSystem.DIMENSIONAL,
        node_link: int | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.alb_net = net
        self.agent = "ALBNNAgent" if agent is None else str(agent)
        if self.agent not in {"ALBNNAgent", "HydroNNAgent", "HybridNNAgent"}:
            raise ValueError(
                "agent must be ALBNNAgent, HydroNNAgent, or HybridNNAgent"
            )
        self.unit_system = UnitSystem.coerce(unit_system)
        self.node_link = node_link
        self.of = [_SpoolState(), _SpoolState()]
        self._lifecycle = RuntimeLifecycle(
            type(self).__name__,
            input_label="bearing input",
        )
        self._pending_input: BearingInput | None = None
        self._latest_output: BearingOutput | None = None
        self._latest_result: ResultBundle | None = None
        self._failure: ResultBundle | None = None
        self._convergence_status = ConvergenceStatus.pending(
            "runtime is not initialized"
        )
        self.uxy: np.ndarray | None = None
        self.uxyt: np.ndarray | None = None
        self.t = 0.0
        self.xv: np.ndarray | None = None
        self.force = np.zeros(2, dtype=float)
        self._results = self._empty_results()

    @staticmethod
    def _empty_results() -> pd.DataFrame:
        return pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the current strict runtime state."""

        return self._lifecycle.state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return cached inference completion."""

        return self._convergence_status

    @property
    def results(self) -> pd.DataFrame:
        """Return legacy history only while the runtime is valid."""

        self._require_valid("read results")
        return self._results

    def init(self) -> None:
        """Reset all current state and enter the ready lifecycle."""

        self._lifecycle.fail()
        self._pending_input = None
        self._latest_output = None
        self._latest_result = None
        self._failure = None
        self._results = self._empty_results()
        self.t = 0.0
        self.uxy = None
        self.uxyt = None
        self.xv = None
        self.force = np.zeros(2, dtype=float)
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.reset()

    def input(self, dto: BearingInput) -> None:
        """Validate and latch one bearing sample without running inference."""

        self._lifecycle.require_input_slot()
        if not isinstance(dto, BearingInput):
            raise TypeError("ALBNN input must be BearingInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("ALBNN input unit_system does not match runtime")
        self._pending_input = dto
        self._latest_output = None
        self._latest_result = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.latch()

    def _spool_snapshot(self) -> np.ndarray:
        if self.agent == "ALBNNAgent":
            return np.asarray([state.xv for state in self.of], dtype=float)
        if self.agent == "HydroNNAgent":
            return np.zeros(2, dtype=float)
        return np.ones(2, dtype=float)

    def evaluate(self) -> None:
        """Run one inference and publish an immutable result."""

        assert self._pending_input is not None
        dto = self._pending_input
        try:
            with self._lifecycle.evaluation():
                spool = self._spool_snapshot()
                nodim = self.unit_system is UnitSystem.NONDIMENSIONAL
                self.alb_net.input(
                    dto.displacement,
                    dto.velocity,
                    spool,
                    nodim=nodim,
                )
                force = finite_real_array(
                    self.alb_net.output(nodim=nodim),
                    "ALBNN force",
                ).reshape(-1)
                if force.shape != (2,):
                    raise ValueError("ALBNN force must contain exactly 2 values")
                output = BearingOutput(force, dto.time, self.unit_system)
                self.t = dto.time
                self.uxy = dto.displacement
                self.uxyt = dto.velocity
                self.xv = spool
                self.force = output.force
                self.signal.lead_loop("finish_signal")
                self._latest_output = output
                self._latest_result = result_snapshot(
                    {
                        "force": output.force,
                        "spool": spool,
                    },
                    {
                        "schema": "alb.albnn-bearing-result.v1",
                        "time": dto.time,
                        "unit_system": self.unit_system.value,
                        "agent": self.agent,
                        "converged": True,
                    },
                )
                self._convergence_status = ConvergenceStatus(
                    0.0,
                    True,
                    message="ALBNN inference completed",
                )
                self._pending_input = None
        except BaseException as exc:
            self._latest_output = None
            self._latest_result = None
            self._failure = self._build_failure_snapshot(exc, "evaluate")
            raise

    def output(self) -> BearingOutput:
        """Read the completed ALBNN force without inference."""

        self._lifecycle.require_output()
        assert self._latest_output is not None
        return self._latest_output

    def step(self, dto: BearingInput) -> BearingOutput:
        """Compose input, evaluate, and output without committing a step."""

        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> ResultBundle:
        """Return the complete immutable current inference result."""

        self._lifecycle.require_output()
        assert self._latest_result is not None
        return self._latest_result

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest sealed inference failure."""

        if self._failure is None:
            raise RuntimeError("no ALBNN runtime failure is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable inference lifecycle diagnostics."""

        return result_snapshot(
            {},
            {
                "schema": "alb.albnn-bearing-diagnostic.v1",
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
                "schema": "alb.albnn-bearing-failure.v1",
                "phase": phase,
                "error_type": type(error).__name__,
                "message": str(error),
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
            },
        )

    def _require_valid(self, action: str) -> None:
        if self._lifecycle.state is LifecycleState.FAILED:
            raise RuntimeError(
                f"ALBNNAgent is failed; call init() before {action}"
            )

    def calc_capacity(self, *args, **kwargs) -> np.ndarray:
        """Return the already completed force without hidden inference."""

        if args or kwargs:
            raise TypeError("calc_capacity() no longer accepts solve options")
        return self.output().force

    def calc_error(self, *args, **kwargs) -> bool:
        return self._convergence_status.converged

    def calc_is_finished(self, *args, **kwargs) -> bool:
        return self._convergence_status.converged

    def save(self, tofile=False, path=None, name=None, *args, **kwargs):
        self._require_valid("save")
        if name is None:
            name = "alb_nn"
        if path is None:
            path = "result"
        node = SaveTreeNode(path, DataFrameResult({name: self._results}))
        if tofile:
            return node.persist(kwargs.get("writer"), path)
        return node

    def finish_signal(self) -> None:
        """Record one completed compatibility row."""

        assert self.uxy is not None
        assert self.uxyt is not None
        self._results.loc[len(self._results)] = [
            self.t,
            self.uxy[0],
            self.uxy[1],
            self.uxyt[0],
            self.uxyt[1],
            self.force[0],
            self.force[1],
        ]


__all__ = ["ALBNNAgent"]
