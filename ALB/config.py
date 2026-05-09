# coding: utf-8
from collections import namedtuple
from dataclasses import asdict, dataclass, field, fields
from typing import Optional, Union

import numpy as np

from ALB.damping import AdaptiveDampConfig, normalize_adaptive_damp_config


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
    miu: float = 0.0195  # dynamic viscosity of the liquid
    c: float = 80e-6  # c, nominal clearance of the bearing
    r: float = 0.04  # r, radius of the bearing
    l: float = 0.08  # l, length of the bearing
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
class GasConfig(HydConfig):
    """Configuration for gas bearing pressure solve.

    This config intentionally mirrors ``HydConfig`` so existing ALB-style
    input dictionaries can be reused with minimal changes.
    """

    pa: float = 101325.0  # Ambient pressure used for gas nondimensionalization.
    p_set: float = 1.0  # Prescribed outer-boundary pressure in nondimensional form.
    gamma: float = 1.0  # Dimensionless frequency ratio in the squeeze term.
    iter_method: str = "skfem_newton"
    thermal_enabled: bool = False  # Thermal coupling switch (reserved interface).
    foil_enabled: bool = False  # Enable foil-spring fluid-structure coupling.
    texture_enabled: bool = False  # Enable textured top-foil thickness correction.
    texture_type: int = 1  # Paper distribution type: 1, 2, or 3.
    texture_depth: float = None  # Texture depth in meters.
    texture_depth_ratio: float = None  # Texture depth divided by clearance.
    texture_circ_fraction: float = 0.0  # Textured portion in circumferential direction.
    texture_axial_fraction: float = 0.0  # Textured portion in axial direction.
    texture_start_theta_index: int = (
        1  # One-based starting texture-cell index in theta.
    )
    texture_start_z_index: int = (
        1  # One-based starting texture-cell index in axial direction.
    )
    foil_relaxation: float = 0.5  # Relaxation factor for foil deformation update.
    foil_tol: float = 1e-6  # Coupling tolerance based on foil deformation change.
    foil_stiffness: float = None  # Optional dimensionless spring stiffness override.
    foil_pitch: float = 4.572e-3  # Bump-foil pitch, meters.
    foil_half_length: float = 1.717e-3  # Half bump length, meters.
    foil_thickness: float = 1.3e-4  # Foil thickness, meters.
    foil_young: float = 2.1e11  # Foil Young's modulus, Pa.
    foil_poisson: float = 0.30  # Foil Poisson ratio.

    def __post_init__(self):
        super().__post_init__()
        if self.pa <= 0:
            raise ValueError("pa must be > 0")
        if self.p_set < 0:
            raise ValueError("p_set must be >= 0 for gas bearings")
        if self.gamma <= 0:
            raise ValueError("gamma must be > 0")
        if self.iter_method != "skfem_newton":
            raise ValueError(
                "GasConfig currently supports iter_method='skfem_newton' only"
            )
        if self.texture_type not in {1, 2, 3}:
            raise ValueError("texture_type must be one of: 1, 2, 3")
        if not 0.0 <= self.texture_circ_fraction <= 1.0:
            raise ValueError("texture_circ_fraction must be in [0, 1]")
        if not 0.0 <= self.texture_axial_fraction <= 1.0:
            raise ValueError("texture_axial_fraction must be in [0, 1]")
        if self.texture_start_theta_index < 1:
            raise ValueError("texture_start_theta_index must be >= 1")
        if self.texture_start_z_index < 1:
            raise ValueError("texture_start_z_index must be >= 1")
        if not 0.0 < self.foil_relaxation <= 1.0:
            raise ValueError("foil_relaxation must be in (0, 1]")
        if self.foil_tol <= 0:
            raise ValueError("foil_tol must be > 0")
        if self.texture_depth is not None and self.texture_depth < 0:
            raise ValueError("texture_depth must be >= 0")
        if self.texture_depth_ratio is not None and self.texture_depth_ratio < 0:
            raise ValueError("texture_depth_ratio must be >= 0")
        if self.foil_stiffness is not None and self.foil_stiffness <= 0:
            raise ValueError("foil_stiffness must be > 0")
        if (
            self.foil_pitch <= 0
            or self.foil_half_length <= 0
            or self.foil_thickness <= 0
        ):
            raise ValueError("foil geometric parameters must be > 0")
        if self.foil_young <= 0:
            raise ValueError("foil_young must be > 0")
        if not -1.0 < self.foil_poisson < 0.5:
            raise ValueError("foil_poisson must be in (-1, 0.5)")
        if (
            self.texture_enabled
            and self.texture_depth is None
            and self.texture_depth_ratio is None
        ):
            raise ValueError(
                "texture_enabled=True requires texture_depth or texture_depth_ratio"
            )

    def to_dict(self):
        data = super().to_dict()
        data["pa"] = self.pa
        data["gamma"] = self.gamma
        data["thermal_enabled"] = self.thermal_enabled
        data["foil_enabled"] = self.foil_enabled
        data["texture_enabled"] = self.texture_enabled
        data["texture_type"] = self.texture_type
        data["texture_depth"] = self.texture_depth
        data["texture_depth_ratio"] = self.texture_depth_ratio
        data["texture_circ_fraction"] = self.texture_circ_fraction
        data["texture_axial_fraction"] = self.texture_axial_fraction
        data["texture_start_theta_index"] = self.texture_start_theta_index
        data["texture_start_z_index"] = self.texture_start_z_index
        data["foil_relaxation"] = self.foil_relaxation
        data["foil_tol"] = self.foil_tol
        data["foil_stiffness"] = self.foil_stiffness
        data["foil_pitch"] = self.foil_pitch
        data["foil_half_length"] = self.foil_half_length
        data["foil_thickness"] = self.foil_thickness
        data["foil_young"] = self.foil_young
        data["foil_poisson"] = self.foil_poisson
        data["texture_depth_abs"] = self.texture_depth_abs
        data["resolved_foil_stiffness"] = self.resolved_foil_stiffness
        return data

    @property
    def texture_depth_abs(self):
        if self.texture_depth is not None:
            return self.texture_depth
        if self.texture_depth_ratio is not None:
            return self.texture_depth_ratio * self.c
        return 0.0

    @property
    def resolved_foil_stiffness(self):
        if self.foil_stiffness is not None:
            return self.foil_stiffness
        numerator = self.c * self.foil_young * self.foil_thickness**3
        denominator = (
            2.0
            * self.pa
            * self.foil_pitch
            * (1.0 - self.foil_poisson**2)
            * self.foil_half_length**3
        )
        return numerator / denominator

    @classmethod
    def paper_2023_foil_bearing(
        cls,
        *,
        textured: bool = True,
        texture_type: int = 1,
        texture_circ_fraction: float = 0.33,
        texture_axial_fraction: float = 1.0,
        texture_depth: float = 4.0e-6,
        eccentricity: float = 0.2,
        attitude_deg: float = 0.0,
        speed_rpm: float = 1.4e5,
        nx: int = 120,
        nz: int = 24,
        max_iter: int = 120,
        error_set: float = 1e-8,
        damp: float = 0.6,
        foil_relaxation: float = 0.5,
        foil_tol: float = 1e-6,
        path: str = None,
    ):
        """Build a gas foil bearing configuration from Zhang et al. (2023)."""
        return cls(
            e=eccentricity,
            angle=attitude_deg,
            freq=speed_rpm / 60.0,
            nx=nx,
            nz=nz,
            max_iter=max_iter,
            error_set=error_set,
            damp=damp,
            coe=True,
            reynold=True,
            miu=1.932e-5,
            c=14e-6,
            r=17.5e-3,
            l=35e-3,
            rho=1.1105,
            pa=101325.0,
            p_set=1.0,
            foil_enabled=True,
            texture_enabled=textured,
            texture_type=texture_type,
            texture_depth=texture_depth if textured else 0.0,
            texture_circ_fraction=texture_circ_fraction if textured else 0.0,
            texture_axial_fraction=texture_axial_fraction if textured else 0.0,
            foil_relaxation=foil_relaxation,
            foil_tol=foil_tol,
            foil_pitch=4.572e-3,
            foil_half_length=1.717e-3,
            foil_thickness=1.3e-4,
            foil_young=2.1e11,
            foil_poisson=0.30,
            path=path,
        )

    @classmethod
    def from_dict(cls, config_dict):
        config = super().from_dict(config_dict)
        direct_keys = [
            "pa",
            "gamma",
            "thermal_enabled",
            "foil_enabled",
            "texture_enabled",
            "texture_type",
            "texture_depth",
            "texture_depth_ratio",
            "texture_circ_fraction",
            "texture_axial_fraction",
            "texture_start_theta_index",
            "texture_start_z_index",
            "foil_relaxation",
            "foil_tol",
            "foil_stiffness",
            "foil_pitch",
            "foil_half_length",
            "foil_thickness",
            "foil_young",
            "foil_poisson",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }
        add_args = asdict(config)
        add_args.update(direct_args)
        return cls(**add_args)


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
class ServoConfig(ConfigData):
    """Configuration for the servovalve."""

    dt: float = 6.667e-4
    tw: float = 1.5059e-8
    zeta: float = 0.0039795
    tp3: float = 0.0017924
    delay: float = 0.0


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
class ThermalConfig(ConfigData):
    """Configuration for thermo-hydrodynamic viscosity coupling.

    Stored on :class:`FPBConfig.thermal_config`; ``None`` disables the thermal
    coupling.  Both dimensional (``args_nodim=False``) and nondimensional
    (``args_nodim=True``) inputs are supported.
    """

    t_in: float = 40.0
    t_ref: Optional[float] = None
    miu0: Optional[float] = None
    beta: float = 0.03
    k_lub: float = 0.00
    cp_lub: float = 2000.0
    flow_rate_factor: float = 1.0
    max_delta_t: float = 80.0
    heat_partition: float = 0.9
    relax: float = 0.5
    tol: float = 1e-3
    max_iter: int = 60
    adaptive_damp: Optional[AdaptiveDampConfig] = None
    miu_min: float = 1e-4
    miu_max: float = 1.0
    coupling: str = "full"
    """``full``: per-node viscosity in thermal source; ``half``: mean viscosity."""
    t_supply: Optional[float] = None
    """Orifice supply oil temperature; defaults to ``t_in``."""
    axial_side_bc: str = "inflow_fixed"
    """Axial-side BC: ``fixed`` (both fixed-T) | ``adiabatic`` | ``inflow_fixed``."""
    axial_side_t: Optional[float] = None
    """Axial-side fixed temperature; defaults to ``t_supply``."""
    supg: bool = True
    """Enable SUPG stabilization for advection-dominated regime."""
    pressure_backend: str = "skfem"
    """Retained for backward compatibility; only ``skfem`` is supported."""
    args_nodim: bool = False
    """Treat numeric inputs as already nondimensional when True."""
    delta_t_scale: Optional[float] = None
    """Fixed characteristic temperature rise."""
    beta_nondim: Optional[float] = None
    """Optional nondimensional beta input."""
    t_ref_nondim: Optional[float] = None
    """Optional nondimensional reference temperature input."""
    transient_enabled: bool = False
    """Enable rho*cp*h*dT/dt transient term."""
    dt: Optional[float] = None
    """Transient time step, seconds."""

    def __post_init__(self):
        self.adaptive_damp = normalize_adaptive_damp_config(self.adaptive_damp)
        if self.beta_nondim is None and self.t_ref_nondim is None:
            return
        if self.delta_t_scale is None or float(self.delta_t_scale) <= 0.0:
            raise ValueError("beta_nondim or t_ref_nondim requires delta_t_scale > 0")
        delta_t = float(self.delta_t_scale)
        t_supply = float(self.t_supply if self.t_supply is not None else self.t_in)
        if self.beta_nondim is not None:
            self.beta = float(self.beta_nondim) / delta_t
        if self.t_ref_nondim is not None:
            self.t_ref = t_supply + float(self.t_ref_nondim) * delta_t

    @classmethod
    def from_dict(cls, config_dict: Optional[dict]):
        if config_dict is None:
            return cls()
        config_dict = dict(config_dict)
        # Legacy alias: thermal_solver -> nodim flag
        if "thermal_solver" in config_dict and "nodim" not in config_dict:
            solver_name = str(config_dict["thermal_solver"]).lower()
            if solver_name == "dimensional":
                config_dict["nodim"] = False
            elif solver_name == "nondimensional":
                config_dict["nodim"] = True
            else:
                raise ValueError(
                    "thermal_solver must be one of: 'dimensional', 'nondimensional'"
                )
        if "args_nodim" not in config_dict and "nodim" in config_dict:
            config_dict["args_nodim"] = bool(config_dict["nodim"])
        # Legacy: delta_t_mode/delta_t_char described the explicit temperature
        # scale; new code should pass delta_t_scale.
        legacy_delta_t_mode = config_dict.get("delta_t_mode")
        if "delta_t_scale" not in config_dict and "delta_t_char" in config_dict:
            if legacy_delta_t_mode is None or str(legacy_delta_t_mode).lower() in {
                "fixed",
                "explicit",
                "manual",
            }:
                config_dict["delta_t_scale"] = config_dict["delta_t_char"]
        valid_fields = {item.name for item in fields(cls)}
        args = {key: config_dict[key] for key in valid_fields if key in config_dict}
        return cls(**args)


