"""Thermal-film coupling, transient thermal state, and nondimensional scales."""

from .scales import FilmNondimScales, ThermalNondimScales
from .solver import (
    NodimThermalHydroBearing,
    NodimViscositySkfemNewtonFilm,
    SkfemThermalModel,
    SkfemThermalModelNondim,
    ThermalHydroBearing,
    ThermalPostProcess,
    ViscosityFilmElem,
    ViscosityFilmNode,
    ViscositySkfemNewtonFilm,
    wrap_pad_collection_with_thermal,
)

__all__ = [
    "FilmNondimScales",
    "NodimThermalHydroBearing",
    "NodimViscositySkfemNewtonFilm",
    "SkfemThermalModel",
    "SkfemThermalModelNondim",
    "ThermalHydroBearing",
    "ThermalNondimScales",
    "ThermalPostProcess",
    "ViscosityFilmElem",
    "ViscosityFilmNode",
    "ViscositySkfemNewtonFilm",
    "wrap_pad_collection_with_thermal",
]
