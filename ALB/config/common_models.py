"""Domain configuration models split from the historical monolith."""

from dataclasses import asdict, dataclass
from numbers import Integral, Real
from typing import Optional, Union

import numpy as np

@dataclass
class ConfigData:
    """Base class for configuration data, providing dictionary-like access."""

    def __getitem__(self, key):
        # getattr is a built-in function to get object attributes
        # This method enables accessing object attributes using dictionary-style key access
        return getattr(self, key)

    def __setitem__(self, key, value):
        """Allows modifying attributes by key name."""
        # This method enables setting object attributes using dictionary-style key assignment
        setattr(self, key, value)

    def to_dict(self):
        """Returns a dictionary containing all fields and computed properties."""
        # 1. First, get a dictionary of all base fields
        # asdict() is used to convert the dataclass instance to a dictionary
        data = asdict(self)

        # 2. Manually add computed properties

        # Note: This section appears to be incomplete in the original code
        # as it only contains a comment without implementation
        return data

    @staticmethod
    def set_config(ConfigClass, config_dict):
        """
        Extracts relevant key-value pairs from a large dictionary and creates an instance of a configuration class.
        Args:
            ConfigClass: The configuration class to instantiate
            config_dict: Dictionary containing configuration values
        Returns:
            An instance of ConfigClass with relevant fields populated
        """
        # Get all field names of this configuration class (including parent classes)
        # This helps determine which keys from config_dict should be used
        keys = ConfigClass().to_dict().keys()

        # Filter the parameters needed for this class from the large dictionary
        # Only keep key-value pairs where the key exists in both the config_dict and the class fields
        class_args = {key: config_dict[key] for key in keys if key in config_dict}

        # Create and return an instance using the filtered parameters
        # The ** operator unpacks the dictionary into keyword arguments
        return ConfigClass(**class_args)

_TIME_GRID_MODES = {"cycle_points", "fixed_dt"}

_TIME_GRID_INTEGER_RTOL = 1e-10

_TIME_GRID_INTEGER_ATOL = 1e-10

def _positive_time_grid_float(name: str, value: Real) -> float:
    """Return a finite positive floating-point time-grid value."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")
    return result

def _positive_time_grid_integer(name: str, value: Integral) -> int:
    """Return a strictly typed positive integer time-grid value."""

    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{name} must be > 0")
    return result

@dataclass(frozen=True)
class ResolvedTimeGrid:
    """Validated physical time-grid values shared by simulation components.

    ``steps`` is the number of time intervals.  The corresponding iterator
    therefore exposes ``steps + 1`` sample times including the initial state.
    """

    mode: str
    freq: float
    cycles: Union[int, float]
    points_per_cycle: int
    dt: float
    steps: int

    @property
    def end_time(self) -> float:
        """Return the physical end time in seconds."""

        return self.dt * self.steps

    @property
    def samples_per_revolution(self) -> float:
        """Return the validated number of time intervals per revolution."""

        return float(self.points_per_cycle)

    def to_dict(self) -> dict:
        """Return a serialization-ready representation of the resolved grid."""

        return {
            "mode": self.mode,
            "freq": self.freq,
            "cycles": self.cycles,
            "points_per_cycle": self.points_per_cycle,
            "dt": self.dt,
            "steps": self.steps,
            "end_time": self.end_time,
            "samples_per_revolution": self.samples_per_revolution,
        }

    def to_time_config(self) -> dict:
        """Return the minimal canonical input that reconstructs this grid."""

        if self.mode == "cycle_points":
            return {
                "mode": self.mode,
                "freq": self.freq,
                "cycles": int(self.cycles),
                "points_per_cycle": self.points_per_cycle,
            }
        return {
            "mode": self.mode,
            "freq": self.freq,
            "dt": self.dt,
            "steps": self.steps,
        }

@dataclass
class TimeGridConfig(ConfigData):
    """Resolve either cycle-based or fixed-step simulation time settings.

    ``cycle_points`` accepts ``freq``, ``cycles``, and ``points_per_cycle``.
    ``fixed_dt`` accepts ``freq``, ``dt``, and ``steps``.
    """

    mode: Optional[str] = None
    freq: Optional[float] = None
    cycles: Optional[int] = None
    points_per_cycle: Optional[int] = None
    dt: Optional[float] = None
    steps: Optional[int] = None

    def __post_init__(self):
        if self.mode is None:
            raise ValueError("mode is required")
        self.mode = str(self.mode).lower()
        if self.mode not in _TIME_GRID_MODES:
            raise ValueError("mode must be 'cycle_points' or 'fixed_dt'")
        self._validate()

    def _validate(self) -> None:
        self.freq = _positive_time_grid_float("freq", self.freq)
        if self.mode == "cycle_points":
            if self.dt is not None or self.steps is not None:
                raise ValueError(
                    "cycle_points does not accept fixed_dt fields 'dt' or 'steps'"
                )
            self.cycles = _positive_time_grid_integer("cycles", self.cycles)
            self.points_per_cycle = _positive_time_grid_integer(
                "points_per_cycle", self.points_per_cycle
            )
            return

        if self.cycles is not None or self.points_per_cycle is not None:
            raise ValueError(
                "fixed_dt does not accept cycle_points fields 'cycles' or "
                "'points_per_cycle'"
            )
        self.dt = _positive_time_grid_float("dt", self.dt)
        self.steps = _positive_time_grid_integer("steps", self.steps)
        points_per_cycle = 1.0 / (self.freq * self.dt)
        rounded = np.rint(points_per_cycle)
        if rounded < 1.0 or not np.isclose(
            points_per_cycle,
            rounded,
            rtol=_TIME_GRID_INTEGER_RTOL,
            atol=_TIME_GRID_INTEGER_ATOL,
        ):
            raise ValueError(
                "fixed_dt requires 1 / (freq * dt) to be a positive integer "
                "within rtol=atol=1e-10"
            )

    @classmethod
    def from_dict(cls, config_dict: dict) -> "TimeGridConfig":
        """Build from canonical 0.4 time-grid keys."""

        data = dict(config_dict)
        allowed = {
            "mode",
            "freq",
            "cycles",
            "points_per_cycle",
            "dt",
            "steps",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"unknown time-grid fields: {unknown}")
        return cls(
            mode=data.get("mode"),
            freq=data.get("freq"),
            cycles=data.get("cycles"),
            points_per_cycle=data.get("points_per_cycle"),
            dt=data.get("dt"),
            steps=data.get("steps"),
        )

    def resolve(self) -> ResolvedTimeGrid:
        """Return validated values used by time iterators and child configs."""

        if self.mode == "cycle_points":
            dt = 1.0 / (self.freq * self.points_per_cycle)
            return ResolvedTimeGrid(
                mode=self.mode,
                freq=self.freq,
                cycles=self.cycles,
                points_per_cycle=self.points_per_cycle,
                dt=dt,
                steps=self.cycles * self.points_per_cycle,
            )

        points_per_cycle = int(np.rint(1.0 / (self.freq * self.dt)))
        return ResolvedTimeGrid(
            mode=self.mode,
            freq=self.freq,
            cycles=self.steps / points_per_cycle,
            points_per_cycle=points_per_cycle,
            dt=self.dt,
            steps=self.steps,
        )

__all__ = ['ConfigData', 'ResolvedTimeGrid', 'TimeGridConfig']