def build_thermal_config(
    thermal_enabled: bool,
    thermal_data: Optional[dict] = None,
    *,
    dt: Optional[float] = None,
    transient_default: bool = False,
) -> Optional[ThermalConfig]:
    """Build a :class:`ThermalConfig` from a flat dict, or return ``None``.

    :param thermal_enabled: ``False`` short-circuits to ``None``.
    :param thermal_data: Optional dict whose keys match :class:`ThermalConfig` fields.
    :param dt: Optional time step for transient solves; fills in when missing.
    :param transient_default: Default for ``transient_enabled`` when not provided.
    """
    if not thermal_enabled:
        return None

    thermal_args = dict(thermal_data or {})
    if thermal_args.get("transient_enabled") is None:
        thermal_args["transient_enabled"] = transient_default
    if thermal_args.get("dt") is None and dt is not None:
        thermal_args["dt"] = dt
    return ThermalConfig.from_dict(thermal_args)


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

    @property
    def thermal_enabled(self) -> bool:
        """Backwards-compatible flag derived from ``thermal_config``."""
        return self.thermal_config is not None

    def to_dict(self):
        """Returns a dictionary containing all fields and computed properties."""
        data = super().to_dict()
        # Then add its own calculated properties
        data["x0s"] = self.x0s
        return data

    @classmethod
    def from_dict(cls, config_dict):
        """Creates an instance from a dictionary.

        Accepts either the new ``thermal_config`` payload (a ``ThermalConfig``
        instance or its dict form) or the legacy ``thermal_enabled`` flag with
        a flat ``thermal`` dictionary.  In all cases the result is folded into
        a single :class:`ThermalConfig` attached to the pad.
        """
        config = super().from_dict(config_dict)
        direct_keys = ["bias", "coe"]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }
        add_args = asdict(config)
        add_args.update(direct_args)

        thermal_config = config_dict.get("thermal_config")
        if thermal_config is None:
            # Legacy: thermal_enabled + thermal dict are still accepted.
            thermal_enabled = bool(config_dict.get("thermal_enabled", False))
            thermal_data = config_dict.get("thermal")
            thermal_config = build_thermal_config(thermal_enabled, thermal_data)
        elif isinstance(thermal_config, dict):
            thermal_config = ThermalConfig.from_dict(thermal_config)
        elif not isinstance(thermal_config, ThermalConfig):
            raise TypeError("thermal_config must be a ThermalConfig, dict, or None")
        add_args["thermal_config"] = thermal_config
        return cls(**add_args)


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


