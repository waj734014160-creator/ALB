"""Compressible gas-film bearing models."""

from ALB.contracts.optional import import_optional_module


_NAMES = (
    "GasFilmRuntime",
    "GasFoilTextureCoupling",
    "GasSkfemNewtonFilm",
    "gas_reynolds_jacobian",
    "gas_reynolds_residual",
)


def __getattr__(name: str):
    """Resolve gas solvers with a stable film-extra error."""

    if name not in _NAMES:
        raise AttributeError(f"module 'ALB.physics.gas' has no attribute '{name}'")
    module_name = (
        "ALB.physics.gas.runtime"
        if name == "GasFilmRuntime"
        else "ALB.physics.gas.solver"
    )
    module = import_optional_module("ALB.physics.gas", module_name, "film")
    return getattr(module, name)


__all__ = list(_NAMES)
