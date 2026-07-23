"""Rotor-dynamics and coupling namespace."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "RossRotor": ("ALB.dynamics.rotor", "RossRotor"),
    "RotorDofLayout": ("ALB.dynamics.rotor_layout", "RotorDofLayout"),
    "SingleRotor": ("ALB.dynamics.rotor", "SingleRotor"),
    "RsRotorBearingCouple": ("ALB.dynamics.coupling", "RsRotorBearingCouple"),
    "RotorBearingCouple": ("ALB.dynamics.coupling", "RotorBearingCouple"),
    "EllipseTrack": ("ALB.dynamics.orbit", "EllipseTrack"),
    "BearingForceTrack": ("ALB.dynamics.orbit", "BearingForceTrack"),
    "TimeIter": ("ALB.core.time", "TimeIter"),
    "TimeIterDt": ("ALB.core.time", "TimeIterDt"),
    "CoupledBearingBinding": (
        "ALB.dynamics.bindings",
        "CoupledBearingBinding",
    ),
    "CouplingRuntimeDependencies": (
        "ALB.dynamics.bindings",
        "CouplingRuntimeDependencies",
    ),
}


def __getattr__(name):
    """Resolve dynamics implementations lazily from compatibility modules."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.dynamics' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.dynamics", module_name, "dynamics")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