@dataclass
class ALBConfig(ConfigData):
    """Configuration for the Active Lubricated Bearing (ALB) system."""

    pad_config: FPBConfig = field(default_factory=FPBConfig)
    servo_config: ServoConfig = field(default_factory=ServoConfig)
    orifice_config: OrificeConfig = field(default_factory=OrificeConfig)
    tank_config: TankConfig = field(default_factory=TankConfig)
    controller_config: Union[PIDConfig, FuzzyPIDConfig] = field(
        default_factory=PIDConfig
    )  # or FuzzyPIDConfig()
    dt: float = 6.667e-4
    node_link: np.int_ = None
    gxy: np.ndarray = np.eye(2)
    gxyt: np.ndarray = np.zeros((2, 2))
    alb: str = "ALB"  # ALB or ALBSV
    servo: str = "moog"  # moog or static
    switch: bool = True  # Whether to enable control
    c: Optional[float] = None  # Optional displacement scale override.
    w: Optional[float] = None  # Optional speed scale override, rpm.

    @property
    def thermal_enabled(self) -> bool:
        """True when the pad-level thermal config is configured."""
        return self.pad_config.thermal_config is not None

    @property
    def thermal_config(self) -> Optional["ThermalConfig"]:
        """Forward ``pad_config.thermal_config`` for convenience."""
        return self.pad_config.thermal_config

    @classmethod
    def from_dict(cls, config_dict, controller: str = "PID"):
        """
        Construct an ALBConfig instance correctly from a dictionary containing all parameters.
        :param controller: the type of the controller, PID or FuzzyPID
        :param config_dict: a dictionary containing all parameters
        """
        selected_controller = config_dict.get("controller", controller)
        if selected_controller not in {"PID", "FuzzyPID"}:
            raise ValueError("Controller must be 'PID' or 'FuzzyPID'")

        alb = config_dict.get("alb", "ALB")
        if alb not in {"ALB", "ALBSV"}:
            raise ValueError("alb must be 'ALB' or 'ALBSV'")
        servo = config_dict.get("servo", "moog")
        if servo not in {"moog", "static"}:
            raise ValueError("servo must be 'moog' or 'static'")

        # Create instances for each nested configuration item
        pad_config_instance = FPBConfig.from_dict(config_dict)
        servo_config_instance = cls.set_config(ServoConfig, config_dict)
        orifice_config_instance = cls.set_config(OrificeConfig, config_dict)
        tank_config_instance = cls.set_config(TankConfig, config_dict)
        if selected_controller == "PID":
            controller_class = PIDConfig
        elif selected_controller == "FuzzyPID":
            controller_class = FuzzyPIDConfig
        controller_instance = cls.set_config(controller_class, config_dict)

        # Extract fields that directly belong to ALBConfig
        direct_keys = [
            "dt",
            "node_link",
            "gxy",
            "gxyt",
            "alb",
            "servo",
            "switch",
            "c",
            "w",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }

        # Use the created instances and direct parameters to construct the final ALBConfig instance
        return cls(
            pad_config=pad_config_instance,
            servo_config=servo_config_instance,
            orifice_config=orifice_config_instance,
            tank_config=tank_config_instance,
            controller_config=controller_instance,
            **direct_args,
        )

    @classmethod
    def keys(cls):
        """Returns a list of all possible configuration keys."""
        keys = cls().to_dict().keys()
        # First, remove the keys of nested configurations
        keys = [
            key
            for key in keys
            if key
            not in [
                "pad_config",
                "servo_config",
                "orifice_config",
                "tank_config",
                "controller_config",
            ]
        ]
        keys.extend(cls().pad_config.to_dict().keys())
        keys.extend(cls().servo_config.to_dict().keys())
        keys.extend(cls().orifice_config.to_dict().keys())
        keys.extend(cls().tank_config.to_dict().keys())
        keys.extend(cls().controller_config.to_dict().keys())
        # Remove duplicates
        keys = list(set(keys))
        return keys


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

    @property
    def thermal_enabled(self) -> bool:
        """Backwards-compatible flag derived from ``thermal_config``."""
        return self.thermal_config is not None

    def to_dict(self):
        data = asdict(self)
        data["x0s"] = self.x0s
        return data

    @classmethod
    def from_dict(cls, config_dict):
        """Create a nodimensional pad config from a flat configuration dictionary.

        Accepts ``thermal_config`` directly or the legacy ``thermal_enabled`` +
        ``thermal`` dict combination, just like :meth:`FPBConfig.from_dict`.
        """
        direct_keys = [
            key
            for key in cls().to_dict().keys()
            if key not in {"x0s", "thermal_config"}
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }

        thermal_config = config_dict.get("thermal_config")
        if thermal_config is None:
            thermal_enabled = bool(config_dict.get("thermal_enabled", False))
            thermal_data = config_dict.get("thermal")
            thermal_config = build_thermal_config(thermal_enabled, thermal_data)
        elif isinstance(thermal_config, dict):
            thermal_config = ThermalConfig.from_dict(thermal_config)
        elif not isinstance(thermal_config, ThermalConfig):
            raise TypeError("thermal_config must be a ThermalConfig, dict, or None")
        direct_args["thermal_config"] = thermal_config
        return cls(**direct_args)


