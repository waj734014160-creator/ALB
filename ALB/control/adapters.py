"""Explicit adapters at the strict controller lifecycle boundary."""

from __future__ import annotations

from typing import Any, cast

import numpy as np

from ALB.contracts import ControllerProtocol
from ALB.contracts.numeric import FloatArray
from ALB.core import LifecycleState, RuntimeLifecycle
from ALB.core.validation import finite_real_scalar, finite_real_vector


class LegacyControllerAdapter:
    """Adapt a deprecated calculating ``output()`` to the strict lifecycle.

    The wrapped controller is called only during :meth:`evaluate`; repeated
    :meth:`output` calls return a copy of the same command. New integrations
    should implement :class:`ALB.contracts.ControllerProtocol` directly.
    Legacy controller support is isolated here and is scheduled for removal in
    the next breaking API release.
    """

    def __init__(self, controller: Any) -> None:
        for method_name in ("input", "output"):
            if not callable(getattr(controller, method_name, None)):
                raise TypeError(f"legacy controller must provide {method_name}()")
        self.wrapped = controller
        self._lifecycle = RuntimeLifecycle(type(self).__name__)
        self._pending_time = 0.0
        self._pending_error = np.zeros(2, dtype=float)
        self._last_output: FloatArray | None = None
        self._lifecycle.reset()

    def __getattr__(self, name: str) -> Any:
        """Expose non-lifecycle metadata from the wrapped controller."""

        return getattr(self.wrapped, name)

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the adapter runtime state."""

        return self._lifecycle.state

    def init(self, *args: Any, **kwargs: Any) -> Any:
        """Reset both the wrapped controller, when supported, and the adapter."""

        reset = getattr(self.wrapped, "init", None)
        result = reset(*args, **kwargs) if callable(reset) else None
        self._pending_time = 0.0
        self._pending_error = np.zeros(2, dtype=float)
        self._last_output = None
        self._lifecycle.reset()
        return result

    def input(self, time: float, error: Any, *args: Any, **kwargs: Any) -> None:
        """Validate and latch one two-axis controller input."""

        del args, kwargs
        checked_time = finite_real_scalar(time, "controller time")
        checked_error = finite_real_vector(error, "controller error", 2)
        self._lifecycle.latch()
        self._pending_time = checked_time
        self._pending_error = checked_error
        self._last_output = None

    def evaluate(self, *args: Any, **kwargs: Any) -> FloatArray:
        """Invoke the legacy calculating output exactly once."""

        del args, kwargs
        with self._lifecycle.evaluation():
            self.wrapped.input(self._pending_time, self._pending_error.copy())
            self._last_output = finite_real_vector(
                self.wrapped.output(), "controller command", 2
            )
        return self.output()

    def output(self, *args: Any, **kwargs: Any) -> FloatArray:
        """Read the completed command without calling the wrapped controller."""

        del args, kwargs
        self._lifecycle.require_output()
        assert self._last_output is not None
        return self._last_output.copy()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate optional legacy persistence without making it a core contract."""

        save = getattr(self.wrapped, "save", None)
        if not callable(save):
            raise AttributeError("wrapped legacy controller does not provide save()")
        return save(*args, **kwargs)


def adapt_controller(controller: Any) -> ControllerProtocol:
    """Return a native controller, explicitly adapting only legacy instances."""

    if isinstance(controller, LegacyControllerAdapter):
        return controller
    for method_name in ("input", "output"):
        if not callable(getattr(controller, method_name, None)):
            raise TypeError(f"controller must provide {method_name}()")
    if callable(getattr(controller, "evaluate", None)):
        return cast(ControllerProtocol, controller)
    return LegacyControllerAdapter(controller)
