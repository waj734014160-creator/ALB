# coding: utf-8
"""Adaptive relaxation utilities for iterative ALB solvers."""

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Optional


@dataclass
class AdaptiveDampConfig:
    """Configuration for residual-trend based relaxation control."""

    enabled: bool = False
    min_value: float = 0.02
    max_value: Optional[float] = None
    shrink_factor: float = 0.5
    growth_factor: float = 1.15
    improve_ratio: float = 0.85
    worsen_ratio: float = 1.05
    improve_patience: int = 2

    def __post_init__(self):
        if self.min_value <= 0.0:
            raise ValueError("min_value must be > 0")
        if self.max_value is not None and self.max_value < self.min_value:
            raise ValueError("max_value must be None or >= min_value")
        if not 0.0 < self.shrink_factor <= 1.0:
            raise ValueError("shrink_factor must be in (0, 1]")
        if self.growth_factor < 1.0:
            raise ValueError("growth_factor must be >= 1")
        if self.improve_ratio <= 0.0:
            raise ValueError("improve_ratio must be > 0")
        if self.worsen_ratio <= 0.0:
            raise ValueError("worsen_ratio must be > 0")
        if self.improve_patience < 1:
            raise ValueError("improve_patience must be >= 1")

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return None
        if isinstance(data, cls):
            return data
        if isinstance(data, dict):
            valid_keys = cls.__dataclass_fields__.keys()
            args = {key: data[key] for key in valid_keys if key in data}
            return cls(**args)
        raise TypeError("adaptive_damp must be an AdaptiveDampConfig, dict, or None")

    def to_dict(self):
        return asdict(self)


def normalize_adaptive_damp_config(config):
    """Return a normalized adaptive damp config or None."""

    return AdaptiveDampConfig.from_dict(config)


class AdaptiveDampController:
    """Update a scalar relaxation value from residual trends."""

    def __init__(self, initial_value: float, config=None):
        self.config = normalize_adaptive_damp_config(config)
        self._initial_value = float(initial_value)
        self._current_value = float(initial_value)
        self._previous_error = None
        self._improve_count = 0
        self.history = []

    @property
    def enabled(self) -> bool:
        return bool(self.config and self.config.enabled)

    @property
    def value(self) -> float:
        return self._current_value

    @property
    def max_value(self) -> float:
        if self.config is None or self.config.max_value is None:
            return self._initial_value
        return float(self.config.max_value)

    @property
    def min_value(self) -> float:
        if self.config is None:
            return self._initial_value
        return min(float(self.config.min_value), self.max_value)

    def reset(self, initial_value: Optional[float] = None):
        if initial_value is not None:
            self._initial_value = float(initial_value)
        self._current_value = self._initial_value
        self._previous_error = None
        self._improve_count = 0
        self.history = []

    def update(self, error) -> float:
        """Record a residual and update the value used by the next iteration."""

        if not self.enabled:
            return self._current_value

        error_value = float(error)
        value_before = self._current_value
        action = "hold"

        if not isfinite(error_value):
            self._shrink()
            self._previous_error = None
            self._improve_count = 0
            action = "shrink_nonfinite"
        elif self._previous_error is None:
            self._previous_error = error_value
            self._improve_count = 0
            action = "initialize"
        elif error_value >= self._previous_error * self.config.worsen_ratio:
            self._shrink()
            self._previous_error = error_value
            self._improve_count = 0
            action = "shrink_worse"
        elif error_value <= self._previous_error * self.config.improve_ratio:
            self._improve_count += 1
            self._previous_error = error_value
            if self._improve_count >= self.config.improve_patience:
                self._grow()
                self._improve_count = 0
                action = "grow_improved"
            else:
                action = "hold_improved"
        else:
            self._previous_error = error_value
            self._improve_count = 0
            action = "hold_flat"

        self.history.append(
            {
                "error": error_value,
                "value_before": value_before,
                "value_after": self._current_value,
                "action": action,
            }
        )
        return self._current_value

    def _shrink(self):
        self._current_value = max(
            self.min_value,
            self._current_value * float(self.config.shrink_factor),
        )

    def _grow(self):
        self._current_value = min(
            self.max_value,
            self._current_value * float(self.config.growth_factor),
        )
