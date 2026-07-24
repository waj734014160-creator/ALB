"""Mixed liquid-film and tilting-pad bearing assemblies."""

from ALB.contracts.optional import import_optional_module
from .units import AppliedTransform, BearingScaleSet, BearingUnitAdapter


_NAMES = (
    "MultiPad",
    "get_pad_pressure_fields",
    "solve_tilting_pad_equilibrium",
)


def __getattr__(name: str):
    """Resolve bearing solvers with a stable film-extra error."""

    if name not in _NAMES:
        raise AttributeError(f"module 'ALB.physics.bearing' has no attribute '{name}'")
    module = import_optional_module("ALB.physics.bearing", "ALB.physics.bearing.solver", "film")
    return getattr(module, name)


__all__ = [
    "AppliedTransform",
    "BearingScaleSet",
    "BearingUnitAdapter",
    *_NAMES,
]
