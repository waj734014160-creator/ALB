"""Compute thermal ALB harmonic coefficients from coupled analytic equations.

This module owns analysis orchestration only. Pressure, energy, restrictor,
and strict-complementarity equations live in ``ALB.physics.thermal``.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.sparse.linalg import splu
from skfem import asm

from ALB.physics.thermal._harmonic_base import PadComplementaritySystem
from ALB.physics.thermal._harmonic_equations import AnalyticPadSystem
from ALB.physics.thermal.solver import _build_film_grid, _transient_mass_form

FloatArray = npt.NDArray[np.float64]
BASE_TOLERANCE = 1.0e-11
LINEAR_TOLERANCE = 1.0e-8


class ThermalLinearizationError(RuntimeError):
    """Preserve the failed pad state and numerical evidence for the API facade."""

    def __init__(self, message: str, values: dict[str, Any], diagnostics: dict[str, Any]):
        super().__init__(message)
        self.values = values
        self.diagnostics = diagnostics


def validate_thermal_harmonic_config(spec: Mapping[str, Any]) -> None:
    """Reject configurations outside the equation implementation's domain."""
    if spec["family"] != "active_lubricated" or spec["unit_system"] != "dimensional":
        raise ValueError("thermal harmonic linearization requires a dimensional active_lubricated bearing")
    film = spec["film"]
    thermal = spec["thermal"]
    if thermal.get("coupling", "full") != "full":
        raise ValueError("thermal harmonic linearization requires full nodal viscosity coupling")
    if film.get("mesh_type") is not None:
        raise ValueError("thermal harmonic linearization currently requires the legacy tensor grid (mesh_type omitted)")
    if film.get("reynolds_boundary", True) is not True or film.get("continuous_boundary", False) or float(film.get("ambient_pressure", 0.0)) != 0.0:
        raise ValueError("thermal harmonic linearization requires Reynolds cavitation and a zero-pressure, nonperiodic pad perimeter")
    if "positions" in spec["restrictors"] and len(spec["restrictors"]["positions"]) != 3:
        raise ValueError("thermal harmonic linearization requires exactly three CSOrifice branches per pad")


def temperature_mass(system: Any) -> Any:
    """Return the coupled capacity matrix; its Laplace variable uses seconds."""
    pad = system.pad
    scales = pad.scales
    storage = np.asarray(system.base_context["h"]) * scales.c * scales.r / scales.qf
    mass = asm(
        _transient_mass_form, pad.thermal_basis,
        rho_cv_h_over_dt=pad.thermal_basis.interpolate(storage),
    ).tolil()
    for row in pad.dirichlet_nodes:
        mass.rows[int(row)] = []
        mass.data[int(row)] = []
    return sp.block_diag([
        sp.csr_matrix((pad.n, pad.n)), mass.tocsr(), sp.csr_matrix((5, 5)),
    ], format="csc")


def solve_frequency(system: Any, omega: float, *, thermal_inertia: bool) -> tuple[Any, float]:
    """Solve six analytic right-hand sides on one fixed base active set."""
    jacobian = system.base_jacobian
    if thermal_inertia:
        jacobian = jacobian + 1j * omega * temperature_mass(system)
    matrix = system._branch_matrix(jacobian, system.base_pressurized).astype(complex)
    factor = splu(matrix)
    transfer = np.zeros((2, 6), dtype=complex)
    max_residual = 0.0
    for column_index in range(6):
        column = system.input_matrix[:, column_index].astype(complex)
        column[:system.n][~system.base_pressurized] = 0.0
        state = factor.solve(-column)
        column_norm = float(np.linalg.norm(column))
        residual = float(np.linalg.norm(matrix @ state + column)) / max(column_norm, 1.0e-30)
        if not np.all(np.isfinite(state)) or not np.isfinite(residual) or residual > LINEAR_TOLERANCE:
            raise RuntimeError(f"harmonic equation solve failed for input column {column_index}: residual={residual}")
        transfer[:, column_index] = system.pad.force_operator @ state[:system.n]
        max_residual = max(max_residual, residual)
    return transfer, max_residual


