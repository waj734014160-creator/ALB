"""Domain configuration models split from the historical monolith."""

from dataclasses import asdict, dataclass
from typing import Optional, Union

import numpy as np

from ALB.core.numerics.damping import (
    AdaptiveDampConfig,
    normalize_adaptive_damp_config,
)
from .common_models import ConfigData
from .thermal_models import ThermalConfig

@dataclass
class HydConfig(ConfigData):
    """Configuration for a single hydrostatic bearing pad."""

    e: float = 0.0  # e, eccentricity ratio
    angle: float = 0  # angle, eccentricity angle
    freq: float = 50  # freq, frequency
    x0: float = 0  # x0, starting position of the pad in the global coordinate system
    lx: float = 360  # LX, non-dimensional radial length, °
    lz: float = 2  # LZ, non-dimensional axial length
    nx: int = 59  # NX, number of grids in x direction
    nz: int = 39  # NZ, number of grids in z direction
    mesh_type: Optional[str] = None
    element_order: Optional[int] = None
    triangle_diagonal: str = "default"
    miu: float = 0.0195  # dynamic viscosity of the liquid
    c: float = 80e-6  # c, nominal clearance of the bearing
    r: float = 0.04  # r, radius of the bearing
    l: float = 0.06  # l, length of the bearing
    ps: float = 7e6  # ps, supply pressure
    rho: float = 872  # rho, density of the liquid
    reynold: Union[bool, str] = (
        True  # Whether to use Reynolds boundary condition, or 'half_reynold' for half Reynolds
    )
    coe: bool = True  # Continuous boundary condition
    p_set: float = 0  # Ambient pressure
    error_set: float = 1e-10  # Convergence error
    max_iter: int = 120  # Maximum number of iterations
    damp: float = 0.8  # Damping factor
    vib: bool = False  # Whether to consider vortex-induced vibration
    dxt: float = None  # Vortex velocity in x direction
    dyt: float = None  # Vortex velocity in y direction
    vf: float = 1  # Vortex frequency ratio
    iter_method: str = "newton"  # Iteration method
    path: str = None  # Save path
    node_link: int = None
    save_p: bool = False
    save_h: bool = False
    ngauss: int = 50  # Number of Gauss iterations for Gauss iteration method
    gdamp: float = 1.2  # Relaxation factor for Gauss iteration method
    err: float = 1e-3  # Allowable residual for Gauss iteration method
    adaptive_damp: Optional[AdaptiveDampConfig] = None

    def __post_init__(self):
        self.adaptive_damp = normalize_adaptive_damp_config(self.adaptive_damp)
        if not 0 <= self.e < 1:
            raise ValueError("e must be in [0, 1)")
        if self.ps <= 0:
            raise ValueError("ps must be > 0")
        if self.c <= 0:
            raise ValueError("c must be > 0")
        if self.freq <= 0:
            raise ValueError("freq must be > 0")
        if self.nx < 2 or self.nz < 2:
            raise ValueError("nx and nz must be >= 2")
        if (self.mesh_type is None) != (self.element_order is None):
            raise ValueError("mesh_type and element_order must be provided together")
        if self.mesh_type is not None:
            if self.mesh_type not in {"triangular", "quadrilateral"}:
                raise ValueError(
                    "mesh_type must be 'triangular' or 'quadrilateral'"
                )
            if self.element_order not in {1, 2}:
                raise ValueError("element_order must be 1 or 2")
        if self.triangle_diagonal not in {"default", "mirrored"}:
            raise ValueError("triangle_diagonal must be 'default' or 'mirrored'")
        if self.lx <= 0 or self.lz <= 0:
            raise ValueError("lx and lz must be > 0")
        if self.error_set <= 0:
            raise ValueError("error_set must be > 0")
        if self.max_iter <= 0:
            raise ValueError("max_iter must be > 0")
        if self.iter_method not in {"newton", "gauss", "lsq", "skfem_newton"}:
            raise ValueError(
                "iter_method must be one of: newton, gauss, lsq, skfem_newton"
            )
        if not isinstance(self.reynold, bool) and self.reynold != "half_reynold":
            raise ValueError("reynold must be bool or 'half_reynold'")
        if self.path is None:
            self.path = ""

    @property
    def w(self):
        """Execute w."""
        return self.freq * 60  # rpm

    @property
    def angle_rad(self):
        """Execute angle_rad."""
        return np.deg2rad(self.angle)  # Convert to radians

    def to_dict(self):
        """Returns a dictionary containing all fields and computed properties."""
        # 1. First, get a dictionary of all base fields
        data = asdict(self)

        # 2. Manually add computed properties
        data["w"] = self.w
        data["angle_rad"] = self.angle_rad

        return data

    @classmethod
    def from_dict(cls, config_dict):
        """Creates an instance from a dictionary."""
        direct_keys = [
            "e",
            "angle",
            "freq",
            "x0",
            "lx",
            "lz",
            "nx",
            "nz",
            "mesh_type",
            "element_order",
            "triangle_diagonal",
            "miu",
            "c",
            "r",
            "l",
            "ps",
            "rho",
            "reynold",
            "coe",
            "p_set",
            "error_set",
            "max_iter",
            "damp",
            "vib",
            "dxt",
            "dyt",
            "vf",
            "iter_method",
            "path",
            "node_link",
            "save_p",
            "save_h",
            "ngauss",
            "gdamp",
            "err",
            "adaptive_damp",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }
        return cls(**direct_args)

