"""Rotor-dynamics and coupling namespace."""

from importlib import import_module


_EXPORTS = {
    "RossRotor": ("ALB.dynamics.rotor", "RossRotor"),
    "SingleRotor": ("ALB.dynamics.rotor", "SingleRotor"),
    "RsRotorBearingCouple": ("ALB.dynamics.coupling", "RsRotorBearingCouple"),
    "RotorBearingCouple": ("ALB.dynamics.coupling", "RotorBearingCouple"),
    "EllipseTrack": ("ALB.dynamics.orbit", "EllipseTrack"),
    "BearingForceTrack": ("ALB.dynamics.orbit", "BearingForceTrack"),
    "TimeIter": ("ALB.core.time", "TimeIter"),
    "TimeIterDt": ("ALB.core.time", "TimeIterDt"),
}


def __getattr__(name):
    """Resolve dynamics implementations lazily from compatibility modules."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.dynamics' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    return getattr(import_module(module_name), attribute_name)


__all__ = list(_EXPORTS)
