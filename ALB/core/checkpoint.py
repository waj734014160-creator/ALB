"""Checkpoint and restore helpers for stateful runtime components (ALB 0.4.7).

The predictor-corrector coupled integrator evaluates a stateful bearing
several times per step ("trials") from the same committed state and then
commits exactly once. Runtimes support this through ``checkpoint()`` and
``restore(token)`` (``ALB.contracts.CheckpointableRuntimeProtocol``). This
module provides the shared mechanics so each runtime only lists the objects
that hold its time-varying state ("components").

Capture rules
-------------
A component snapshot records the attribute dictionary (and ``__slots__``) of
one object. Values are stored as follows:

* ``dict``, ``list``, and ``set`` (including subclasses) keep the original
  container object plus a copy of its content. Restoring writes the content
  back *in place*, so containers shared by reference with other objects (for
  example a film model ``args`` dictionary shared with its elements) stay
  consistent. Dictionary values are captured recursively with these same
  rules, so a mapping of append-only channel histories (for example a
  controller ``_history`` dictionary of lists) or of arrays is restored in
  place as well; a dictionary that contains itself is kept by reference at
  the repeated level.
* ``numpy.ndarray`` keeps the original array plus a copy; writeable arrays are
  refilled in place on restore.
* ``pandas.DataFrame`` is copied; restore assigns a fresh copy (frames are
  append-only logs and are not shared between objects).
* Every other value (numbers, immutable DTOs and snapshots, references to
  meshes, assembled operators, solver objects, torch modules) is kept by
  reference and reassigned on restore. Such references are never copied,
  so checkpoints do not duplicate meshes or FEM assemblies.

Items inside captured lists and sets are kept by reference. This assumes
that runtime code appends or replaces list items instead of mutating them in
place, which holds for the histories and caches captured by ALB runtimes.

Attributes created after the checkpoint are removed on restore. A token can
be restored any number of times; each restore starts from the captured
content again.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd


_MISSING = object()


def _capture_value(
    value: Any,
    _active: frozenset[int] = frozenset(),
) -> tuple[str, Any, Any]:
    """Return ``(kind, original, saved)`` for one attribute value.

    ``_active`` holds the ids of the dictionaries being captured on the
    current recursion path; a dictionary met again inside itself is kept by
    reference so cyclic mappings terminate.
    """

    if isinstance(value, np.ndarray):
        return ("ndarray", value, value.copy())
    if isinstance(value, pd.DataFrame):
        return ("frame", None, value.copy())
    if isinstance(value, dict):
        if id(value) in _active:
            return ("ref", value, None)
        nested = _active | {id(value)}
        return (
            "dict",
            value,
            {key: _capture_value(item, nested) for key, item in value.items()},
        )
    if isinstance(value, list):
        return ("list", value, list(value))
    if isinstance(value, set):
        return ("set", value, set(value))
    return ("ref", value, None)


def _restored_value(kind: str, original: Any, saved: Any) -> Any:
    """Return the object to reassign after restoring captured content."""

    if kind == "ndarray":
        if (
            original.flags.writeable
            and original.shape == saved.shape
            and original.dtype == saved.dtype
        ):
            np.copyto(original, saved)
            return original
        return saved.copy()
    if kind == "frame":
        return saved.copy()
    if kind == "dict":
        # Restore nested containers in place first, then refill the mapping
        # with the captured keys and (restored) values.
        restored = {
            key: _restored_value(*captured) for key, captured in saved.items()
        }
        original.clear()
        original.update(restored)
        return original
    if kind == "list":
        original[:] = saved
        return original
    if kind == "set":
        original.clear()
        original.update(saved)
        return original
    return original


def _slot_names(target: Any) -> tuple[str, ...]:
    names: list[str] = []
    for cls in type(target).__mro__:
        slots = cls.__dict__.get("__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for name in slots:
            if name not in ("__dict__", "__weakref__") and name not in names:
                names.append(name)
    return tuple(names)


class ComponentSnapshot:
    """Captured attribute state of one runtime component object."""

    __slots__ = ("target", "attributes", "slots")

    def __init__(self, target: Any) -> None:
        self.target = target
        self.attributes: dict[str, tuple[str, Any, Any]] | None = (
            None
            if not hasattr(target, "__dict__")
            else {
                name: _capture_value(value)
                for name, value in vars(target).items()
            }
        )
        slots: dict[str, Any] = {}
        for name in _slot_names(target):
            value = getattr(target, name, _MISSING)
            slots[name] = (
                ("missing", None, None)
                if value is _MISSING
                else _capture_value(value)
            )
        self.slots = slots

    def restore(self) -> None:
        """Write the captured attribute state back into the component."""

        target = self.target
        if self.attributes is not None:
            current = vars(target)
            for name in [key for key in current if key not in self.attributes]:
                del current[name]
            for name, (kind, original, saved) in self.attributes.items():
                current[name] = _restored_value(kind, original, saved)
        for name, (kind, original, saved) in self.slots.items():
            if kind == "missing":
                if hasattr(target, name):
                    delattr(target, name)
                continue
            object.__setattr__(
                target,
                name,
                _restored_value(kind, original, saved),
            )


def capture_components(components: Iterable[Any]) -> tuple[ComponentSnapshot, ...]:
    """Capture every distinct component once, preserving the given order."""

    seen: set[int] = set()
    snapshots = []
    for component in components:
        if component is None or id(component) in seen:
            continue
        seen.add(id(component))
        snapshots.append(ComponentSnapshot(component))
    return tuple(snapshots)


class RuntimeCheckpoint:
    """Opaque token of one runtime's committed state.

    ``checkpoint()`` implementations create it from the runtime's own
    component snapshots and the tokens of child runtimes (pads of a
    multi-pad or an active bearing, the film inside a thermal wrapper).
    Only the runtime that created a token can restore it.
    """

    __slots__ = ("_owner", "_components", "_children")

    def __init__(
        self,
        owner: Any,
        components: Iterable[Any] = (),
        children: Iterable[tuple[Any, "RuntimeCheckpoint"]] = (),
    ) -> None:
        self._owner = owner
        self._children = tuple(children)
        self._components = capture_components(components)

    @property
    def owner(self) -> Any:
        """Return the runtime that created this token."""

        return self._owner

    def restore(self, owner: Any) -> None:
        """Restore ``owner`` and its children to the captured state.

        Raises
        ------
        ValueError
            If ``owner`` is not the runtime that created this token.
        """

        if owner is not self._owner:
            raise ValueError(
                "checkpoint token belongs to another runtime "
                f"({type(self._owner).__name__})"
            )
        for child, token in self._children:
            child.restore(token)
        for snapshot in self._components:
            snapshot.restore()


def require_checkpoint_token(token: object) -> RuntimeCheckpoint:
    """Return ``token`` as a checkpoint or raise ``TypeError``."""

    if not isinstance(token, RuntimeCheckpoint):
        raise TypeError("restore() requires a token returned by checkpoint()")
    return token


__all__ = [
    "ComponentSnapshot",
    "RuntimeCheckpoint",
    "capture_components",
    "require_checkpoint_token",
]
