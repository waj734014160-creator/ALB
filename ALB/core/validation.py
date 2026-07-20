"""Shared validation and saturation helpers."""

from typing import Any, Mapping, Optional

import numpy as np

from ALB.contracts.types import UnitSystem


VALID_UNIT_SYSTEMS = frozenset(unit_system.value for unit_system in UnitSystem)


def finite_vector(value: Any, name: str, size: int = 2) -> np.ndarray:
    """Return a finite one-dimensional vector with an exact size."""

    vector = np.asarray(value, dtype=float).reshape(-1)
    if vector.shape != (size,):
        raise ValueError(f"{name} must contain exactly {size} values")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must contain only finite values")
    return vector


def validate_bearing_output(output: Mapping[str, Any]) -> np.ndarray:
    """Validate and return the standard two-axis bearing force."""

    if not isinstance(output, Mapping):
        raise TypeError("bearing output must be a mapping")
    if "force" not in output:
        raise KeyError("bearing output must contain 'force'")
    return finite_vector(output["force"], "bearing force", size=2)


def get_unit_system(component: Any) -> str:
    """Return and validate a component unit-system declaration."""

    if not hasattr(component, "unit_system"):
        raise TypeError(f"{type(component).__name__} must declare unit_system")
    value = getattr(component, "unit_system")
    if isinstance(value, UnitSystem):
        return value.value
    return UnitSystem.coerce(value).value


def require_unit_system(
    component: Any,
    expected: str,
    *,
    component_name: Optional[str] = None,
) -> str:
    """Reject unit-incompatible components at an integration boundary."""

    if expected not in VALID_UNIT_SYSTEMS:
        raise ValueError("expected unit system must be dimensional or nondimensional")
    actual = get_unit_system(component)
    if actual != expected:
        label = component_name or type(component).__name__
        raise TypeError(f"{label} must declare unit_system='{expected}', got '{actual}'")
    return actual


def limit_signal(value: Any, up: Any = 1, down: Any = -1) -> np.ndarray:
    """Clip a scalar or array-like signal with broadcast-compatible limits."""

    limited = np.array(value)
    upper = np.ones_like(limited) * up
    lower = np.ones_like(limited) * down
    limited = np.where(limited > upper, upper, limited)
    limited = np.where(limited < lower, lower, limited)
    return limited
