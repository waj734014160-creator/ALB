"""Control-facing namespace for controllers, valves, and damping policies."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "ControllerBlock": ("ALB.control.blocks", "ControllerBlock"),
    "ValveBlock": ("ALB.control.blocks", "ValveBlock"),
    "AdaptiveDampConfig": ("ALB.core.numerics.damping", "AdaptiveDampConfig"),
    "AdaptiveDampController": (
        "ALB.core.numerics.damping",
        "AdaptiveDampController",
    ),
}


def __getattr__(name):
    """Resolve strict control blocks and typed damping policies lazily."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.control' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.control", module_name, "control")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
