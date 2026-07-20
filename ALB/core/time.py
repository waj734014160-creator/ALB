"""Constant-step time-grid implementations."""

from typing import Any, Iterator

import numpy as np


class TimeIter:
    """Inclusive constant-step grid defined by start, end, and interval count."""

    def __init__(self, start: float, end: float, num: int, **kwargs: Any) -> None:
        self.start = start
        self.end = end
        self.num = num
        dtype = kwargs.get("dtype", np.float64)
        self._ts = np.linspace(start, end, num + 1, dtype=dtype)

    def __call__(self, *args: Any, **kwargs: Any) -> Iterator[float]:
        for t in self._ts:
            yield t

    def __iter__(self) -> Iterator[float]:
        return self()

    @property
    def dt(self) -> float:
        """Return the constant time increment."""

        return (self.end - self.start) / self.num

    @property
    def t_list(self) -> np.ndarray:
        """Return the inclusive sample array."""

        return self._ts

class TimeIterDt:
    """Inclusive constant-step grid defined by increment and interval count."""

    def __init__(self, dt: float, num: int, **kwargs: Any) -> None:
        self._dt = dt
        self.num = num
        dtype = kwargs.get("dtype", np.float64)
        self._ts = np.linspace(0, dt * num, num + 1, dtype=dtype)

    def __call__(self, *args: Any, **kwargs: Any) -> Iterator[float]:
        for t in self._ts:
            yield t

    def __iter__(self) -> Iterator[float]:
        return self()

    @property
    def dt(self) -> float:
        """Return the configured time increment."""

        return self._dt

    @property
    def t_list(self) -> np.ndarray:
        """Return the inclusive sample array."""

        return self._ts
