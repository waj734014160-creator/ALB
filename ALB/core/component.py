"""Reusable runtime component templates.

Only lifecycle, results, composition, and unit metadata are shared here.
Domain-specific ``input`` and ``output`` semantics are defined by protocols in
``ALB.contracts`` and by specialized bases such as ``BearingComponentBase``.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np
import numpy.typing as npt
import pandas as pd

from .validation import finite_vector, validate_bearing_output


class ComponentBase(ABC):
    """Small common template for components with result storage."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._results = pd.DataFrame()

    @property
    def results(self) -> Any:
        """Return the component-owned result store."""

        return self._results

class BaseSimpleModel(ComponentBase, ABC):
    """Abstract template for internal numerical models."""

    @abstractmethod
    def _reset_for_owner(self, *args: Any, **kwargs: Any) -> Any:
        """Initialize the model."""

    @abstractmethod
    def input(self, *args: Any, **kwargs: Any) -> Any:
        """Accept domain-specific model input."""

    @abstractmethod
    def output(self, *args: Any, **kwargs: Any) -> Any:
        """Return domain-specific model output."""

    @abstractmethod
    def calc_error(self, *args: Any, **kwargs: Any) -> Any:
        """Return the model residual value."""

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
    def validate_state(
        uxy: Any,
        uxyt: Any,
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        """Validate and return position and velocity vectors."""

        return finite_vector(uxy, "uxy", 2), finite_vector(uxyt, "uxyt", 2)

    @staticmethod
    def validate_output(output: Any) -> npt.NDArray[np.float64]:
        """Validate and return a standard two-axis force vector."""

        return validate_bearing_output(output)


class BaseSystem:
    """Internal main-model plus auxiliary-model composition base."""

    def __init__(self, main_model: Any = None, *simple_models: Any, **args: Any) -> None:
        self.args = args
        self.main_model = main_model
        self.simple_models = list(simple_models)

    @property
    def margs(self) -> Any:
        """Return main-model arguments with a clear missing-model error."""

        if self.main_model is None:
            raise AttributeError("BaseSystem has no main_model")
        return self.main_model.args

    def _reset_for_owner(self, *args: Any, **kwargs: Any) -> None:
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

    def output(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def save(self, tofile: bool, path: str, name: str, *args: Any, **kwargs: Any) -> None:
        return None

class BaseCSystem(ABC):
    """Internal composition base for peer runtime components."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()

    def calc_is_finished(self, *args: Any, **kwargs: Any) -> None:
        return None

    def _reset_for_owner(self, *args: Any, **kwargs: Any) -> None:
        return None

    def solve(self, *args: Any, **kwargs: Any) -> None:
        return None

    def output(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def input(self, *args: Any, **kwargs: Any) -> None:
        return None

    def save(self, tofile: bool, path: str, name: str, *args: Any, **kwargs: Any) -> None:
        return None
