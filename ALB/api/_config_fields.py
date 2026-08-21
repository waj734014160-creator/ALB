"""Canonical public bearing and simulation configuration field definitions.

Each entry gives the public JSON/Python name, the native runtime argument, value
type, unit, default or required status, applicability, and stable constraints.
Validation, runtime materialization, and API-reference generation consume these
definitions instead of maintaining separate public-field lists.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping


_UNSET = object()


@dataclass(frozen=True, slots=True)
class ConfigField:
    """Describe one public configuration value and its user-facing contract.

    ``applicability`` contains ``family:unit_system`` selectors. ``default`` is
    ``_UNSET`` only when the value is required or supplied by a parent section;
    ``required`` marks fields that have no default at the public boundary.
    ``choices`` and ``constraint`` describe stable enum and range conditions.
    ``default_description`` records a conditional fallback when no single literal
    default exists. ``value_type`` uses JSON-oriented type names so generated
    references do not depend on implementation annotations.
    """

    native_name: str
    unit: str
    description: str
    applicability: tuple[str, ...] = ()
    default: Any = _UNSET
    required: bool = False
    choices: tuple[Any, ...] = ()
    constraint: str = ""
    value_type: str = "number"
    default_description: str = ""

    @property
    def has_default(self) -> bool:
        """Return whether the public boundary defines an explicit default."""

        return self.default is not _UNSET


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


# Public defaults are copied from the native dataclass constructors and from the
# facade materialization rules in ``ALB.api.building``. Keeping them here lets
# validation and documentation share one machine-readable contract.
_DIMENSIONAL_DEFAULTS: Mapping[str, Any] = {
    "eccentricity": 0.0,
    "attitude_angle_deg": 0.0,
    "rotation_frequency_hz": 50.0,
    "start_angle_deg": 0.0,
    "arc_angle_deg": 360.0,
    "axial_length_ratio": 2.0,
    "circumferential_elements": 59,
    "axial_elements": 39,
    "mesh_type": None,
    "element_order": None,
    "viscosity": 0.0195,
    "clearance": 8.0e-5,
    "radius": 0.04,
    "length": 0.06,
    "supply_pressure": 7.0e6,
    "density": 872.0,
    "reynolds_boundary": True,
    "continuous_boundary": "family-dependent: liquid/gas=true, active=false",
    "ambient_pressure": 0.0,
    "solver_tolerance": 1.0e-10,
    "max_iterations": 120,
    "relaxation": 0.8,
    "vibration_enabled": False,
    "x_velocity": None,
    "y_velocity": None,
    "whirl_ratio": 1.0,
    "solver": "newton",
    "save_pressure": False,
    "save_thickness": False,
    "gauss_points": 50,
    "gauss_relaxation": 1.2,
    "gauss_tolerance": 1.0e-3,
    "pad_bias_deg": 0.0,
    "adaptive_damping": None,
}

_NONDIMENSIONAL_DEFAULTS: Mapping[str, Any] = {
    "bearing_number": 1.0,
    "reference_bearing_number": None,
    "length_ratio": 1.0,
    "arc_angle_deg": 360.0,
    "axial_length_ratio": 2.0,
    "circumferential_elements": 59,
    "axial_elements": 39,
    "pad_bias_deg": 0.0,
    "eccentricity": 0.0,
    "attitude_angle_deg": 0.0,
    "reynolds_boundary": True,
    "continuous_boundary": True,
    "ambient_pressure": 0.0,
    "solver_tolerance": 1.0e-10,
    "max_iterations": 120,
    "relaxation": 0.8,
    "x_velocity": 0.0,
    "y_velocity": 0.0,
    "whirl_ratio": 1.0,
    "x_center_velocity": 0.0,
    "y_center_velocity": 0.0,
    "scale_viscosity": 1.0,
    "scale_clearance": 1.0,
    "scale_radius": 1.0,
    "scale_length": None,
    "scale_pressure": 1.0,
    "scale_density": 1.0,
    "scale_speed_rpm": None,
    "save_pressure": False,
    "save_thickness": False,
    "adaptive_damping": None,
}

_GAS_DEFAULTS: Mapping[str, Any] = {
    "ambient_pressure_pa": 101325.0,
    "gas_frequency_ratio": 1.0,
    "foil_enabled": False,
    "texture_enabled": False,
    "texture_type": 1,
    "texture_depth": None,
    "texture_depth_ratio": None,
    "texture_circumferential_fraction": 0.0,
    "texture_axial_fraction": 0.0,
    "texture_start_theta_index": 1,
    "texture_start_axial_index": 1,
    "foil_relaxation": 0.5,
    "foil_tolerance": 1.0e-6,
    "foil_stiffness": None,
    "foil_pitch": 4.572e-3,
    "foil_half_length": 1.717e-3,
    "foil_thickness": 1.3e-4,
    "foil_young_modulus": 2.1e11,
    "foil_poisson_ratio": 0.3,
}

_BOOLEAN_FIELDS = {
    "adaptive_damping",
    "continuous_boundary",
    "foil_enabled",
    "reynolds_boundary",
    "save_pressure",
    "save_thickness",
    "texture_enabled",
    "vibration_enabled",
}
_INTEGER_FIELDS = {
    "axial_elements",
    "circumferential_elements",
    "element_order",
    "gauss_points",
    "max_iterations",
    "texture_start_axial_index",
    "texture_start_theta_index",
    "texture_type",
}
_STRING_FIELDS = {"mesh_type", "solver"}

_FILM_CONSTRAINTS = {
    "eccentricity": "0 <= value < 1",
    "rotation_frequency_hz": "> 0",
    "arc_angle_deg": "> 0",
    "axial_length_ratio": "> 0",
    "circumferential_elements": ">= 2",
    "axial_elements": ">= 2",
    "element_order": "1 or 2; required together with mesh_type",
    "mesh_type": "required together with element_order",
    "viscosity": "> 0",
    "clearance": "> 0",
    "radius": "> 0",
    "length": "> 0",
    "supply_pressure": "> 0",
    "density": "> 0",
    "solver_tolerance": "> 0",
    "max_iterations": ">= 1",
    "bearing_number": "> 0",
    "length_ratio": "> 0",
    "scale_viscosity": "> 0",
    "scale_clearance": "> 0",
    "scale_radius": "> 0",
    "scale_length": "None or > 0",
    "scale_pressure": "> 0",
    "scale_density": "> 0",
    "scale_speed_rpm": "None or > 0",
    "ambient_pressure_pa": "> 0",
    "gas_frequency_ratio": "> 0",
    "texture_depth": "None or >= 0",
    "texture_depth_ratio": "None or >= 0",
    "texture_circumferential_fraction": "0 <= value <= 1",
    "texture_axial_fraction": "0 <= value <= 1",
    "texture_start_theta_index": ">= 1",
    "texture_start_axial_index": ">= 1",
    "foil_relaxation": "0 < value <= 1",
    "foil_tolerance": "> 0",
    "foil_stiffness": "None or > 0",
    "foil_pitch": "> 0",
    "foil_half_length": "> 0",
    "foil_thickness": "> 0",
    "foil_young_modulus": "> 0",
    "foil_poisson_ratio": "-1 < value < 0.5",
}


def _enrich_fields(
    fields: Mapping[str, ConfigField],
    defaults: Mapping[str, Any],
) -> dict[str, ConfigField]:
    """Return fields completed with public type, default, and range metadata."""

    result: dict[str, ConfigField] = {}
    for name, field in fields.items():
        default = defaults[name]
        if name == "adaptive_damping":
            value_type = "boolean or mapping or null"
        elif name == "reynolds_boundary":
            value_type = "boolean or 'half_reynold'"
        elif name in _BOOLEAN_FIELDS:
            value_type = "boolean"
        elif name in _INTEGER_FIELDS:
            value_type = "integer or null" if default is None else "integer"
        elif name in _STRING_FIELDS:
            value_type = "string or null" if default is None else "string"
        else:
            value_type = "number or null" if default is None else "number"
        result[name] = replace(
            field,
            default=default,
            value_type=value_type,
            constraint=field.constraint or _FILM_CONSTRAINTS.get(name, "finite"),
        )
    return result


DIMENSIONAL_FILM_FIELDS = _enrich_fields(
    DIMENSIONAL_FILM_FIELDS,
    _DIMENSIONAL_DEFAULTS,
)
DIMENSIONAL_FILM_FIELDS["continuous_boundary"] = replace(
    DIMENSIONAL_FILM_FIELDS["continuous_boundary"],
    default=_UNSET,
    default_description="true for liquid_film; false for active_lubricated",
)
NONDIMENSIONAL_FILM_FIELDS = _enrich_fields(
    NONDIMENSIONAL_FILM_FIELDS,
    _NONDIMENSIONAL_DEFAULTS,
)
GAS_ONLY_FILM_FIELDS = _enrich_fields(GAS_ONLY_FILM_FIELDS, _GAS_DEFAULTS)
GAS_FILM_FIELDS = {**DIMENSIONAL_FILM_FIELDS, **GAS_ONLY_FILM_FIELDS}
GAS_FILM_FIELDS["continuous_boundary"] = replace(
    GAS_FILM_FIELDS["continuous_boundary"],
    default=True,
    default_description="",
)
GAS_FILM_FIELDS["ambient_pressure"] = replace(
    GAS_FILM_FIELDS["ambient_pressure"], default=1.0, constraint=">= 0"
)
GAS_FILM_FIELDS["solver"] = replace(
    GAS_FILM_FIELDS["solver"],
    default="skfem_newton",
    choices=("skfem_newton",),
)
GAS_FILM_OVERRIDE_FIELDS: dict[str, ConfigField] = {
    "continuous_boundary": GAS_FILM_FIELDS["continuous_boundary"],
    "ambient_pressure": GAS_FILM_FIELDS["ambient_pressure"],
    "solver": GAS_FILM_FIELDS["solver"],
    **GAS_ONLY_FILM_FIELDS,
}


def _field(
    unit: str,
    description: str,
    *,
    value_type: str,
    default: Any = _UNSET,
    required: bool = False,
    choices: tuple[Any, ...] = (),
    constraint: str = "",
    applicability: tuple[str, ...] = (),
    native_name: str | None = None,
    default_description: str = "",
) -> ConfigField:
    """Create metadata for a non-film field with an identity native name."""

    return ConfigField(
        native_name=native_name or "same as public field",
        unit=unit,
        description=description,
        applicability=applicability,
        default=default,
        required=required,
        choices=choices,
        constraint=constraint,
        value_type=value_type,
        default_description=default_description,
    )


BEARING_DOCUMENT_FIELDS: dict[str, ConfigField] = {
    "schema_version": _field(
        "version", "Exact document schema version.", value_type="string",
        default="0.4.0", choices=("0.4.0",),
    ),
    "kind": _field(
        "name", "Document role at the top level or in an include.",
        value_type="string", required=True,
        choices=("bearing", "bearing_profile"),
    ),
    "includes": _field(
        "path list", "Ordered relative bearing-profile paths merged before spec.",
        value_type="array[string]", default=(),
        constraint="relative, unique, acyclic, and contained below document root",
    ),
    "spec": _field(
        "mapping", "Bearing specification overlaid after included profiles.",
        value_type="object", required=True,
    ),
}

BEARING_SPEC_FIELDS: dict[str, ConfigField] = {
    "family": _field(
        "name", "Bearing runtime family discriminator.", value_type="string",
        required=True,
        choices=("liquid_film", "active_lubricated", "gas_film", "multi_pad", "surrogate"),
    ),
    "unit_system": _field(
        "name", "Input and output unit system for this bearing.",
        value_type="string", required=True,
        choices=("dimensional", "nondimensional"),
        constraint="gas_film requires dimensional",
    ),
    "time_step": _field(
        "s or local time unit", "Bearing-local integration time step.",
        value_type="number", required=True, constraint="finite and > 0",
    ),
    "node": _field(
        "index", "Optional rotor node used by direct coupling metadata.",
        value_type="integer or null", default=None, constraint=">= 0 when provided",
    ),
    "film": _field(
        "mapping", "Film geometry, material, mesh, and solver section.",
        value_type="object", required=True,
        applicability=("liquid_film", "active_lubricated", "gas_film"),
    ),
    "restrictors": _field(
        "mapping", "Optional liquid restrictors or required active restrictors.",
        value_type="object or null", default=None,
        applicability=("liquid_film", "active_lubricated"),
    ),
    "thermal": _field(
        "mapping", "Optional thermo-hydrodynamic coupling section.",
        value_type="object or null", default=None,
        applicability=("liquid_film", "active_lubricated"),
    ),
    "tank": _field(
        "mapping", "Active-bearing recess/tank geometry.", value_type="object",
        required=True, applicability=("active_lubricated",),
    ),
    "valve": _field(
        "mapping", "Active-bearing servo-valve model.", value_type="object",
        required=True, applicability=("active_lubricated",),
    ),
    "control": _field(
        "mapping", "Active-bearing controller declaration.", value_type="object",
        required=True, applicability=("active_lubricated",),
    ),
    "transforms": _field(
        "mapping", "Optional physical-to-controller input transforms.",
        value_type="object", default={}, applicability=("active_lubricated",),
    ),
    "pads": _field(
        "list", "Nonempty child bearing specs or relative bearing-file paths.",
        value_type="array[string or object]", required=True,
        applicability=("multi_pad",),
        constraint="at least one item; child time_step and unit_system must agree",
    ),
    "model_package": _field(
        "mapping", "Validated ALBNN package location and augmentation override.",
        value_type="object", required=True, applicability=("surrogate",),
    ),
    "runtime": _field(
        "mapping", "Surrogate runtime parameters and spool source.",
        value_type="object", default={}, applicability=("surrogate",),
    ),
}

LIQUID_RESTRICTOR_FIELDS: dict[str, ConfigField] = {
    "positions": _field(
        "normalized coordinate pairs", "Restrictor circumferential/axial positions.",
        value_type="array[array[number, 2]]", required=True,
        constraint="nonempty",
    ),
    "radius": _field(
        "m", "Physical restrictor radius.", value_type="number or null",
        default=None, constraint="exactly one of radius and flow_coefficient",
    ),
    "flow_coefficient": _field(
        "1", "Already nondimensionalized restrictor flow coefficient.",
        value_type="number or null", default=None,
        constraint="exactly one of radius and flow_coefficient",
    ),
    "pressure": _field(
        "Pa or p/ps", "Optional restrictor supply pressure override.",
        value_type="number or null", default=None,
    ),
    "discharge_coefficient": _field(
        "1", "Orifice discharge coefficient.", value_type="number",
        default=0.6, constraint="> 0",
    ),
}

ACTIVE_RESTRICTOR_FIELDS: dict[str, ConfigField] = {
    "positions": _field(
        "normalized coordinate pairs", "Active restrictor locations.",
        value_type="array[array[number, 2]]", required=True,
        constraint="nonempty",
    ),
    "supply_pressure": _field(
        "Pa or p/ps", "Restrictor supply pressure.", value_type="number",
        default_description="film.supply_pressure for dimensional; 1.0 for nondimensional",
    ),
    "tank_pressure": _field(
        "Pa or p/ps", "Tank/reference pressure.", value_type="number", default=0.0,
    ),
    "flow_coefficient": _field(
        "1", "Legacy active flow coefficient or dimensional cq1 override.",
        value_type="number or null", default=None,
    ),
    "orifice_diameter": _field(
        "m", "Dimensional orifice diameter.", value_type="number", default=0.002,
        constraint="> 0", applicability=("active_lubricated:dimensional",),
    ),
    "orifice_length": _field(
        "m", "Dimensional orifice length.", value_type="number", default=0.02,
        constraint="> 0", applicability=("active_lubricated:dimensional",),
    ),
    "valve_area": _field(
        "m^2", "Dimensional valve reference area.", value_type="number",
        default=1.83e-5 / 15.0, constraint="> 0",
        applicability=("active_lubricated:dimensional",),
    ),
    "discharge_coefficient": _field(
        "1", "Dimensional orifice discharge coefficient.", value_type="number",
        default=0.6, constraint="> 0",
        applicability=("active_lubricated:dimensional",),
    ),
    "flow_projection": _field(
        "name", "Point-source projection onto pressure/thermal degrees of freedom.",
        value_type="string", default="nearest_node",
        choices=("nearest_node", "element_shape"),
    ),
    "base_flow_coefficient": _field(
        "1", "Nondimensional base-flow coefficient cq0.", value_type="number",
        default=1.0, applicability=("active_lubricated:nondimensional",),
    ),
    "spool_flow_coefficient": _field(
        "1", "Nondimensional spool-flow coefficient cq1.", value_type="number",
        default_description="flow_coefficient when provided; otherwise 1.0",
        applicability=("active_lubricated:nondimensional",),
    ),
    "pressure_flow_coefficient": _field(
        "1", "Nondimensional pressure-flow coefficient cq2.", value_type="number",
        default=0.0, applicability=("active_lubricated:nondimensional",),
    ),
}

TANK_FIELDS: dict[str, ConfigField] = {
    "x_range": _field(
        "normalized pair", "Circumferential tank/recess interval.",
        value_type="array[number, 2]", default=(0.49, 0.51),
    ),
    "z_range": _field(
        "normalized pair", "Axial tank/recess interval.",
        value_type="array[number, 2]", default=(0.2, 0.8),
    ),
    "depth_ratio": _field(
        "h/c", "Tank depth divided by clearance.", value_type="number", default=2.0,
    ),
}

VALVE_COMMON_FIELDS: dict[str, ConfigField] = {
    "model": _field(
        "name", "Servo-valve model discriminator.", value_type="string",
        required=True, choices=("second_order", "static", "transfer_function"),
    ),
}
SECOND_ORDER_VALVE_FIELDS: dict[str, ConfigField] = {
    **VALVE_COMMON_FIELDS,
    "natural_frequency_hz": _field(
        "Hz", "Second-order natural frequency.", value_type="number",
        required=True, constraint="> 0",
    ),
    "damping_ratio": _field(
        "1", "Second-order damping ratio.", value_type="number",
        required=True, constraint="> 0",
    ),
    "delay": _field(
        "s", "Nonnegative command delay.", value_type="number", default=0.0,
        constraint=">= 0",
    ),
}
STATIC_VALVE_FIELDS = dict(VALVE_COMMON_FIELDS)
TRANSFER_FUNCTION_VALVE_FIELDS: dict[str, ConfigField] = {
    **VALVE_COMMON_FIELDS,
    "numerator": _field(
        "descending powers of s", "Continuous-time numerator coefficients.",
        value_type="array[number]", required=True,
        constraint="finite, nonempty, nonzero leading coefficient; transfer proper",
    ),
    "denominator": _field(
        "descending powers of s", "Continuous-time denominator coefficients.",
        value_type="array[number]", required=True,
        constraint="finite, nonempty, nonzero leading coefficient",
    ),
}

CONTROL_FIELDS: dict[str, ConfigField] = {
    "mode": _field(
        "name", "Controller ownership and algorithm mode.", value_type="string",
        required=True,
        choices=("pid", "fuzzy_pid", "uncontrolled", "external_spool"),
    ),
    "gains": _field(
        "mapping", "PID gains; accepted only for pid mode.",
        value_type="object or null", default=None, applicability=("pid",),
    ),
    "frequency_hz": _field(
        "Hz", "Controller update/reference frequency.", value_type="number",
        default_description="50.0 for pid; 5.0 for fuzzy_pid",
        applicability=("pid", "fuzzy_pid"),
    ),
    "sensor_angles_deg": _field(
        "deg", "Two sensor directions used by PID/fuzzy PID.",
        value_type="array[number, 2]", default=(45.0, 135.0),
        applicability=("pid", "fuzzy_pid"),
    ),
    "error_range": _field(
        "[min, max, step]", "Fuzzy error universe.", value_type="array[number, 3]",
        default=(-1.0, 1.0, 0.01), applicability=("fuzzy_pid",),
    ),
    "delta_error_range": _field(
        "[min, max, step]", "Fuzzy error-change universe.",
        value_type="array[number, 3]", default=(-1.0, 1.0, 0.01),
        applicability=("fuzzy_pid",),
    ),
    "kp_range": _field(
        "[min, max, step]", "Fuzzy proportional-gain universe.",
        value_type="array[number, 3]", default=(0.0, 1.0, 0.01),
        applicability=("fuzzy_pid",),
    ),
    "ki_range": _field(
        "[min, max, step]", "Fuzzy integral-gain universe.",
        value_type="array[number, 3]", default=(0.0, 0.0, 0.01),
        applicability=("fuzzy_pid",),
    ),
    "kd_range": _field(
        "[min, max, step]", "Fuzzy derivative-gain universe.",
        value_type="array[number, 3]", default=(0.0, 1.0, 0.01),
        applicability=("fuzzy_pid",),
    ),
    "rule_path": _field(
        "relative path", "Fuzzy rule CSV resolved below resource_root.",
        value_type="string", default="fuzzy_rules.csv", applicability=("fuzzy_pid",),
    ),
}

PID_GAIN_FIELDS: dict[str, ConfigField] = {
    "kp": _field("controller units", "Proportional gain.", value_type="number", default=0.0),
    "ki": _field("controller units", "Integral gain.", value_type="number", default=0.0),
    "kd": _field("controller units", "Derivative gain.", value_type="number", default=0.0),
    "feedforward": _field("controller units", "Constant feed-forward term.", value_type="number", default=0.0),
}

TRANSFORM_FIELDS: dict[str, ConfigField] = {
    "displacement_to_control": _field(
        "matrix", "Physical-displacement to controller-input transform.",
        value_type="array[array[number]]", default=((1.0, 0.0), (0.0, 1.0)),
    ),
    "velocity_to_control": _field(
        "matrix", "Physical-velocity to controller-input transform.",
        value_type="array[array[number]]", default=((0.0, 0.0), (0.0, 0.0)),
    ),
}

THERMAL_FIELDS: dict[str, ConfigField] = {
    "t_in": _field("degC", "Lubricant inlet temperature.", value_type="number", default=40.0),
    "t_ref": _field("degC", "Reference temperature for viscosity.", value_type="number or null", default=None),
    "miu0": _field("Pa*s", "Viscosity at t_ref; inherits film viscosity when absent.", value_type="number or null", default=None, constraint="None or > 0"),
    "beta": _field("1/degC", "Dimensional viscosity-temperature coefficient.", value_type="number", default=0.03),
    "k_lub": _field("W/(m*K)", "Lubricant thermal conductivity.", value_type="number", default=0.0, constraint=">= 0"),
    "cp_lub": _field("J/(kg*K)", "Lubricant heat capacity.", value_type="number", default=2000.0, constraint="> 0"),
    "max_delta_t": _field("degC", "Maximum accepted temperature rise.", value_type="number", default=80.0),
    "heat_partition": _field("1", "Fraction of friction heat entering lubricant.", value_type="number", default=0.9),
    "relax": _field("1", "Outer thermal relaxation factor.", value_type="number", default=0.5),
    "miu_update": _field("name", "Outer viscosity update rule.", value_type="string", default="linear", choices=("linear", "log")),
    "miu_update_max_ratio": _field("1", "Optional multiplier cap for log viscosity updates.", value_type="number or null", default=None, constraint="None or > 1"),
    "heat_partition_steps": _field("sequence", "Optional positive continuation schedule ending at heat_partition.", value_type="array[number] or null", default=None),
    "iter_method": _field("name", "Thermal nonlinear iteration method.", value_type="string", default="direct", choices=("direct", "newton", "direct_then_newton")),
    "tol": _field("1", "Thermal outer-iteration tolerance.", value_type="number", default=1.0e-6, constraint="> 0"),
    "max_iter": _field("count", "Thermal outer-iteration limit.", value_type="integer", default=60, constraint="> 0"),
    "adaptive_damp": _field("mapping", "Optional adaptive outer-relaxation policy.", value_type="boolean or object or null", default=None),
    "miu_min": _field("Pa*s", "Viscosity clipping lower bound.", value_type="number", default=1.0e-4),
    "miu_max": _field("Pa*s", "Viscosity clipping upper bound.", value_type="number", default=1.0),
    "coupling": _field("name", "Nodal or mean-viscosity thermal coupling.", value_type="string", default="full", choices=("full", "half")),
    "t_supply": _field("degC", "Orifice supply temperature; falls back to t_in.", value_type="number or null", default=None),
    "axial_side_bc": _field("name", "Axial-side thermal boundary condition.", value_type="string", default="inflow_fixed", choices=("fixed", "adiabatic", "inflow_fixed")),
    "axial_side_t": _field("degC", "Fixed axial-side temperature; falls back to t_supply.", value_type="number or null", default=None),
    "supg": _field("bool", "Enable SUPG stabilization.", value_type="boolean", default=True),
    "delta_t_scale": _field("degC", "Characteristic nondimensional temperature rise.", value_type="number or null", default=None, constraint="> 0 when beta_nondim or t_ref_nondim is provided"),
    "beta_nondim": _field("1", "Optional nondimensional viscosity-temperature coefficient.", value_type="number or null", default=None),
    "t_ref_nondim": _field("1", "Optional nondimensional reference temperature.", value_type="number or null", default=None),
    "transient_enabled": _field("bool", "Enable the thermal transient term.", value_type="boolean", default=False, constraint="requires iter_method='direct'"),
    "thermal_newton_max_iter": _field("count", "Maximum Newton iterations per thermal subsolve.", value_type="integer", default=30, constraint="> 0"),
    "thermal_newton_tol": _field("1", "Newton residual tolerance; falls back to tol.", value_type="number or null", default=None, constraint="None or > 0"),
    "thermal_newton_damp": _field("1", "Initial Newton damping factor.", value_type="number", default=1.0, constraint="> 0"),
    "thermal_newton_min_damp": _field("1", "Minimum line-search damping factor.", value_type="number", default=1.0e-3, constraint="0 < value <= thermal_newton_damp"),
    "thermal_newton_line_search": _field("bool", "Enable residual-decreasing Newton line search.", value_type="boolean", default=False),
}

MODEL_PACKAGE_FIELDS: dict[str, ConfigField] = {
    "path": _field(
        "relative directory", "ALBNN package directory below the outer document.",
        value_type="string", required=True,
        constraint="nonempty, relative, no '..' segment",
    ),
    "use_augment": _field(
        "bool", "Optional inference augmentation override.",
        value_type="boolean or null", default=None,
    ),
}
SURROGATE_RUNTIME_FIELDS: dict[str, ConfigField] = {
    "parameters": _field(
        "mapping", "Attributes exposed on the inference runtime config.",
        value_type="object", default={},
    ),
    "spool_mode": _field(
        "name", "Use a fixed normalized spool or require external input.",
        value_type="string", default="fixed", choices=("fixed", "external"),
    ),
    "spool": _field(
        "normalized pair", "Fixed normalized spool command.",
        value_type="array[number, 2]", default=(0.0, 0.0),
        constraint="each value in [-1, 1]; forbidden when spool_mode='external'",
    ),
}

SIMULATION_DOCUMENT_FIELDS: dict[str, ConfigField] = {
    "schema_version": _field("version", "Exact document schema version.", value_type="string", default="0.4.0", choices=("0.4.0",)),
    "kind": _field("name", "Simulation document role.", value_type="string", required=True, choices=("simulation", "simulation_profile")),
    "includes": _field("path list", "Ordered relative simulation profiles.", value_type="array[string]", default=(), constraint="relative, unique, acyclic, and contained below document root"),
    "spec": _field("mapping", "Simulation specification overlaid after profiles.", value_type="object", required=True),
}
SIMULATION_SPEC_FIELDS: dict[str, ConfigField] = {
    "rotor": _field("mapping", "ROSS rotor resource and operating point.", value_type="object", required=True),
    "time_grid": _field("mapping", "Global fixed step and advance count.", value_type="object", required=True),
    "mounts": _field("list", "Bearing file paths mounted at unique rotor nodes.", value_type="array[object]", required=True, constraint="nonempty; nodes unique after construction"),
    "loads": _field("list", "Static, gravity, or unbalance rotor loads.", value_type="array[object]", default=()),
    "history": _field("mapping", "Committed-history retention policy.", value_type="object", default={}),
}
SIMULATION_ROTOR_FIELDS: dict[str, ConfigField] = {
    "model": _field("name", "Rotor resource loader.", value_type="string", required=True, choices=("ross_excel",)),
    "path": _field("relative file", "ROSS Excel rotor file below the outer document.", value_type="string", required=True, constraint="nonempty, relative, contained below document root"),
    "frequency_hz": _field("Hz", "Rotor rotation frequency passed to the ROSS adapter.", value_type="number", required=True, constraint="finite"),
    "alpha": _field("1", "ROSS proportional mass damping coefficient.", value_type="number", default=0.0, constraint="finite"),
    "beta": _field("1", "ROSS proportional stiffness damping coefficient.", value_type="number", default=0.0, constraint="finite"),
}
SIMULATION_TIME_GRID_FIELDS: dict[str, ConfigField] = {
    "time_step": _field("s", "Global dimensional integration time step.", value_type="number", required=True, constraint="finite and > 0"),
    "steps": _field("count", "Advances after the initial committed state.", value_type="integer", required=True, constraint=">= 0"),
}
SIMULATION_MOUNT_FIELDS: dict[str, ConfigField] = {
    "bearing": _field("relative file", "Bearing JSON5 document resolved from the simulation directory.", value_type="string", required=True, constraint="nonempty relative path"),
    "node": _field("index", "Rotor node receiving displacement and bearing force.", value_type="integer", required=True, constraint=">= 0"),
}
STATIC_LOAD_FIELDS: dict[str, ConfigField] = {
    "type": _field("name", "Static load discriminator.", value_type="string", default="static", choices=("static",)),
    "node": _field("index", "Rotor node receiving the force.", value_type="integer", required=True, constraint=">= 0"),
    "force": _field("N", "Fixed [Fx, Fy] vector.", value_type="array[number, 2]", required=True, constraint="finite"),
}
GRAVITY_LOAD_FIELDS: dict[str, ConfigField] = {
    "type": _field("name", "Gravity load discriminator.", value_type="string", default="gravity", choices=("gravity",)),
    "acceleration": _field("m/s^2", "Y-axis gravity acceleration; sign controls direction.", value_type="number", default=9.80665, constraint="finite"),
}
UNBALANCE_LOAD_FIELDS: dict[str, ConfigField] = {
    "type": _field("name", "Unbalance load discriminator.", value_type="string", default="unbalance", choices=("unbalance",)),
    "node": _field("index or list", "One rotor node or a nonempty sequence of nodes.", value_type="integer or array[integer]", required=True, constraint="all >= 0"),
    "phase": _field("rad", "Initial excitation phase.", value_type="number", default=0.0, constraint="finite"),
    "t_max": _field("s", "Positive ramp or gate time scale.", value_type="number", default=1.0, constraint="> 0"),
    "m": _field("kg", "Equivalent unbalance mass.", value_type="number", default=0.0, constraint="finite"),
    "freq": _field("Hz", "Unbalance excitation frequency.", value_type="number", default=0.0, constraint="finite"),
    "e": _field("m", "Unbalance mass eccentricity radius.", value_type="number", default=0.0, constraint="finite"),
    "no_step": _field("bool", "Use a linear [0, t_max] ramp instead of a step.", value_type="boolean", default=False),
}
SIMULATION_HISTORY_FIELDS: dict[str, ConfigField] = {
    "mode": _field("name", "History storage strategy.", value_type="string", default="memory", choices=("memory", "ring_buffer", "disk_stream")),
    "fields": _field("field list", "Committed arrays retained or streamed.", value_type="array[string]", default=("rotor_displacement", "rotor_velocity", "bearing_force"), choices=("rotor_displacement", "rotor_velocity", "bearing_force"), constraint="nonempty and unique membership not required"),
    "downsample": _field("count", "Retain committed indices divisible by this value plus the final state.", value_type="integer", default=1, constraint=">= 1"),
    "capacity": _field("count", "Ring-buffer sample capacity.", value_type="integer or null", default=None, constraint="required and >= 1 only for ring_buffer"),
    "directory": _field("relative directory", "Disk-stream output directory below the outer document.", value_type="string or null", default=None, constraint="required only for disk_stream; contained below document root"),
}


BEARING_FIELD_GROUPS: dict[str, Mapping[str, ConfigField]] = {
    "document": BEARING_DOCUMENT_FIELDS,
    "spec": BEARING_SPEC_FIELDS,
    "film_dimensional": DIMENSIONAL_FILM_FIELDS,
    "film_nondimensional": NONDIMENSIONAL_FILM_FIELDS,
    "film_gas_additions": GAS_FILM_OVERRIDE_FIELDS,
    "restrictors_liquid": LIQUID_RESTRICTOR_FIELDS,
    "restrictors_active": ACTIVE_RESTRICTOR_FIELDS,
    "tank": TANK_FIELDS,
    "valve_second_order": SECOND_ORDER_VALVE_FIELDS,
    "valve_static": STATIC_VALVE_FIELDS,
    "valve_transfer_function": TRANSFER_FUNCTION_VALVE_FIELDS,
    "control": CONTROL_FIELDS,
    "control_pid_gains": PID_GAIN_FIELDS,
    "transforms": TRANSFORM_FIELDS,
    "thermal": THERMAL_FIELDS,
    "model_package": MODEL_PACKAGE_FIELDS,
    "surrogate_runtime": SURROGATE_RUNTIME_FIELDS,
}

SIMULATION_FIELD_GROUPS: dict[str, Mapping[str, ConfigField]] = {
    "document": SIMULATION_DOCUMENT_FIELDS,
    "spec": SIMULATION_SPEC_FIELDS,
    "rotor": SIMULATION_ROTOR_FIELDS,
    "time_grid": SIMULATION_TIME_GRID_FIELDS,
    "mount": SIMULATION_MOUNT_FIELDS,
    "load_static": STATIC_LOAD_FIELDS,
    "load_gravity": GRAVITY_LOAD_FIELDS,
    "load_unbalance": UNBALANCE_LOAD_FIELDS,
    "history": SIMULATION_HISTORY_FIELDS,
}


def applicable_field_names(
    fields: Mapping[str, ConfigField],
    selector: str,
) -> set[str]:
    """Return public names whose applicability is empty or includes selector."""

    return {
        name
        for name, field in fields.items()
        if not field.applicability or selector in field.applicability
    }


def native_name_map(
    fields: dict[str, ConfigField],
) -> dict[str, str]:
    """Return the direct public-name to native-argument mapping."""

    return {name: field.native_name for name, field in fields.items()}


__all__ = [
    "ACTIVE_RESTRICTOR_FIELDS",
    "BEARING_DOCUMENT_FIELDS",
    "BEARING_FIELD_GROUPS",
    "BEARING_SPEC_FIELDS",
    "CONTROL_FIELDS",
    "ConfigField",
    "DIMENSIONAL_FILM_FIELDS",
    "GAS_FILM_FIELDS",
    "GAS_FILM_OVERRIDE_FIELDS",
    "GAS_ONLY_FILM_FIELDS",
    "GRAVITY_LOAD_FIELDS",
    "LIQUID_RESTRICTOR_FIELDS",
    "MODEL_PACKAGE_FIELDS",
    "NONDIMENSIONAL_FILM_FIELDS",
    "PID_GAIN_FIELDS",
    "SECOND_ORDER_VALVE_FIELDS",
    "SIMULATION_DOCUMENT_FIELDS",
    "SIMULATION_FIELD_GROUPS",
    "SIMULATION_HISTORY_FIELDS",
    "SIMULATION_MOUNT_FIELDS",
    "SIMULATION_ROTOR_FIELDS",
    "SIMULATION_SPEC_FIELDS",
    "SIMULATION_TIME_GRID_FIELDS",
    "STATIC_LOAD_FIELDS",
    "STATIC_VALVE_FIELDS",
    "SURROGATE_RUNTIME_FIELDS",
    "TANK_FIELDS",
    "THERMAL_FIELDS",
    "TRANSFER_FUNCTION_VALVE_FIELDS",
    "TRANSFORM_FIELDS",
    "UNBALANCE_LOAD_FIELDS",
    "VALVE_COMMON_FIELDS",
    "applicable_field_names",
    "native_name_map",
]
