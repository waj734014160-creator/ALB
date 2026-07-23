"""Typed lifecycle, commit, and snapshot support for rotor coupling."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

import numpy.typing as npt

from ALB.contracts import ResultBundle, StepContext, result_snapshot
from ALB.contracts.lifecycle import LifecycleState
from ALB.core.lifecycle import RuntimeLifecycle
from ALB.core.steps import StepCommitLedger


class CouplingStepRuntime:
    """Coordinate one coupled step without owning numerical component state."""

    def __init__(self) -> None:
        self.lifecycle = RuntimeLifecycle(
            "rotor-bearing coupling", input_label="step context"
        )
        self.ledger = StepCommitLedger()

    @property
    def state(self) -> LifecycleState:
        """Return the current coupled-runtime state."""

        return self.lifecycle.state

    @property
    def is_valid(self) -> bool:
        """Return whether public coupled state may be accessed."""

        return self.lifecycle.is_valid

    def fail(self) -> None:
        """Invalidate the runtime after topology or numerical mutation."""

        self.lifecycle.fail()

    def reset_ledger(self) -> None:
        """Start a new exactly-once physical-step sequence."""

        self.ledger = StepCommitLedger()

    def publish_initial(self, context: StepContext) -> None:
        """Commit and expose the initialized state as step zero."""

        self.ledger.commit_step(context)
        self.lifecycle.reset(output_available=True)

    def latch(self, context: StepContext) -> None:
        """Validate and latch the next physical step without mutating components."""

        self.ledger.validate_next(context)
        self.lifecycle.require_input_slot()
        self.lifecycle.latch()

    @contextmanager
    def evaluation(self) -> Iterator[None]:
        """Invalidate the runtime if any coupled component mutation fails."""

        with self.lifecycle.evaluation():
            yield

    def commit(self, context: StepContext) -> None:
        """Record a successfully assembled physical step exactly once."""

        self.ledger.commit_step(context)


def coupling_snapshot(
    rotor_state: Mapping[str, npt.ArrayLike],
    bearing_force: npt.ArrayLike,
    nodal_force: npt.ArrayLike,
    context: StepContext,
    *,
    initial: bool = False,
    unit_adapters: tuple[Mapping[str, object], ...] = (),
) -> ResultBundle:
    """Build the standard immutable result for one coupled physical step."""

    metadata: dict[str, object] = {
        "step_index": context.step_index,
        "time": context.time,
        "unit_system": context.unit_system.value,
    }
    if initial:
        metadata["initial_snapshot"] = True
    if unit_adapters:
        metadata["unit_adapters"] = unit_adapters
    return result_snapshot(
        {
            "rotor_displacement": rotor_state["uxy"],
            "rotor_velocity": rotor_state["uxyt"],
            "bearing_force": bearing_force,
            "nodal_force": nodal_force,
        },
        metadata,
    )


__all__ = ["CouplingStepRuntime", "coupling_snapshot"]


class PostCommitRecordingError(RuntimeError):
    """Report recorder failure after the physical step was committed."""

    physical_step_committed = True

    def __init__(self, pending_record: object) -> None:
        super().__init__("physical step committed but result recording is pending")
        self.pending_record = pending_record


class PostCommitObserverError(RuntimeError):
    """Report strict observer failure after the physical step was committed."""

    physical_step_committed = True

    def __init__(self, failures: tuple[object, ...]) -> None:
        super().__init__("physical step committed but an observer failed")
        self.failures = failures


__all__ = [
    "CouplingStepRuntime",
    "PostCommitObserverError",
    "PostCommitRecordingError",
    "coupling_snapshot",
]
