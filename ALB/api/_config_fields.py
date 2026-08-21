"""Canonical public film-configuration field definitions.

Each entry gives the public JSON/Python name, the native solver argument, the
unit expected from users, and the physical or numerical meaning. Validation,
runtime materialization, and API-reference generation must consume these
definitions instead of maintaining separate field-name lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_UNSET = object()


@dataclass(frozen=True, slots=True)
class ConfigField:
    """Describe one public configuration value and its user-facing contract.

    ``applicability`` contains ``family:unit_system`` selectors. ``default`` is
    ``_UNSET`` when the default is conditional or intentionally undocumented;
    ``required`` marks fields that have no default at the public boundary.
    ``choices`` and ``constraint`` describe stable enum and range conditions.
    """

    native_name: str
    unit: str
    description: str
    applicability: tuple[str, ...] = ()
    default: Any = _UNSET
    required: bool = False
    choices: tuple[Any, ...] = ()
    constraint: str = ""


DIMENSIONAL_FILM_FIELDS: dict[str, ConfigField] = {
    "eccentricity": ConfigField("e", "1", "Initial eccentricity ratio e/c."),
    "attitude_angle_deg": ConfigField(
        "angle", "deg", "Initial eccentricity attitude angle."
    ),
    "rotation_frequency_hz": ConfigField(
        "freq", "Hz", "Journal rotation frequency."
    ),
    "start_angle_deg": ConfigField(
        "x0", "deg", "Circumferential start angle of the film domain."
    ),
    "arc_angle_deg": ConfigField(
        "lx", "deg", "Circumferential angular span of the film domain."
    ),
    "axial_length_ratio": ConfigField(
        "lz", "1", "Modeled axial length divided by bearing length."
    ),
    "circumferential_elements": ConfigField(
        "nx", "count", "Finite-element count around the film arc."
    ),
    "axial_elements": ConfigField(
        "nz", "count", "Finite-element count along the bearing axis."
    ),
    "mesh_type": ConfigField(
        "mesh_type",
        "name",
        "Explicit pressure/thermal mesh topology.",
        choices=("triangular", "quadrilateral"),
    ),
    "element_order": ConfigField(
        "element_order",
        "count",
        "Polynomial order of the explicit pressure/thermal basis.",
        choices=(1, 2),
    ),
    "viscosity": ConfigField("miu", "Pa*s", "Lubricant dynamic viscosity."),
    "clearance": ConfigField("c", "m", "Radial bearing clearance."),
    "radius": ConfigField("r", "m", "Journal radius."),
    "length": ConfigField("l", "m", "Physical bearing axial length."),
    "supply_pressure": ConfigField(
        "ps", "Pa", "Reference or restrictor supply pressure."
    ),
    "density": ConfigField("rho", "kg/m^3", "Lubricant density."),
    "reynolds_boundary": ConfigField(
        "reynold", "bool", "Enable the Reynolds cavitation boundary."
    ),
    "continuous_boundary": ConfigField(
        "coe", "bool", "Couple the circumferential end boundaries."
    ),
    "ambient_pressure": ConfigField(
        "p_set", "Pa", "Pressure prescribed on ambient film boundaries."
    ),
    "solver_tolerance": ConfigField(
        "error_set", "1", "Relative convergence tolerance of the film solve."
    ),
    "max_iterations": ConfigField(
        "max_iter", "count", "Maximum nonlinear film iterations."
    ),
    "relaxation": ConfigField(
        "damp", "1", "Fixed relaxation factor used by the film iteration."
    ),
    "vibration_enabled": ConfigField(
        "vib", "bool", "Include squeeze-film velocity terms."
    ),
    "x_velocity": ConfigField(
        "dxt", "m/s", "Initial journal-center velocity on the x axis."
    ),
    "y_velocity": ConfigField(
        "dyt", "m/s", "Initial journal-center velocity on the y axis."
    ),
    "whirl_ratio": ConfigField(
        "vf", "1", "Whirl frequency divided by journal rotation frequency."
    ),
    "solver": ConfigField(
        "iter_method", "name", "Native film iteration method identifier."
    ),
    "save_pressure": ConfigField(
        "save_p", "bool", "Include pressure in native persistence outputs."
    ),
    "save_thickness": ConfigField(
        "save_h", "bool", "Include film thickness in native persistence outputs."
    ),
    "gauss_points": ConfigField(
        "ngauss", "count", "Quadrature points used by Gauss integration."
    ),
    "gauss_relaxation": ConfigField(
        "gdamp", "1", "Relaxation factor for the Gauss solver."
    ),
    "gauss_tolerance": ConfigField(
        "err", "1", "Convergence tolerance for the Gauss solver."
    ),
    "pad_bias_deg": ConfigField(
        "bias", "deg", "Angular offset applied to this pad."
    ),
    "adaptive_damping": ConfigField(
        "adaptive_damp", "bool", "Adapt the iteration relaxation factor."
    ),
}


NONDIMENSIONAL_FILM_FIELDS: dict[str, ConfigField] = {
    "bearing_number": ConfigField(
        "lambda_value", "1", "Operating nondimensional bearing number."
    ),
    "reference_bearing_number": ConfigField(
        "lambda0", "1", "Reference bearing number used for scaling."
    ),
    "length_ratio": ConfigField(
        "lr", "1", "Bearing length divided by journal radius."
    ),
    "arc_angle_deg": ConfigField(
        "lx", "deg", "Circumferential angular span of the film domain."
    ),
    "axial_length_ratio": ConfigField(
        "lz", "1", "Modeled axial length divided by bearing length."
    ),
    "circumferential_elements": ConfigField(
        "nx", "count", "Finite-element count around the film arc."
    ),
    "axial_elements": ConfigField(
        "nz", "count", "Finite-element count along the bearing axis."
    ),
    "pad_bias_deg": ConfigField(
        "bias", "deg", "Angular offset applied to this pad."
    ),
    "eccentricity": ConfigField("e", "1", "Initial eccentricity ratio e/c."),
    "attitude_angle_deg": ConfigField(
        "angle", "deg", "Initial eccentricity attitude angle."
    ),
    "reynolds_boundary": ConfigField(
        "reynold", "bool", "Enable the Reynolds cavitation boundary."
    ),
    "continuous_boundary": ConfigField(
        "coe", "bool", "Couple the circumferential end boundaries."
    ),
    "ambient_pressure": ConfigField(
        "p_set", "p/ps", "Nondimensional ambient boundary pressure."
    ),
    "solver_tolerance": ConfigField(
        "error_set", "1", "Relative convergence tolerance of the film solve."
    ),
    "max_iterations": ConfigField(
        "max_iter", "count", "Maximum nonlinear film iterations."
    ),
    "relaxation": ConfigField(
        "damp", "1", "Fixed relaxation factor used by the film iteration."
    ),
    "x_velocity": ConfigField(
        "dxt", "1", "Nondimensional journal-center x velocity."
    ),
    "y_velocity": ConfigField(
        "dyt", "1", "Nondimensional journal-center y velocity."
    ),
    "whirl_ratio": ConfigField(
        "vf", "1", "Whirl frequency divided by journal rotation frequency."
    ),
    "x_center_velocity": ConfigField(
        "xct", "1", "Nondimensional moving-frame x velocity."
    ),
    "y_center_velocity": ConfigField(
        "yct", "1", "Nondimensional moving-frame y velocity."
    ),
    "scale_viscosity": ConfigField(
        "scale_miu", "Pa*s", "Viscosity used to dimensionalize outputs."
    ),
    "scale_clearance": ConfigField(
        "scale_c", "m", "Clearance used to dimensionalize displacement."
    ),
    "scale_radius": ConfigField(
        "scale_r", "m", "Journal radius used for dimensional scaling."
    ),
    "scale_length": ConfigField(
        "scale_l", "m", "Bearing length used for dimensional scaling."
    ),
    "scale_pressure": ConfigField(
        "scale_ps", "Pa", "Pressure used to dimensionalize pressure and force."
    ),
    "scale_density": ConfigField(
        "scale_rho", "kg/m^3", "Density used for dimensional scaling."
    ),
    "scale_speed_rpm": ConfigField(
        "scale_w", "rpm", "Journal speed used for dimensional scaling."
    ),
    "save_pressure": ConfigField(
        "save_p", "bool", "Include pressure in native persistence outputs."
    ),
    "save_thickness": ConfigField(
        "save_h", "bool", "Include film thickness in native persistence outputs."
    ),
    "adaptive_damping": ConfigField(
        "adaptive_damp", "bool", "Adapt the iteration relaxation factor."
    ),
}


GAS_ONLY_FILM_FIELDS: dict[str, ConfigField] = {
    "ambient_pressure_pa": ConfigField(
        "pa", "Pa", "Absolute ambient gas pressure."
    ),
    "gas_frequency_ratio": ConfigField(
        "gamma", "1", "Gas-film frequency-ratio coefficient."
    ),
    "foil_enabled": ConfigField(
        "foil_enabled", "bool", "Enable compliant-foil deformation."
    ),
    "texture_enabled": ConfigField(
        "texture_enabled", "bool", "Enable the configured surface texture."
    ),
    "texture_type": ConfigField(
        "texture_type",
        "integer",
        "Surface-texture geometry identifier.",
        applicability=("gas_film:dimensional",),
        default=1,
        choices=(1, 2, 3),
    ),
    "texture_depth": ConfigField(
        "texture_depth", "m", "Absolute texture depth."
    ),
    "texture_depth_ratio": ConfigField(
        "texture_depth_ratio", "1", "Texture depth divided by clearance."
    ),
    "texture_circumferential_fraction": ConfigField(
        "texture_circ_fraction", "1", "Textured fraction around the film arc."
    ),
    "texture_axial_fraction": ConfigField(
        "texture_axial_fraction", "1", "Textured fraction along the bearing axis."
    ),
    "texture_start_theta_index": ConfigField(
        "texture_start_theta_index",
        "index",
        "One-based circumferential mesh index where texture begins.",
        applicability=("gas_film:dimensional",),
        default=1,
        constraint=">= 1",
    ),
    "texture_start_axial_index": ConfigField(
        "texture_start_z_index",
        "index",
        "One-based axial mesh index where texture begins.",
        applicability=("gas_film:dimensional",),
        default=1,
        constraint=">= 1",
    ),
    "foil_relaxation": ConfigField(
        "foil_relaxation", "1", "Relaxation factor for foil deformation."
    ),
    "foil_tolerance": ConfigField(
        "foil_tol", "1", "Convergence tolerance for foil deformation."
    ),
    "foil_stiffness": ConfigField(
        "foil_stiffness", "N/m^3", "Distributed support stiffness of the foil."
    ),
    "foil_pitch": ConfigField(
        "foil_pitch", "m", "Circumferential pitch of foil supports."
    ),
    "foil_half_length": ConfigField(
        "foil_half_length", "m", "Half-length used by the foil model."
    ),
    "foil_thickness": ConfigField(
        "foil_thickness", "m", "Foil material thickness."
    ),
    "foil_young_modulus": ConfigField(
        "foil_young", "Pa", "Foil Young's modulus."
    ),
    "foil_poisson_ratio": ConfigField(
        "foil_poisson", "1", "Foil Poisson ratio."
    ),
}


GAS_FILM_FIELDS = {**DIMENSIONAL_FILM_FIELDS, **GAS_ONLY_FILM_FIELDS}


def native_name_map(
    fields: dict[str, ConfigField],
) -> dict[str, str]:
    """Return the direct public-name to native-argument mapping."""

    return {name: field.native_name for name, field in fields.items()}


__all__ = [
    "ConfigField",
    "DIMENSIONAL_FILM_FIELDS",
    "GAS_FILM_FIELDS",
    "GAS_ONLY_FILM_FIELDS",
    "NONDIMENSIONAL_FILM_FIELDS",
    "native_name_map",
]
