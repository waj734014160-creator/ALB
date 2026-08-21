"""Typed ROSS node layout, index validation, and force mapping."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt

from ALB.contracts.numeric import FloatArray, finite_real_array


class _ShaftElementProtocol(Protocol):
    def dof_mapping(self) -> Mapping[str, int]:
        """Return the ROSS local degree-of-freedom mapping."""


@dataclass(frozen=True, slots=True)
class RotorDofLayout:
    """Describe ROSS node-local DOFs and map them to global indices.

    Parameters
    ----------
    dof_per_node
        Number of degrees of freedom per ROSS node; at least four.
    x, y
        Local translational indices used for ALB displacement and force.
    alpha, beta
        Local rotational indices required to validate the ROSS layout.

    Raises
    ------
    ValueError
        If indices are repeated, negative, or outside the node layout.
    """

    dof_per_node: int
    x: int
    y: int
    alpha: int
    beta: int

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.alpha, self.beta)
        if self.dof_per_node < 4:
            raise ValueError("dof_per_node must be at least four")
        if len(set(values)) != len(values):
            raise ValueError("rotor local DOF indices must be unique")
        if any(value < 0 or value >= self.dof_per_node for value in values):
            raise ValueError("rotor local DOF index is outside the node layout")

    @classmethod
    def from_dof_per_node(cls, dof_per_node: int) -> "RotorDofLayout":
        """Return the standard ROSS four- or six-DOF node layout.

        Parameters
        ----------
        dof_per_node
            Supported ROSS node width, either four or six.

        Returns
        -------
        RotorDofLayout
            Canonical translational and rotational local indices.

        Raises
        ------
        ValueError
            If the node width is not four or six.
        """

        if dof_per_node == 4:
            return cls(4, x=0, y=1, alpha=2, beta=3)
        if dof_per_node == 6:
            return cls(6, x=0, y=1, alpha=3, beta=4)
        raise ValueError("only four- and six-DOF ROSS layouts are supported")

    @classmethod
    def from_ross(cls, rotor: object) -> "RotorDofLayout":
        """Build a layout from one ROSS rotor's shaft-element mapping.

        Parameters
        ----------
        rotor
            ROSS-compatible object exposing integer ``number_dof`` and optional
            ``shaft_elements`` with ``dof_mapping()``.

        Returns
        -------
        RotorDofLayout
            Validated node-local DOF layout.

        Raises
        ------
        TypeError
            If ``number_dof`` is not an integer.
        ValueError
            If a shaft mapping omits a required physical direction.
        """

        number_dof: object = getattr(rotor, "number_dof", None)
        if isinstance(number_dof, (bool, np.bool_)) or not isinstance(
            number_dof, (Integral, np.integer)
        ):
            raise TypeError("ROSS rotor number_dof must be an integer")
        dof_per_node = int(number_dof)
        shaft_elements: object = getattr(rotor, "shaft_elements", None)
        if not isinstance(shaft_elements, Sequence) or not shaft_elements:
            return cls.from_dof_per_node(dof_per_node)
        element = cast(_ShaftElementProtocol, shaft_elements[0])
        mapping = element.dof_mapping()
        required = {name: f"{name}_0" for name in ("x", "y", "alpha", "beta")}
        missing = [key for key in required.values() if key not in mapping]
        if missing:
            raise ValueError(f"ROSS shaft DOF mapping is missing {missing}")
        indices = {name: int(mapping[key]) for name, key in required.items()}
        return cls(dof_per_node, **indices)

    def local_index(self, direction: str) -> int:
        """Return the local index for one physical direction.

        Parameters
        ----------
        direction
            One of ``"x"``, ``"y"``, ``"alpha"``, or ``"beta"``.

        Returns
        -------
        int
            Zero-based index within a node.

        Raises
        ------
        ValueError
            If ``direction`` is unsupported.
        """

        if direction not in {"x", "y", "alpha", "beta"}:
            raise ValueError("direction must be one of: x, y, alpha, beta")
        return cast(int, getattr(self, direction))

    def global_index(self, node: int, direction: str, total_dof: int) -> int:
        """Map one node and direction to a validated global DOF index.

        Parameters
        ----------
        node
            Nonnegative rotor node index.
        direction
            Physical direction accepted by ``local_index``.
        total_dof
            Total global vector width used as the upper bound.

        Returns
        -------
        int
            Zero-based global DOF index.

        Raises
        ------
        TypeError
            If ``node`` is not an integer.
        ValueError
            If the node is negative, the direction is invalid, or the result is
            outside ``total_dof``.
        """

        if isinstance(node, (bool, np.bool_)) or not isinstance(
            node, (Integral, np.integer)
        ):
            raise TypeError("node index must be an integer")
        normalized_node = int(node)
        if normalized_node < 0:
            raise ValueError("node index must be nonnegative")
        index = self.dof_per_node * normalized_node + self.local_index(direction)
        if index >= total_dof:
            raise ValueError(
                f"node {normalized_node} direction {direction!r} "
                f"exceeds total_dof {total_dof}"
            )
        return index


def normalize_node_indices(node: object) -> npt.NDArray[np.int64]:
    """Return node indices after rejecting booleans and non-integral values."""

    raw_nodes = list(np.asarray(node, dtype=object).reshape(-1))
    if any(
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (Integral, np.integer))
        for value in raw_nodes
    ):
        raise TypeError("node indices must be integers")
    try:
        normalized = np.asarray([int(value) for value in raw_nodes], dtype=np.int64)
    except OverflowError as exc:
        raise ValueError("node indices exceed the supported integer range") from exc
    if np.any(normalized < 0):
        raise ValueError("node indices must be nonnegative")
    return normalized


def node_force_to_array(
    total_dof: int,
    layout: RotorDofLayout,
    force: npt.ArrayLike,
    node: object,
) -> FloatArray:
    """Map finite per-node XY forces through one explicit ROSS DOF layout."""

    if isinstance(total_dof, (bool, np.bool_)) or not isinstance(
        total_dof, (Integral, np.integer)
    ):
        raise TypeError("ndof must be an integer")
    normalized_dof = int(total_dof)
    if normalized_dof <= 0:
        raise ValueError("ndof must be positive")
    if not isinstance(layout, RotorDofLayout):
        raise TypeError("layout must be RotorDofLayout")

    force_array = finite_real_array(force, "force")
    if force_array.ndim == 1:
        if force_array.size != 2:
            raise ValueError("one node force must contain exactly two values")
        force_array = force_array.reshape(1, 2)
    if force_array.ndim != 2 or force_array.shape[1] != 2:
        raise ValueError("force must have shape (node_count, 2)")

    nodes = normalize_node_indices(node)
    if len(nodes) != force_array.shape[0]:
        raise ValueError("node count must match the number of force rows")
    mapped = np.zeros(normalized_dof, dtype=np.float64)
    for index, node_index in enumerate(nodes):
        x_index = layout.global_index(int(node_index), "x", normalized_dof)
        y_index = layout.global_index(int(node_index), "y", normalized_dof)
        mapped[x_index] += force_array[index, 0]
        mapped[y_index] += force_array[index, 1]
    return mapped


def location_mapping_matrix(
    total_dof: int,
    actuator_locations: Sequence[tuple[int, str]],
    layout: RotorDofLayout | None = None,
) -> FloatArray:
    """Map physical node directions to columns in a global DOF vector."""

    selected_layout = layout or RotorDofLayout.from_dof_per_node(4)
    mapping = np.zeros((total_dof, len(actuator_locations)), dtype=np.float64)
    for column, (node, direction) in enumerate(actuator_locations):
        row = selected_layout.global_index(node, direction, total_dof)
        mapping[row, column] = 1.0
    return mapping


_nodeforce2array = node_force_to_array


__all__ = [
    "RotorDofLayout",
    "location_mapping_matrix",
    "node_force_to_array",
    "normalize_node_indices",
]
