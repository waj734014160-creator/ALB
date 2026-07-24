"""Strict immutable configuration documents for the ALB 0.4 facade."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np

from .errors import ConfigurationError


SCHEMA_VERSION = "0.4.0"
_BEARING_KINDS = {"bearing", "bearing_profile"}
_BEARING_FAMILIES = {
    "active_lubricated",
    "gas_film",
    "liquid_film",
    "multi_pad",
    "surrogate",
}
_UNIT_SYSTEMS = {"dimensional", "nondimensional"}
_CONTROL_MODES = {"pid", "fuzzy_pid", "uncontrolled", "external_spool"}
_VALVE_MODELS = {"second_order", "third_order", "static"}

_DIMENSIONAL_FILM_FIELDS = {
    "eccentricity",
    "attitude_angle_deg",
    "rotation_frequency_hz",
    "start_angle_deg",
    "arc_angle_deg",
    "axial_length_ratio",
    "circumferential_elements",
    "axial_elements",
    "viscosity",
    "clearance",
    "radius",
    "length",
    "supply_pressure",
    "density",
    "reynolds_boundary",
    "continuous_boundary",
    "ambient_pressure",
    "solver_tolerance",
    "max_iterations",
    "relaxation",
    "vibration_enabled",
    "x_velocity",
    "y_velocity",
    "whirl_ratio",
    "solver",
    "save_pressure",
    "save_thickness",
    "gauss_points",
    "gauss_relaxation",
    "gauss_tolerance",
    "pad_bias_deg",
    "adaptive_damping",
}
_NONDIMENSIONAL_FILM_FIELDS = {
    "bearing_number",
    "reference_bearing_number",
    "length_ratio",
    "arc_angle_deg",
    "axial_length_ratio",
    "circumferential_elements",
    "axial_elements",
    "pad_bias_deg",
    "eccentricity",
    "attitude_angle_deg",
    "reynolds_boundary",
    "continuous_boundary",
    "ambient_pressure",
    "solver_tolerance",
    "max_iterations",
    "relaxation",
    "x_velocity",
    "y_velocity",
    "whirl_ratio",
    "x_center_velocity",
    "y_center_velocity",
    "scale_viscosity",
    "scale_clearance",
    "scale_radius",
    "scale_length",
    "scale_pressure",
    "scale_density",
    "scale_speed_rpm",
    "save_pressure",
    "save_thickness",
    "adaptive_damping",
}
_GAS_FILM_FIELDS = (
    _DIMENSIONAL_FILM_FIELDS
    | {
        "ambient_pressure_pa",
        "gas_frequency_ratio",
        "foil_enabled",
        "texture_enabled",
        "texture_type",
        "texture_depth",
        "texture_depth_ratio",
        "texture_circumferential_fraction",
        "texture_axial_fraction",
        "texture_start_theta_index",
        "texture_start_axial_index",
        "foil_relaxation",
        "foil_tolerance",
        "foil_stiffness",
        "foil_pitch",
        "foil_half_length",
        "foil_thickness",
        "foil_young_modulus",
        "foil_poisson_ratio",
    }
)
_THERMAL_FIELDS = {
    "t_in",
    "t_ref",
    "miu0",
    "beta",
    "k_lub",
    "cp_lub",
    "max_delta_t",
    "heat_partition",
    "relax",
    "miu_update",
    "miu_update_max_ratio",
    "heat_partition_steps",
    "iter_method",
    "tol",
    "max_iter",
    "adaptive_damp",
    "miu_min",
    "miu_max",
    "coupling",
    "t_supply",
    "axial_side_bc",
    "axial_side_t",
    "supg",
    "delta_t_scale",
    "beta_nondim",
    "t_ref_nondim",
    "transient_enabled",
    "thermal_newton_max_iter",
    "thermal_newton_tol",
    "thermal_newton_damp",
    "thermal_newton_min_damp",
    "thermal_newton_line_search",
}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, np.ndarray):
        result = value.copy()
        result.setflags(write=False)
        return result
    return deepcopy(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    return deepcopy(value)


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{path} must be a mapping")
    return {str(key): _thaw(item) for key, item in value.items()}


def _reject_unknown(
    value: Mapping[str, Any],
    allowed: set[str],
    path: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigurationError(f"unknown {path} fields: {unknown}")


def _finite_float(value: Any, path: str) -> float:
    """Return a strict finite JSON-compatible real value."""

    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (int, float, np.integer, np.floating),
    ):
        raise ConfigurationError(f"{path} must be a real number")
    result = float(value)
    if not np.isfinite(result):
        raise ConfigurationError(f"{path} must be finite")
    return result


def _positive_float(value: Any, path: str) -> float:
    """Return a strict finite positive JSON-compatible real value."""

    result = _finite_float(value, path)
    if result <= 0.0:
        raise ConfigurationError(f"{path} must be finite and > 0")
    return result


def _require_integer(
    value: Any,
    path: str,
    *,
    minimum: int | None = None,
) -> int:
    """Return a strict integer without boolean or floating-point coercion."""

    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (int, np.integer),
    ):
        raise ConfigurationError(f"{path} must be an integer")
    result = int(value)
    if minimum is not None and result < minimum:
        raise ConfigurationError(f"{path} must be >= {minimum}")
    return result


def _ensure_finite(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _ensure_finite(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _ensure_finite(item, f"{path}[{index}]")
        return
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        raise ConfigurationError(f"{path} must be finite")


def _validate_film(
    film: Mapping[str, Any],
    *,
    family: str,
    unit_system: str,
) -> None:
    if family == "gas_film":
        allowed = _GAS_FILM_FIELDS
    elif unit_system == "dimensional":
        allowed = _DIMENSIONAL_FILM_FIELDS
    else:
        allowed = _NONDIMENSIONAL_FILM_FIELDS
    _reject_unknown(film, allowed, "spec.film")


def _validate_thermal(value: Any) -> None:
    if value is None:
        return
    thermal = _require_mapping(value, "spec.thermal")
    _reject_unknown(thermal, _THERMAL_FIELDS, "spec.thermal")
    transient = thermal.get("transient_enabled", False)
    if not isinstance(transient, (bool, np.bool_)):
        raise ConfigurationError(
            "spec.thermal.transient_enabled must be a bool"
        )


def _validate_active_sections(spec: Mapping[str, Any]) -> None:
    valve = _require_mapping(spec.get("valve"), "spec.valve")
    _reject_unknown(
        valve,
        {
            "model",
            "response_time",
            "damping_ratio",
            "third_order_time_constant",
            "delay",
        },
        "spec.valve",
    )
    if valve.get("model") not in _VALVE_MODELS:
        raise ConfigurationError(
            "spec.valve.model must be second_order, third_order, or static"
        )

    control = _require_mapping(spec.get("control"), "spec.control")
    _reject_unknown(
        control,
        {
            "mode",
            "gains",
            "frequency_hz",
            "sensor_angles_deg",
            "error_range",
            "delta_error_range",
            "kp_range",
            "ki_range",
            "kd_range",
            "rule_path",
        },
        "spec.control",
    )
    mode = control.get("mode")
    if mode not in _CONTROL_MODES:
        raise ConfigurationError(
            "spec.control.mode must be pid, fuzzy_pid, uncontrolled, or "
            "external_spool"
        )
    gains = control.get("gains")
    if mode == "pid":
        gains_mapping = _require_mapping(gains, "spec.control.gains")
        _reject_unknown(
            gains_mapping,
            {"kp", "ki", "kd", "feedforward"},
            "spec.control.gains",
        )
    elif gains is not None:
        raise ConfigurationError(
            "spec.control.gains is accepted only when mode is pid"
        )

    restrictors = _require_mapping(
        spec.get("restrictors"),
        "spec.restrictors",
    )
    positions = restrictors.get("positions")
    if (
        not isinstance(positions, Sequence)
        or isinstance(positions, (str, bytes))
        or len(positions) == 0
    ):
        raise ConfigurationError(
            "spec.restrictors.positions must contain at least one position"
        )
    unit_system = str(spec["unit_system"])
    allowed = {
        "positions",
        "supply_pressure",
        "tank_pressure",
        "flow_coefficient",
        "orifice_diameter",
        "orifice_length",
        "valve_area",
        "discharge_coefficient",
    }
    if unit_system == "nondimensional":
        allowed |= {
            "base_flow_coefficient",
            "spool_flow_coefficient",
            "pressure_flow_coefficient",
        }
    _reject_unknown(restrictors, allowed, "spec.restrictors")
    for name in (
        "orifice_diameter",
        "orifice_length",
        "valve_area",
        "discharge_coefficient",
    ):
        if name in restrictors:
            _positive_float(restrictors[name], f"spec.restrictors.{name}")

    tank = _require_mapping(spec.get("tank"), "spec.tank")
    _reject_unknown(
        tank,
        {"x_range", "z_range", "depth_ratio"},
        "spec.tank",
    )

    transforms = _require_mapping(
        spec.get("transforms", {}),
        "spec.transforms",
    )
    _reject_unknown(
        transforms,
        {"displacement_to_control", "velocity_to_control"},
        "spec.transforms",
    )


def _validate_liquid_restrictors(value: Any) -> None:
    if value is None:
        return
    restrictors = _require_mapping(value, "spec.restrictors")
    _reject_unknown(
        restrictors,
        {
            "positions",
            "radius",
            "flow_coefficient",
            "pressure",
            "discharge_coefficient",
        },
        "spec.restrictors",
    )
    if ("radius" in restrictors) == ("flow_coefficient" in restrictors):
        raise ConfigurationError(
            "liquid-film restrictors require exactly one of radius or "
            "flow_coefficient"
        )
    positions = restrictors.get("positions")
    if (
        not isinstance(positions, Sequence)
        or isinstance(positions, (str, bytes))
        or len(positions) == 0
    ):
        raise ConfigurationError(
            "spec.restrictors.positions must contain at least one position"
        )


def _validate_spec(spec: Mapping[str, Any]) -> None:
    family = spec.get("family")
    if family not in _BEARING_FAMILIES:
        raise ConfigurationError(
            "spec.family must be active_lubricated, liquid_film, gas_film, "
            "multi_pad, or surrogate"
        )
    unit_system = spec.get("unit_system")
    if unit_system not in _UNIT_SYSTEMS:
        raise ConfigurationError(
            "spec.unit_system must be dimensional or nondimensional"
        )
    if family == "gas_film" and unit_system != "dimensional":
        raise ConfigurationError("gas_film currently requires dimensional units")
    _positive_float(spec.get("time_step"), "spec.time_step")
    node = spec.get("node")
    if node is not None:
        try:
            _require_integer(node, "spec.node", minimum=0)
        except ConfigurationError as exc:
            raise ConfigurationError(
                "spec.node must be a nonnegative integer or null"
            ) from exc

    common = {"family", "unit_system", "time_step", "node"}
    if family == "active_lubricated":
        allowed = common | {
            "film",
            "restrictors",
            "tank",
            "valve",
            "control",
            "thermal",
            "transforms",
        }
    elif family == "liquid_film":
        allowed = common | {"film", "restrictors", "thermal"}
    elif family == "gas_film":
        allowed = common | {"film"}
    elif family == "multi_pad":
        allowed = common | {"pads"}
    else:
        allowed = common | {"model_package", "runtime"}
    _reject_unknown(spec, allowed, "spec")

    if family in {"active_lubricated", "liquid_film", "gas_film"}:
        film = _require_mapping(spec.get("film"), "spec.film")
        _validate_film(film, family=str(family), unit_system=str(unit_system))
    if family == "active_lubricated":
        _validate_active_sections(spec)
        _validate_thermal(spec.get("thermal"))
    elif family == "liquid_film":
        _validate_liquid_restrictors(spec.get("restrictors"))
        _validate_thermal(spec.get("thermal"))
    elif family == "multi_pad":
        pads = spec.get("pads")
        if (
            not isinstance(pads, Sequence)
            or isinstance(pads, (str, bytes))
            or len(pads) == 0
        ):
            raise ConfigurationError("spec.pads must contain at least one pad")
        for index, pad in enumerate(pads):
            if not isinstance(pad, (str, Mapping)):
                raise ConfigurationError(
                    f"spec.pads[{index}] must be a file path or bearing spec"
                )
    elif family == "surrogate":
        package = _require_mapping(
            spec.get("model_package"),
            "spec.model_package",
        )
        _reject_unknown(
            package,
            {"path", "use_augment"},
            "spec.model_package",
        )
        if not isinstance(package.get("path"), str) or not package["path"]:
            raise ConfigurationError(
                "spec.model_package.path must be a nonempty relative path"
            )
        package_path = Path(package["path"])
        if package_path.is_absolute() or ".." in package_path.parts:
            raise ConfigurationError(
                "spec.model_package.path must stay below the document directory"
            )
        if "use_augment" in package and not isinstance(
            package["use_augment"],
            (bool, np.bool_),
        ):
            raise ConfigurationError(
                "spec.model_package.use_augment must be a bool"
            )
        runtime = _require_mapping(spec.get("runtime", {}), "spec.runtime")
        _reject_unknown(
            runtime,
            {"parameters", "spool_mode", "spool"},
            "spec.runtime",
        )
        _require_mapping(runtime.get("parameters", {}), "spec.runtime.parameters")
        spool_mode = runtime.get("spool_mode", "fixed")
        if spool_mode not in {"fixed", "external"}:
            raise ConfigurationError(
                "spec.runtime.spool_mode must be fixed or external"
            )
        spool = runtime.get("spool", [0.0, 0.0])
        if spool_mode == "external" and "spool" in runtime:
            raise ConfigurationError(
                "external surrogate spool mode cannot define a fixed spool"
            )
        if spool_mode == "fixed":
            try:
                spool_array = np.asarray(spool, dtype=float)
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(
                    "spec.runtime.spool must contain two real values"
                ) from exc
            if spool_array.shape != (2,) or not np.all(np.isfinite(spool_array)):
                raise ConfigurationError(
                    "spec.runtime.spool must contain two finite values"
                )
            if np.any(np.abs(spool_array) > 1.0):
                raise ConfigurationError(
                    "spec.runtime.spool values must be within [-1, 1]"
                )
    _ensure_finite(spec, "spec")


@dataclass(frozen=True, slots=True)
class BearingConfig:
    """Validated immutable bearing configuration."""

    spec: Mapping[str, Any]
    source_path: Path | None = None
    resource_root: Path | None = None

    def __post_init__(self) -> None:
        copied = _require_mapping(self.spec, "spec")
        _validate_spec(copied)
        source = (
            None
            if self.source_path is None
            else Path(self.source_path).resolve()
        )
        root = (
            source.parent
            if self.resource_root is None and source is not None
            else None
            if self.resource_root is None
            else Path(self.resource_root).resolve()
        )
        object.__setattr__(self, "spec", _freeze(copied))
        object.__setattr__(self, "source_path", source)
        object.__setattr__(self, "resource_root", root)

    @property
    def family(self) -> str:
        """Return the bearing family discriminator."""

        return str(self.spec["family"])

    @property
    def unit_system(self) -> str:
        """Return dimensional or nondimensional."""

        return str(self.spec["unit_system"])

    @property
    def control_mode(self) -> str | None:
        """Return the active-bearing control mode, if applicable."""

        if self.family == "surrogate":
            runtime = self.spec.get("runtime", {})
            assert isinstance(runtime, Mapping)
            if runtime.get("spool_mode", "fixed") == "external":
                return "external_spool"
            return None
        if self.family != "active_lubricated":
            return None
        control = self.spec["control"]
        assert isinstance(control, Mapping)
        return str(control["mode"])

    def to_dict(self) -> dict[str, Any]:
        """Return a caller-owned strict 0.4 document."""

        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "bearing",
            "spec": _thaw(self.spec),
        }

    def with_overrides(self, overrides: Mapping[str, Any]) -> "BearingConfig":
        """Return a revalidated copy with dotted-path values replaced."""

        if not isinstance(overrides, Mapping):
            raise TypeError("overrides must be a mapping")
        copied = _thaw(self.spec)
        assert isinstance(copied, dict)
        for raw_path, value in overrides.items():
            path = str(raw_path)
            parts = path.split(".")
            if not path or any(not part for part in parts):
                raise ConfigurationError(
                    f"override path is invalid: {path!r}"
                )
            target: dict[str, Any] = copied
            for part in parts[:-1]:
                child = target.get(part)
                if not isinstance(child, dict):
                    raise ConfigurationError(
                        f"override path does not name a mapping: {path!r}"
                    )
                target = child
            target[parts[-1]] = _thaw(value)
        return BearingConfig(
            copied,
            source_path=self.source_path,
            resource_root=self.resource_root,
        )

    def sweep(
        self,
        path: str,
        values: Iterable[Any],
    ) -> tuple["BearingConfig", ...]:
        """Return one validated immutable configuration per supplied value."""

        return tuple(self.with_overrides({path: value}) for value in values)


def _read_json5(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(
            f"configuration must be UTF-8: {path}"
        ) from exc
    try:
        import json5  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "JSON5 loading requires the 'io' extra: pip install re-alb[io]"
        ) from exc
    try:
        payload = json5.loads(text, allow_duplicate_keys=False)
    except Exception as exc:
        raise ConfigurationError(f"invalid JSON5 document: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ConfigurationError("configuration document root must be a mapping")
    return {str(key): _thaw(value) for key, value in payload.items()}


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(
                dict(result[key]),
                {str(child): _thaw(item) for child, item in value.items()},
            )
        else:
            result[key] = _thaw(value)
    return result


def _load_bearing_document(
    path: Path,
    *,
    root: Path,
    stack: tuple[Path, ...],
    included: set[Path],
    top_level: bool,
) -> tuple[str, dict[str, Any]]:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ConfigurationError(
            f"include escapes the configuration root: {path}"
        ) from exc
    if resolved in stack:
        chain = " -> ".join(str(item) for item in (*stack, resolved))
        raise ConfigurationError(f"configuration include cycle: {chain}")
    if not top_level and resolved in included:
        raise ConfigurationError(f"duplicate configuration include: {resolved}")
    if not resolved.is_file():
        raise ConfigurationError(f"configuration file does not exist: {resolved}")
    payload = _read_json5(resolved)
    _reject_unknown(
        payload,
        {"schema_version", "kind", "includes", "spec"},
        "document",
    )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ConfigurationError(
            f"schema_version must be {SCHEMA_VERSION!r}; runtime migration is "
            "not supported"
        )
    kind = payload.get("kind")
    if kind not in _BEARING_KINDS:
        raise ConfigurationError(
            "bearing configuration kind must be bearing or bearing_profile"
        )
    if top_level and kind != "bearing":
        raise ConfigurationError("top-level bearing document must use kind='bearing'")
    if not top_level:
        included.add(resolved)
        if kind != "bearing_profile":
            raise ConfigurationError("bearing documents may include only profiles")
    raw_includes = payload.get("includes", [])
    if not isinstance(raw_includes, Sequence) or isinstance(
        raw_includes,
        (str, bytes),
    ):
        raise ConfigurationError("document.includes must be a list of paths")
    merged: dict[str, Any] = {}
    for index, raw_include in enumerate(raw_includes):
        if not isinstance(raw_include, str) or not raw_include:
            raise ConfigurationError(
                f"document.includes[{index}] must be a nonempty path"
            )
        include_path = Path(raw_include)
        if include_path.is_absolute():
            raise ConfigurationError("configuration includes must be relative")
        _, child_spec = _load_bearing_document(
            resolved.parent / include_path,
            root=root,
            stack=(*stack, resolved),
            included=included,
            top_level=False,
        )
        merged = _deep_merge(merged, child_spec)
    local_spec = _require_mapping(payload.get("spec", {}), "document.spec")
    return str(kind), _deep_merge(merged, local_spec)


def load_bearing_config(path: str | Path) -> BearingConfig:
    """Load one strict UTF-8 0.4 bearing document with bounded includes."""

    source = Path(path).resolve()
    _, spec = _load_bearing_document(
        source,
        root=source.parent,
        stack=(),
        included=set(),
        top_level=True,
    )
    return BearingConfig(spec, source_path=source, resource_root=source.parent)


__all__ = ["BearingConfig", "SCHEMA_VERSION", "load_bearing_config"]
