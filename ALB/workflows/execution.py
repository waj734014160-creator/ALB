"""Task enumeration and local multiprocessing workflow helpers."""

from __future__ import annotations

import itertools
import multiprocessing as mp
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from ALB.infrastructure.config_io import read_json5


def iter_parameter_combinations(**kwargs: Any) -> Iterator[dict[str, Any]]:
    """Yield the Cartesian product of named scalar or sequence values."""

    keys = tuple(kwargs)
    values = []
    for value in kwargs.values():
        values.append(value if isinstance(value, (list, tuple)) else [value])
    for instance in itertools.product(*values):
        yield dict(zip(keys, instance))


class UnpackTask:
    """Adapt a keyword-argument task for multiprocessing map."""

    def __init__(self, task: Callable[..., Any]) -> None:
        self.task = task

    def __call__(self, kwargs: Mapping[str, Any]) -> Any:
        return self.task(**kwargs)


class MultiTask:
    """Execute a Cartesian task set in a local multiprocessing pool."""

    def __init__(
        self,
        task_func: Callable[..., Any],
        pool_size: int,
        task_args: dict[str, Any] | None = None,
        file_path: str | Path | None = None,
    ) -> None:
        self.task_func = UnpackTask(task_func)
        self.pool_size = pool_size
        if file_path is not None:
            self.task_args = read_json5(file_path)
        elif task_args is not None:
            self.task_args = task_args
        else:
            raise ValueError("task_args or file_path is required")

    def run(self) -> None:
        """Map all parameter combinations and close the worker pool."""

        with mp.Pool(processes=self.pool_size) as pool:
            pool.map(self.task_func, iter_parameter_combinations(**self.task_args))


__all__ = ["MultiTask", "UnpackTask", "iter_parameter_combinations"]
