"""Domain configuration models split from the historical monolith."""

from dataclasses import dataclass, field, fields
from typing import Union

import numpy as np

from .common_models import ConfigData

@dataclass
class ServoConfig(ConfigData):
    """Configuration for the servovalve.

    The class defaults define the standard ``moog`` servovalve parameters.
    ``ALBConfig`` and ``NodimALBConfig`` install the current ``moog_2nd``
    defaults through their own ``servo_config`` default factories.
    """

    dt: float = 6.667e-4
    tw: float = 1.5059e-8
    zeta: float = 0.0039795
    tp3: float = 0.0017924
    delay: float = 0.0

@dataclass
class Moog2ndServoConfig(ServoConfig):
    """Default configuration for the single-second-order Moog servovalve."""

    tw: float = 9.587647174210562e-4
    zeta: float = 0.7

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

__all__ = ['ServoConfig', 'Moog2ndServoConfig', 'PIDConfig', 'LQGConfig', 'FuzzyPIDConfig']
