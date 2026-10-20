"""Constant-step time-grid implementations."""

from typing import Any, Iterator, TypeAlias, cast

import numpy as np
import numpy.typing as npt


FloatArray: TypeAlias = npt.NDArray[np.float64]


class TimeIter:
    """Inclusive constant-step grid defined by start, end, and interval count."""

    def __init__(self, start: float, end: float, num: int, **kwargs: Any) -> None:
        self.start = start
        self.end = end
        self.num = num
        dtype = kwargs.get("dtype", np.float64)
        self._ts = cast(FloatArray, np.linspace(start, end, num + 1, dtype=dtype))

    def __call__(self, *args: Any, **kwargs: Any) -> Iterator[float]:
        for t in self._ts:
            yield float(t)

    def __iter__(self) -> Iterator[float]:
        return self()

    @property
    def dt(self) -> float:
        """Return the constant time increment."""

        return (self.end - self.start) / self.num

    @property
    def t_list(self) -> FloatArray:
        """Return the inclusive sample array."""

        return self._ts

class TimeIterDt:
    """Inclusive constant-step grid defined by increment and interval count."""

    def __init__(self, dt: float, num: int, **kwargs: Any) -> None:
        self._dt = dt
        self.num = num
        dtype = kwargs.get("dtype", np.float64)
        self._ts = cast(FloatArray, np.linspace(0, dt * num, num + 1, dtype=dtype))

    def __call__(self, *args: Any, **kwargs: Any) -> Iterator[float]:
        for t in self._ts:
            yield float(t)

    def __iter__(self) -> Iterator[float]:
        return self()

    @property
    def dt(self) -> float:
        """Return the configured time increment."""

        return self._dt

    @property
    def t_list(self) -> FloatArray:
        """Return the inclusive sample array."""

        return self._ts


CONTROL_PERIOD_RELATIVE_TOLERANCE = 1.0e-9
"""Relative tolerance of the ``control_period = m * time_step`` test."""


def control_steps_per_period(control_period: float, time_step: float) -> int | None:
    """Return ``m`` when ``control_period / time_step`` is a positive integer.

    The ratio ``r = Ts / h`` is accepted when ``|r - round(r)| <= 1e-9 * r``
    and ``round(r) >= 1``. ``None`` means the period is not an integer
    multiple of the step.
    """

    period = float(control_period)
    step = float(time_step)
    if not (np.isfinite(period) and np.isfinite(step)) or period <= 0.0 or step <= 0.0:
        raise ValueError("control_period and time_step must be finite and > 0")
    ratio = period / step
    steps = int(round(ratio))
    if steps >= 1 and abs(ratio - steps) <= CONTROL_PERIOD_RELATIVE_TOLERANCE * ratio:
        return steps
    return None


def fit_time_step_to_control_period(
    control_period: float,
    time_step: float,
) -> tuple[float, int]:
    """Return the largest step ``h' <= h`` that divides ``Ts`` and its ratio.

    An exact integer multiple keeps ``h``. When ``h > Ts`` the step becomes
    ``Ts`` with ``m = 1``. Otherwise ``m = ceil(Ts / h)`` and
    ``h' = Ts / m``, so the controller period is preserved exactly.
    """

    steps = control_steps_per_period(control_period, time_step)
    if steps is not None:
        return float(time_step), steps
    period = float(control_period)
    if float(time_step) > period:
        return period, 1
    steps = int(np.ceil(period / float(time_step)))
    return period / steps, steps
