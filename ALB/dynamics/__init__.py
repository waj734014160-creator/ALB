"""Rotor-dynamics and coupling namespace."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "CouplingRuntimeDependencies": (
        "ALB.dynamics.bindings",
        "CouplingRuntimeDependencies",
    ),
    "RossRotor": ("ALB.dynamics.rotor", "RossRotor"),
    "RotorDofLayout": ("ALB.dynamics.rotor_layout", "RotorDofLayout"),
}


def __getattr__(name):
    """Resolve advanced rotor implementations lazily."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.dynamics' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.dynamics", module_name, "dynamics")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
