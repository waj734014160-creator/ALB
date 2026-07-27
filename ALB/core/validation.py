"""Shared validation and saturation helpers."""

from typing import Any, Mapping, Optional, cast

import numpy as np
import numpy.typing as npt

from ALB.contracts.numeric import (
    FloatArray,
    finite_real_array as finite_real_array,
    finite_real_scalar as finite_real_scalar,
    finite_real_time as finite_real_time,
    finite_real_vector as finite_real_vector,
)
from ALB.contracts.types import UnitSystem


VALID_UNIT_SYSTEMS = frozenset(unit_system.value for unit_system in UnitSystem)


def require_protocol(
    value: object,
    protocol: object,
    name: str,
) -> None:
    """Require a value to satisfy one runtime-checkable protocol."""

    protocol_type = cast(type[Any], protocol)
    if not isinstance(value, protocol_type):
        raise TypeError(f"{name} must satisfy {protocol_type.__name__}")


def strict_nonnegative_integer(value: object, name: str) -> int:
    """Return one nonnegative built-in integer while rejecting booleans."""

    if isinstance(value, (bool, np.bool_)) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def finite_vector(value: Any, name: str, size: int = 2) -> FloatArray:
    """Return a finite one-dimensional vector with an exact size."""

    return finite_real_vector(value, name, size)


def validate_bearing_output(output: Mapping[str, Any]) -> FloatArray:
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


def limit_signal(value: Any, up: Any = 1, down: Any = -1) -> npt.NDArray[np.generic]:
    """Clip a scalar or array-like signal with broadcast-compatible limits."""

    limited = np.array(value)
    upper = np.ones_like(limited) * up
    lower = np.ones_like(limited) * down
    limited = np.where(limited > upper, upper, limited)
    limited = np.where(limited < lower, lower, limited)
    return cast(npt.NDArray[np.generic], limited)
