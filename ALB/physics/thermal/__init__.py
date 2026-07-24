"""Thermal-film coupling, transient thermal state, and nondimensional scales."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "FilmNondimScales": ("ALB.physics.thermal.scales", "FilmNondimScales"),
    "ThermalNondimScales": ("ALB.physics.thermal.scales", "ThermalNondimScales"),
}


def __getattr__(name: str):
    """Resolve thermal implementations with a stable film-extra error."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.physics.thermal' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.physics.thermal", module_name, "film")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
