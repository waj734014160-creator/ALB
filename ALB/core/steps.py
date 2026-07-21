"""Physical-step commit validation for use by top-level couplers and workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable

from ALB.contracts import StepContext


@dataclass(slots=True)
class StepCommitLedger:
    """Reject duplicate or out-of-order physical step commits."""

    _last_context: StepContext | None = field(default=None, init=False)

    @property
    def last_context(self) -> StepContext | None:
        """Return the most recently committed step context."""

        return self._last_context

    def commit_step(
        self,
        context: StepContext,
        recorder: Callable[[StepContext], None] | None = None,
    ) -> None:
        """Commit one strictly increasing context and optionally record it."""

        self.validate_next(context)
        if recorder is not None:
            recorder(context)
        self._last_context = context

    def validate_next(self, context: StepContext) -> None:
        """Validate a prospective commit without mutating the ledger."""

        if self._last_context is None:
            return
        if context.identity == self._last_context.identity:
            raise RuntimeError("physical step has already been committed")
        if context.unit_system is not self._last_context.unit_system:
            raise RuntimeError("unit_system cannot change within one workflow")
        if context.dt != self._last_context.dt:
            raise RuntimeError("dt cannot change within one workflow")
        expected_index = self._last_context.step_index + 1
        if context.step_index != expected_index:
            raise RuntimeError(
                f"physical step_index must advance exactly to {expected_index}"
            )
        elapsed = context.time - self._last_context.time
        if not math.isclose(
            elapsed,
            context.dt,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        ):
            raise RuntimeError("physical step time increment must match dt")
