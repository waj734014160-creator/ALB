"""Thermal-film coupling, transient thermal state, and nondimensional scales."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "FilmNondimScales": ("ALB.physics.thermal.scales", "FilmNondimScales"),
    "ThermalNondimScales": ("ALB.physics.thermal.scales", "ThermalNondimScales"),
    "NodimThermalHydroBearing": (
        "ALB.physics.thermal.solver",
        "NodimThermalHydroBearing",
    ),
    "NodimViscositySkfemNewtonFilm": (
        "ALB.physics.thermal.solver",
        "NodimViscositySkfemNewtonFilm",
    ),
    "SkfemThermalModel": ("ALB.physics.thermal.solver", "SkfemThermalModel"),
    "SkfemThermalModelNondim": (
        "ALB.physics.thermal.solver",
        "SkfemThermalModelNondim",
    ),
    "ThermalHydroBearing": ("ALB.physics.thermal.solver", "ThermalHydroBearing"),
    "ThermalPostProcess": ("ALB.physics.thermal.solver", "ThermalPostProcess"),
    "ViscosityFilmElem": ("ALB.physics.thermal.solver", "ViscosityFilmElem"),
    "ViscosityFilmNode": ("ALB.physics.thermal.solver", "ViscosityFilmNode"),
    "ViscositySkfemNewtonFilm": (
        "ALB.physics.thermal.solver",
        "ViscositySkfemNewtonFilm",
    ),
    "wrap_pad_collection_with_thermal": (
        "ALB.physics.thermal.solver",
        "wrap_pad_collection_with_thermal",
    ),
}


def __getattr__(name: str):
    """Resolve thermal implementations with a stable film-extra error."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.physics.thermal' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.physics.thermal", module_name, "film")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
