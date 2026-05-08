"""Nondimensional scaling helpers for pressure and thermal models.

This module is the single source of truth for converting between dimensional
quantities and the nondimensional inputs consumed by the pressure / thermal
solvers.  Use :class:`FilmNondimScales` for Reynolds-equation scaling and
:class:`ThermalNondimScales` for thermo-hydro scaling.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Pressure / Reynolds equation scaling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilmNondimScales:
    """Reference scales for nondimensionalising the Reynolds film equation.

    The conventions here match the legacy :func:`ALB.film.film_args_trans`
    helper but expose them as a typed, immutable object so any caller can
    convert between dimensional and nondimensional film inputs without
    duplicating the formulas.
    """

    w: float  # Rotor speed, rpm.
    miu: float  # Reference dynamic viscosity, Pa*s.
    c: float  # Radial clearance, m.
    r: float  # Journal radius, m.
    l: float  # Bearing length, m.
    ps: float  # Supply pressure, Pa.
    rho: float = 0.0  # Lubricant density, kg/m^3.
    vf: float = 1.0  # Squeeze-velocity feed coefficient.

    # ------------------------------------------------------------------
    # Derived scales
    # ------------------------------------------------------------------

    @property
    def w_rad(self) -> float:
        """Rotor speed in rad/s."""
        return self.w / 60.0 * 2.0 * np.pi

    @property
    def w_hz(self) -> float:
        """Rotor speed in Hz."""
        return self.w / 60.0

    @property
    def lr(self) -> float:
        """Length-to-diameter ratio (L / 2R)."""
        return self.l / (2.0 * self.r)

    @property
    def lambda_value(self) -> float:
        """Reynolds bearing number ``1.5 * miu * omega * L^2 / (ps * c^2)``."""
        return 1.5 * self.miu * self.w_rad * self.l**2 / (self.ps * self.c**2)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_dimensional(
        cls,
        w: float,
        miu: float,
        c: float,
        r: float,
        l: float,
        ps: float,
        rho: float = 0.0,
        vf: float = 1.0,
    ) -> "FilmNondimScales":
        """Build a scaler from dimensional inputs."""
        return cls(w=w, miu=miu, c=c, r=r, l=l, ps=ps, rho=rho, vf=vf)

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def vortex_to_nondim(self, dxt: float, dyt: float) -> Tuple[float, float]:
        """Convert vortex velocities into the nondimensional ``xct`` / ``yct``."""
        if self.w == 0:
            return 0.0, 0.0
        denom = self.c * (self.vf * self.w_hz * 2.0 * np.pi)
        return float(dxt) / denom, float(dyt) / denom

    def to_film_args(
        self,
        x0: float,
        lx: float,
        lz: float,
        nx: int,
        nz: int,
        dxt: float = 0.0,
        dyt: float = 0.0,
    ) -> Dict[str, Any]:
        """Return the nondimensional ``args`` dict consumed by film models.

        ``x0`` and ``lx`` are expected in degrees, ``lz`` in nondimensional
        units; the result mirrors the legacy ``film_args_trans`` output so
        existing call sites can drop in this constructor.
        """
        xct, yct = self.vortex_to_nondim(dxt, dyt)
        x0_rad = float(np.deg2rad(x0))
        lx_rad = float(np.deg2rad(lx))
        return {
            "w": self.w,
            "x0": x0_rad,
            "nx": int(nx),
            "nz": int(nz),
            "size": [int(nx), int(nz)],
            "miu": self.miu,
            "miu0": self.miu,
            "c": self.c,
            "r": self.r,
            "l": self.l,
            "ps": self.ps,
            "w_rad": self.w_rad,
            "w_hz": self.w_hz,
            "lr": self.lr,
            "x_lim": np.array([x0_rad, x0_rad + lx_rad]),
            "z_lim": np.array([-1.0, lz - 1.0]),
            "lambda": self.lambda_value,
            "lambda0": self.lambda_value,
            "rho": self.rho,
            "dxt": dxt,
            "dyt": dyt,
            "vf": self.vf,
            "xct": xct,
            "yct": yct,
        }


# ---------------------------------------------------------------------------
# Thermal / energy equation scaling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalNondimScales:
    """Reference scales used by the nondimensional thermo-hydro solver."""

    c: float
    r: float
    l: float
    ps: float
    miu0: float
    rho: float
    cp: float
    omega: float
    beta: float
    t_ref: float
    t_supply: float
    heat_partition: float = 1.0
    delta_t_scale: Optional[float] = None

    @classmethod
    def from_model_config(cls, model, config, miu0: Optional[float] = None):
        """Build the thermal scales from a film model and a :class:`ThermalConfig`."""
        omega = float(model.args["w"]) * 2.0 * np.pi / 60.0
        rho = float(
            getattr(model, "_input_args", {}).get("rho", model.args.get("rho", 872.0))
        )
        return cls(
            c=float(model.args["c"]),
            r=float(model.args["r"]),
            l=float(model.args["l"]),
            ps=float(model.args["ps"]),
            miu0=float(miu0 if miu0 is not None else model._input_args["miu"]),
            rho=rho,
            cp=float(config.cp_lub),
            omega=omega,
            beta=float(config.beta),
            t_ref=float(config.t_ref if config.t_ref is not None else config.t_in),
            t_supply=float(
                config.t_supply if config.t_supply is not None else config.t_in
            ),
            heat_partition=float(config.heat_partition),
            delta_t_scale=getattr(config, "delta_t_scale", None),
        )

    @property
    def lr(self) -> float:
        return self.l / (2.0 * self.r)

    @property
    def lambda0(self) -> float:
        return 1.5 * self.miu0 * self.omega * self.l**2 / (self.ps * self.c**2)

    @property
    def delta_t(self) -> float:
        if self.delta_t_scale is not None:
            if self.delta_t_scale <= 0:
                raise ValueError(
                    "Explicit temperature scaling requires delta_t_scale > 0"
                )
            return float(self.delta_t_scale)
        scale = self.heat_partition * self.ps / (self.rho * self.cp)
        return max(float(scale), 1e-12)

    @property
    def theta_e(self) -> float:
        return (
            self.heat_partition * self.ps / (self.rho * self.cp * self.delta_t)
        )

    @property
    def beta_nondim(self) -> float:
        return self.beta * self.delta_t

    @property
    def t_ref_nondim(self) -> float:
        return (self.t_ref - self.t_supply) / self.delta_t

    @property
    def flow_scale(self) -> float:
        return self.ps * self.c**3 / (12.0 * self.miu0 * self.lr**2 * self.r)

    def temperature_to_nondim(self, temperature, t_supply: float):
        return (np.asarray(temperature, dtype=float) - float(t_supply)) / self.delta_t

    def temperature_from_nondim(self, temperature_bar, t_supply: float):
        return float(t_supply) + np.asarray(temperature_bar, dtype=float) * self.delta_t

    def viscosity_to_nondim(self, miu):
        return np.asarray(miu, dtype=float) / self.miu0

    def viscosity_from_nondim(self, miu_bar):
        return np.asarray(miu_bar, dtype=float) * self.miu0

    def viscosity_ratio_from_temperature_nondim(self, temperature_bar):
        temperature_bar = np.asarray(temperature_bar, dtype=float)
        return np.exp(-self.beta_nondim * (temperature_bar - self.t_ref_nondim))

    def viscosity_from_temperature_nondim(self, temperature_bar):
        return self.miu0 * self.viscosity_ratio_from_temperature_nondim(temperature_bar)

    def heat_source_to_nondim(self, phi):
        return (
            np.asarray(phi, dtype=float)
            * self.r
            / (self.rho * self.cp * self.flow_scale * self.delta_t)
        )

    def heat_source_from_nondim(self, phi_bar):
        return np.asarray(phi_bar, dtype=float) * (
            self.rho * self.cp * self.flow_scale * self.delta_t / self.r
        )

    def flux_to_nondim(self, q):
        return np.asarray(q, dtype=float) / self.flow_scale

    def flux_from_nondim(self, q_bar):
        return np.asarray(q_bar, dtype=float) * self.flow_scale
