"""Internal numerical analysis algorithms preserved across facade revisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, cast

import numpy as np
import numpy.typing as npt
from scipy import sparse as sp  # type: ignore[import-untyped]
from scipy.sparse import linalg as sl  # type: ignore[import-untyped]


FloatArray = npt.NDArray[np.float64]


def _stable_vector_norm(value: FloatArray) -> float:
    """Return a stable finite Euclidean norm while preserving normal results."""

    array = np.asarray(value, dtype=float).reshape(-1)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        ordinary = float(np.linalg.norm(array))
    if np.isfinite(ordinary) and ordinary > 0.0:
        return ordinary
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        stable = float(np.hypot.reduce(np.abs(array)))
    if not np.isfinite(stable):
        raise ValueError("vector magnitude must be finite")
    return stable


def _stable_load_norm(value: FloatArray) -> float:
    """Return a finite nonzero load magnitude for relative residuals."""

    magnitude = _stable_vector_norm(value)
    if magnitude <= 0.0:
        raise ValueError("load magnitude must be finite and nonzero")
    return magnitude


@dataclass(frozen=True, slots=True)
class EquilibriumEvaluation:
    """One force evaluation made by the established equilibrium iteration."""

    coordinate: FloatArray
    force: FloatArray
    residual: float
    inner_converged: bool


@dataclass(frozen=True, slots=True)
class EquilibriumOutcome:
    """Complete immutable state returned by the equilibrium iteration."""

    coordinate: FloatArray
    force: FloatArray
    residual: float
    converged: bool
    inner_converged: bool
    iterations: int
    stop_reason: str
    evaluations: tuple[EquilibriumEvaluation, ...]


class EquilibriumSolver:
    """Run the pre-0.4.1 damped Newton/fixed-stiffness algorithm unchanged."""

    def __init__(
        self,
        *,
        stiffness: FloatArray,
        max_iterations: int,
        tolerance: float,
        damping: float,
        jacobian_step: float,
        stall_patience: int,
        stall_relative_tolerance: float,
    ) -> None:
        self._stiffness = np.asarray(stiffness, dtype=float)
        self._max_iterations = int(max_iterations)
        self._tolerance = float(tolerance)
        self._damping = float(damping)
        self._jacobian_step = float(jacobian_step)
        self._stall_patience = int(stall_patience)
        self._stall_relative_tolerance = float(stall_relative_tolerance)

    @staticmethod
    def _limit_eccentricity_step(
        coordinate: FloatArray,
        step: FloatArray,
        *,
        limit: float = 1.0,
        margin: float = 1.0e-6,
        min_scale: float = 1.0e-6,
    ) -> FloatArray:
        """Keep the established Newton update inside the eccentricity disk."""

        current = np.asarray(coordinate, dtype=np.float64)
        delta = np.asarray(step, dtype=np.float64)
        safe_limit = float(limit) - float(margin)
        if not np.all(np.isfinite(delta)):
            return current.copy()
        candidate = current + delta
        if np.linalg.norm(candidate) < safe_limit:
            return cast(FloatArray, candidate)
        scale = 0.5
        while scale >= min_scale:
            candidate = current + scale * delta
            if np.linalg.norm(candidate) < safe_limit:
                return cast(FloatArray, candidate)
            scale *= 0.5
        current_norm = np.linalg.norm(current)
        if current_norm >= safe_limit and current_norm > 0.0:
            return cast(FloatArray, current / current_norm * safe_limit)
        return current.copy()

    def run(
        self,
        *,
        load: FloatArray,
        initial_coordinate: FloatArray,
        evaluate_force: Callable[[FloatArray], tuple[FloatArray, bool]],
        reset_iteration: Callable[[], None],
    ) -> EquilibriumOutcome:
        """Return the same update sequence as the retained static solver."""

        applied_load = np.asarray(load, dtype=float)
        coordinate = np.asarray(initial_coordinate, dtype=float).copy()
        evaluations: list[EquilibriumEvaluation] = []
        current: EquilibriumEvaluation | None = None
        state_matches_current = False
        last_jacobian: FloatArray | None = None
        best_error = np.inf
        stall_count = 0
        use_fixed_stiffness = False
        stop_reason = "max_iter"
        converged = False
        iteration = 0
        load_norm = _stable_load_norm(applied_load)

        def evaluate(candidate: FloatArray) -> EquilibriumEvaluation:
            force, inner_converged = evaluate_force(candidate.copy())
            force = np.asarray(force, dtype=float)
            residual = float(
                _stable_vector_norm(applied_load + force) / load_norm
            )
            result = EquilibriumEvaluation(
                coordinate=np.asarray(candidate, dtype=float).copy(),
                force=force.copy(),
                residual=residual,
                inner_converged=bool(inner_converged),
            )
            evaluations.append(result)
            return result

        for iteration in range(self._max_iterations):
            reset_iteration()
            current = evaluate(coordinate)
            state_matches_current = True
            if not current.inner_converged:
                stop_reason = "inner_not_converged"
                break
            if current.residual < self._tolerance:
                converged = True
                stop_reason = "converged"
                break

            if current.residual < best_error * (
                1.0 - self._stall_relative_tolerance
            ):
                best_error = current.residual
                stall_count = 0
            else:
                stall_count += 1
            if (
                not use_fixed_stiffness
                and self._stall_patience > 0
                and stall_count >= self._stall_patience
            ):
                use_fixed_stiffness = True

            residual_force = applied_load + current.force
            if use_fixed_stiffness:
                step = np.array(
                    [
                        residual_force[0]
                        / (self._stiffness[0] * (1.0 + abs(coordinate[0]))),
                        residual_force[1]
                        / (self._stiffness[1] * (1.0 + abs(coordinate[1]))),
                    ],
                    dtype=float,
                )
            else:
                probe_x = coordinate + np.array(
                    [self._jacobian_step, 0.0],
                    dtype=float,
                )
                evaluated_x = evaluate(probe_x)
                state_matches_current = False
                jacobian_built = evaluated_x.inner_converged
                evaluated_y: EquilibriumEvaluation | None = None
                if jacobian_built:
                    probe_y = coordinate + np.array(
                        [0.0, self._jacobian_step],
                        dtype=float,
                    )
                    evaluated_y = evaluate(probe_y)
                    jacobian_built = evaluated_y.inner_converged
                if jacobian_built:
                    assert evaluated_y is not None
                    jacobian = np.array(
                        [
                            [
                                (
                                    evaluated_x.force[0] - current.force[0]
                                )
                                / self._jacobian_step,
                                (
                                    evaluated_y.force[0] - current.force[0]
                                )
                                / self._jacobian_step,
                            ],
                            [
                                (
                                    evaluated_x.force[1] - current.force[1]
                                )
                                / self._jacobian_step,
                                (
                                    evaluated_y.force[1] - current.force[1]
                                )
                                / self._jacobian_step,
                            ],
                        ],
                        dtype=float,
                    )
                    last_jacobian = jacobian
                elif last_jacobian is not None:
                    jacobian = last_jacobian
                else:
                    stop_reason = (
                        "inner_not_converged_dx"
                        if not evaluated_x.inner_converged
                        else "inner_not_converged_dy"
                    )
                    break
                try:
                    step = np.linalg.solve(jacobian, -residual_force)
                except np.linalg.LinAlgError:
                    step = -residual_force / self._stiffness
                step = step * self._damping
            coordinate = self._limit_eccentricity_step(coordinate, step)
            state_matches_current = False
            if np.linalg.norm(coordinate) >= 1.0:
                coordinate = coordinate / 2.0

        if (
            current is None
            or not np.allclose(current.coordinate, coordinate)
            or not state_matches_current
        ):
            current = evaluate(coordinate)
            if current.inner_converged and current.residual < self._tolerance:
                converged = True
                stop_reason = "converged"
            elif (
                not current.inner_converged
                and stop_reason == "max_iter"
            ):
                stop_reason = "inner_not_converged_final"

        return EquilibriumOutcome(
            coordinate=coordinate.copy(),
            force=current.force.copy(),
            residual=current.residual,
            converged=converged,
            inner_converged=current.inner_converged,
            iterations=iteration,
            stop_reason=stop_reason,
            evaluations=tuple(evaluations),
        )


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
    "EquilibriumEvaluation",
    "EquilibriumOutcome",
    "EquilibriumSolver",
    "aggregate_active_linearization",
    "linearize_film_runtime",
]
