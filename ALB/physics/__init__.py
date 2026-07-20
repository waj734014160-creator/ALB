"""Physics-facing namespace for film, bearing, orifice, gas, and thermal models."""

from importlib import import_module


_EXPORTS = {
    "FilmSystem": ("ALB.physics.film", "FilmSystem"),
    "NodimNewtonFilm": ("ALB.physics.film", "NodimNewtonFilm"),
    "HydrostaticBearing": ("ALB.physics.bearing", "HydrostaticBearing"),
    "NodimHydrostaticBearing": (
        "ALB.physics.bearing",
        "NodimHydrostaticBearing",
    ),
    "MultiPad": ("ALB.physics.bearing", "MultiPad"),
    "GasBearing": ("ALB.physics.gas", "GasBearing"),
    "CSOrifice": ("ALB.physics.hydraulics", "CSOrifice"),
    "NodimCSOrifice": ("ALB.physics.hydraulics", "NodimCSOrifice"),
    "ThermalHydroBearing": ("ALB.thermal", "ThermalHydroBearing"),
    "NodimThermalHydroBearing": ("ALB.thermal", "NodimThermalHydroBearing"),
}


def __getattr__(name):
    """Resolve physics implementations lazily from their compatibility modules."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.physics' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    return getattr(import_module(module_name), attribute_name)


__all__ = list(_EXPORTS)
