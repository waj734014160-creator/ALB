"""Finite-element nodes, elements, meshes, boundaries, and assembly helpers."""

from .base import (
    BaseBoundary,
    BaseElem,
    BaseMainModel,
    BaseMesh,
    BaseNode,
    ElemManager,
    MatrixProcess,
    NodeManager,
    _assemble_matrixs,
    _assemble_rights,
)
from .boundary import (
    check_boundary,
    couple_boundary_matrix,
    set_continuity_boundary,
    set_value_boundary,
)
from .mesh import Mesh, create_rect, create_rect_by_mesh, create_serend_2d, create_tri

__all__ = [
    "BaseBoundary",
    "BaseElem",
    "BaseMainModel",
    "BaseMesh",
    "BaseNode",
    "ElemManager",
    "MatrixProcess",
    "Mesh",
    "NodeManager",
    "_assemble_matrixs",
    "_assemble_rights",
    "check_boundary",
    "couple_boundary_matrix",
    "create_rect",
    "create_rect_by_mesh",
    "create_serend_2d",
    "create_tri",
    "set_continuity_boundary",
    "set_value_boundary",
]
