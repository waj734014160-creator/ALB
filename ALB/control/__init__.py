"""Control-facing namespace for controllers, valves, and damping policies."""

from importlib import import_module


_EXPORTS = {
    "PID": ("ALB.controller", "PID"),
    "FuzzyPID": ("ALB.controller", "FuzzyPID"),
    "ALBLQGController": ("ALB.controller", "ALBLQGController"),
    "limit_signal": ("ALB.core.validation", "limit_signal"),
    "moog_servovalve": ("ALB.servovalve", "moog_servovalve"),
    "moog_2nd_servovalve": ("ALB.servovalve", "moog_2nd_servovalve"),
    "AdaptiveDampConfig": ("ALB.core.numerics.damping", "AdaptiveDampConfig"),
    "AdaptiveDampController": (
        "ALB.core.numerics.damping",
        "AdaptiveDampController",
    ),
}


def __getattr__(name):
    """Resolve control implementations lazily from compatibility modules."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.control' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    return getattr(import_module(module_name), attribute_name)


__all__ = list(_EXPORTS)
