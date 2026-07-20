"""Deployed neural-surrogate namespace."""

from importlib import import_module


_EXPORTS = {
    "Net": ("ALB.surrogate.networks", "Net"),
    "ALBNet": ("ALB.surrogate.inference", "ALBNet"),
    "ALBNN": ("ALB.surrogate.inference", "ALBNN"),
    "ALBNNC4Canonical": ("ALB.surrogate.inference", "ALBNNC4Canonical"),
    "ALBNNForceExpert": ("ALB.surrogate.inference", "ALBNNForceExpert"),
    "ALBNNResidualCorrector": (
        "ALB.surrogate.inference",
        "ALBNNResidualCorrector",
    ),
    "albnn": ("ALB.surrogate.inference", "albnn"),
    "load_albnn_package": ("ALB.surrogate.package", "load_albnn_package"),
    "open_model_package": ("ALB.surrogate.package", "open_model_package"),
}


def __getattr__(name):
    """Resolve surrogate implementations lazily from explicit 0.2 modules."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.surrogate' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    return getattr(import_module(module_name), attribute_name)


__all__ = list(_EXPORTS)
