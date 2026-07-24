"""Domain configuration models split from the historical monolith."""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .film_models import HydConfig

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

__all__ = ['GasConfig']
