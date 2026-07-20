"""Stable task-name serialization helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_parameter_name(*args: Any, separator: str = "_") -> str:
    """Serialize mappings or parallel name/value sequences into one task name."""

    if not args:
        raise ValueError("at least one argument")
    if len(args) == 1:
        if not isinstance(args[0], dict):
            raise ValueError("the argument must be dict if only one argument")
        payload = dict(args[0])
    elif len(args) == 2 and all(isinstance(arg, (list, tuple)) for arg in args):
        if len(args[0]) != len(args[1]):
            raise ValueError("two arguments must have the same length")
        payload = dict(zip(args[0], args[1]))
    elif all(isinstance(arg, dict) for arg in args):
        payload = {}
        for mapping in args:
            payload.update(mapping)
    else:
        raise ValueError("arguments must be mappings or parallel sequences")
    return separator.join(
        f"{key}{separator}{value}" for key, value in payload.items()
    )


def parse_parameter_name(
    name: str,
    *,
    separator: str = "_",
    remove_extension: bool = True,
    ignore_prefix: int = 0,
) -> dict[str, str]:
    """Parse a name produced by :func:`build_parameter_name`."""

    value = name[ignore_prefix:]
    if remove_extension:
        value = Path(value).stem
    parts = value.split(separator)
    return dict(zip(parts[::2], parts[1::2]))


__all__ = ["build_parameter_name", "parse_parameter_name"]