@dataclass
class NodimOrificeConfig(ConfigData):
    """Configuration for nondimensional capillary-slot orifices."""

    position: np.ndarray = field(default_factory=lambda: np.array([[0.5, 0.5]]))
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


@dataclass
class NodimALBConfig(ConfigData):
    """Configuration for ALB models assembled from nondimensional inputs."""

    pad_config: NodimPadConfig = field(default_factory=NodimPadConfig)
    orifice_config: NodimOrificeConfig = field(default_factory=NodimOrificeConfig)
    servo_config: ServoConfig = field(default_factory=ServoConfig)
    tank_config: TankConfig = field(default_factory=TankConfig)
    controller_config: Union[PIDConfig, FuzzyPIDConfig] = field(
        default_factory=PIDConfig
    )
    dt: float = 6.667e-4
    node_link: np.int_ = None
    gxy: np.ndarray = np.eye(2)
    gxyt: np.ndarray = np.zeros((2, 2))
    alb: str = "ALB"  # ALB or ALBSV
    servo: str = "moog"  # moog or static
    switch: bool = True

    @property
    def thermal_enabled(self) -> bool:
        return self.pad_config.thermal_config is not None

    @property
    def thermal_config(self) -> Optional[ThermalConfig]:
        return self.pad_config.thermal_config

    @classmethod
    def from_dict(cls, config_dict, controller: str = "PID"):
        """Create a nodimensional ALB config from the flat task/config dictionary style."""
        selected_controller = config_dict.get("controller", controller)
        if selected_controller not in {"PID", "FuzzyPID"}:
            raise ValueError("Controller must be 'PID' or 'FuzzyPID'")

        alb = config_dict.get("alb", "ALB")
        if alb not in {"ALB", "ALBSV"}:
            raise ValueError("alb must be 'ALB' or 'ALBSV'")
        servo = config_dict.get("servo", "moog")
        if servo not in {"moog", "static"}:
            raise ValueError("servo must be 'moog' or 'static'")

        controller_class = PIDConfig if selected_controller == "PID" else FuzzyPIDConfig
        direct_keys = [
            "dt",
            "node_link",
            "gxy",
            "gxyt",
            "alb",
            "servo",
            "switch",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }

        # Mirror ALBConfig.from_dict by rebuilding the nested nodim config
        # objects from a shared flat configuration payload.
        return cls(
            pad_config=NodimPadConfig.from_dict(config_dict),
            orifice_config=NodimOrificeConfig.from_dict(config_dict),
            servo_config=cls.set_config(ServoConfig, config_dict),
            tank_config=cls.set_config(TankConfig, config_dict),
            controller_config=cls.set_config(controller_class, config_dict),
            **direct_args,
        )


@dataclass
class ALBNetConfig(ConfigData):
    """Configuration for the ALB Neural Network agent."""

    scaler_X: str = "G:\\仿真计算\\20250622-代理训练\\model2\\scaler_X.pkl"
    scaler_y: str = "G:\\仿真计算\\20250622-代理训练\\model2\\scaler_y.pkl"
    model: str = "G:\\仿真计算\\20250622-代理训练\\model2\\best_model2.pth"
    c: float = 120e-6
    vf: float = 1
    freq: float = None
    ps: float = 10e6
    l: float = 0.06
    r: float = 0.04
    agent: str = "ALBNNAgent"  # ALBNNAgent, HydroNNAgent, HybridNNAgent
    metadata: Optional[str] = None
    lambda_value: float = 1.0
    beta_nondim: float = 0.03

    @classmethod
    def from_dict(cls, config_dict):
        """Creates an instance from a dictionary."""
        direct_keys = [
            "scaler_X",
            "scaler_y",
            "model",
            "c",
            "vf",
            "freq",
            "ps",
            "l",
            "r",
            "agent",
            "metadata",
            "lambda_value",
            "beta_nondim",
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
