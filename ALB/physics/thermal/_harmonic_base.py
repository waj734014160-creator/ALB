"""Strict NCP base refinement for the analytic thermal harmonic system."""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

INPUT_NAMES = ("ex", "ey", "vx", "vy", "sx", "sy")

class PadComplementaritySystem:
    """Refine the nonlinear base before freezing its cavitation active set."""

    def __init__(self, analytic_pad):
        self.pad = analytic_pad
        self.n = analytic_pad.n
        self.state_size = analytic_pad.state_size
        self.initial_pressurized = analytic_pad.active_pressure.copy()
        self.boundary = self._pressure_boundary_nodes()
        self.interior = ~self.boundary
        self.identity_pressure = sp.hstack(
            [
                sp.eye(self.n, format="csr"),
                sp.csr_matrix(
                    (self.n, self.state_size - self.n), dtype=float
                ),
            ],
            format="csr",
        )
        self.pad.active_pressure[:] = True
        self.base_state = None
        self.base_residual = None
        self.base_jacobian = None
        self.base_context = None
        self.input_matrix = None
        self.base_pressurized = None
        self.complementarity_scale = None

    def _pressure_boundary_nodes(self):
        """Return fixed-pressure perimeter nodes for the current pad grid."""

        coords = np.asarray(
            [node.coords for node in self.pad.model.nodes.values()], dtype=float
        )
        x = coords[:, 0]
        z = coords[:, 1]
        x_span = max(float(np.ptp(x)), 1.0)
        z_span = max(float(np.ptp(z)), 1.0)
        boundary = np.isclose(x, np.min(x), atol=x_span * 1.0e-10)
        boundary |= np.isclose(x, np.max(x), atol=x_span * 1.0e-10)
        boundary |= np.isclose(z, np.min(z), atol=z_span * 1.0e-10)
        boundary |= np.isclose(z, np.max(z), atol=z_span * 1.0e-10)
        return boundary

    def raw_assemble(self, state):
        """Assemble unconstrained pressure rows and constrained thermal rows."""

        self.pad.active_pressure[:] = True
        return self.pad.assemble(np.asarray(state, dtype=float))

    def complementarity_merit(self, state, raw_residual=None):
        """Return the exact FB/equality residual used for base refinement."""

        if raw_residual is None:
            raw_residual = self.raw_assemble(state)[0]
        pressure = np.asarray(state[: self.n], dtype=float)
        reynolds = np.asarray(raw_residual[: self.n], dtype=float)
        top = np.sqrt(pressure**2 + reynolds**2) - pressure - reynolds
        top[self.boundary] = pressure[self.boundary]
        return np.r_[top, raw_residual[self.n :]]

    def _branch_matrix(self, jacobian, pressurized):
        """Build an equality matrix for one primal-dual active-set branch."""

        pressurized = np.asarray(pressurized, dtype=bool) & self.interior
        selector_p = sp.diags(pressurized.astype(float), format="csr")
        selector_i = sp.diags((~pressurized).astype(float), format="csr")
        top = selector_p @ jacobian[: self.n, :] + selector_i @ self.identity_pressure
        return sp.vstack([top, jacobian[self.n :, :]], format="csc")

    @staticmethod
    def _scale_from_state(pressure, reynolds, interior):
        """Scale pressure and Reynolds slack in the PDAS test consistently."""

        p_scale = max(float(np.max(np.abs(pressure[interior]))), 1.0e-8)
        r_scale = max(float(np.max(np.abs(reynolds[interior]))), 1.0e-10)
        return float(np.clip(p_scale / r_scale, 1.0e-4, 1.0e4))

    def refine_base(self, maximum_iterations=30, tolerance=1.0e-11):
        """Refine the coupled base state with a primal-dual NCP Newton method."""

        state = self.pad.z.copy()
        state[: self.n][self.boundary] = 0.0
        pressurized = self.initial_pressurized & self.interior
        history = []
        converged = False
        scale = 1.0

        for iteration in range(maximum_iterations):
            raw_residual, jacobian, _ = self.raw_assemble(state)
            pressure = state[: self.n]
            reynolds = raw_residual[: self.n]
            scale = self._scale_from_state(pressure, reynolds, self.interior)
            merit = self.complementarity_merit(state, raw_residual)
            merit_norm = float(np.linalg.norm(merit))
            new_pressurized = (
                (pressure - scale * reynolds) > 0.0
            ) & self.interior
            switches = int(np.count_nonzero(new_pressurized ^ pressurized))
            history.append(
                {
                    "iteration": iteration,
                    "merit_l2": merit_norm,
                    "pressurized_nodes": int(np.count_nonzero(pressurized)),
                    "classification_switches": switches,
                }
            )
            if merit_norm <= tolerance and switches == 0:
                converged = True
                break
            pressurized = new_pressurized

            branch_matrix = self._branch_matrix(jacobian, pressurized)
            branch_residual = raw_residual.copy()
            branch_residual[: self.n][~pressurized] = pressure[~pressurized]
            update = splu(branch_matrix).solve(-branch_residual)

            accepted = False
            for alpha in (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125):
                candidate = state + alpha * update
                candidate[: self.n][self.boundary] = 0.0
                candidate_raw = self.raw_assemble(candidate)[0]
                candidate_norm = float(
                    np.linalg.norm(
                        self.complementarity_merit(candidate, candidate_raw)
                    )
                )
                if candidate_norm < merit_norm:
                    state = candidate
                    accepted = True
                    break
            if not accepted:
                state += 0.015625 * update
                state[: self.n][self.boundary] = 0.0

        raw_residual, jacobian, context = self.raw_assemble(state)
        pressure = state[: self.n]
        reynolds = raw_residual[: self.n]
        scale = self._scale_from_state(pressure, reynolds, self.interior)
        pressurized = ((pressure - scale * reynolds) > 0.0) & self.interior
        final_merit = self.complementarity_merit(state, raw_residual)
        final_norm = float(np.linalg.norm(final_merit))
        converged = converged or final_norm <= tolerance

        columns = []
        for input_index in range(len(INPUT_NAMES)):
            columns.append(
                self.pad.analytic_input_column(input_index, context)
            )
        self.base_state = state
        self.base_residual = raw_residual
        self.base_jacobian = jacobian.tocsc()
        self.base_context = context
        self.input_matrix = np.column_stack(columns)
        self.base_pressurized = pressurized
        self.complementarity_scale = scale
        self.pad.z = state.copy()

        p_tolerance = max(float(np.max(np.abs(pressure))) * 1.0e-10, 1.0e-13)
        r_tolerance = max(
            float(np.max(np.abs(reynolds[self.interior]))) * 1.0e-10,
            1.0e-13,
        )
        weak = (
            self.interior
            & (np.abs(pressure) <= p_tolerance)
            & (np.abs(reynolds) <= r_tolerance)
        )
        return {
            "converged": converged,
            "final_merit_l2": final_norm,
            "iterations": len(history),
            "history": history,
            "boundary_nodes": int(np.count_nonzero(self.boundary)),
            "pressurized_nodes": int(np.count_nonzero(pressurized)),
            "cavitated_nodes": int(
                np.count_nonzero(self.interior & ~pressurized)
            ),
            "weakly_active_nodes": int(np.count_nonzero(weak)),
            "minimum_pressure": float(np.min(pressure[self.interior])),
            "minimum_reynolds_slack": float(
                np.min(reynolds[self.interior])
            ),
            "p_tolerance": p_tolerance,
            "r_tolerance": r_tolerance,
            "complementarity_scale": scale,
            "equality_residual_l2": float(
                np.linalg.norm(raw_residual[self.n :])
            ),
        }
