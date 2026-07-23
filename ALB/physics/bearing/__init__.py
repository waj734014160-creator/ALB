"""Hydrostatic and tilting-pad bearing assemblies."""

from ALB.contracts.optional import import_optional_module
from .units import AppliedTransform, BearingScaleSet, BearingUnitAdapter
from .decorators import LegacyBearingAdapter


_NAMES = (
    "BearingDynamicChar",
    "HydrostaticBearing",
    "MultiPad",
    "NodimHydrostaticBearing",
    "StaticPosition",
    "TiltingPadHydrodynamicPad",
    "four_pads_bearing",
    "four_pads_bearings",
    "get_pad_pressure_fields",
    "nodim_four_pads_bearing",
    "nodim_four_pads_bearings",
    "solve_tilting_pad_equilibrium",
    "tilting_pads_bearing",
    "tilting_pads_bearings",
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
    "LegacyBearingAdapter",
    *_NAMES,
]
