"""System-assembly namespace for active lubricated bearings."""

from importlib import import_module


_EXPORTS = {
    "ALBHarmonicCoefficients": ("ALB.systems.alb", "ALBHarmonicCoefficients"),
}


def __getattr__(name):
    """Resolve advanced system data types lazily."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.systems' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    return getattr(import_module(module_name), attribute_name)


__all__ = list(_EXPORTS)
