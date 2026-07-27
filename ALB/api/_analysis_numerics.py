"""Internal numerical analysis algorithms preserved across facade revisions."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
from scipy import sparse as sp  # type: ignore[import-untyped]
from scipy.sparse import linalg as sl  # type: ignore[import-untyped]


FloatArray = npt.NDArray[np.float64]


def linearize_film_runtime(runtime: Any) -> tuple[FloatArray, FloatArray]:
    """Return the established pressure-equation derivative K and C matrices."""

    from ALB.physics.bearing.solver import _FilmDynamicAnalyzer

    analyzer = _FilmDynamicAnalyzer(runtime)
    stiffness = np.asarray(
        analyzer.calc_k(nodim=False),  # type: ignore[no-untyped-call]
        dtype=np.float64,
    )
    damping = np.asarray(
        analyzer.calc_c(nodim=False),  # type: ignore[no-untyped-call]
        dtype=np.float64,
    )
    return stiffness, damping


def linearize_pad_spool_force(pad: Any) -> FloatArray:
    """Return the original coupled restrictor spool-to-force derivative."""

    from ALB.physics.hydraulics.orifice import CSOrifice

    if len(pad.simple_models) != 1:
        raise TypeError(
            "active linearization requires exactly one CSOrifice per pad"
        )
    orifice = pad.simple_models[0]
    nodes = orifice.node if isinstance(orifice, CSOrifice) else None
    if not isinstance(orifice, CSOrifice) or nodes is None or len(nodes) != 3:
        raise TypeError(
            "active linearization supports the established three-node "
            "CSOrifice topology only"
        )
    matrix = pad.main_model.matrixs["ke"]
    freedoms = pad.main_model.node_manager.freedoms
    film_matrix = matrix[0:freedoms, 0:freedoms]
    source_flow = float(orifice.q)
    node_flow = np.abs(np.asarray(orifice.qn, dtype=float))
    cq0 = float(orifice.cq0)
    cq1 = np.asarray(orifice.cq1_h2, dtype=float)
    cq2 = float(orifice.cq2)
    spool = float(orifice.xv)
    if spool == 0.0:
        raise TypeError(
            "active linearization requires a nonzero base spool position"
        )
    flow_sign = 1.0 if source_flow >= 0.0 else -1.0
    source_slope = (
        2.0 * flow_sign * source_flow / cq0**2 / spool**2
    )
    branch_slope = 2.0 * cq1 * node_flow + cq2
    branch_matrix = (
        source_slope * np.ones((len(nodes), len(nodes)))
        + np.diag(branch_slope)
    )
    branch_inverse = np.linalg.inv(branch_matrix)
    source_rhs = (
        2.0
        * flow_sign
        * source_flow**2
        / cq0**2
        / spool**3
        * np.ones(len(nodes))
    )
    pressure_rhs = branch_inverse.dot(source_rhs)
    pressure_coupling = branch_inverse
    node_numbers = np.asarray(
        [node.number for node in nodes],
        dtype=np.int64,
    )
    columns = np.repeat(
        node_numbers.reshape((1, -1)),
        3,
        axis=0,
    )
    rows = columns.T
    coupling_matrix = sp.coo_matrix(
        (
            pressure_coupling.reshape(-1),
            (rows.reshape(-1), columns.reshape(-1)),
        ),
        shape=(freedoms, freedoms),
    )
    coupled_matrix = film_matrix + coupling_matrix
    right = np.zeros(freedoms)
    right[node_numbers] = pressure_rhs
    pressure = np.asarray(
        pad.main_model.latest_result[:freedoms],
        dtype=float,
    )
    constraints = []
    for index in range(freedoms):
        if abs(pressure[index]) < 1.0e-10:
            row = np.zeros(freedoms)
            row[index] = 1.0
            constraints.append(row)
    constraint = np.asarray(constraints, dtype=float)
    constraint_transpose = sp.coo_matrix(constraint.T)
    zero = np.zeros((constraint.shape[0], constraint.shape[0]))
    augmented = sp.hstack([coupled_matrix, constraint_transpose])
    augmented_constraint = sp.coo_matrix(
        np.hstack([constraint, zero])
    )
    augmented = sp.vstack([augmented, augmented_constraint]).tocsr()
    right = np.hstack([right, np.zeros(constraint.shape[0])])
    solution = sl.spsolve(augmented, right)

    previous = pad.main_model.latest_result.copy()
    try:
        pad.main_model._results[-1] = solution
        pad.main_model.update_to_nodes()
        derivative = pad.postprocess.calc_capacity(nodim=False)
    finally:
        pad.main_model._results[-1] = previous
        pad.main_model.update_to_nodes()
    return np.asarray(derivative, dtype=float)


def aggregate_active_linearization(
    pads: tuple[Any, ...],
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray, FloatArray]:
    """Apply the original four-pad K/C and spool-Jacobian aggregation."""

    if len(pads) != 4:
        raise ValueError("active linearization requires the established four-pad topology")
    pad_spool = []
    pad_stiffness = []
    pad_damping = []
    for pad in pads:
        pad_spool.append(linearize_pad_spool_force(pad))
        stiffness, damping = linearize_film_runtime(pad)
        pad_stiffness.append(stiffness)
        pad_damping.append(damping)
    spool_rows = np.asarray(pad_spool, dtype=float)
    spool_jacobian = np.zeros((2, 2), dtype=float)
    spool_jacobian[1] += spool_rows[0]
    spool_jacobian[1] += spool_rows[1]
    spool_jacobian[0] += spool_rows[2]
    spool_jacobian[0] += spool_rows[3]
    return (
        np.sum(np.asarray(pad_stiffness), axis=0),
        np.sum(np.asarray(pad_damping), axis=0),
        spool_jacobian.T,
        np.asarray(pad_stiffness),
        np.asarray(pad_damping),
    )


__all__ = [
    "aggregate_active_linearization",
    "linearize_film_runtime",
]
