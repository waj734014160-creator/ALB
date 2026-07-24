"""Materialize strict 0.4 configurations into native bearing runtimes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from ALB.config.control_models import (
    FuzzyPIDConfig,
    Moog2ndServoConfig,
    PIDConfig,
    ServoConfig,
)
from ALB.config.film_models import FPBConfig, HydConfig, NodimPadConfig
from ALB.config.gas_models import GasConfig
from ALB.config.hydraulics_models import (
    HybridOrificeConfig,
    NodimOrificeConfig,
    OrificeConfig,
    TankConfig,
)
from ALB.config.system_models import ALBConfig, NodimALBConfig
from ALB.config.thermal_models import ThermalConfig
from ALB.physics.bearing.solver import MultiPad, _build_liquid_film_runtime
from ALB.physics.gas.runtime import GasFilmRuntime
from ALB.physics.thermal.solver import (
    NodimThermalHydroBearing,
    ThermalHydroBearing,
)
from ALB.systems.alb.assembly_runtime import assemble_active_runtime
from ALB.surrogate.package import load_albnn_package
from ALB.surrogate.runtime import SurrogateBearingRuntime

from .config import BearingConfig, load_bearing_config
from .errors import BuildError


_DIMENSIONAL_FILM_MAP = {
    "eccentricity": "e",
    "attitude_angle_deg": "angle",
    "rotation_frequency_hz": "freq",
    "start_angle_deg": "x0",
    "arc_angle_deg": "lx",
    "axial_length_ratio": "lz",
    "circumferential_elements": "nx",
    "axial_elements": "nz",
    "viscosity": "miu",
    "clearance": "c",
    "radius": "r",
    "length": "l",
    "supply_pressure": "ps",
    "density": "rho",
    "reynolds_boundary": "reynold",
    "continuous_boundary": "coe",
    "ambient_pressure": "p_set",
    "solver_tolerance": "error_set",
    "max_iterations": "max_iter",
    "relaxation": "damp",
    "vibration_enabled": "vib",
    "x_velocity": "dxt",
    "y_velocity": "dyt",
    "whirl_ratio": "vf",
    "solver": "iter_method",
    "save_pressure": "save_p",
    "save_thickness": "save_h",
    "gauss_points": "ngauss",
    "gauss_relaxation": "gdamp",
    "gauss_tolerance": "err",
    "pad_bias_deg": "bias",
    "adaptive_damping": "adaptive_damp",
}
_NONDIMENSIONAL_FILM_MAP = {
    "bearing_number": "lambda_value",
    "reference_bearing_number": "lambda0",
    "length_ratio": "lr",
    "arc_angle_deg": "lx",
    "axial_length_ratio": "lz",
    "circumferential_elements": "nx",
    "axial_elements": "nz",
    "pad_bias_deg": "bias",
    "eccentricity": "e",
    "attitude_angle_deg": "angle",
    "reynolds_boundary": "reynold",
    "continuous_boundary": "coe",
    "ambient_pressure": "p_set",
    "solver_tolerance": "error_set",
    "max_iterations": "max_iter",
    "relaxation": "damp",
    "x_velocity": "dxt",
    "y_velocity": "dyt",
    "whirl_ratio": "vf",
    "x_center_velocity": "xct",
    "y_center_velocity": "yct",
    "scale_viscosity": "scale_miu",
    "scale_clearance": "scale_c",
    "scale_radius": "scale_r",
    "scale_length": "scale_l",
    "scale_pressure": "scale_ps",
    "scale_density": "scale_rho",
    "scale_speed_rpm": "scale_w",
    "save_pressure": "save_p",
    "save_thickness": "save_h",
    "adaptive_damping": "adaptive_damp",
}
_GAS_FILM_MAP = {
    **_DIMENSIONAL_FILM_MAP,
    "ambient_pressure_pa": "pa",
    "gas_frequency_ratio": "gamma",
    "foil_enabled": "foil_enabled",
    "texture_enabled": "texture_enabled",
    "texture_type": "texture_type",
    "texture_depth": "texture_depth",
    "texture_depth_ratio": "texture_depth_ratio",
    "texture_circumferential_fraction": "texture_circ_fraction",
    "texture_axial_fraction": "texture_axial_fraction",
    "texture_start_theta_index": "texture_start_theta_index",
    "texture_start_axial_index": "texture_start_z_index",
    "foil_relaxation": "foil_relaxation",
    "foil_tolerance": "foil_tol",
    "foil_stiffness": "foil_stiffness",
    "foil_pitch": "foil_pitch",
    "foil_half_length": "foil_half_length",
    "foil_thickness": "foil_thickness",
    "foil_young_modulus": "foil_young",
    "foil_poisson_ratio": "foil_poisson",
}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.copy()
    return value


def _translate(
    source: Mapping[str, Any],
    names: Mapping[str, str],
) -> dict[str, Any]:
    return {
        names[key]: _plain(value)
        for key, value in source.items()
        if key in names
    }


def _thermal_config(
    config: BearingConfig,
) -> ThermalConfig | None:
    thermal = config.spec.get("thermal")
    if thermal is None:
        return None
    assert isinstance(thermal, Mapping)
    values = _plain(thermal)
    values["args_nodim"] = config.unit_system == "nondimensional"
    values["dt"] = float(config.spec["time_step"])
    return ThermalConfig(**values)


def _dimensional_pad(config: BearingConfig, *, active: bool) -> HydConfig:
    film = config.spec["film"]
    assert isinstance(film, Mapping)
    values = _translate(film, _DIMENSIONAL_FILM_MAP)
    values["node_link"] = config.spec.get("node")
    if active:
        values["thermal_config"] = _thermal_config(config)
        return FPBConfig(**values)
    return HydConfig(**values)


def _nondimensional_pad(config: BearingConfig) -> NodimPadConfig:
    film = config.spec["film"]
    assert isinstance(film, Mapping)
    values = _translate(film, _NONDIMENSIONAL_FILM_MAP)
    values["node_link"] = config.spec.get("node")
    values["thermal_config"] = _thermal_config(config)
    return NodimPadConfig(**values)


def _liquid_restrictors(
    config: BearingConfig,
) -> HybridOrificeConfig | None:
    source = config.spec.get("restrictors")
    if source is None:
        return None
    assert isinstance(source, Mapping)
    return HybridOrificeConfig(
        positions=_plain(source["positions"]),
        radius=source.get("radius"),
        cq=source.get("flow_coefficient"),
        pressure=source.get("pressure"),
        discharge_coefficient=float(
            source.get("discharge_coefficient", 0.6)
        ),
    )


def _active_config(config: BearingConfig) -> ALBConfig | NodimALBConfig:
    nodim = config.unit_system == "nondimensional"
    pad = (
        _nondimensional_pad(config)
        if nodim
        else _dimensional_pad(config, active=True)
    )
    restrictors = config.spec["restrictors"]
    assert isinstance(restrictors, Mapping)
    positions = _plain(restrictors.get("positions", []))
    orifice: NodimOrificeConfig | OrificeConfig
    if nodim:
        orifice = NodimOrificeConfig(
            position=np.asarray(positions, dtype=float),
            cq0=float(restrictors.get("base_flow_coefficient", 1.0)),
            cq1=float(
                restrictors.get(
                    "spool_flow_coefficient",
                    restrictors.get("flow_coefficient", 1.0),
                )
            ),
            cq2=float(
                restrictors.get("pressure_flow_coefficient", 0.0)
            ),
            ps=float(restrictors.get("supply_pressure", 1.0)),
            p0=float(restrictors.get("tank_pressure", 0.0)),
        )
    else:
        orifice = OrificeConfig(
            position=positions,
            ps=float(
                restrictors.get(
                    "supply_pressure",
                    getattr(pad, "ps", 7.0e6),
                )
            ),
            p0=float(restrictors.get("tank_pressure", 0.0)),
            cq1_nondim=restrictors.get("flow_coefficient"),
            diameter=float(restrictors.get("orifice_diameter", 0.002)),
            length=float(restrictors.get("orifice_length", 0.02)),
            valve_area=float(
                restrictors.get("valve_area", 1.83e-5 / 15)
            ),
            discharge_coefficient=float(
                restrictors.get("discharge_coefficient", 0.6)
            ),
        )

    tank_source = config.spec["tank"]
    assert isinstance(tank_source, Mapping)
    tank = TankConfig(
        xrange=_plain(tank_source.get("x_range", [0.49, 0.51])),
        zrange=_plain(tank_source.get("z_range", [0.2, 0.8])),
        h_tank=float(tank_source.get("depth_ratio", 2.0)),
    )
    valve_source = config.spec["valve"]
    assert isinstance(valve_source, Mapping)
    valve_model = str(valve_source["model"])
    valve_type = (
        Moog2ndServoConfig
        if valve_model == "second_order"
        else ServoConfig
    )
    valve = valve_type(
        dt=float(config.spec["time_step"]),
        tw=float(valve_source.get("response_time", valve_type().tw)),
        zeta=float(valve_source.get("damping_ratio", valve_type().zeta)),
        tp3=float(
            valve_source.get(
                "third_order_time_constant",
                valve_type().tp3,
            )
        ),
        delay=float(valve_source.get("delay", 0.0)),
    )
    control_source = config.spec["control"]
    assert isinstance(control_source, Mapping)
    mode = str(control_source["mode"])
    controller: PIDConfig | FuzzyPIDConfig | None
    if mode == "pid":
        gains = control_source["gains"]
        assert isinstance(gains, Mapping)
        controller = PIDConfig(
            dt=float(config.spec["time_step"]),
            kp=float(gains.get("kp", 0.0)),
            ki=float(gains.get("ki", 0.0)),
            kd=float(gains.get("kd", 0.0)),
            uf=float(gains.get("feedforward", 0.0)),
            freq=float(control_source.get("frequency_hz", 50.0)),
            sensor_angles=np.asarray(
                control_source.get("sensor_angles_deg", [45.0, 135.0]),
                dtype=float,
            ),
        )
    elif mode == "fuzzy_pid":
        rule_path = str(control_source.get("rule_path", "fuzzy_rules.csv"))
        if config.resource_root is not None:
            rule_path = str((config.resource_root / rule_path).resolve())
        controller = FuzzyPIDConfig(
            dt=float(config.spec["time_step"]),
            freq=float(control_source.get("frequency_hz", 5.0)),
            error_range=_plain(
                control_source.get("error_range", [-1.0, 1.0, 0.01])
            ),
            delta_error_range=_plain(
                control_source.get(
                    "delta_error_range",
                    [-1.0, 1.0, 0.01],
                )
            ),
            kp_range=_plain(
                control_source.get("kp_range", [0.0, 1.0, 0.01])
            ),
            ki_range=_plain(
                control_source.get("ki_range", [0.0, 0.0, 0.01])
            ),
            kd_range=_plain(
                control_source.get("kd_range", [0.0, 1.0, 0.01])
            ),
            rule_path=rule_path,
            sensor_angles=_plain(
                control_source.get("sensor_angles_deg", [45.0, 135.0])
            ),
        )
    else:
        controller = None

    transforms = config.spec.get("transforms", {})
    assert isinstance(transforms, Mapping)
    common: dict[str, Any] = {
        "pad_config": pad,
        "servo_config": valve,
        "orifice_config": orifice,
        "tank_config": tank,
        "controller_config": controller,
        "dt": float(config.spec["time_step"]),
        "node_link": config.spec.get("node"),
        "gxy": np.asarray(
            transforms.get("displacement_to_control", np.eye(2)),
            dtype=float,
        ),
        "gxyt": np.asarray(
            transforms.get("velocity_to_control", np.zeros((2, 2))),
            dtype=float,
        ),
        "control_mode": mode,
        "valve_model": valve_model,
    }
    return NodimALBConfig(**common) if nodim else ALBConfig(**common)


def build_runtime(config: BearingConfig) -> object:
    """Build one initialized native runtime from a validated config."""

    if not isinstance(config, BearingConfig):
        raise TypeError("config must be BearingConfig")
    try:
        if config.family == "active_lubricated":
            return assemble_active_runtime(_active_config(config))
        if config.family == "liquid_film":
            pad = (
                _nondimensional_pad(config)
                if config.unit_system == "nondimensional"
                else _dimensional_pad(config, active=False)
            )
            runtime = _build_liquid_film_runtime(
                pad,
                orifices=_liquid_restrictors(config),
            )
            thermal = _thermal_config(config)
            if thermal is None:
                return runtime
            if config.unit_system == "nondimensional":
                return NodimThermalHydroBearing(runtime, thermal)
            return ThermalHydroBearing(runtime, thermal)
        if config.family == "gas_film":
            film = config.spec["film"]
            assert isinstance(film, Mapping)
            values = _translate(film, _GAS_FILM_MAP)
            values["node_link"] = config.spec.get("node")
            return GasFilmRuntime(GasConfig(**values))
        if config.family == "multi_pad":
            pads = config.spec["pads"]
            assert isinstance(pads, tuple)
            children: list[object] = []
            for item in pads:
                if isinstance(item, str):
                    if config.resource_root is None:
                        raise BuildError(
                            "file-referenced pads require a source document"
                        )
                    child_config = load_bearing_config(
                        config.resource_root / item
                    )
                elif isinstance(item, Mapping):
                    child_spec = _plain(item)
                    child_spec.setdefault("time_step", config.spec["time_step"])
                    child_spec.setdefault("node", config.spec.get("node"))
                    child_spec.setdefault("unit_system", config.unit_system)
                    child_config = BearingConfig(
                        child_spec,
                        resource_root=config.resource_root,
                    )
                else:
                    raise BuildError("invalid multi-pad child")
                children.append(build_runtime(child_config))
            return MultiPad(*children)  # type: ignore[no-untyped-call]
        if config.family == "surrogate":
            package = config.spec["model_package"]
            runtime = config.spec.get("runtime", {})
            assert isinstance(package, Mapping)
            assert isinstance(runtime, Mapping)
            if config.resource_root is None:
                raise BuildError(
                    "surrogate config requires a document resource root"
                )
            package_path = (
                config.resource_root / str(package["path"])
            ).resolve()
            try:
                package_path.relative_to(config.resource_root)
            except ValueError as exc:
                raise BuildError(
                    "surrogate package path escapes the document directory"
                ) from exc
            model = load_albnn_package(
                package_path,
                use_augment=package.get("use_augment"),
                runtime_parameters=_plain(runtime.get("parameters", {})),
            )
            external = runtime.get("spool_mode", "fixed") == "external"
            return SurrogateBearingRuntime(
                model,
                unit_system=config.unit_system,
                node_link=config.spec.get("node"),
                external_spool=external,
                fixed_spool=runtime.get("spool", (0.0, 0.0)),
            )
        raise AssertionError(f"unhandled bearing family: {config.family}")
    except BuildError:
        raise
    except Exception as exc:
        raise BuildError(
            f"failed to build {config.family} bearing: {exc}"
        ) from exc


__all__ = ["build_runtime"]
