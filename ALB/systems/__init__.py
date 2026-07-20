"""System-assembly namespace for active lubricated bearings."""

from importlib import import_module


_EXPORTS = {
    "ALB": ("ALB.alb", "ALB"),
    "NodimALB": ("ALB.alb", "NodimALB"),
    "alb2": ("ALB.alb", "alb2"),
    "nodim_alb": ("ALB.alb", "nodim_alb"),
    "ALBHarmonicCoefficients": ("ALB.harmonic_linear", "ALBHarmonicCoefficients"),
    "ALBHarmonicLinear": ("ALB.harmonic_linear", "ALBHarmonicLinear"),
    "alb_harmonic_linear": ("ALB.harmonic_linear", "alb_harmonic_linear"),
}


def __getattr__(name):
    """Resolve system implementations lazily from compatibility modules."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.systems' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    return getattr(import_module(module_name), attribute_name)


__all__ = list(_EXPORTS)
