"""Domain configuration models split from the historical monolith."""

from collections import namedtuple
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .common_models import ConfigData

@dataclass
class TankConfig(ConfigData):
    """Configuration for the oil tank."""

    xrange: list = field(default_factory=lambda: [0.49, 0.51])
    zrange: list = field(default_factory=lambda: [0.2, 0.8])
    h_tank: float = 2

@dataclass
class OrificeConfig(ConfigData):
    """Configuration for the orifice."""

    position: list = field(
        default_factory=lambda: [[0.5, 0.25 + 0.25 * i] for i in range(3)]
    )
    ps: float = 7e6
    p0: float = 0  # Tank pressure
    cq1_nondim: Optional[float] = None

@dataclass
class NodimOrificeConfig(ConfigData):
    """Configuration for nondimensional capillary-slot orifices."""

    position: np.ndarray = field(
        default_factory=lambda: np.array([[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]])
    )
    cq0: float = 1.0
    cq1: float = 1.0
    cq2: float = 0.0
    ps: float = 1.0
    p0: float = 0.0
    q_leak: float = 0.0

    def __post_init__(self):
        # Store the position array in a consistent numeric shape for builders.
        self.position = np.asarray(self.position, dtype=float)
        self.cq1 = np.asarray(self.cq1, dtype=float)
        if self.cq1.size != 1:
            raise ValueError("cq1 must be scalar; node-wise h correction is cq1_h2")
        self.cq1 = float(self.cq1.reshape(-1)[0])
        if self.cq0 <= 0:
            raise ValueError("cq0 must be > 0")
        if self.cq1 < 0 or self.cq2 < 0:
            raise ValueError("cq1 and cq2 must be >= 0")
        if self.ps < 0 or self.p0 < 0:
            raise ValueError("ps and p0 must be >= 0")
        try:
            self.q_leak = float(self.q_leak)
        except (TypeError, ValueError) as exc:
            raise ValueError("q_leak must be 0.0 for CSOrifice") from exc
        if not np.isfinite(self.q_leak) or self.q_leak != 0.0:
            raise ValueError("q_leak must be 0.0 for CSOrifice")

    @classmethod
    def from_dict(cls, config_dict):
        """Create a nodimensional orifice config from a flat configuration dictionary."""
        direct_keys = [
            "position",
            "cq0",
            "cq1",
            "cq2",
            "ps",
            "p0",
            "q_leak",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }
        return cls(**direct_args)

CsoArgs = namedtuple(
    "CsoArgs",
    ["d", "l", "q_leak", "w", "cd", "cq1_nondim"],
    defaults=[0.002, 0.02, 0, 1.83e-5 / 15, 0.6, None],
)

__all__ = ['TankConfig', 'OrificeConfig', 'NodimOrificeConfig', 'CsoArgs']