def _temperature_branch_diagnostics(system: Any) -> dict[str, float]:
    """Require a smooth base inside the production solver's temperature bounds."""
    equations = system.pad
    scales = equations.scales
    temperature = np.asarray(system.base_state[system.n:2 * system.n])
    rise = temperature * scales.delta_t
    lower = -5.0
    upper = float(equations.wrapper.config.max_delta_t)
    if not np.all(np.isfinite(rise)) or np.any(rise <= lower) or np.any(rise >= upper):
        raise RuntimeError("thermal base reaches the production temperature clipping bound")
    raw_viscosity = scales.viscosity_from_temperature_nondim(temperature)
    for bound in (equations.wrapper.config.miu_min, equations.wrapper.config.miu_max):
        if np.any(np.isclose(raw_viscosity, bound, rtol=1.0e-10, atol=0.0)):
            raise RuntimeError("thermal base lies on a viscosity clipping transition")
    return {
        "temperature_rise_min_k": float(np.min(rise)),
        "temperature_rise_max_k": float(np.max(rise)),
        "temperature_rise_lower_bound_k": lower,
        "temperature_rise_upper_bound_k": upper,
    }


def linearize_thermal_runtime(
    runtime: Any,
    operating_point: FloatArray,
    excitation_frequency: float,
    spool: FloatArray,
) -> tuple[dict[str, Any], dict[str, Any], float, int]:
    """Refine an isolated production base and compute dimensional K, C and G.

    The returned ``spool_transfer`` is a complex N/normalized-spool matrix.
    ``stiffness`` and ``damping`` use N/m and N*s/m with
    ``delta_F = -(K + i*omega*C) delta_x + G delta_spool``. Thermal storage
    follows the configured ``transient_enabled`` switch. Control and valve
    dynamics do not enter these open-loop local bearing coefficients.
    """
    if len(runtime._pads) != 4:
        raise ValueError("thermal harmonic linearization requires four pads")
    if np.any(np.asarray(spool) == 0.0):
        raise ValueError("thermal harmonic linearization requires nonzero base spool values away from valve switching")
    omega = 2.0 * np.pi * excitation_frequency
    values: dict[str, Any] = {
        "operating_point": operating_point, "base_spool": spool,
    }
    diagnostics: dict[str, Any] = {
        "schema": "alb.thermal-harmonic-linearization.v1",
        "method": "coupled_analytic_equations",
        "excitation_frequency": excitation_frequency,
        "unit_system": "dimensional",
        "force_convention": "delta_f=-(K+i*omega*C)*delta_u+G*delta_spool",
        "cavitation": "fixed_strict_base_active_set",
        "supg_tau": "frozen_at_production_base",
        "thermal_source_coordinates": "production_flow_info",
        "pad_diagnostics": {},
    }
    pad_forces, pad_stiffness, pad_damping, pad_spool, pad_transfer = [], [], [], [], []
    pad_states, pad_masks = [], []
    max_residual = 0.0
    iterations = 0
    pad_index = -1
    system = None
    try:
        for pad_index, pad in enumerate(runtime._pads):
            film = pad.bearing.main_model
            if len(pad.bearing.simple_models) != 1 or len(pad.bearing.simple_models[0].node) != 3:
                raise ValueError("one three-branch CSOrifice is required per thermal pad")
            scales = pad.thermal_model.build_mesh(film, _build_film_grid(film))["scales"]
            initial_temperature = np.asarray(pad.result_snapshot().values["temperature"])
            initial = {"temperature_nondim": scales.temperature_to_nondim(initial_temperature, scales.t_supply)}
            inputs = np.r_[operating_point / scales.c, [0.0, 0.0], spool]
            equations = AnalyticPadSystem(pad, initial, inputs, (1, 1, 0, 0)[pad_index])
            system = PadComplementaritySystem(equations)
            audit = system.refine_base(maximum_iterations=30, tolerance=BASE_TOLERANCE)
            history = audit.pop("history")
            audit["history"] = {
                key: np.asarray([row[key] for row in history]) for key in history[0]
            }
            diagnostics["pad_diagnostics"][str(pad_index)] = audit
            if not audit["converged"] or not np.isfinite(audit["final_merit_l2"]):
                raise RuntimeError(f"strict thermal base did not converge on pad {pad_index}")
            if audit["weakly_active_nodes"]:
                raise RuntimeError(f"thermal base has biactive cavitation nodes on pad {pad_index}")
            assert system.base_state is not None
            assert system.base_context is not None
            assert system.base_pressurized is not None
            audit.update(_temperature_branch_diagnostics(system))
            final_boundary, _ = equations._thermal_boundary(system.base_context["qz"])
            if not np.array_equal(final_boundary, equations.dirichlet_nodes):
                raise RuntimeError(f"thermal inflow boundary changed during base refinement on pad {pad_index}")
            flows = system.base_state[2 * system.n + 2:]
            if np.any((flows > 0.0) != equations.cold_source_active):
                raise RuntimeError(f"thermal source branch changed during base refinement on pad {pad_index}")
            if np.any(np.abs(flows) <= 1.0e-13):
                raise RuntimeError(f"thermal base lies on a zero-flow source branch on pad {pad_index}")
            supply_delta = equations.orifice._supply_pressure_for_equations() - system.base_state[2 * system.n + 1]
            if abs(supply_delta) <= 1.0e-13:
                raise RuntimeError(f"thermal base lies on a singular valve pressure branch on pad {pad_index}")
            inertia = bool(pad.config.transient_enabled)
            transfer, residual = solve_frequency(system, omega, thermal_inertia=inertia)
            force_scale = float(scales.ps * scales.r * scales.l / 2.0)
            gamma_velocity = omega / (float(scales.omega) * float(film.args["vf"]))
            impedance = -force_scale / scales.c * (transfer[:, :2] + 1j * gamma_velocity * transfer[:, 2:4])
            pad_stiffness.append(impedance.real)
            pad_damping.append(impedance.imag / omega)
            pad_spool.append(force_scale * transfer[:, 4:])
            pad_transfer.append(transfer)
            pad_forces.append(force_scale * (equations.force_operator @ system.base_state[:system.n]))
            pad_states.append(system.base_state.copy())
            pad_masks.append(system.base_pressurized.copy())
            audit["linear_residual_relative"] = residual
            max_residual = max(max_residual, residual, audit["final_merit_l2"])
            iterations += int(audit["iterations"])
            diagnostics.update(
                thermal_inertia=inertia, shaft_frequency_hz=scales.omega / (2 * np.pi),
                whirl_ratio=omega / scales.omega, flow_projection=equations.orifice.flow_projection,
            )
        stiffness = np.sum(pad_stiffness, axis=0)
        damping = np.sum(pad_damping, axis=0)
        spool_transfer = np.sum(pad_spool, axis=0)
        values.update(
            static_force=np.sum(pad_forces, axis=0), stiffness=stiffness, damping=damping,
            dynamic_stiffness_real=stiffness, dynamic_stiffness_imag=omega * damping,
            spool_transfer=spool_transfer, spool_jacobian=spool_transfer,
            pad_stiffness=np.asarray(pad_stiffness), pad_damping=np.asarray(pad_damping),
            pad_spool_transfer=np.asarray(pad_spool), pad_force=np.asarray(pad_forces),
            pad_force_transfer_nondim=np.asarray(pad_transfer),
            pad_base_state=np.asarray(pad_states), pad_pressurized=np.asarray(pad_masks),
        )
        for value in values.values():
            if not np.all(np.isfinite(value)):
                raise RuntimeError("thermal harmonic coefficients contain non-finite values")
    except (ValueError, TypeError, RuntimeError, np.linalg.LinAlgError) as exc:
        if system is not None and system.base_state is not None:
            values["failed_pad_state"] = system.base_state
        diagnostics.update(failed_pad=pad_index, message=str(exc))
        raise ThermalLinearizationError(str(exc), values, diagnostics) from exc
    return values, diagnostics, max_residual, iterations


__all__ = ["linearize_thermal_runtime", "validate_thermal_harmonic_config"]
