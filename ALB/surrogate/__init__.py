"""Deployed neural-surrogate namespace."""

from importlib import import_module


_EXPORTS = {
    "Net": ("ALB.nn", "Net"),
    "ALBNet": ("ALB.nn", "ALBNet"),
    "ALBNN": ("ALB.nn", "ALBNN"),
    "ALBNNC4Canonical": ("ALB.nn", "ALBNNC4Canonical"),
    "albnn": ("ALB.nn", "albnn"),
}


def __getattr__(name):
    """Resolve surrogate implementations lazily from ``ALB.nn``."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.surrogate' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    return getattr(import_module(module_name), attribute_name)


__all__ = list(_EXPORTS)
