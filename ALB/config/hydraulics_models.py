"""Domain configuration models split from the historical monolith."""

from collections import namedtuple
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from .common_models import ConfigData


FLOW_PROJECTION_MODES = frozenset({"nearest_node", "element_shape"})


def normalize_flow_projection(value: str) -> str:
    """Return one validated active-orifice flow projection mode."""

    normalized = str(value).strip().lower()
    if normalized not in FLOW_PROJECTION_MODES:
        choices = ", ".join(sorted(FLOW_PROJECTION_MODES))
        raise ValueError(f"flow_projection must be one of: {choices}")
    return normalized


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
    diameter: float = 0.002
    length: float = 0.02
    valve_area: float = 1.83e-5 / 15
    discharge_coefficient: float = 0.6
    flow_projection: str = "nearest_node"

    def __post_init__(self) -> None:
        self.flow_projection = normalize_flow_projection(self.flow_projection)


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
    flow_projection: str = "nearest_node"

    def __post_init__(self) -> None:
        # Store the position array in a consistent numeric shape for builders.
        self.flow_projection = normalize_flow_projection(self.flow_projection)
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
            "flow_projection",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }
        return cls(**direct_args)


@dataclass(frozen=True)
class HybridOrificeConfig:
    """Constructor-time orifice topology for a mixed liquid-film bearing.

    Exactly one of ``radius`` and ``cq`` must be supplied. ``positions`` use
    the normalized local film coordinates consumed by the existing mesh
    coupling code.
    """

    positions: Sequence[Sequence[float]]
    radius: Optional[float] = None
    cq: Optional[float] = None
    pressure: Optional[float] = None
    discharge_coefficient: float = 0.6

    def __post_init__(self) -> None:
        positions = np.asarray(self.positions, dtype=float)
        if positions.size == 0:
            raise ValueError("positions must contain at least one orifice")
        try:
            positions = positions.reshape((-1, 2))
        except ValueError as exc:
            raise ValueError("positions must contain coordinate pairs") from exc
        if not np.all(np.isfinite(positions)):
            raise ValueError("positions must contain only finite values")
        if np.any(positions < 0.0) or np.any(positions > 1.0):
            raise ValueError("positions must lie within normalized [0, 1] bounds")

        uses_radius = self.radius is not None
        uses_cq = self.cq is not None
        if uses_radius == uses_cq:
            raise ValueError("provide exactly one of radius or cq")
        if self.radius is not None:
            radius = float(self.radius)
            if not np.isfinite(radius) or radius <= 0.0:
                raise ValueError("radius must be finite and > 0")
            object.__setattr__(self, "radius", radius)
        if self.cq is not None:
            cq = float(self.cq)
            if not np.isfinite(cq) or cq <= 0.0:
                raise ValueError("cq must be finite and > 0")
            object.__setattr__(self, "cq", cq)

        if self.pressure is not None:
            pressure = float(self.pressure)
            if not np.isfinite(pressure) or pressure < 0.0:
                raise ValueError("pressure must be finite and >= 0")
            object.__setattr__(self, "pressure", pressure)
        discharge_coefficient = float(self.discharge_coefficient)
        if (
            not np.isfinite(discharge_coefficient)
            or discharge_coefficient <= 0.0
        ):
            raise ValueError(
                "discharge_coefficient must be finite and > 0"
            )
        object.__setattr__(
            self,
            "discharge_coefficient",
            discharge_coefficient,
        )
        object.__setattr__(
            self,
            "positions",
            tuple(tuple(float(value) for value in row) for row in positions),
        )


CsoArgs = namedtuple(
    "CsoArgs",
    ["d", "l", "q_leak", "w", "cd", "cq1_nondim"],
    defaults=[0.002, 0.02, 0, 1.83e-5 / 15, 0.6, None],
)

__all__ = [
    "CsoArgs",
    "HybridOrificeConfig",
    "NodimOrificeConfig",
    "OrificeConfig",
    "TankConfig",
]
