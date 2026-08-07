"""Domain configuration models split from the historical monolith."""

from dataclasses import dataclass, field, fields
from numbers import Real
from typing import Union

import numpy as np

from .common_models import ConfigData


def _finite_real(name: str, value: object) -> float:
    """Return one finite real servovalve configuration value."""

    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _polynomial(name: str, value) -> tuple[float, ...]:
    """Normalize one nonempty finite polynomial coefficient sequence."""

    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a coefficient sequence")
    try:
        coefficients = tuple(
            _finite_real(f"{name}[{index}]", item)
            for index, item in enumerate(value)
        )
    except TypeError as exc:
        raise TypeError(f"{name} must be a coefficient sequence") from exc
    if not coefficients:
        raise ValueError(f"{name} must not be empty")
    if coefficients[0] == 0.0:
        raise ValueError(f"{name} leading coefficient must be nonzero")
    return coefficients


@dataclass
class SecondOrderServoConfig(ConfigData):
    """Continuous-time second-order servovalve configuration.

    ``natural_frequency_hz`` is specified in cycles per second. The runtime
    converts it to the historical ``tw = 1 / (2*pi*f_n)`` representation so
    the validated numerical transfer function remains unchanged.
    """

    dt: float = 6.667e-4
    natural_frequency_hz: float = 166.0
    damping_ratio: float = 0.7
    delay: float = 0.0

    def __post_init__(self) -> None:
        self.dt = _finite_real("dt", self.dt)
        self.natural_frequency_hz = _finite_real(
            "natural_frequency_hz", self.natural_frequency_hz
        )
        self.damping_ratio = _finite_real(
            "damping_ratio", self.damping_ratio
        )
        self.delay = _finite_real("delay", self.delay)
        if self.dt <= 0.0:
            raise ValueError("dt must be > 0")
        if self.natural_frequency_hz <= 0.0:
            raise ValueError("natural_frequency_hz must be > 0")
        if self.damping_ratio <= 0.0:
            raise ValueError("damping_ratio must be > 0")
        if self.delay < 0.0:
            raise ValueError("delay must be >= 0")


@dataclass
class TransferFunctionServoConfig(ConfigData):
    """Continuous-time SISO servovalve defined by polynomial coefficients.

    Coefficients use descending powers of ``s`` and include the complete gain
    and any rational delay approximation. Improper transfer functions are
    rejected because the runtime requires a causal state-space realization.
    """

    dt: float = 6.667e-4
    numerator: tuple[float, ...] = (1.0,)
    denominator: tuple[float, ...] = (1.0,)

    def __post_init__(self) -> None:
        self.dt = _finite_real("dt", self.dt)
        if self.dt <= 0.0:
            raise ValueError("dt must be > 0")
        self.numerator = _polynomial("numerator", self.numerator)
        self.denominator = _polynomial("denominator", self.denominator)
        if all(value == 0.0 for value in self.numerator):
            raise ValueError("numerator must not be the zero polynomial")
        if len(self.numerator) > len(self.denominator):
            raise ValueError("transfer function must be proper")

    @property
    def is_static(self) -> bool:
        """Return whether the transfer function has no dynamic poles."""

        return len(self.denominator) == 1


@dataclass
class PIDConfig(ConfigData):
    """Configuration for the PID controller."""

    dt: float = 6.667e-4
    kp: float = 0.0
    ki: float = 0.0
    kd: float = 0.0
    uf: float = 0.0
    freq: float = 50
    sensor_angles: np.ndarray = field(default_factory=lambda: np.array([45, 135]))

    def __post_init__(self):
        if self.dt <= 0:
            raise ValueError("dt must be > 0")
        if self.freq <= 0:
            raise ValueError("freq must be > 0")
        if self.kp < 0 or self.ki < 0 or self.kd < 0:
            raise ValueError("kp, ki and kd must be >= 0")

@dataclass
class LQGConfig(ConfigData):
    """Core runtime configuration for :class:`ALBLQGController`.

    Scalar output bounds apply to every actuator channel. One-dimensional
    sequences can be used when individual channels require different bounds.
    Plant assembly and weighting-matrix policies remain explicit controller
    design inputs because their dimensions depend on the selected rotor.
    """

    dt: float = 6.667e-4
    freq: float = 50.0
    eso_enable: bool = True
    output_min: Union[float, list] = -1.0
    output_max: Union[float, list] = 1.0

    def __post_init__(self):
        if self.dt <= 0:
            raise ValueError("dt must be > 0")
        if self.freq <= 0:
            raise ValueError("freq must be > 0")
        if not isinstance(self.eso_enable, (bool, np.bool_)):
            raise TypeError("eso_enable must be a boolean")
        self.eso_enable = bool(self.eso_enable)

        lower = np.asarray(self.output_min, dtype=float)
        upper = np.asarray(self.output_max, dtype=float)
        if lower.ndim > 1 or upper.ndim > 1:
            raise ValueError("output limits must be scalars or one-dimensional")
        if lower.size == 0 or upper.size == 0:
            raise ValueError("output limits must not be empty")
        if not np.all(np.isfinite(lower)) or not np.all(np.isfinite(upper)):
            raise ValueError("output limits must be finite")
        if lower.size != upper.size and lower.size != 1 and upper.size != 1:
            raise ValueError("output_min and output_max sizes are incompatible")
        lower, upper = np.broadcast_arrays(lower.reshape(-1), upper.reshape(-1))
        if np.any(lower >= upper):
            raise ValueError("output_min must be less than output_max")

    @classmethod
    def from_dict(cls, config_dict):
        """Build the core LQG config from a flat shared-config payload."""
        if isinstance(config_dict, cls):
            return config_dict
        valid_fields = {item.name for item in fields(cls)}
        values = {
            key: config_dict[key] for key in valid_fields if key in config_dict
        }
        return cls(**values)

@dataclass
class FuzzyPIDConfig(ConfigData):
    """Configuration for the Fuzzy PID controller."""

    dt: float = 6.667e-4
    freq: float = 5.0
    error_range: list = field(default_factory=lambda: [-1, 1, 0.01])
    delta_error_range: list = field(default_factory=lambda: [-1, 1, 0.01])
    kp_range: list = field(default_factory=lambda: [0, 1, 0.01])
    ki_range: list = field(default_factory=lambda: [0, 0, 0.01])
    kd_range: list = field(default_factory=lambda: [0, 1, 0.01])
    rule_path: str = "../fuzzy_rule.csv"
    sensor_angles: list = field(default_factory=lambda: [45, 135])

__all__ = [
    'SecondOrderServoConfig',
    'TransferFunctionServoConfig',
    'PIDConfig',
    'LQGConfig',
    'FuzzyPIDConfig',
]
