"""Active lubricated bearing assembly and harmonic linear capabilities."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "ALB": ("ALB.systems.alb.assembly", "ALB"),
    "ALBBuilder": ("ALB.systems.alb.assembly", "ALBBuilder"),
    "ALBLinearAgent": ("ALB.systems.alb.assembly", "ALBLinearAgent"),
    "ALBNNAgent": ("ALB.systems.alb.assembly", "ALBNNAgent"),
    "NodimALB": ("ALB.systems.alb.assembly", "NodimALB"),
    "alb2": ("ALB.systems.alb.assembly", "alb2"),
    "alb2_fuzzy": ("ALB.systems.alb.assembly", "alb2_fuzzy"),
    "alb2_static": ("ALB.systems.alb.assembly", "alb2_static"),
    "nodim_alb": ("ALB.systems.alb.assembly", "nodim_alb"),
    "ALBHarmonicCoefficients": ("ALB.systems.alb.harmonic", "ALBHarmonicCoefficients"),
    "ALBHarmonicLinear": ("ALB.systems.alb.harmonic", "ALBHarmonicLinear"),
    "alb_harmonic_linear": ("ALB.systems.alb.harmonic", "alb_harmonic_linear"),
    "load_builtin_alb_harmonic_coefficients": (
        "ALB.systems.alb.harmonic",
        "load_builtin_alb_harmonic_coefficients",
    ),
    "BearingBlock": ("ALB.systems.alb.ports", "BearingBlock"),
    "DirectSpoolBearingBlock": (
        "ALB.systems.alb.ports",
        "DirectSpoolBearingBlock",
    ),
    "DirectSpoolBearingInput": (
        "ALB.systems.alb.ports",
        "DirectSpoolBearingInput",
    ),
    "HarmonicBearingBlock": ("ALB.systems.alb.ports", "HarmonicBearingBlock"),
}


def __getattr__(name: str):
    """Resolve ALB system implementations with a stable extras error."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.systems.alb' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.systems.alb", module_name, "all")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
