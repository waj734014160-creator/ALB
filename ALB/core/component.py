"""Reusable runtime component templates.

Only lifecycle, results, event composition, and unit metadata are shared here.
Domain-specific ``input`` and ``output`` semantics are defined by protocols in
``ALB.contracts`` and by specialized bases such as ``BearingComponentBase``.
"""

from abc import ABC, abstractmethod
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from .events import Signal
from .validation import finite_vector, validate_bearing_output


class ComponentBase(ABC):
    """Small common template for event-aware components with result storage."""

    unit_system = "unspecified"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._results = pd.DataFrame()
        self.signal = Signal(sys=self)

    @property
    def results(self) -> Any:
        """Return the component-owned result store."""

        return self._results

    def start_signal(self) -> None:
        """Optional lifecycle callback invoked at calculation start."""

        return None

    def finish_signal(self) -> None:
        """Optional lifecycle callback invoked at calculation completion."""

        return None


class BaseSimpleModel(ComponentBase, ABC):
    """Backward-compatible abstract template for legacy simple models."""

    @abstractmethod
    def init(self, *args: Any, **kwargs: Any) -> Any:
        """Initialize the model."""

    @abstractmethod
    def input(self, *args: Any, **kwargs: Any) -> Any:
        """Accept domain-specific model input."""

    @abstractmethod
    def output(self, *args: Any, **kwargs: Any) -> Any:
        """Return domain-specific model output."""

    @abstractmethod
    def calc_error(self, *args: Any, **kwargs: Any) -> Any:
        """Return the legacy model residual value."""

    @abstractmethod
    def save(
        self,
        tofile: bool = True,
        path: Optional[str] = None,
        name: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Return or persist model results."""


class BearingComponentBase(BaseSimpleModel, ABC):
    """Template for dimensional two-axis bearings used by rotor coupling."""

    unit_system = "dimensional"
    force_size = 2

    @staticmethod
    def validate_state(uxy: Any, uxyt: Any) -> tuple:
        """Validate and return position and velocity vectors."""

        return finite_vector(uxy, "uxy", 2), finite_vector(uxyt, "uxyt", 2)

    @staticmethod
    def validate_output(output: Any) -> np.ndarray:
        """Validate and return a standard two-axis force vector."""

        return validate_bearing_output(output)


class _CompositeSignalMixin:
    """Attach child component signals without duplicating registrations."""

    signal: Signal

    def _set_signal_children(self, components: Iterable[Any]) -> None:
        signals = [component.signal for component in components if component is not None]
        self.signal.children = signals

    def _add_signal_child(self, component: Any) -> None:
        if component is not None:
            self.signal.add_child(component.signal)


class BaseSystem(_CompositeSignalMixin):
    """Backward-compatible main-model plus auxiliary-model composition base."""

    unit_system = "unspecified"

    def __init__(self, main_model: Any = None, *simple_models: Any, **args: Any) -> None:
        self.args = args
        self.main_model = main_model
        self.simple_models = list(simple_models)
        self.signal = Signal(sys=self)
        self._set_signal_children([main_model] + self.simple_models)

    @property
    def margs(self) -> Any:
        """Return main-model arguments with a clear missing-model error."""

        if self.main_model is None:
            raise AttributeError("BaseSystem has no main_model")
        return self.main_model.args

    def init(self, *args: Any, **kwargs: Any) -> None:
        return None

    def solve(self, *args: Any, **kwargs: Any) -> None:
        return None

    def calc_is_finished(self, *args: Any, **kwargs: Any) -> None:
        return None

    def input(self, *args: Any, **kwargs: Any) -> None:
        return None

    def add_simple_model(self, simple_model: Any) -> None:
        """Attach one or many auxiliary models exactly once."""

        if isinstance(simple_model, (list, tuple, np.ndarray)):
            for model in simple_model:
                self.add_simple_model(model)
            return
        if not any(existing is simple_model for existing in self.simple_models):
            self.simple_models.append(simple_model)
        self._add_signal_child(simple_model)

    def output(self, *args: Any, **kwargs: Any) -> None:
        return None

    def save(self, tofile: bool, path: str, name: str, *args: Any, **kwargs: Any) -> None:
        return None

    def start_signal(self) -> None:
        return None

    def finish_signal(self) -> None:
        return None

class BaseCSystem(_CompositeSignalMixin, ABC):
    """Backward-compatible composition base for peer runtime components."""

    unit_system = "unspecified"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.signal = Signal(sys=self)

    def calc_is_finished(self, *args: Any, **kwargs: Any) -> None:
        return None

    def init(self, *args: Any, **kwargs: Any) -> None:
        return None

    def solve(self, *args: Any, **kwargs: Any) -> None:
        return None

    def output(self, *args: Any, **kwargs: Any) -> None:
        return None

    def input(self, *args: Any, **kwargs: Any) -> None:
        return None

    def save(self, tofile: bool, path: str, name: str, *args: Any, **kwargs: Any) -> None:
        return None

    def start_signal(self) -> None:
        return None

    def finish_signal(self) -> None:
        return None
