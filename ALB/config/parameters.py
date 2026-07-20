"""Validated configuration parameter injection helpers."""

from __future__ import annotations

import inspect
import warnings
from collections.abc import Callable, Iterable
from operator import itemgetter
from typing import Any

from .common import ConfigData


class ParameterHub:
    """Expose one configuration object through explicit parameter requests."""

    def __init__(self, data: ConfigData) -> None:
        self.data = data
        self._params = data.to_dict()

    def request(self, function: Callable[..., Any]) -> Any:
        """Call ``function`` with every matching parameter from the configuration."""

        signature = inspect.signature(function)
        required = {
            key: self._params[key]
            for key in signature.parameters
            if key in self._params
        }
        if not required:
            raise ValueError("The required parameters are not enough")
        return function(**required)

    def direct(self, keys: Iterable[str]) -> dict[str, Any]:
        """Return all requested parameters or fail atomically."""

        requested = tuple(keys)
        try:
            if len(requested) == 1:
                values = (self._params[requested[0]],)
            else:
                values = itemgetter(*requested)(self._params)
        except KeyError as exc:
            raise KeyError("The required parameters are not enough") from exc
        return dict(zip(requested, values))

    def soft_direct(
        self,
        keys: Iterable[str],
        warning: bool = True,
    ) -> dict[str, Any]:
        """Return available parameters and optionally warn about omissions."""

        requested = tuple(keys)
        required = {key: self._params[key] for key in requested if key in self._params}
        if len(required) != len(requested) and warning:
            warnings.warn("The required parameters are not enough", stacklevel=2)
        return required

    def soft_request(
        self,
        function: Callable[..., Any],
        warning: bool = True,
    ) -> dict[str, Any]:
        """Return matching function parameters without invoking the function."""

        signature = inspect.signature(function)
        required = {
            key: self._params[key]
            for key in signature.parameters
            if key in self._params
        }
        if len(required) != len(signature.parameters) and warning:
            warnings.warn("The required parameters are not enough", stacklevel=2)
        return required

    def __getitem__(self, item: str) -> Any:
        return self._params[item]

    def __setitem__(self, key: str, value: Any) -> None:
        self._params[key] = value

    def update(self, **kwargs: Any) -> None:
        """Update the hub-local parameter snapshot."""

        self._params.update(kwargs)


__all__ = ["ParameterHub"]
