"""Deployed neural-surrogate namespace."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "create_model_package": ("ALB.surrogate.package", "create_model_package"),
    "load_albnn_package": ("ALB.surrogate.package", "load_albnn_package"),
    "open_model_package": ("ALB.surrogate.package", "open_model_package"),
}


def __getattr__(name):
    """Resolve packaged surrogate implementations lazily."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.surrogate' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.surrogate", module_name, "surrogate")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
