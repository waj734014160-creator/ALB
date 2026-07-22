"""Shared validation and saturation helpers."""

from typing import Any, Mapping, Optional, TypeAlias, cast

import numpy as np
import numpy.typing as npt

from ALB.contracts.types import UnitSystem


VALID_UNIT_SYSTEMS = frozenset(unit_system.value for unit_system in UnitSystem)
FloatArray: TypeAlias = npt.NDArray[np.float64]


def finite_real_array(
    value: Any,
    name: str,
    *,
    shape: tuple[int, ...] | None = None,
) -> FloatArray:
    """Return a copied finite real array without discarding imaginary parts."""

    raw = np.asarray(value)
    if np.iscomplexobj(raw):
        raise ValueError(f"{name} must be real; complex values are not supported")
    try:
        array = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain real numeric values") from exc
    if shape is not None and array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return cast(FloatArray, array.copy())


def finite_real_vector(value: Any, name: str, size: int) -> FloatArray:
    """Return a finite one-dimensional real vector with an exact size."""

    vector = finite_real_array(value, name).reshape(-1)
    if vector.shape != (size,):
        raise ValueError(f"{name} must contain exactly {size} values")
    return cast(FloatArray, vector)


def finite_real_scalar(value: Any, name: str) -> float:
    """Return one finite real scalar without implicit complex conversion."""

    flattened = finite_real_array(value, name).reshape(-1)
    if flattened.size != 1:
        raise ValueError(f"{name} must contain exactly one value")
    return float(flattened[0])


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
