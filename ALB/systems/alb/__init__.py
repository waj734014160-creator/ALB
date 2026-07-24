"""Active lubricated bearing assembly and harmonic linear capabilities."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "ALBHarmonicCoefficients": (
        "ALB.systems.alb.harmonic_coefficients",
        "ALBHarmonicCoefficients",
    ),
    "load_builtin_alb_harmonic_coefficients": (
        "ALB.systems.alb.harmonic_coefficients",
        "load_builtin_alb_harmonic_coefficients",
    ),
    "bearing_scale_set_from_config": (
        "ALB.systems.alb.scales",
        "bearing_scale_set_from_config",
    ),
}


def __getattr__(name: str):
    """Resolve ALB system implementations with a stable extras error."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.systems.alb' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.systems.alb", module_name, "all")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
