"""Consistent error reporting for optional domain dependencies."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType


def missing_optional_dependency(
    namespace: str,
    extra: str,
    error: ModuleNotFoundError,
) -> ModuleNotFoundError:
    """Build a stable installation hint for a missing optional dependency."""

    missing = error.name or "unknown"
    return ModuleNotFoundError(
        f"{namespace} requires the optional '{extra}' extra; "
        f"install it with 'pip install re-alb[{extra}]' "
        f"(missing module: {missing})",
        name=missing,
    )


def import_optional_module(namespace: str, module: str, extra: str) -> ModuleType:
    """Import a domain module and translate missing dependencies into one error form."""

    try:
        return import_module(module)
    except ModuleNotFoundError as error:
        if error.name == module or (error.name or "").startswith("ALB."):
            raise
        raise missing_optional_dependency(namespace, extra, error) from error
