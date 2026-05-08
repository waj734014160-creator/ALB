# coding: utf-8

from importlib import import_module

_EXPORTS = {
    "ALB": ("ALB.alb", "ALB"),
    "NodimALB": ("ALB.alb", "NodimALB"),
    "alb2": ("ALB.alb", "alb2"),
    "alb2_fuzzy": ("ALB.alb", "alb2_fuzzy"),
    "alb2_static": ("ALB.alb", "alb2_static"),
    "nodim_alb": ("ALB.alb", "nodim_alb"),
    "HydrostaticBearing": ("ALB.bearing", "HydrostaticBearing"),
    "NodimHydrostaticBearing": ("ALB.bearing", "NodimHydrostaticBearing"),
    "MultiPad": ("ALB.bearing", "MultiPad"),
    "StaticPosition": ("ALB.bearing", "StaticPosition"),
    "four_pads_bearing": ("ALB.bearing", "four_pads_bearing"),
    "four_pads_bearings": ("ALB.bearing", "four_pads_bearings"),
    "nodim_four_pads_bearing": ("ALB.bearing", "nodim_four_pads_bearing"),
    "nodim_four_pads_bearings": ("ALB.bearing", "nodim_four_pads_bearings"),
    "TiltingPadHydrodynamicPad": ("ALB.bearing", "TiltingPadHydrodynamicPad"),
    "tilting_pads_bearing": ("ALB.bearing", "tilting_pads_bearing"),
    "tilting_pads_bearings": ("ALB.bearing", "tilting_pads_bearings"),
    "solve_tilting_pad_equilibrium": (
        "ALB.bearing",
        "solve_tilting_pad_equilibrium",
    ),
    "get_pad_pressure_fields": ("ALB.bearing", "get_pad_pressure_fields"),
    "ALBConfig": ("ALB.config", "ALBConfig"),
    "NodimALBConfig": ("ALB.config", "NodimALBConfig"),
    "NodimPadConfig": ("ALB.config", "NodimPadConfig"),
    "NodimOrificeConfig": ("ALB.config", "NodimOrificeConfig"),
    "FPBConfig": ("ALB.config", "FPBConfig"),
    "FuzzyPIDConfig": ("ALB.config", "FuzzyPIDConfig"),
    "HydConfig": ("ALB.config", "HydConfig"),
    "GasConfig": ("ALB.config", "GasConfig"),
    "PIDConfig": ("ALB.config", "PIDConfig"),
    "GasBearing": ("ALB.gas", "GasBearing"),
    "FuzzyPID": ("ALB.controller", "FuzzyPID"),
    "PID": ("ALB.controller", "PID"),
    "ThermalConfig": ("ALB.thermal", "ThermalConfig"),
    "SkfemThermalModel": ("ALB.thermal", "SkfemThermalModel"),
    "SkfemThermalModelNondim": ("ALB.thermal", "SkfemThermalModelNondim"),
    "ThermalHydroBearing": ("ALB.thermal", "ThermalHydroBearing"),
    "NodimThermalHydroBearing": ("ALB.thermal", "NodimThermalHydroBearing"),
    "ThermalNondimScales": ("ALB.nondim", "ThermalNondimScales"),
    "FilmNondimScales": ("ALB.nondim", "FilmNondimScales"),
    "build_thermal_config": ("ALB.config", "build_thermal_config"),
    "NodimCSOrifice": ("ALB.orifice", "NodimCSOrifice"),
    "NodimNewtonFilm": ("ALB.film", "NodimNewtonFilm"),
    "ALBNN": ("ALB.nn", "ALBNN"),
    "albnn": ("ALB.nn", "albnn"),
}


def __getattr__(name):
    if name in _EXPORTS:
        module_name, attr_name = _EXPORTS[name]
        try:
            module = import_module(module_name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"Failed to import '{name}' from '{module_name}'. "
                f"Missing optional dependency: {exc.name}."
            ) from exc
        return getattr(module, attr_name)
    raise AttributeError(f"module 'ALB' has no attribute '{name}'")


__all__ = [
    "ALB",
    "NodimALB",
    "alb2",
    "alb2_fuzzy",
    "alb2_static",
    "nodim_alb",
    "HydrostaticBearing",
    "NodimHydrostaticBearing",
    "MultiPad",
    "StaticPosition",
    "four_pads_bearing",
    "four_pads_bearings",
    "nodim_four_pads_bearing",
    "nodim_four_pads_bearings",
    "TiltingPadHydrodynamicPad",
    "tilting_pads_bearing",
    "tilting_pads_bearings",
    "solve_tilting_pad_equilibrium",
    "get_pad_pressure_fields",
    "ALBConfig",
    "NodimALBConfig",
    "NodimPadConfig",
    "NodimOrificeConfig",
    "FPBConfig",
    "FuzzyPIDConfig",
    "HydConfig",
    "GasConfig",
    "PIDConfig",
    "GasBearing",
    "FuzzyPID",
    "PID",
    "ThermalConfig",
    "SkfemThermalModel",
    "SkfemThermalModelNondim",
    "ThermalHydroBearing",
    "NodimThermalHydroBearing",
    "ThermalNondimScales",
    "NodimCSOrifice",
    "NodimNewtonFilm",
    "ALBNN",
    "albnn",
]
