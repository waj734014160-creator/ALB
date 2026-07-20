"""Physical-step commit coordination owned only by top-level workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
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

        if self._last_context is not None:
            if context.identity == self._last_context.identity:
                raise RuntimeError("physical step has already been committed")
            if context.step_index <= self._last_context.step_index:
                raise RuntimeError("physical steps must be committed in increasing order")
            if context.time <= self._last_context.time:
                raise RuntimeError("physical step time must increase")
            if context.unit_system is not self._last_context.unit_system:
                raise RuntimeError("unit_system cannot change within one workflow")
        if recorder is not None:
            recorder(context)
        self._last_context = context