@dataclass
class FPBConfig(HydConfig):
    """Configuration for a four-pad bearing."""

    bias: float = 0  # Pad bias angle, default 0
    coe: bool = False  # Whether to use continuous boundary, default False
    thermal_config: Optional["ThermalConfig"] = None

    @property
    def x0s(self):
        """Starting angles for the four pads."""
        lx = self.lx
        bias = self.bias
        x0s = [
            bias - lx / 2,
            bias + 180 - lx / 2,
            bias + 270 - lx / 2,
            bias + 90 - lx / 2,
        ]
        return x0s

    def to_dict(self):
        """Returns a dictionary containing all fields and computed properties."""
        data = super().to_dict()
        # Then add its own calculated properties
        data["x0s"] = self.x0s
        return data

    @classmethod
    def from_dict(cls, config_dict):
        """Create an instance from strict typed configuration fields."""
        forbidden = sorted(
            set(config_dict).intersection({"thermal_enabled", "thermal"})
        )
        if forbidden:
            raise ValueError(f"removed pad configuration fields: {forbidden}")
        config = super().from_dict(config_dict)
        direct_keys = ["bias", "coe"]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }
        add_args = asdict(config)
        add_args.update(direct_args)

        thermal_config = config_dict.get("thermal_config")
        if isinstance(thermal_config, dict):
            thermal_config = ThermalConfig.from_dict(thermal_config)
        elif thermal_config is not None and not isinstance(
            thermal_config,
            ThermalConfig,
        ):
            raise TypeError("thermal_config must be a ThermalConfig, dict, or None")
        add_args["thermal_config"] = thermal_config
        return cls(**add_args)

@dataclass
class NodimPadConfig(ConfigData):
    """Configuration for four nondimensional hydrostatic bearing pads."""

    lambda_value: float = 1.0
    lr: float = 1.0
    lx: float = 360.0
    lz: float = 2.0
    nx: int = 59
    nz: int = 39
    bias: float = 0.0
    e: float = 0.0
    angle: float = 0.0
    reynold: Union[bool, str] = True
    coe: bool = True
    p_set: float = 0.0
    error_set: float = 1e-10
    max_iter: int = 120
    damp: float = 0.8
    adaptive_damp: Optional[AdaptiveDampConfig] = None
    node_link: int = None
    save_p: bool = False
    save_h: bool = False
    dxt: float = 0.0
    dyt: float = 0.0
    vf: float = 1.0
    xct: float = 0.0
    yct: float = 0.0
    scale_miu: float = 1.0
    scale_c: float = 1.0
    scale_r: float = 1.0
    scale_l: Optional[float] = None
    scale_ps: float = 1.0
    scale_rho: float = 1.0
    scale_w: Optional[float] = None
    lambda0: float = None
    path: str = "bearing_result"
    thermal_config: Optional[ThermalConfig] = None

    def __post_init__(self):
        self.adaptive_damp = normalize_adaptive_damp_config(self.adaptive_damp)
        if self.lambda_value <= 0:
            raise ValueError("lambda_value must be > 0")
        if self.lr <= 0:
            raise ValueError("lr must be > 0")
        if self.lx <= 0 or self.lz <= 0:
            raise ValueError("lx and lz must be > 0")
        if self.nx < 2 or self.nz < 2:
            raise ValueError("nx and nz must be >= 2")
        if not 0 <= self.e < 1:
            raise ValueError("e must be in [0, 1)")
        if self.error_set <= 0:
            raise ValueError("error_set must be > 0")
        if self.max_iter <= 0:
            raise ValueError("max_iter must be > 0")
        if not isinstance(self.reynold, bool) and self.reynold != "half_reynold":
            raise ValueError("reynold must be bool or 'half_reynold'")

    @property
    def x0s(self):
        """Return the four pad start angles using the same convention as FPBConfig."""
        lx = self.lx
        bias = self.bias
        return [
            bias - lx / 2.0,
            bias + 180.0 - lx / 2.0,
            bias + 270.0 - lx / 2.0,
            bias + 90.0 - lx / 2.0,
        ]

    def to_dict(self):
        data = asdict(self)
        data["x0s"] = self.x0s
        return data

    @classmethod
    def from_dict(cls, config_dict):
        """Create a nondimensional pad from strict typed fields."""
        forbidden = sorted(
            set(config_dict).intersection({"thermal_enabled", "thermal"})
        )
        if forbidden:
            raise ValueError(f"removed pad configuration fields: {forbidden}")
        direct_keys = [
            key
            for key in cls().to_dict().keys()
            if key not in {"x0s", "thermal_config"}
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }

        thermal_config = config_dict.get("thermal_config")
        if isinstance(thermal_config, dict):
            thermal_config = ThermalConfig.from_dict(thermal_config)
        elif thermal_config is not None and not isinstance(
            thermal_config,
            ThermalConfig,
        ):
            raise TypeError("thermal_config must be a ThermalConfig, dict, or None")
        direct_args["thermal_config"] = thermal_config
        return cls(**direct_args)

__all__ = ['HydConfig', 'FPBConfig', 'NodimPadConfig']
