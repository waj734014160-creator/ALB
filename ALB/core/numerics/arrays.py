"""Small array composition helpers used by numerical workflows."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np


def horizontal_stack_nonempty(
    arrays: Iterable[np.ndarray],
    **kwargs: Any,
) -> np.ndarray | list[Any]:
    """Horizontally stack nonempty arrays and preserve an empty result."""

    values = [array for array in arrays if len(array) != 0]
    if not values:
        return []
    return np.hstack(values, **kwargs)


def vertical_stack_nonempty(
    arrays: Iterable[np.ndarray],
    **kwargs: Any,
) -> np.ndarray | list[Any]:
    """Vertically stack nonempty arrays and preserve an empty result."""

    values = [array for array in arrays if len(array) != 0]
    if not values:
        return []
    return np.vstack(values, **kwargs)


__all__ = ["horizontal_stack_nonempty", "vertical_stack_nonempty"]
