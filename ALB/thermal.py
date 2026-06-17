import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np
from scipy.sparse.linalg import spsolve
from skfem import Basis, BilinearForm, ElementTriP1, LinearForm, MeshTri, asm, enforce
from skfem.helpers import dot, grad

from ALB.base import BaseCSystem, BasePostProcess
from ALB.config import ThermalConfig, build_thermal_config  # noqa: F401  re-exported
from ALB.damping import AdaptiveDampController
from ALB.film import (
    FilmOutput,
    NodimNewtonFilm,
    RectFilmElem,
    RectFilmNode,
    SkfemNewtonFilm,
    film_args_trans,
)
from ALB.matrix.static import calc_fe, calc_fe_vf, calc_ke
from ALB.nondim import ThermalNondimScales

_MIU_NUMERIC_FLOOR = 1e-12

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ThermalFilmGrid:
    x_axis: np.ndarray
    z_axis: np.ndarray
    x_dim: np.ndarray
    z_dim: np.ndarray
    h_grid: np.ndarray
    ix: np.ndarray
    iz: np.ndarray
    n_film_nodes: int
    film_xs: np.ndarray
    film_zs: np.ndarray

    def __getitem__(self, key):
        return getattr(self, key)


_FILM_MODEL_PARAM_KEYS = [
    "w",
    "x0",
    "lx",
    "lz",
    "nx",
    "nz",
    "miu",
    "c",
    "r",
    "l",
    "ps",
    "rho",
    "dxt",
    "dyt",
    "vf",
]

_PRESSURE_BACKEND_ERROR = (
    "pressure_backend only supports 'skfem'; the legacy h_eff branch is retained "
    "in code for reference and is not user-selectable"
)


def _transform_film_args(input_args: Dict[str, float]):
    return film_args_trans(*(input_args[key] for key in _FILM_MODEL_PARAM_KEYS))


def _node_sequence(model):
    return list(model.nodes.values())


def _node_coords_array(nodes) -> np.ndarray:
    return np.asarray([node.coords for node in nodes], dtype=float)


def _build_film_grid(model) -> ThermalFilmGrid:
    nodes = _node_sequence(model)
    coords = _node_coords_array(nodes)
    xs = coords[:, 0]
    zs = coords[:, 1]
    hs = np.fromiter((node.h for node in nodes), dtype=float) * model.args["c"]

    x_axis = np.unique(np.round(xs, 12))
    z_axis = np.unique(np.round(zs, 12))
    x_dim = x_axis * model.args["r"]
    z_dim = z_axis * model.args["l"] / 2.0

    h_grid = np.zeros((x_axis.size, z_axis.size), dtype=float)
    ix = SkfemThermalModel._nearest_index(x_axis, xs)
    iz = SkfemThermalModel._nearest_index(z_axis, zs)
    h_grid[ix, iz] = np.maximum(hs, 1e-9)

    return ThermalFilmGrid(
        x_axis=x_axis,
        z_axis=z_axis,
        x_dim=x_dim,
        z_dim=z_dim,
        h_grid=h_grid,
        ix=ix,
        iz=iz,
        n_film_nodes=len(nodes),
        film_xs=xs,
        film_zs=zs,
    )


def _build_thermal_mesh_data(
    model,
    grid: ThermalFilmGrid,
    *,
    x_axis: np.ndarray,
    z_axis: np.ndarray,
    h_scale: float,
    ps: float,
) -> Dict[str, np.ndarray]:
    """Build shared scikit-fem mesh mappings and pressure gradients.

    The dimensional and nondimensional thermal solvers use the same tensor
    topology.  Only coordinate axes, film-thickness scaling, and pressure scale
    differ, so keeping this block shared prevents the two build_mesh methods
    from drifting apart.
    """
    mesh = MeshTri.init_tensor(x_axis, z_axis)
    basis = Basis(mesh, ElementTriP1())

    node_ix = SkfemThermalModel._nearest_index(x_axis, mesh.p[0])
    node_iz = SkfemThermalModel._nearest_index(z_axis, mesh.p[1])
    h_nodal = np.maximum(grid["h_grid"][node_ix, node_iz] / h_scale, 1e-9)

    nodes = list(model.nodes.values())
    p_nodal = np.array([node.p for node in nodes], dtype=float) * ps
    p_grid = np.zeros((x_axis.size, z_axis.size), dtype=float)
    p_grid[grid["ix"], grid["iz"]] = p_nodal

    dp_dx_grid = np.gradient(p_grid, x_axis, axis=0)
    dp_dz_grid = np.gradient(p_grid, z_axis, axis=1)
    dp_dx_nodal = dp_dx_grid[node_ix, node_iz]
    dp_dz_nodal = dp_dz_grid[node_ix, node_iz]

    nx_grid, nz_grid = len(x_axis), len(z_axis)
    grid_to_thermal = np.full((nx_grid, nz_grid), -1, dtype=int)
    grid_to_thermal[node_ix, node_iz] = np.arange(mesh.p.shape[1])
    film_to_thermal_idx = grid_to_thermal[grid["ix"], grid["iz"]]

    grid_to_film = np.full((nx_grid, nz_grid), -1, dtype=int)
    grid_to_film[grid["ix"], grid["iz"]] = np.arange(grid["n_film_nodes"])
    thermal_to_film_idx = grid_to_film[node_ix, node_iz]

    return {
        "mesh": mesh,
        "basis": basis,
        "h_nodal": h_nodal,
        "grid": grid,
        "ps": ps,
        "dp_dx_nodal": dp_dx_nodal,
        "dp_dz_nodal": dp_dz_nodal,
        "node_ix": node_ix,
        "node_iz": node_iz,
        "film_to_thermal_idx": film_to_thermal_idx,
        "thermal_to_film_idx": thermal_to_film_idx,
    }


def wrap_pad_collection_with_thermal(pads, thermal_config: Optional[ThermalConfig]):
    if thermal_config is None:
        return list(pads)

    wrapped_pads = []
    thermal_args = vars(thermal_config)
    for pad in pads:
        wrapped_pads.append(
            ThermalHydroBearing(pad, ThermalConfig.from_dict(thermal_args))
        )
    return wrapped_pads


# ---------------------------------------------------------------------------
# Viscosity-field aware node and element
# ---------------------------------------------------------------------------


class ViscosityFilmNode(RectFilmNode):
    """Film node extended with a local viscosity ratio field (miu / miu0)."""

    def __init__(self, coords, p=0, h=0, miu_ratio=1.0):
        super().__init__(coords, p=p, h=h)
        self._miu_ratio = miu_ratio

    @property
    def miu_ratio(self):
        return self._miu_ratio

    @miu_ratio.setter
    def miu_ratio(self, val: float):
        self._miu_ratio = val


class ViscosityFilmElem(RectFilmElem):
    """Film element that accounts for per-node viscosity ratio in Reynolds equation.

    With the current reference-viscosity scaling, the nondimensional Reynolds
    equation keeps the Couette/squeeze RHS at lambda0 while the Poiseuille
    diffusion term is divided by the local viscosity ratio miu/miu0. This
    element mirrors that behavior through an effective film thickness

        h_eff_i = h_i / (miu_ratio_i)^(1/3)

    for the stiffness matrix (so that h_eff^3 = h^3 / miu_ratio), while the
    force vector continues to use the reference lambda0.
    """

    def calc_matrixs(self):
        h = np.array([node.h for node in self.nodes.values()])
        miu_r = np.array([node.miu_ratio for node in self.nodes.values()])
        h_eff = h / np.cbrt(np.clip(miu_r, 1e-12, None))
        lr = self.args["lr"]
        self._matrixs["ke"] = calc_ke(h_eff, lr, self.lz, self.lx)

    def calc_rights(self):
        h = np.array([node.h for node in self.nodes.values()])
        lambda0 = float(self.args["lambda0"])
        x0 = self.nodes[0].coords[0]
        vf = self.args["vf"]
        xct = self.args["xct"]
        yct = self.args["yct"]
        # Keep the RHS at the reference scaling; local viscosity only affects
        # the Poiseuille diffusion term above.
        self._rights["fe"] = calc_fe(h, self.lz, lambda0) + calc_fe_vf(
            x0, self.lx, self.lz, lambda0, vf, xct, yct
        )


@BilinearForm
def _reynolds_lhs_miu(u, v, w):
    return w.h3_over_miu * (w.lr**2 * grad(u)[0] * grad(v)[0] + grad(u)[1] * grad(v)[1])


@LinearForm
def _reynolds_rhs_miu0(v, w):
    dh_dx = grad(w.h)[0]
    return (-w.lambda0 * dh_dx - 2.0 * w.lambda0 * w.vf * w.dh_dt) * v


class ViscositySkfemNewtonFilm(SkfemNewtonFilm):
    """Skfem pressure assembly with mu(T) in LHS and mu0 in RHS scaling."""

    def _nodal_pressure_fields(self):
        nodes = [self.node_manager.nodes[i] for i in range(self.node_manager.non)]
        coords = _node_coords_array(nodes)
        h_nodal = np.fromiter((node.h for node in nodes), dtype=float)
        theta = coords[:, 0]
        dh_dt_nodal = self.args["xct"] * np.sin(theta) - self.args["yct"] * np.cos(
            theta
        )
        miu_ratio_nodal = np.fromiter(
            (float(getattr(node, "miu_ratio", 1.0)) for node in nodes), dtype=float
        )
        return h_nodal, dh_dt_nodal, miu_ratio_nodal

    def calc_matrixs_rights(self, calc=True, csc=True):
        if not self._skfem_initialized:
            self._init_skfem()

        if calc:
            h_nodal, dh_dt_nodal, miu_ratio_nodal = self._nodal_pressure_fields()

            h_qp = self.basis.interpolate(h_nodal)
            miu_ratio_qp = self.basis.interpolate(miu_ratio_nodal)
            h3_over_miu_qp = h_qp**3 / np.clip(miu_ratio_qp, 1e-12, None)
            dh_dt_qp = self.basis.interpolate(dh_dt_nodal)

            lambda0 = float(self.args["lambda0"])
            vf = self.args["vf"]
            lr = self.args["lr"]

            K = asm(_reynolds_lhs_miu, self.basis, h3_over_miu=h3_over_miu_qp, lr=lr)
            F = asm(
                _reynolds_rhs_miu0,
                self.basis,
                h=h_qp,
                dh_dt=dh_dt_qp,
                lambda0=lambda0,
                vf=vf,
            )

            if csc:
                self.matrixs = {"ke": K.tocsc()}
            else:
                self.matrixs = {"ke": K.toarray()}
            self.rights = {"fe": F}

        return self.matrixs, self.rights


class NodimViscositySkfemNewtonFilm(NodimNewtonFilm):
    """Nondimensional skfem pressure assembly with mu(T) in the LHS."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._skfem_initialized = False
        self.mesh_skfem = None
        self.basis = None

    _init_skfem = SkfemNewtonFilm._init_skfem
    _nodal_pressure_fields = ViscositySkfemNewtonFilm._nodal_pressure_fields
    calc_matrixs_rights = ViscositySkfemNewtonFilm.calc_matrixs_rights


# ---------------------------------------------------------------------------
# Thermal model (scikit-fem based)
# ---------------------------------------------------------------------------


@BilinearForm
def _diffusion_form(u, v, w):
    return w.k * dot(grad(u), grad(v))


@LinearForm
def _source_form(v, w):
    return w.q * v


@BilinearForm
def _advection_diffusion_form(u, v, w):
    """Advection-diffusion bilinear form for the energy equation.

    Weak form of:  rho*cv*(qx*dT/dx + qz*dT/dz) = k*laplacian(T) + Phi

    After moving convection to the LHS:
        k*dot(grad(u), grad(v)) + rho*cv*(qx*du/dx + qz*du/dz)*v
    """
    diffusion = w.k * dot(grad(u), grad(v))
    convection = w.rho_cv * (w.qx * grad(u)[0] + w.qz * grad(u)[1]) * v
    return diffusion + convection


@BilinearForm
def _supg_stiffness_form(u, v, w):
    """SUPG stabilization bilinear form.

    Adds tau * (q . grad v) * rho_cv * (q . grad u) to the stiffness matrix.
    For linear triangular elements the Laplacian of u vanishes, so only
    the advection operator contributes to the residual.
    """
    q_dot_grad_u = w.qx * grad(u)[0] + w.qz * grad(u)[1]
    q_dot_grad_v = w.qx * grad(v)[0] + w.qz * grad(v)[1]
    return w.tau * w.rho_cv * q_dot_grad_v * q_dot_grad_u


@LinearForm
def _supg_load_form(v, w):
    """SUPG stabilization load form.

    Adds tau * (q . grad v) * Phi to the load vector.
    """
    q_dot_grad_v = w.qx * grad(v)[0] + w.qz * grad(v)[1]
    return w.tau * q_dot_grad_v * w.q


@BilinearForm
def _transient_mass_form(u, v, w):
    return w.rho_cv_h_over_dt * u * v


@LinearForm
def _transient_rhs_form(v, w):
    return w.rho_cv_h_over_dt * w.t_prev * v


@BilinearForm
def _temperature_flux_source_jacobian_form(u, v, w):
    t_grad = grad(w.t_current)
    flux_term = w.rho_cv * (
        w.dqx_dt * u * t_grad[0] + w.dqz_dt * u * t_grad[1]
    ) * v
    source_term = w.dphi_dt * u * v
    return flux_term - source_term


@BilinearForm
def _nondim_temperature_flux_source_jacobian_form(u, v, w):
    t_grad = grad(w.t_current)
    flux_term = (w.dqx_dt * u * t_grad[0] + w.dqz_dt * u * t_grad[1]) * v
    source_term = w.dphi_dt * u * v
    return flux_term - source_term


class SkfemThermalModel:
    """Steady thermal model in the x-z plane solved by scikit-fem.

    Used by :class:`ThermalHydroBearing` for the dimensional coupling path.
    The nondimensional wrapper :class:`NodimThermalHydroBearing` always uses
    :class:`SkfemThermalModelNondim`.  This class is retained as a reference
    implementation for direct dimensional thermal solves and validation.
    """

    def __init__(self, config: ThermalConfig):
        self.config = config

    @staticmethod
    def _nearest_index(sorted_axis: np.ndarray, values: np.ndarray) -> np.ndarray:
        idx = np.searchsorted(sorted_axis, values)
        idx = np.clip(idx, 0, len(sorted_axis) - 1)
        left = np.clip(idx - 1, 0, len(sorted_axis) - 1)
        use_left = np.abs(values - sorted_axis[left]) < np.abs(
            values - sorted_axis[idx]
        )
        return np.where(use_left, left, idx)

    def _extract_rect_grid(self, model) -> ThermalFilmGrid:
        return _build_film_grid(model)

    def build_mesh(self, model, grid: Optional[ThermalFilmGrid] = None):
        """Build the thermal mesh and geometry data from the film model.

        Returns a dict with mesh, basis, interpolation arrays, pressure
        gradients, and the film-grid info needed later by ``solve``.
        Call once per geometry change (not every viscosity update).
        """
        if grid is None:
            grid = self._extract_rect_grid(model)
        x_dim = grid["x_dim"]
        z_dim = grid["z_dim"]

        omega = model.args["w"] * 2.0 * np.pi / 60.0
        surface_speed = omega * model.args["r"]

        rho = float(model.args["rho"])
        c_m = float(model.args["c"])
        l_m = float(model.args["l"])

        ps = float(model.args["ps"])
        mesh_data = _build_thermal_mesh_data(
            model, grid, x_axis=x_dim, z_axis=z_dim, h_scale=1.0, ps=ps
        )
        mesh_data.update(
            {
                "surface_speed": surface_speed,
                "rho": rho,
                "c_m": c_m,
                "l_m": l_m,
            }
        )
        return mesh_data

    def update_pressure_gradients(self, model, mesh_data: dict):
        """Update only the pressure gradients in mesh_data (no mesh rebuild)."""
        grid = mesh_data["grid"]
        ps = mesh_data["ps"]
        x_dim = grid["x_dim"]
        z_dim = grid["z_dim"]

        nodes = list(model.nodes.values())
        p_nodal = np.array([n.p for n in nodes], dtype=float) * ps
        p_grid = np.zeros((len(x_dim), len(z_dim)), dtype=float)
        p_grid[grid["ix"], grid["iz"]] = p_nodal

        dp_dx_grid = np.gradient(p_grid, x_dim, axis=0)
        dp_dz_grid = np.gradient(p_grid, z_dim, axis=1)

        node_ix = mesh_data["node_ix"]
        node_iz = mesh_data["node_iz"]
        mesh_data["dp_dx_nodal"] = dp_dx_grid[node_ix, node_iz]
        mesh_data["dp_dz_nodal"] = dp_dz_grid[node_ix, node_iz]

    def _prepare_viscosity_nodal(self, viscosity, mesh) -> np.ndarray:
        viscosity_input = np.asarray(viscosity, dtype=float)
        if viscosity_input.size == 1:
            viscosity_nodal = np.full(
                mesh.p.shape[1], float(viscosity_input), dtype=float
            )
        elif viscosity_input.size == mesh.p.shape[1]:
            viscosity_nodal = viscosity_input.reshape(-1).copy()
        else:
            viscosity_nodal = np.full(
                mesh.p.shape[1], float(np.mean(viscosity_input)), dtype=float
            )
        return np.clip(viscosity_nodal, self.config.miu_min, self.config.miu_max)

    def _calc_flux_and_source(self, mesh_data: dict, viscosity_nodal: np.ndarray):
        h_nodal = mesh_data["h_nodal"]
        surface_speed = mesh_data["surface_speed"]
        dp_dx = mesh_data["dp_dx_nodal"]
        dp_dz = mesh_data["dp_dz_nodal"]

        viscosity_safe = np.maximum(viscosity_nodal, _MIU_NUMERIC_FLOOR)
        h3_over_12mu = h_nodal**3 / (12.0 * viscosity_safe)
        qx_nodal = surface_speed * h_nodal / 2.0 - h3_over_12mu * dp_dx
        qz_nodal = -h3_over_12mu * dp_dz

        phi_couette = viscosity_nodal * surface_speed**2 / h_nodal
        phi_poiseuille = h3_over_12mu * (dp_dx**2 + dp_dz**2)
        phi_nodal = self.config.heat_partition * (phi_couette + phi_poiseuille)
        return qx_nodal, qz_nodal, phi_nodal

    def _orifice_flow_totals(self, orifice_data: Optional[list]):
        if not orifice_data:
            return 0.0, 0.0
        return sum(abs(item[2]) for item in orifice_data), sum(
            item[2] for item in orifice_data
        )

    def _assemble_energy_system(self, basis, rho_cv, qx_nodal, qz_nodal, phi_nodal):
        K = asm(
            _advection_diffusion_form,
            basis,
            k=self.config.k_lub,
            rho_cv=rho_cv,
            qx=basis.interpolate(qx_nodal),
            qz=basis.interpolate(qz_nodal),
        )
        f = asm(_source_form, basis, q=basis.interpolate(phi_nodal))
        return K, f

    def _apply_transient_term(self, K, f, basis, h_nodal, rho_cv, temperature_prev):
        dt = self.config.dt
        if dt is None or dt <= 0:
            raise ValueError("Transient thermal solve requires a positive dt")
        if temperature_prev is None:
            raise ValueError(
                "Transient thermal solve requires temperature_prev as the initial field"
            )
        t_prev = np.asarray(temperature_prev, dtype=float).reshape(-1)
        if t_prev.size != basis.N:
            raise ValueError(
                "temperature_prev size must match the thermal mesh node count"
            )
        rho_cv_h_over_dt = rho_cv * h_nodal / dt
        interp_mass = basis.interpolate(rho_cv_h_over_dt)
        interp_t_prev = basis.interpolate(t_prev)
        K += asm(_transient_mass_form, basis, rho_cv_h_over_dt=interp_mass)
        f += asm(
            _transient_rhs_form,
            basis,
            rho_cv_h_over_dt=interp_mass,
            t_prev=interp_t_prev,
        )
        return K, f

    def _apply_supg(self, K, f, mesh, basis, rho_cv, qx_nodal, qz_nodal, phi_nodal):
        if not self.config.supg:
            return K, f
        tx_arr = mesh.p[0]
        tz_arr = mesh.p[1]
        q_mag = np.sqrt(qx_nodal**2 + qz_nodal**2)
        dx_mesh = (
            float(np.min(np.diff(np.unique(tx_arr))))
            if len(np.unique(tx_arr)) > 1
            else 1.0
        )
        dz_mesh = (
            float(np.min(np.diff(np.unique(tz_arr))))
            if len(np.unique(tz_arr)) > 1
            else 1.0
        )
        h_elem = np.sqrt(dx_mesh**2 + dz_mesh**2)
        alpha_diff = self.config.k_lub / (rho_cv + 1e-30)
        pe_h = q_mag * h_elem / (2.0 * alpha_diff + 1e-30)
        pe_safe = np.clip(pe_h, 1e-10, 500.0)
        xi = 1.0 / np.tanh(pe_safe) - 1.0 / pe_safe
        tau_nodal = xi * h_elem / (2.0 * q_mag + 1e-12)
        interp_qx = basis.interpolate(qx_nodal)
        interp_qz = basis.interpolate(qz_nodal)
        interp_tau = basis.interpolate(tau_nodal)
        interp_phi = basis.interpolate(phi_nodal)
        K += asm(
            _supg_stiffness_form,
            basis,
            rho_cv=rho_cv,
            qx=interp_qx,
            qz=interp_qz,
            tau=interp_tau,
        )
        f += asm(
            _supg_load_form,
            basis,
            qx=interp_qx,
            qz=interp_qz,
            tau=interp_tau,
            q=interp_phi,
        )
        return K, f

    def _boundary_nodes(self, mesh, qz_nodal):
        tx = mesh.p[0]
        tz = mesh.p[1]
        x_min, x_max = float(tx.min()), float(tx.max())
        z_min, z_max = float(tz.min()), float(tz.max())
        tol_x = (x_max - x_min) * 1e-8
        tol_z = (z_max - z_min) * 1e-8

        inlet_nodes = np.where(np.abs(tx - x_min) < tol_x)[0]
        side_z_min = np.where(np.abs(tz - z_min) < tol_z)[0]
        side_z_max = np.where(np.abs(tz - z_max) < tol_z)[0]

        side_mode = str(self.config.axial_side_bc).lower()
        dirichlet_parts = [inlet_nodes]
        if side_mode == "fixed":
            dirichlet_parts.extend([side_z_min, side_z_max])
        elif side_mode == "adiabatic":
            pass
        elif side_mode == "inflow_fixed":
            if side_z_min.size > 0 and float(np.mean(qz_nodal[side_z_min])) > 0.0:
                dirichlet_parts.append(side_z_min)
            if side_z_max.size > 0 and float(np.mean(qz_nodal[side_z_max])) < 0.0:
                dirichlet_parts.append(side_z_max)
        else:
            raise ValueError(
                "axial_side_bc must be one of: 'fixed', 'adiabatic', 'inflow_fixed'"
            )
        return inlet_nodes, np.unique(np.concatenate(dirichlet_parts)).astype(int)

    def _apply_orifice_sources(self, K, f, mesh, rho_cv, t_supply, orifice_data):
        if not orifice_data:
            return K, f
        tx = mesh.p[0]
        tz = mesh.p[1]
        K = K.tolil()
        for ox, oz, q_vol in orifice_data:
            if q_vol <= 0:
                continue
            dist2 = (tx - ox) ** 2 + (tz - oz) ** 2
            j = int(np.argmin(dist2))
            alpha_o = rho_cv * q_vol
            K[j, j] += alpha_o
            f[j] += alpha_o * t_supply
        return K.tocsr(), f

    def _temperature_boundary_values(self, size, inlet_nodes, t_supply):
        side_temp = (
            self.config.axial_side_t
            if self.config.axial_side_t is not None
            else t_supply
        )
        t_bc = np.full(size, side_temp, dtype=float)
        t_bc[inlet_nodes] = t_supply
        return t_bc

    def _calc_flux_source_derivatives(
        self,
        mesh_data: dict,
        viscosity_nodal: np.ndarray,
        dviscosity_dt: np.ndarray,
    ):
        h_nodal = mesh_data["h_nodal"]
        surface_speed = mesh_data["surface_speed"]
        dp_dx = mesh_data["dp_dx_nodal"]
        dp_dz = mesh_data["dp_dz_nodal"]

        viscosity_safe = np.maximum(viscosity_nodal, _MIU_NUMERIC_FLOOR)
        h3_over_12mu = h_nodal**3 / (12.0 * viscosity_safe)
        dh3_over_12mu_dt = (
            -(h_nodal**3) / (12.0 * viscosity_safe**2) * dviscosity_dt
        )
        qx_nodal = surface_speed * h_nodal / 2.0 - h3_over_12mu * dp_dx
        qz_nodal = -h3_over_12mu * dp_dz
        dqx_dt = -dh3_over_12mu_dt * dp_dx
        dqz_dt = -dh3_over_12mu_dt * dp_dz

        pressure_grad_sq = dp_dx**2 + dp_dz**2
        phi_couette = viscosity_nodal * surface_speed**2 / h_nodal
        phi_poiseuille = h3_over_12mu * pressure_grad_sq
        dphi_dt = self.config.heat_partition * (
            dviscosity_dt * surface_speed**2 / h_nodal
            + dh3_over_12mu_dt * pressure_grad_sq
        )
        phi_nodal = self.config.heat_partition * (phi_couette + phi_poiseuille)
        return qx_nodal, qz_nodal, phi_nodal, dqx_dt, dqz_dt, dphi_dt

    def _viscosity_from_temperature_with_derivative(
        self,
        temperature: np.ndarray,
        *,
        miu0: float,
        t_ref: float,
    ):
        raw = float(miu0) * np.exp(-self.config.beta * (temperature - float(t_ref)))
        viscosity = np.clip(raw, self.config.miu_min, self.config.miu_max)
        active = (raw > self.config.miu_min) & (raw < self.config.miu_max)
        dviscosity_dt = np.where(active, -self.config.beta * viscosity, 0.0)
        return viscosity, dviscosity_dt

    def _calc_supg_tau_nodal(self, mesh, rho_cv, qx_nodal, qz_nodal):
        tx_arr = mesh.p[0]
        tz_arr = mesh.p[1]
        q_mag = np.sqrt(qx_nodal**2 + qz_nodal**2)
        dx_mesh = (
            float(np.min(np.diff(np.unique(tx_arr))))
            if len(np.unique(tx_arr)) > 1
            else 1.0
        )
        dz_mesh = (
            float(np.min(np.diff(np.unique(tz_arr))))
            if len(np.unique(tz_arr)) > 1
            else 1.0
        )
        h_elem = np.sqrt(dx_mesh**2 + dz_mesh**2)
        alpha_diff = self.config.k_lub / (rho_cv + 1e-30)
        pe_h = q_mag * h_elem / (2.0 * alpha_diff + 1e-30)
        pe_safe = np.clip(pe_h, 1e-10, 500.0)
        xi = 1.0 / np.tanh(pe_safe) - 1.0 / pe_safe
        return xi * h_elem / (2.0 * q_mag + 1e-12)

    @staticmethod
    def _apply_dirichlet_to_residual_jacobian(K, f, J_extra, temperature, nodes, t_bc):
        J = (K + J_extra).tolil()
        residual = np.asarray(K @ temperature - f, dtype=float)
        if nodes.size > 0:
            residual[nodes] = temperature[nodes] - t_bc[nodes]
            for node in nodes:
                J.rows[int(node)] = [int(node)]
                J.data[int(node)] = [1.0]
        return residual, J.tocsr()

    @staticmethod
    def _apply_dirichlet_to_residual(K, f, temperature, nodes, t_bc):
        """Apply Dirichlet rows to a residual without building a Jacobian."""
        residual = np.asarray(K @ temperature - f, dtype=float)
        if nodes.size > 0:
            residual[nodes] = temperature[nodes] - t_bc[nodes]
        return residual

    @staticmethod
    def _relative_residual_norm(residual, K, temperature, f, free_nodes):
        if free_nodes.size == 0:
            selected = residual
        else:
            selected = residual[free_nodes]
        numerator = float(np.max(np.abs(selected))) if selected.size else 0.0
        scale_vec = np.asarray(K @ temperature, dtype=float)
        denominator = max(
            float(np.max(np.abs(scale_vec))) if scale_vec.size else 0.0,
            float(np.max(np.abs(f))) if f.size else 0.0,
            1.0,
        )
        return numerator / denominator

    def _initial_temperature_guess(
        self,
        basis,
        t_supply: float,
        temperature_initial: Optional[np.ndarray],
        lower: float,
        upper: float,
    ):
        if temperature_initial is None:
            return np.full(basis.N, t_supply, dtype=float)
        guess = np.asarray(temperature_initial, dtype=float).reshape(-1)
        if guess.size != basis.N:
            return np.full(basis.N, t_supply, dtype=float)
        return np.clip(guess.copy(), lower, upper)

    def _assemble_supg_with_frozen_tau(
        self,
        K,
        f,
        basis,
        qx_nodal,
        qz_nodal,
        phi_nodal,
        *,
        rho_cv: Optional[float] = None,
        tau_nodal: Optional[np.ndarray] = None,
        nondim: bool = False,
    ):
        if not self.config.supg:
            return K, f
        if tau_nodal is None:
            raise ValueError("tau_nodal is required for frozen SUPG assembly")
        form_k = _nondim_supg_stiffness_form if nondim else _supg_stiffness_form
        kwargs = {
            "qx": basis.interpolate(qx_nodal),
            "qz": basis.interpolate(qz_nodal),
            "tau": basis.interpolate(tau_nodal),
        }
        if not nondim:
            kwargs["rho_cv"] = rho_cv
        K += asm(form_k, basis, **kwargs)
        form_f = _nondim_supg_load_form if nondim else _supg_load_form
        f += asm(
            form_f,
            basis,
            qx=basis.interpolate(qx_nodal),
            qz=basis.interpolate(qz_nodal),
            tau=basis.interpolate(tau_nodal),
            q=basis.interpolate(phi_nodal),
        )
        return K, f

    def solve_segregated_newton(
        self,
        model,
        viscosity: Union[float, np.ndarray],
        mesh_data: Optional[dict] = None,
        orifice_data: Optional[list] = None,
        temperature_prev: Optional[np.ndarray] = None,
        transient: bool = False,
        *,
        temperature_initial: Optional[np.ndarray] = None,
        miu0: Optional[float] = None,
        t_ref: Optional[float] = None,
    ) -> Dict[str, np.ndarray]:
        """Solve the fixed-pressure nonlinear thermal equation by Newton iteration."""
        if mesh_data is None:
            mesh_data = self.build_mesh(model)

        mesh = mesh_data["mesh"]
        basis = mesh_data["basis"]
        grid = mesh_data["grid"]
        t_supply = (
            self.config.t_supply
            if self.config.t_supply is not None
            else self.config.t_in
        )
        q_orifice_total, q_orifice_net = self._orifice_flow_totals(orifice_data)
        rho_cv = mesh_data["rho"] * self.config.cp_lub
        miu0_value = float(
            miu0
            if miu0 is not None
            else self.config.miu0
            if self.config.miu0 is not None
            else np.mean(np.asarray(viscosity, dtype=float))
        )
        t_ref_value = float(
            t_ref
            if t_ref is not None
            else self.config.t_ref
            if self.config.t_ref is not None
            else self.config.t_in
        )
        lower = t_supply - 5.0
        upper = t_supply + self.config.max_delta_t
        temperature = self._initial_temperature_guess(
            basis, t_supply, temperature_initial, lower, upper
        )

        initial_miu, initial_dmiu = self._viscosity_from_temperature_with_derivative(
            temperature, miu0=miu0_value, t_ref=t_ref_value
        )
        initial_qx, initial_qz, _, _, _, _ = self._calc_flux_source_derivatives(
            mesh_data, initial_miu, initial_dmiu
        )
        tau_nodal = (
            self._calc_supg_tau_nodal(mesh, rho_cv, initial_qx, initial_qz)
            if self.config.supg
            else None
        )
        inlet_nodes, dirichlet_nodes = self._boundary_nodes(mesh, initial_qz)
        t_bc = self._temperature_boundary_values(basis.N, inlet_nodes, t_supply)
        if dirichlet_nodes.size > 0:
            temperature[dirichlet_nodes] = t_bc[dirichlet_nodes]
        all_nodes = np.arange(basis.N, dtype=int)
        free_nodes = np.setdiff1d(all_nodes, dirichlet_nodes, assume_unique=False)

        def residual_system(current, *, include_jacobian: bool):
            viscosity_nodal, dviscosity_dt = (
                self._viscosity_from_temperature_with_derivative(
                    current, miu0=miu0_value, t_ref=t_ref_value
                )
            )
            qx_nodal, qz_nodal, phi_nodal, dqx_dt, dqz_dt, dphi_dt = (
                self._calc_flux_source_derivatives(
                    mesh_data, viscosity_nodal, dviscosity_dt
                )
            )
            K, f = self._assemble_energy_system(
                basis, rho_cv, qx_nodal, qz_nodal, phi_nodal
            )
            if transient:
                K, f = self._apply_transient_term(
                    K, f, basis, mesh_data["h_nodal"], rho_cv, temperature_prev
                )
            K, f = self._assemble_supg_with_frozen_tau(
                K,
                f,
                basis,
                qx_nodal,
                qz_nodal,
                phi_nodal,
                rho_cv=rho_cv,
                tau_nodal=tau_nodal,
                nondim=False,
            )
            K, f = self._apply_orifice_sources(
                K, f, mesh, rho_cv, t_supply, orifice_data
            )
            if include_jacobian:
                J_extra = asm(
                    _temperature_flux_source_jacobian_form,
                    basis,
                    rho_cv=rho_cv,
                    dqx_dt=basis.interpolate(dqx_dt),
                    dqz_dt=basis.interpolate(dqz_dt),
                    dphi_dt=basis.interpolate(dphi_dt),
                    t_current=basis.interpolate(current),
                )
                residual, J = self._apply_dirichlet_to_residual_jacobian(
                    K, f, J_extra, current, dirichlet_nodes, t_bc
                )
            else:
                residual = self._apply_dirichlet_to_residual(
                    K, f, current, dirichlet_nodes, t_bc
                )
                J = None
            norm = self._relative_residual_norm(
                residual, K, current, f, free_nodes
            )
            return residual, J, norm, K, f, viscosity_nodal, qx_nodal, qz_nodal, phi_nodal

        tol = (
            self.config.thermal_newton_tol
            if self.config.thermal_newton_tol is not None
            else self.config.tol
        )
        converged = False
        iterations = 0
        line_search_steps = 0
        residual_norm = np.inf
        final_fields = None
        for i in range(self.config.thermal_newton_max_iter):
            iterations = i + 1
            (
                residual,
                J,
                residual_norm,
                K,
                f,
                viscosity_nodal,
                qx_nodal,
                qz_nodal,
                phi_nodal,
            ) = residual_system(temperature, include_jacobian=True)
            final_fields = (viscosity_nodal, qx_nodal, qz_nodal, phi_nodal)
            if residual_norm < tol:
                converged = True
                break
            delta = spsolve(J, -residual)
            if not np.all(np.isfinite(delta)):
                break
            alpha = float(self.config.thermal_newton_damp)
            accepted = False
            trial = temperature
            trial_norm = residual_norm
            if self.config.thermal_newton_line_search:
                while alpha >= self.config.thermal_newton_min_damp:
                    candidate = np.clip(temperature + alpha * delta, lower, upper)
                    if dirichlet_nodes.size > 0:
                        candidate[dirichlet_nodes] = t_bc[dirichlet_nodes]
                    _, _, candidate_norm, *_ = residual_system(
                        candidate, include_jacobian=False
                    )
                    if np.isfinite(candidate_norm) and candidate_norm < residual_norm:
                        trial = candidate
                        trial_norm = candidate_norm
                        accepted = True
                        break
                    alpha *= 0.5
                    line_search_steps += 1
                if not accepted:
                    break
            else:
                alpha = max(alpha, self.config.thermal_newton_min_damp)
                trial = np.clip(temperature + alpha * delta, lower, upper)
                if dirichlet_nodes.size > 0:
                    trial[dirichlet_nodes] = t_bc[dirichlet_nodes]
                _, _, trial_norm, *_ = residual_system(
                    trial, include_jacobian=False
                )
                if not np.isfinite(trial_norm):
                    break
            temperature = trial
            residual_norm = trial_norm
        else:
            (
                _,
                _,
                residual_norm,
                _,
                _,
                viscosity_nodal,
                qx_nodal,
                qz_nodal,
                phi_nodal,
            ) = residual_system(temperature, include_jacobian=False)
            final_fields = (viscosity_nodal, qx_nodal, qz_nodal, phi_nodal)

        if final_fields is None:
            viscosity_nodal, _ = self._viscosity_from_temperature_with_derivative(
                temperature, miu0=miu0_value, t_ref=t_ref_value
            )
            qx_nodal, qz_nodal, phi_nodal = self._calc_flux_and_source(
                mesh_data, viscosity_nodal
            )
        else:
            viscosity_nodal, qx_nodal, qz_nodal, phi_nodal = final_fields

        return {
            "temperature": temperature,
            "t_eff": float(np.mean(temperature)),
            "mesh": mesh,
            "n_film_nodes": grid["n_film_nodes"],
            "grid": grid,
            "q_orifice_total": q_orifice_total,
            "q_orifice_net": q_orifice_net,
            "newton_converged": bool(converged),
            "newton_iterations": int(iterations),
            "newton_residual": float(residual_norm),
            "newton_line_search_steps": int(line_search_steps),
            "viscosity_nodal": viscosity_nodal,
            "qx": qx_nodal,
            "qz": qz_nodal,
            "heat_source": phi_nodal,
        }

    def solve(
        self,
        model,
        viscosity: Union[float, np.ndarray],
        mesh_data: Optional[dict] = None,
        orifice_data: Optional[list] = None,
        temperature_prev: Optional[np.ndarray] = None,
        transient: bool = False,
    ) -> Dict[str, np.ndarray]:
        """Solve the 2-D advection-diffusion energy equation on the film.

        Governing equation (with constant c_v):

            rho * c_v * (qx * dT/dx + qz * dT/dz)
                = k * laplacian(T) + mu*U^2/h
                  + h^3/(12*mu) * [(dp/dx)^2 + (dp/dz)^2]

        where the in-plane volume fluxes are:

            qx = U*h/2 - h^3/(12*mu) * dp/dx
            qz =       - h^3/(12*mu) * dp/dz
        """
        if mesh_data is None:
            mesh_data = self.build_mesh(model)

        mesh = mesh_data["mesh"]
        basis = mesh_data["basis"]
        grid = mesh_data["grid"]
        viscosity_nodal = self._prepare_viscosity_nodal(viscosity, mesh)
        qx_nodal, qz_nodal, phi_nodal = self._calc_flux_and_source(
            mesh_data, viscosity_nodal
        )
        t_supply = (
            self.config.t_supply
            if self.config.t_supply is not None
            else self.config.t_in
        )
        q_orifice_total, q_orifice_net = self._orifice_flow_totals(orifice_data)

        rho_cv = mesh_data["rho"] * self.config.cp_lub
        K, f = self._assemble_energy_system(
            basis, rho_cv, qx_nodal, qz_nodal, phi_nodal
        )

        if transient:
            K, f = self._apply_transient_term(
                K, f, basis, mesh_data["h_nodal"], rho_cv, temperature_prev
            )

        K, f = self._apply_supg(
            K, f, mesh, basis, rho_cv, qx_nodal, qz_nodal, phi_nodal
        )
        inlet_nodes, dirichlet_nodes = self._boundary_nodes(mesh, qz_nodal)
        K, f = self._apply_orifice_sources(K, f, mesh, rho_cv, t_supply, orifice_data)
        t_bc = self._temperature_boundary_values(K.shape[0], inlet_nodes, t_supply)

        if dirichlet_nodes.size > 0:
            K_bc, f_bc = enforce(K, f, D=dirichlet_nodes, x=t_bc)
        else:
            K_bc, f_bc = K, f
        t_nodal = spsolve(K_bc, f_bc)

        # Clamp to physical range
        t_nodal = np.clip(t_nodal, t_supply - 5.0, t_supply + self.config.max_delta_t)

        return {
            "temperature": t_nodal,
            "t_eff": float(np.mean(t_nodal)),
            "mesh": mesh,
            "n_film_nodes": grid["n_film_nodes"],
            "grid": grid,
            "q_orifice_total": q_orifice_total,
            "q_orifice_net": q_orifice_net,
        }


@BilinearForm
def _nondim_advection_diffusion_form(u, v, w):
    diffusion = w.diff_x * grad(u)[0] * grad(v)[0] + w.diff_z * grad(u)[1] * grad(v)[1]
    convection = (w.qx * grad(u)[0] + w.qz * grad(u)[1]) * v
    return diffusion + convection


@BilinearForm
def _nondim_supg_stiffness_form(u, v, w):
    q_dot_grad_u = w.qx * grad(u)[0] + w.qz * grad(u)[1]
    q_dot_grad_v = w.qx * grad(v)[0] + w.qz * grad(v)[1]
    return w.tau * q_dot_grad_v * q_dot_grad_u


@LinearForm
def _nondim_supg_load_form(v, w):
    q_dot_grad_v = w.qx * grad(v)[0] + w.qz * grad(v)[1]
    return w.tau * q_dot_grad_v * w.q


class SkfemThermalModelNondim(SkfemThermalModel):
    """Steady thermal model assembled in nondimensional coordinates and fields."""

    def build_mesh(self, model, grid: Optional[ThermalFilmGrid] = None):
        if grid is None:
            grid = self._extract_rect_grid(model)
        x_axis = grid["x_axis"]
        z_axis = grid["z_axis"]

        scales = ThermalNondimScales.from_model_config(
            model,
            self.config,
            miu0=float(model.args["miu0"]),
        )
        mesh_data = _build_thermal_mesh_data(
            model, grid, x_axis=x_axis, z_axis=z_axis, h_scale=model.args["c"], ps=1.0
        )
        mesh_data["scales"] = scales
        mesh_data["ps"] = scales.ps
        return mesh_data

    def _nondim_viscosity_from_temperature_with_derivative(
        self, temperature_bar: np.ndarray, scales: ThermalNondimScales
    ):
        raw_dim = scales.viscosity_from_temperature_nondim(temperature_bar)
        clipped_dim = np.clip(raw_dim, self.config.miu_min, self.config.miu_max)
        active = (raw_dim > self.config.miu_min) & (raw_dim < self.config.miu_max)
        miu_bar = np.clip(scales.viscosity_to_nondim(clipped_dim), 1e-12, None)
        dmiu_bar_dt = np.where(active, -scales.beta_nondim * miu_bar, 0.0)
        return clipped_dim, miu_bar, dmiu_bar_dt

    @staticmethod
    def _calc_nondim_flux_source_derivatives(
        mesh_data: dict,
        miu_bar: np.ndarray,
        dmiu_bar_dt: np.ndarray,
    ):
        h_bar = mesh_data["h_nodal"]
        scales: ThermalNondimScales = mesh_data["scales"]
        dp_dx_bar = mesh_data["dp_dx_nodal"]
        dp_dz_bar = mesh_data["dp_dz_nodal"]

        ax_coeff = scales.lr**2 * h_bar**3 / miu_bar
        az_coeff = scales.lr * h_bar**3 / miu_bar
        dax_dt = -(scales.lr**2 * h_bar**3) / (miu_bar**2) * dmiu_bar_dt
        daz_dt = -(scales.lr * h_bar**3) / (miu_bar**2) * dmiu_bar_dt

        qx_bar = scales.lambda0 * h_bar - ax_coeff * dp_dx_bar
        qz_bar = -az_coeff * dp_dz_bar
        conv_x = qx_bar
        conv_z = qz_bar / scales.lr
        dconv_x_dt = -dax_dt * dp_dx_bar
        dconv_z_dt = (-daz_dt * dp_dz_bar) / scales.lr

        shear_coeff = scales.lambda0**2 / (3.0 * scales.lr**2)
        grad_sq = scales.lr**2 * dp_dx_bar**2 + dp_dz_bar**2
        phi_bar = scales.theta_e * (
            shear_coeff * miu_bar / h_bar + h_bar**3 / miu_bar * grad_sq
        )
        dphi_dt = scales.theta_e * (
            shear_coeff * dmiu_bar_dt / h_bar
            - h_bar**3 / (miu_bar**2) * grad_sq * dmiu_bar_dt
        )
        return conv_x, conv_z, phi_bar, dconv_x_dt, dconv_z_dt, dphi_dt

    def _calc_nondim_supg_tau_nodal(self, mesh, diff_x, diff_z, conv_x, conv_z):
        tx_arr = mesh.p[0]
        tz_arr = mesh.p[1]
        q_mag = np.sqrt(conv_x**2 + conv_z**2)
        dx_mesh = (
            float(np.min(np.diff(np.unique(tx_arr))))
            if len(np.unique(tx_arr)) > 1
            else 1.0
        )
        dz_mesh = (
            float(np.min(np.diff(np.unique(tz_arr))))
            if len(np.unique(tz_arr)) > 1
            else 1.0
        )
        h_elem = np.sqrt(dx_mesh**2 + dz_mesh**2)
        alpha_nd = max(diff_x, diff_z, 1e-30)
        pe_h = q_mag * h_elem / (2.0 * alpha_nd + 1e-30)
        pe_safe = np.clip(pe_h, 1e-10, 500.0)
        xi = 1.0 / np.tanh(pe_safe) - 1.0 / pe_safe
        return xi * h_elem / (2.0 * q_mag + 1e-12)

    def update_pressure_gradients(self, model, mesh_data: dict):
        grid = mesh_data["grid"]
        x_axis = grid["x_axis"]
        z_axis = grid["z_axis"]

        nodes = list(model.nodes.values())
        p_nodal = np.array([node.p for node in nodes], dtype=float)
        p_grid = np.zeros((len(x_axis), len(z_axis)), dtype=float)
        p_grid[grid["ix"], grid["iz"]] = p_nodal

        dp_dx_grid = np.gradient(p_grid, x_axis, axis=0)
        dp_dz_grid = np.gradient(p_grid, z_axis, axis=1)

        node_ix = mesh_data["node_ix"]
        node_iz = mesh_data["node_iz"]
        mesh_data["dp_dx_nodal"] = dp_dx_grid[node_ix, node_iz]
        mesh_data["dp_dz_nodal"] = dp_dz_grid[node_ix, node_iz]

    def solve_segregated_newton(
        self,
        model,
        viscosity: Union[float, np.ndarray],
        mesh_data: Optional[dict] = None,
        orifice_data: Optional[list] = None,
        temperature_prev: Optional[np.ndarray] = None,
        transient: bool = False,
        *,
        temperature_initial: Optional[np.ndarray] = None,
        miu0: Optional[float] = None,
        t_ref: Optional[float] = None,
    ) -> Dict[str, np.ndarray]:
        """Solve the fixed-pressure nondimensional thermal equation by Newton iteration."""
        if transient:
            raise NotImplementedError(
                "The nondimensional thermal solver currently supports steady solves only."
            )
        if mesh_data is None:
            mesh_data = self.build_mesh(model)

        mesh = mesh_data["mesh"]
        basis = mesh_data["basis"]
        scales: ThermalNondimScales = mesh_data["scales"]
        t_supply = (
            self.config.t_supply
            if self.config.t_supply is not None
            else self.config.t_in
        )
        lower = -5.0 / scales.delta_t
        upper = self.config.max_delta_t / scales.delta_t
        if temperature_initial is None:
            temperature_bar = np.zeros(basis.N, dtype=float)
        else:
            initial = np.asarray(temperature_initial, dtype=float).reshape(-1)
            if initial.size == basis.N:
                temperature_bar = scales.temperature_to_nondim(initial, t_supply)
            else:
                temperature_bar = np.zeros(basis.N, dtype=float)
        temperature_bar = np.clip(temperature_bar, lower, upper)

        q_orifice_total = 0.0
        q_orifice_net = 0.0
        if orifice_data:
            q_orifice_total = sum(abs(item[2]) for item in orifice_data)
            q_orifice_net = sum(item[2] for item in orifice_data)

        rho_cv = scales.rho * scales.cp
        diff_x = self.config.k_lub / (rho_cv * scales.flow_scale * scales.r + 1e-30)
        diff_z = diff_x / (scales.lr**2)

        _, initial_miu_bar, initial_dmiu = (
            self._nondim_viscosity_from_temperature_with_derivative(
                temperature_bar, scales
            )
        )
        initial_qx, initial_qz, _, _, _, _ = (
            self._calc_nondim_flux_source_derivatives(
                mesh_data, initial_miu_bar, initial_dmiu
            )
        )
        tau_nodal = (
            self._calc_nondim_supg_tau_nodal(
                mesh, diff_x, diff_z, initial_qx, initial_qz
            )
            if self.config.supg
            else None
        )

        t_supply_dim = (
            self.config.t_supply
            if self.config.t_supply is not None
            else self.config.t_in
        )
        side_temp = (
            self.config.axial_side_t
            if self.config.axial_side_t is not None
            else t_supply_dim
        )
        side_temp_bar = scales.temperature_to_nondim(side_temp, t_supply_dim)
        tx = mesh.p[0]
        tz = mesh.p[1]
        x_min, x_max = float(tx.min()), float(tx.max())
        z_min, z_max = float(tz.min()), float(tz.max())
        tol_x = (x_max - x_min) * 1e-8
        tol_z = (z_max - z_min) * 1e-8
        inlet_nodes = np.where(np.abs(tx - x_min) < tol_x)[0]
        side_z_min = np.where(np.abs(tz - z_min) < tol_z)[0]
        side_z_max = np.where(np.abs(tz - z_max) < tol_z)[0]
        side_mode = str(self.config.axial_side_bc).lower()
        dirichlet_parts = [inlet_nodes]
        if side_mode == "fixed":
            dirichlet_parts.extend([side_z_min, side_z_max])
        elif side_mode == "adiabatic":
            pass
        elif side_mode == "inflow_fixed":
            if side_z_min.size > 0 and float(np.mean(initial_qz[side_z_min])) > 0.0:
                dirichlet_parts.append(side_z_min)
            if side_z_max.size > 0 and float(np.mean(initial_qz[side_z_max])) < 0.0:
                dirichlet_parts.append(side_z_max)
        else:
            raise ValueError(
                "axial_side_bc must be one of: 'fixed', 'adiabatic', 'inflow_fixed'"
            )
        dirichlet_nodes = np.unique(np.concatenate(dirichlet_parts)).astype(int)
        t_bc = np.full(basis.N, side_temp_bar, dtype=float)
        t_bc[inlet_nodes] = 0.0
        if dirichlet_nodes.size > 0:
            temperature_bar[dirichlet_nodes] = t_bc[dirichlet_nodes]
        all_nodes = np.arange(basis.N, dtype=int)
        free_nodes = np.setdiff1d(all_nodes, dirichlet_nodes, assume_unique=False)

        def apply_orifice(K, f):
            if not orifice_data:
                return K, f
            K = K.tolil()
            for ox, oz, q_bar in orifice_data:
                if q_bar <= 0:
                    continue
                dist2 = (tx - ox) ** 2 + (tz - oz) ** 2
                j = int(np.argmin(dist2))
                K[j, j] += float(q_bar)
                f[j] += 0.0
            return K.tocsr(), f

        def residual_system(current_bar, *, include_jacobian: bool):
            miu_nodal, miu_bar, dmiu_bar_dt = (
                self._nondim_viscosity_from_temperature_with_derivative(
                    current_bar, scales
                )
            )
            conv_x, conv_z, phi_bar, dconv_x_dt, dconv_z_dt, dphi_dt = (
                self._calc_nondim_flux_source_derivatives(
                    mesh_data, miu_bar, dmiu_bar_dt
                )
            )
            K = asm(
                _nondim_advection_diffusion_form,
                basis,
                diff_x=diff_x,
                diff_z=diff_z,
                qx=basis.interpolate(conv_x),
                qz=basis.interpolate(conv_z),
            )
            f = asm(_source_form, basis, q=basis.interpolate(phi_bar))
            K, f = self._assemble_supg_with_frozen_tau(
                K,
                f,
                basis,
                conv_x,
                conv_z,
                phi_bar,
                tau_nodal=tau_nodal,
                nondim=True,
            )
            K, f = apply_orifice(K, f)
            if include_jacobian:
                J_extra = asm(
                    _nondim_temperature_flux_source_jacobian_form,
                    basis,
                    dqx_dt=basis.interpolate(dconv_x_dt),
                    dqz_dt=basis.interpolate(dconv_z_dt),
                    dphi_dt=basis.interpolate(dphi_dt),
                    t_current=basis.interpolate(current_bar),
                )
                residual, J = self._apply_dirichlet_to_residual_jacobian(
                    K, f, J_extra, current_bar, dirichlet_nodes, t_bc
                )
            else:
                residual = self._apply_dirichlet_to_residual(
                    K, f, current_bar, dirichlet_nodes, t_bc
                )
                J = None
            norm = self._relative_residual_norm(
                residual, K, current_bar, f, free_nodes
            )
            return residual, J, norm, K, f, miu_nodal, conv_x, conv_z, phi_bar

        tol = (
            self.config.thermal_newton_tol
            if self.config.thermal_newton_tol is not None
            else self.config.tol
        )
        converged = False
        iterations = 0
        line_search_steps = 0
        residual_norm = np.inf
        final_fields = None
        for i in range(self.config.thermal_newton_max_iter):
            iterations = i + 1
            (
                residual,
                J,
                residual_norm,
                K,
                f,
                miu_nodal,
                conv_x,
                conv_z,
                phi_bar,
            ) = residual_system(temperature_bar, include_jacobian=True)
            final_fields = (miu_nodal, conv_x, conv_z, phi_bar)
            if residual_norm < tol:
                converged = True
                break
            delta = spsolve(J, -residual)
            if not np.all(np.isfinite(delta)):
                break
            alpha = float(self.config.thermal_newton_damp)
            accepted = False
            trial = temperature_bar
            trial_norm = residual_norm
            if self.config.thermal_newton_line_search:
                while alpha >= self.config.thermal_newton_min_damp:
                    candidate = np.clip(temperature_bar + alpha * delta, lower, upper)
                    if dirichlet_nodes.size > 0:
                        candidate[dirichlet_nodes] = t_bc[dirichlet_nodes]
                    _, _, candidate_norm, *_ = residual_system(
                        candidate, include_jacobian=False
                    )
                    if np.isfinite(candidate_norm) and candidate_norm < residual_norm:
                        trial = candidate
                        trial_norm = candidate_norm
                        accepted = True
                        break
                    alpha *= 0.5
                    line_search_steps += 1
                if not accepted:
                    break
            else:
                alpha = max(alpha, self.config.thermal_newton_min_damp)
                trial = np.clip(temperature_bar + alpha * delta, lower, upper)
                if dirichlet_nodes.size > 0:
                    trial[dirichlet_nodes] = t_bc[dirichlet_nodes]
                _, _, trial_norm, *_ = residual_system(
                    trial, include_jacobian=False
                )
                if not np.isfinite(trial_norm):
                    break
            temperature_bar = trial
            residual_norm = trial_norm
        else:
            (
                _,
                _,
                residual_norm,
                _,
                _,
                miu_nodal,
                conv_x,
                conv_z,
                phi_bar,
            ) = residual_system(temperature_bar, include_jacobian=False)
            final_fields = (miu_nodal, conv_x, conv_z, phi_bar)

        if final_fields is None:
            miu_nodal, miu_bar, _ = (
                self._nondim_viscosity_from_temperature_with_derivative(
                    temperature_bar, scales
                )
            )
            conv_x, conv_z, phi_bar, _, _, _ = (
                self._calc_nondim_flux_source_derivatives(
                    mesh_data, miu_bar, np.zeros_like(miu_bar)
                )
            )
        else:
            miu_nodal, conv_x, conv_z, phi_bar = final_fields
        t_nodal = scales.temperature_from_nondim(temperature_bar, t_supply)
        qz_bar = conv_z * scales.lr

        return {
            "temperature": t_nodal,
            "temperature_nondim": temperature_bar,
            "t_eff": float(np.mean(t_nodal)),
            "t_eff_nondim": float(np.mean(temperature_bar)),
            "mesh": mesh,
            "n_film_nodes": mesh_data["grid"]["n_film_nodes"],
            "grid": mesh_data["grid"],
            "q_orifice_total": q_orifice_total,
            "q_orifice_net": q_orifice_net,
            "qx_nondim": conv_x,
            "qz_nondim": qz_bar,
            "heat_source_nondim": phi_bar,
            "scales": scales,
            "newton_converged": bool(converged),
            "newton_iterations": int(iterations),
            "newton_residual": float(residual_norm),
            "newton_line_search_steps": int(line_search_steps),
            "viscosity_nodal": miu_nodal,
        }

    def solve(
        self,
        model,
        viscosity: Union[float, np.ndarray],
        mesh_data: Optional[dict] = None,
        orifice_data: Optional[list] = None,
        temperature_prev: Optional[np.ndarray] = None,
        transient: bool = False,
    ) -> Dict[str, np.ndarray]:
        if transient:
            raise NotImplementedError(
                "The nondimensional thermal solver currently supports steady solves only."
            )
        if mesh_data is None:
            mesh_data = self.build_mesh(model)

        mesh = mesh_data["mesh"]
        basis = mesh_data["basis"]
        h_bar = mesh_data["h_nodal"]
        scales: ThermalNondimScales = mesh_data["scales"]
        dp_dx_bar = mesh_data["dp_dx_nodal"]
        dp_dz_bar = mesh_data["dp_dz_nodal"]

        viscosity_input = np.asarray(viscosity, dtype=float)
        if viscosity_input.size == 1:
            miu_nodal = np.full(mesh.p.shape[1], float(viscosity_input), dtype=float)
        elif viscosity_input.size == mesh.p.shape[1]:
            miu_nodal = viscosity_input.reshape(-1).copy()
        else:
            miu_nodal = np.full(
                mesh.p.shape[1], float(np.mean(viscosity_input)), dtype=float
            )
        miu_nodal = np.clip(miu_nodal, self.config.miu_min, self.config.miu_max)
        miu_bar = np.clip(scales.viscosity_to_nondim(miu_nodal), 1e-12, None)

        qx_bar = scales.lambda0 * h_bar - scales.lr**2 * h_bar**3 / miu_bar * dp_dx_bar
        qz_bar = -scales.lr * h_bar**3 / miu_bar * dp_dz_bar
        conv_x = qx_bar
        conv_z = qz_bar / scales.lr

        phi_bar = scales.theta_e * (
            scales.lambda0**2 / (3.0 * scales.lr**2) * miu_bar / h_bar
            + h_bar**3 / miu_bar * (scales.lr**2 * dp_dx_bar**2 + dp_dz_bar**2)
        )

        q_orifice_total = 0.0
        q_orifice_net = 0.0
        if orifice_data:
            q_orifice_total = sum(abs(item[2]) for item in orifice_data)
            q_orifice_net = sum(item[2] for item in orifice_data)

        rho_cv = scales.rho * scales.cp
        diff_x = self.config.k_lub / (rho_cv * scales.flow_scale * scales.r + 1e-30)
        diff_z = diff_x / (scales.lr**2)
        K = asm(
            _nondim_advection_diffusion_form,
            basis,
            diff_x=diff_x,
            diff_z=diff_z,
            qx=basis.interpolate(conv_x),
            qz=basis.interpolate(conv_z),
        )
        f = asm(_source_form, basis, q=basis.interpolate(phi_bar))

        if self.config.supg:
            tx_arr = mesh.p[0]
            tz_arr = mesh.p[1]
            q_mag = np.sqrt(conv_x**2 + conv_z**2)
            dx_mesh = (
                float(np.min(np.diff(np.unique(tx_arr))))
                if len(np.unique(tx_arr)) > 1
                else 1.0
            )
            dz_mesh = (
                float(np.min(np.diff(np.unique(tz_arr))))
                if len(np.unique(tz_arr)) > 1
                else 1.0
            )
            h_elem = np.sqrt(dx_mesh**2 + dz_mesh**2)
            alpha_nd = max(diff_x, diff_z, 1e-30)
            pe_h = q_mag * h_elem / (2.0 * alpha_nd + 1e-30)
            pe_safe = np.clip(pe_h, 1e-10, 500.0)
            xi = 1.0 / np.tanh(pe_safe) - 1.0 / pe_safe
            tau_nodal = xi * h_elem / (2.0 * q_mag + 1e-12)
            K += asm(
                _nondim_supg_stiffness_form,
                basis,
                qx=basis.interpolate(conv_x),
                qz=basis.interpolate(conv_z),
                tau=basis.interpolate(tau_nodal),
            )
            f += asm(
                _nondim_supg_load_form,
                basis,
                qx=basis.interpolate(conv_x),
                qz=basis.interpolate(conv_z),
                tau=basis.interpolate(tau_nodal),
                q=basis.interpolate(phi_bar),
            )

        if orifice_data:
            K = K.tolil()
            tx = mesh.p[0]
            tz = mesh.p[1]
            t_supply_bar = 0.0
            for ox, oz, q_bar in orifice_data:
                if q_bar <= 0:
                    continue
                dist2 = (tx - ox) ** 2 + (tz - oz) ** 2
                j = int(np.argmin(dist2))
                K[j, j] += float(q_bar)
                f[j] += float(q_bar) * t_supply_bar
            K = K.tocsr()

        t_supply = (
            self.config.t_supply
            if self.config.t_supply is not None
            else self.config.t_in
        )
        side_temp = (
            self.config.axial_side_t
            if self.config.axial_side_t is not None
            else t_supply
        )
        side_temp_bar = scales.temperature_to_nondim(side_temp, t_supply)

        tx = mesh.p[0]
        tz = mesh.p[1]
        x_min, x_max = float(tx.min()), float(tx.max())
        z_min, z_max = float(tz.min()), float(tz.max())
        tol_x = (x_max - x_min) * 1e-8
        tol_z = (z_max - z_min) * 1e-8

        inlet_nodes = np.where(np.abs(tx - x_min) < tol_x)[0]
        side_z_min = np.where(np.abs(tz - z_min) < tol_z)[0]
        side_z_max = np.where(np.abs(tz - z_max) < tol_z)[0]

        side_mode = str(self.config.axial_side_bc).lower()
        dirichlet_parts = [inlet_nodes]
        if side_mode == "fixed":
            dirichlet_parts.extend([side_z_min, side_z_max])
        elif side_mode == "adiabatic":
            pass
        elif side_mode == "inflow_fixed":
            if side_z_min.size > 0 and float(np.mean(conv_z[side_z_min])) > 0.0:
                dirichlet_parts.append(side_z_min)
            if side_z_max.size > 0 and float(np.mean(conv_z[side_z_max])) < 0.0:
                dirichlet_parts.append(side_z_max)
        else:
            raise ValueError(
                "axial_side_bc must be one of: 'fixed', 'adiabatic', 'inflow_fixed'"
            )
        dirichlet_nodes = np.unique(np.concatenate(dirichlet_parts)).astype(int)

        t_bc = np.full(K.shape[0], side_temp_bar, dtype=float)
        t_bc[inlet_nodes] = 0.0
        if dirichlet_nodes.size > 0:
            K_bc, f_bc = enforce(K, f, D=dirichlet_nodes, x=t_bc)
        else:
            K_bc, f_bc = K, f
        t_bar = spsolve(K_bc, f_bc)
        t_bar = np.clip(
            t_bar, -5.0 / scales.delta_t, self.config.max_delta_t / scales.delta_t
        )
        t_nodal = scales.temperature_from_nondim(t_bar, t_supply)

        return {
            "temperature": t_nodal,
            "temperature_nondim": t_bar,
            "t_eff": float(np.mean(t_nodal)),
            "t_eff_nondim": float(np.mean(t_bar)),
            "mesh": mesh,
            "n_film_nodes": mesh_data["grid"]["n_film_nodes"],
            "grid": mesh_data["grid"],
            "q_orifice_total": q_orifice_total,
            "q_orifice_net": q_orifice_net,
            "qx_nondim": qx_bar,
            "qz_nondim": qz_bar,
            "heat_source_nondim": phi_bar,
            "scales": scales,
        }


class ThermalPostProcess(BasePostProcess):
    """Post-processing utilities for thermo-hydrodynamic results.

    The post-process data is stored on the structured film grid so pressure,
    temperature and viscosity fields can be rendered with quadrilateral cells.
    """

    _FIELD_MAP = {
        "pressure": "pressure_field",
        "temperature": "temperature_field",
        "viscosity": "viscosity_field_grid",
    }

    def __init__(self, bearing):
        super().__init__()
        self.bearing = bearing

    def update(self, result: Dict[str, object]) -> Dict[str, object]:
        required = [
            "field_x",
            "field_z",
            "pressure_field",
            "temperature_field",
            "viscosity_field_grid",
        ]
        missing = [key for key in required if key not in result]
        if missing:
            raise KeyError(
                "Thermal post-process requires structured fields in result: "
                + ", ".join(missing)
            )

        x_axis = np.asarray(result["field_x"], dtype=float).copy()
        z_axis = np.asarray(result["field_z"], dtype=float).copy()
        x_grid, z_grid = np.meshgrid(x_axis, z_axis, indexing="ij")

        data = {
            "x_axis": x_axis,
            "z_axis": z_axis,
            "x_grid": x_grid,
            "z_grid": z_grid,
            "pressure_field": np.asarray(result["pressure_field"], dtype=float).copy(),
            "temperature_field": np.asarray(
                result["temperature_field"], dtype=float
            ).copy(),
            "viscosity_field_grid": np.asarray(
                result["viscosity_field_grid"], dtype=float
            ).copy(),
            "mesh_type": "quadrilateral",
            "summary": {
                "t_eff": float(result.get("t_eff", np.nan)),
                "viscosity_mean": float(result.get("viscosity", np.nan)),
                "thermal_converged": bool(result.get("thermal_converged", False)),
                "thermal_iterations": int(result.get("thermal_iterations", 0)),
                "thermal_transient": bool(result.get("thermal_transient", False)),
            },
        }
        self.postprocess_result = data
        return data

    def _require_data(self) -> Dict[str, object]:
        if not self.postprocess_result:
            raise RuntimeError(
                "No thermal post-process data available. Run ThermalHydroBearing.output() first."
            )
        return self.postprocess_result

    def _field_key(self, field: str) -> str:
        field_key = self._FIELD_MAP.get(str(field).lower())
        if field_key is None:
            raise ValueError("field must be one of: pressure, temperature, viscosity")
        return field_key

    @property
    def pressure_field(self) -> np.ndarray:
        return self._require_data()["pressure_field"]

    @property
    def temperature_field(self) -> np.ndarray:
        return self._require_data()["temperature_field"]

    @property
    def viscosity_field(self) -> np.ndarray:
        return self._require_data()["viscosity_field_grid"]

    @property
    def x_axis(self) -> np.ndarray:
        return self._require_data()["x_axis"]

    @property
    def z_axis(self) -> np.ndarray:
        return self._require_data()["z_axis"]

    def to_dict(self) -> Dict[str, object]:
        data = self._require_data()
        return {
            key: value.copy()
            if isinstance(value, np.ndarray)
            else dict(value)
            if isinstance(value, dict)
            else value
            for key, value in data.items()
        }

    def save(self, path: Union[str, Path]) -> Path:
        data = self._require_data()
        output_path = Path(path)
        output_path.mkdir(parents=True, exist_ok=True)

        np.savetxt(output_path / "x_axis.csv", data["x_axis"], delimiter=",")
        np.savetxt(output_path / "z_axis.csv", data["z_axis"], delimiter=",")
        np.savetxt(
            output_path / "pressure_field.csv", data["pressure_field"], delimiter=","
        )
        np.savetxt(
            output_path / "temperature_field.csv",
            data["temperature_field"],
            delimiter=",",
        )
        np.savetxt(
            output_path / "viscosity_field.csv",
            data["viscosity_field_grid"],
            delimiter=",",
        )
        np.savez(
            output_path / "thermal_fields.npz",
            x_axis=data["x_axis"],
            z_axis=data["z_axis"],
            pressure_field=data["pressure_field"],
            temperature_field=data["temperature_field"],
            viscosity_field=data["viscosity_field_grid"],
        )
        (output_path / "summary.json").write_text(
            json.dumps(data["summary"], indent=2), encoding="utf-8"
        )
        return output_path

    def _plot_quad_field(
        self,
        field: str,
        *,
        title: str,
        colorbar_label: str,
        cmap: str,
        ax=None,
        show: bool = True,
        save_path: Optional[Union[str, Path]] = None,
    ):
        import matplotlib.pyplot as plt

        data = self._require_data()
        field_key = self._field_key(field)
        if ax is None:
            fig, ax = plt.subplots(figsize=(7, 4.5))
        else:
            fig = ax.figure

        quad = ax.pcolormesh(
            data["x_grid"],
            data["z_grid"],
            data[field_key],
            shading="auto",
            cmap=cmap,
        )
        fig.colorbar(quad, ax=ax, label=colorbar_label)
        ax.set_xlabel("x [m]")
        ax.set_ylabel("z [m]")
        ax.set_title(title)

        if save_path is not None:
            fig.savefig(save_path, dpi=160, bbox_inches="tight")
        if show:
            plt.show()
        return fig, ax

    def plot_pressure_field(self, ax=None, show: bool = True, save_path=None):
        return self._plot_quad_field(
            "pressure",
            title="Pressure Field",
            colorbar_label="Pa",
            cmap="viridis",
            ax=ax,
            show=show,
            save_path=save_path,
        )

    def plot_temperature_field(self, ax=None, show: bool = True, save_path=None):
        return self._plot_quad_field(
            "temperature",
            title="Temperature Field",
            colorbar_label="degC",
            cmap="inferno",
            ax=ax,
            show=show,
            save_path=save_path,
        )

    def plot_viscosity_field(self, ax=None, show: bool = True, save_path=None):
        return self._plot_quad_field(
            "viscosity",
            title="Viscosity Field",
            colorbar_label="Pa.s",
            cmap="coolwarm",
            ax=ax,
            show=show,
            save_path=save_path,
        )

    def plot_line(
        self,
        field: str,
        *,
        axis: str = "x",
        index: Optional[int] = None,
        coordinate: Optional[float] = None,
        ax=None,
        show: bool = True,
        save_path: Optional[Union[str, Path]] = None,
    ):
        import matplotlib.pyplot as plt

        data = self._require_data()
        field_key = self._field_key(field)
        axis = str(axis).lower()
        field_values = np.asarray(data[field_key], dtype=float)

        if ax is None:
            fig, ax = plt.subplots(figsize=(7, 4.5))
        else:
            fig = ax.figure

        if axis == "x":
            fixed_axis = data["z_axis"]
            sweep_axis = data["x_axis"]
            if coordinate is not None:
                index = int(np.argmin(np.abs(fixed_axis - coordinate)))
            if index is None:
                index = fixed_axis.size // 2
            curve = field_values[:, index]
            subtitle = f"z={fixed_axis[index]:.4e} m"
            ax.set_xlabel("x [m]")
        elif axis == "z":
            fixed_axis = data["x_axis"]
            sweep_axis = data["z_axis"]
            if coordinate is not None:
                index = int(np.argmin(np.abs(fixed_axis - coordinate)))
            if index is None:
                index = fixed_axis.size // 2
            curve = field_values[index, :]
            subtitle = f"x={fixed_axis[index]:.4e} m"
            ax.set_xlabel("z [m]")
        else:
            raise ValueError("axis must be 'x' or 'z'")

        ax.plot(sweep_axis, curve, linewidth=1.5)
        ax.set_ylabel(field.capitalize())
        ax.set_title(f"{field.capitalize()} Line ({subtitle})")
        ax.grid(True, alpha=0.3)

        if save_path is not None:
            fig.savefig(save_path, dpi=160, bbox_inches="tight")
        if show:
            plt.show()
        return fig, ax


# ---------------------------------------------------------------------------
# Thermal-hydro bearing wrapper (viscosity field propagation)
# ---------------------------------------------------------------------------


class NodimThermalHydroBearing(BaseCSystem):
    """Thermal-hydro bearing wrapper consuming nondimensional inputs/outputs.

    This is the *base* (nondimensional) implementation of the thermal-pressure
    coupled wrapper, mirroring the design of :class:`NodimFilmModel` ->
    :class:`FilmModel`: the base class only accepts nondimensional inputs and
    runs the nondimensional pressure / thermal solvers.  Conversion of
    dimensional inputs is delegated entirely to :class:`ThermalHydroBearing`,
    which performs the dim->nondim translation at the ``__init__`` boundary
    and then delegates to this base class.

    Replaces the original mean-viscosity approach.  The film model nodes are
    replaced with ``ViscosityFilmNode`` and elements with
    ``ViscosityFilmElem`` so that the Reynolds-equation FE matrices account
    for the spatially varying viscosity.
    """

    def __init__(self, bearing, thermal_config: Optional[ThermalConfig] = None):
        super().__init__()
        self.bearing = bearing
        self.signal.children = [bearing.signal]
        cfg = (
            thermal_config
            if thermal_config is not None
            else ThermalConfig(args_nodim=True)
        )
        self._validate_inputs(bearing, cfg)
        self.config = cfg

        model = self.bearing.main_model
        miu0 = float(
            getattr(model, "_input_args", {}).get(
                "miu", model.args.get("miu0", model.args.get("miu", 1.0))
            )
        )
        self._miu0 = miu0 if self.config.miu0 is None else float(self.config.miu0)
        self._t_ref = (
            self.config.t_in if self.config.t_ref is None else float(self.config.t_ref)
        )

        self._ensure_pressure_backend()
        self._freeze_reference_lambda()
        self._freeze_reference_viscosity()

        # Replace nodes and elements with viscosity-aware versions.
        self._replace_nodes_and_elems()
        self._thermal_grid = _build_film_grid(self.bearing.main_model)

        self.thermal_model = self._build_thermal_model()
        self._last_thermal: Dict[str, object] = {}
        self.post_process = ThermalPostProcess(self)
        self._temperature_prev: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Hooks for dimensional subclass override
    # ------------------------------------------------------------------

    def _validate_inputs(self, bearing, cfg: ThermalConfig) -> None:
        """Reject dimensional inputs.  Overridden by :class:`ThermalHydroBearing`."""
        if not cfg.args_nodim:
            raise TypeError(
                "NodimThermalHydroBearing requires a nondimensional ThermalConfig "
                "(args_nodim=True). Use ThermalHydroBearing for dimensional "
                "inputs."
            )
        film_args = getattr(bearing.main_model, "args", {})
        if not film_args.get("args_nodim", False):
            raise TypeError(
                "NodimThermalHydroBearing requires the wrapped bearing to use a "
                "nondimensional film model (main_model.args['args_nodim']=True). "
                "Use ThermalHydroBearing for dimensional film models."
            )

    def _build_thermal_model(self):
        """Return the thermal solver instance.  Overridden by dim subclass."""
        return SkfemThermalModelNondim(self.config)

    def __getattr__(self, name):
        bearing = self.__dict__.get("bearing")
        if bearing is None:
            raise AttributeError(name)
        return getattr(bearing, name)

    def _ensure_pressure_backend(self):
        """Replace the bearing's film model with the nondim viscosity-aware variant."""
        backend = str(self.config.pressure_backend).lower()
        if backend != "skfem":
            raise ValueError(_PRESSURE_BACKEND_ERROR)

        old_model = self.bearing.main_model
        if isinstance(
            old_model, (ViscositySkfemNewtonFilm, NodimViscositySkfemNewtonFilm)
        ):
            return

        save_switch = getattr(old_model, "save_switch", {"p": False, "h": False})
        x_lim = old_model.args["x_lim"]
        z_lim = old_model.args["z_lim"]
        new_model = NodimViscositySkfemNewtonFilm(
            lambda_value=old_model.args["lambda"],
            lambda0=old_model.args.get("lambda0", old_model.args["lambda"]),
            lr=old_model.args["lr"],
            x0=x_lim[0],
            lx=x_lim[1] - x_lim[0],
            lz=z_lim[1] - z_lim[0],
            nx=old_model.args["nx"],
            nz=old_model.args["nz"],
            miu=old_model.args.get("miu0", old_model.args.get("miu", 1.0)),
            c=old_model.args.get("c", 1.0),
            r=old_model.args.get("r", 1.0),
            l=old_model.args.get("l", 2.0 * old_model.args["lr"]),
            ps=old_model.args.get("ps", 1.0),
            rho=old_model.args.get("rho", 1.0),
            w=old_model.args.get("w"),
            dxt=old_model.args.get("dxt", 0.0),
            dyt=old_model.args.get("dyt", 0.0),
            vf=old_model.args.get("vf", 1.0),
            xct=old_model.args.get("xct", 0.0),
            yct=old_model.args.get("yct", 0.0),
            angle_unit="rad",
            reynold=old_model.args.get("reynold", True),
            error_set=getattr(old_model, "_error_set", 1e-7),
            damp=getattr(old_model, "_damp", 0.8),
            adaptive_damp=getattr(old_model, "_adaptive_damp_config", None),
            save_p=save_switch.get("p", False),
            save_h=save_switch.get("h", False),
            mesh=old_model.mesh,
            filmboundary=old_model.boundary,
            node_manager=old_model.node_manager,
            elem_manager=old_model.elem_manager,
            matrix_process=old_model.matrix_process,
        )
        new_model._results = [
            np.array(r, dtype=float).copy() for r in old_model.results
        ]

        self.bearing.main_model = new_model
        if hasattr(self.bearing, "_output"):
            self.bearing._output = FilmOutput(new_model)
        if hasattr(self.bearing, "signal") and len(self.bearing.signal.children) > 0:
            self.bearing.signal.children[0] = new_model.signal

    def _current_film_input_args(self, model) -> Dict[str, float]:
        input_args = dict(getattr(model, "_input_args", {}))
        hub = getattr(self.bearing, "input_args", None)
        if hub is not None:
            input_args.update(hub.soft_direct(_FILM_MODEL_PARAM_KEYS, warning=False))
        input_args.update(
            {
                key: model._input_args[key]
                for key in _FILM_MODEL_PARAM_KEYS
                if key in model._input_args
            }
        )
        return input_args

    def _freeze_reference_lambda(self):
        model = self.bearing.main_model
        if "lambda0" not in model.args:
            model.args["lambda0"] = float(model.args["lambda"])
        model.args["lambda"] = model.args["lambda0"]
        model.elem_manager.elems_args = model.args

    def _freeze_reference_viscosity(self):
        model = self.bearing.main_model
        model.args["miu0"] = float(self._miu0)
        model.args["miu"] = float(self._miu0)

    # ------------------------------------------------------------------
    # Node / element replacement
    # ------------------------------------------------------------------

    def _replace_nodes_and_elems(self):
        """Swap ``RectFilmNode`` -> ``ViscosityFilmNode`` and
        ``RectFilmElem`` -> ``ViscosityFilmElem`` in-place."""
        model = self.bearing.main_model

        # Build new nodes keeping coords, p, h
        old_nodes = model.node_manager.nodes  # dict {number: node}
        new_nodes = {}
        for num, old in old_nodes.items():
            vn = ViscosityFilmNode(old.coords, p=old.p, h=old.h)
            vn._number = old._number
            vn.freedom = old.freedom
            new_nodes[num] = vn

        # Build new elements, referencing new nodes
        old_elems = model.elem_manager.elems  # dict {number: elem}
        new_elems = {}
        for num, old_e in old_elems.items():
            enodes = {k: new_nodes[n.number] for k, n in old_e.nodes.items()}
            ve = ViscosityFilmElem.__new__(ViscosityFilmElem)
            # Replicate BaseElem init logic
            ve._nodes = enodes
            ve._nodes_number = len(enodes)
            ve._number = old_e._number
            ve._args = old_e._args
            ve._mapping = old_e._mapping
            ve._matrixs = {}
            ve._rights = {}
            ve.lx = old_e.lx
            ve.lz = old_e.lz
            ve.args = old_e.args
            new_elems[num] = ve

        # Replace in managers
        model.node_manager._nodes = new_nodes
        model.elem_manager._elems = new_elems

    # ------------------------------------------------------------------
    # Viscosity helpers
    # ------------------------------------------------------------------

    def _viscosity_from_temperature(
        self, temperature: Union[float, np.ndarray]
    ) -> Union[float, np.ndarray]:
        miu = self._miu0 * np.exp(-self.config.beta * (temperature - self._t_ref))
        return np.clip(miu, self.config.miu_min, self.config.miu_max)

    def _viscosity_from_temperature_nondim(
        self, temperature_nondim: Union[float, np.ndarray], scales: ThermalNondimScales
    ) -> Union[float, np.ndarray]:
        miu = scales.viscosity_from_temperature_nondim(temperature_nondim)
        return np.clip(miu, self.config.miu_min, self.config.miu_max)

    def _map_thermal_to_film(
        self, thermal_mesh, t_nodal: np.ndarray, mesh_data: Optional[dict] = None
    ) -> np.ndarray:
        """Map temperature from the thermal triangular mesh to film nodes.

        Returns an array of temperatures aligned with the film model node
        ordering.
        """
        if mesh_data is not None and "film_to_thermal_idx" in mesh_data:
            return t_nodal[mesh_data["film_to_thermal_idx"]]

        model = self.bearing.main_model
        film_nodes = list(model.nodes.values())
        r = model.args["r"]
        l_half = model.args["l"] / 2.0
        tx = thermal_mesh.p[0]
        tz = thermal_mesh.p[1]

        t_film = np.empty(len(film_nodes), dtype=float)
        for i, node in enumerate(film_nodes):
            x_dim = node.coords[0] * r
            z_dim = node.coords[1] * l_half
            dist = (tx - x_dim) ** 2 + (tz - z_dim) ** 2
            t_film[i] = t_nodal[np.argmin(dist)]
        return t_film

    def _apply_miu_ratio_to_nodes(self, miu_field: np.ndarray):
        """Write per-node viscosity ratio (miu / miu0) to film nodes."""
        model = self.bearing.main_model
        for i, node in enumerate(model.nodes.values()):
            node_miu = max(float(miu_field[i]), _MIU_NUMERIC_FLOOR)
            node.miu_ratio = node_miu / self._miu0

    def _relaxed_miu_update(
        self, miu_field: np.ndarray, miu_target: np.ndarray, relax: float
    ):
        """Return the relaxed viscosity field and its relative update norm."""
        if self.config.miu_update == "log":
            old_safe = np.maximum(miu_field, _MIU_NUMERIC_FLOOR)
            target_safe = np.maximum(miu_target, _MIU_NUMERIC_FLOOR)
            step = float(relax) * (np.log(target_safe) - np.log(old_safe))
            if self.config.miu_update_max_ratio is not None:
                cap = float(np.log(self.config.miu_update_max_ratio))
                step = np.clip(step, -cap, cap)
            miu_new = np.exp(np.log(old_safe) + step)
            miu_new = np.minimum(miu_new, self.config.miu_max)
            if self.config.miu_min > 0.0:
                miu_new = np.maximum(miu_new, self.config.miu_min)
        else:
            miu_new = (1.0 - relax) * miu_field + relax * miu_target
        rel_err = float(
            np.max(np.abs(miu_new - miu_field))
            / max(float(np.max(np.abs(miu_field))), _MIU_NUMERIC_FLOOR)
        )
        return miu_new, rel_err

    def _map_miu_to_thermal(
        self,
        miu_field: np.ndarray,
        grid: dict,
        thermal_mesh,
        mesh_data: Optional[dict] = None,
    ) -> np.ndarray:
        """Map film-node viscosity field to thermal mesh nodes."""
        if mesh_data is not None and "thermal_to_film_idx" in mesh_data:
            return miu_field[mesh_data["thermal_to_film_idx"]]

        model = self.bearing.main_model
        r = model.args["r"]
        l_half = model.args["l"] / 2.0

        film_xs_dim = grid["film_xs"] * r
        film_zs_dim = grid["film_zs"] * l_half

        tx = thermal_mesh.p[0]
        tz = thermal_mesh.p[1]
        miu_thermal = np.empty(tx.size, dtype=float)
        for j in range(tx.size):
            dist = (film_xs_dim - tx[j]) ** 2 + (film_zs_dim - tz[j]) ** 2
            miu_thermal[j] = miu_field[np.argmin(dist)]
        return miu_thermal

    def _get_thermal_viscosity(
        self, miu_field: np.ndarray, miu_mean: float, mesh_data: dict
    ) -> Union[float, np.ndarray]:
        """Return viscosity input for the thermal solver based on coupling mode."""
        if self.config.coupling == "full":
            return self._map_miu_to_thermal(
                miu_field, mesh_data["grid"], mesh_data["mesh"], mesh_data
            )
        return miu_mean

    def _sync_reference_film_args(self):
        """Refresh transformed film args while keeping Reynolds scaling at mu0."""
        model = self.bearing.main_model
        model.args["miu0"] = float(self._miu0)
        model.args["miu"] = float(self._miu0)
        model.args["lambda"] = float(model.args.get("lambda0", model.args["lambda"]))
        model.elem_manager.elems_args = model.args

    def _build_thermal_config_readonly(self, scales: ThermalNondimScales) -> dict:
        return {
            "args_nodim": bool(self.config.args_nodim),
            "beta": float(self.config.beta),
            "beta_nondim": float(scales.beta_nondim),
            "delta_t": float(scales.delta_t),
            "delta_t_scale": None
            if self.config.delta_t_scale is None
            else float(self.config.delta_t_scale),
            "t_ref": float(self._t_ref),
            "t_ref_nondim": float(scales.t_ref_nondim),
            "t_supply": float(scales.t_supply),
            "miu0": float(self._miu0),
        }

    def _build_structured_result_fields(
        self,
        model,
        t_film: np.ndarray,
        miu_field: np.ndarray,
        mesh_data: dict,
        *,
        t_film_nondim: Optional[np.ndarray] = None,
        scales: Optional[ThermalNondimScales] = None,
    ) -> Dict[str, np.ndarray]:
        grid = mesh_data["grid"]
        x_dim = np.asarray(grid["x_dim"], dtype=float)
        z_dim = np.asarray(grid["z_dim"], dtype=float)

        pressure_field = np.zeros((x_dim.size, z_dim.size), dtype=float)
        temperature_field = np.zeros_like(pressure_field)
        viscosity_field_grid = np.zeros_like(pressure_field)
        temperature_nondim_field = np.zeros_like(pressure_field)

        p_nodal = (
            np.array([node.p for node in model.nodes.values()], dtype=float)
            * mesh_data["ps"]
        )
        pressure_field[grid["ix"], grid["iz"]] = p_nodal
        temperature_field[grid["ix"], grid["iz"]] = np.asarray(t_film, dtype=float)
        viscosity_field_grid[grid["ix"], grid["iz"]] = np.asarray(
            miu_field, dtype=float
        )

        fields = {
            "field_x": x_dim,
            "field_z": z_dim,
            "pressure_field": pressure_field,
            "temperature_field": temperature_field,
            "viscosity_field_grid": viscosity_field_grid,
        }
        if scales is not None:
            fields.update(
                {
                    "pressure_nondim_field": pressure_field / float(scales.ps),
                    "viscosity_ratio_field": viscosity_field_grid / float(scales.miu0),
                    "field_x_nondim": x_dim / float(scales.r),
                    "field_z_nondim": z_dim / (float(scales.l) / 2.0),
                }
            )
            if t_film_nondim is None:
                t_supply = (
                    self.config.t_supply
                    if self.config.t_supply is not None
                    else self.config.t_in
                )
                t_film_nondim = scales.temperature_to_nondim(t_film, t_supply)
            temperature_nondim_field[grid["ix"], grid["iz"]] = np.asarray(
                t_film_nondim, dtype=float
            )
            fields["temperature_nondim_field"] = temperature_nondim_field
        return fields

    def _collect_orifice_info(self):
        """Scan bearing.simple_models for orifices and return dimensional flow data.

        Returns a list of (x_dim, z_dim, Q_vol) tuples where:
        - x_dim, z_dim: orifice position in metres
        - Q_vol: volumetric flow rate in m³/s (positive = injection)

        Returns an empty list if no orifices are present.
        """
        model = self.bearing.main_model
        result = []
        for sm in self.bearing.simple_models:
            if hasattr(sm, "flow_info"):
                result.extend(sm.flow_info(model)["flow"])

        return result

    # ------------------------------------------------------------------
    # Public interface  (delegates to bearing)
    # ------------------------------------------------------------------

    def init(self, *args, **kwargs):
        self.bearing.init(*args, **kwargs)
        # reset all viscosity ratios to 1.0
        for node in self.bearing.main_model.nodes.values():
            node.miu_ratio = 1.0
        self._last_thermal = {}
        self._temperature_prev = None

    def input(self, *args, **kwargs):
        self.bearing.input(*args, **kwargs)

    def calc_is_finished(self, *args, **kwargs):
        return self.bearing.calc_is_finished(*args, **kwargs)

    def _solve_coupled(self, *args, transient=False, temperature_prev=None, **kwargs):
        if self.config.heat_partition_steps is not None:
            return self._solve_coupled_continuation(
                *args,
                transient=transient,
                temperature_prev=temperature_prev,
                **kwargs,
            )
        return self._solve_coupled_for_method(
            *args,
            transient=transient,
            temperature_prev=temperature_prev,
            **kwargs,
        )

    def _solve_coupled_for_method(
        self,
        *args,
        transient=False,
        temperature_prev=None,
        initial_miu_field: Optional[np.ndarray] = None,
        initial_temperature: Optional[np.ndarray] = None,
        **kwargs,
    ):
        iter_method = self.config.iter_method
        if iter_method == "newton":
            return self._solve_coupled_newton(
                *args,
                transient=transient,
                temperature_prev=temperature_prev,
                solver_used="newton",
                initial_miu_field=initial_miu_field,
                initial_temperature=initial_temperature,
                **kwargs,
            )
        if iter_method == "direct_then_newton":
            fixed_result = self._solve_coupled_fixed_point(
                *args,
                transient=transient,
                temperature_prev=temperature_prev,
                solver_used="direct",
                initial_miu_field=initial_miu_field,
                **kwargs,
            )
            if fixed_result.get("thermal_converged", False):
                return fixed_result
            return self._solve_coupled_newton(
                *args,
                transient=transient,
                temperature_prev=temperature_prev,
                solver_used="direct_then_newton",
                initial_miu_field=np.asarray(
                    fixed_result["viscosity_field"], dtype=float
                ),
                initial_temperature=np.asarray(
                    fixed_result["temperature"], dtype=float
                ),
                **kwargs,
            )
        return self._solve_coupled_fixed_point(
            *args,
            transient=transient,
            temperature_prev=temperature_prev,
            solver_used="direct",
            initial_miu_field=initial_miu_field,
            **kwargs,
        )

    def _solve_coupled_continuation(
        self, *args, transient=False, temperature_prev=None, **kwargs
    ):
        original_heat_partition = float(self.config.heat_partition)
        schedule = tuple(float(value) for value in self.config.heat_partition_steps)
        initial_miu_field = None
        initial_temperature = None
        completed_steps = []
        result = None
        try:
            for heat_partition in schedule:
                self.config.heat_partition = float(heat_partition)
                result = self._solve_coupled_for_method(
                    *args,
                    transient=transient,
                    temperature_prev=temperature_prev,
                    initial_miu_field=initial_miu_field,
                    initial_temperature=initial_temperature,
                    **kwargs,
                )
                completed_steps.append(float(heat_partition))
                initial_miu_field = np.asarray(
                    result["viscosity_field"], dtype=float
                ).copy()
                initial_temperature = np.asarray(
                    result["temperature"], dtype=float
                ).copy()
                if not bool(result.get("thermal_converged", False)):
                    break
        finally:
            self.config.heat_partition = original_heat_partition

        if result is None:
            raise RuntimeError("heat_partition_steps produced no thermal solve")
        result["thermal_continuation_steps"] = completed_steps
        result["thermal_continuation_target"] = original_heat_partition
        self._last_thermal["continuation_steps"] = completed_steps
        self._last_thermal["continuation_target"] = original_heat_partition
        return result

    def _thermal_target_from_solution(self, thermal: dict, mesh_data: dict):
        t_film = self._map_thermal_to_film(
            thermal["mesh"], thermal["temperature"], mesh_data
        )
        t_film_nondim = None
        if "temperature_nondim" in thermal and "scales" in thermal:
            t_film_nondim = self._map_thermal_to_film(
                thermal["mesh"], thermal["temperature_nondim"], mesh_data
            )
            miu_target = self._viscosity_from_temperature_nondim(
                t_film_nondim, thermal["scales"]
            )
        else:
            miu_target = self._viscosity_from_temperature(t_film)
        return t_film, t_film_nondim, miu_target

    def _build_coupled_result(
        self,
        hydro: dict,
        thermal: dict,
        mesh_data: dict,
        t_film: np.ndarray,
        t_film_nondim: Optional[np.ndarray],
        miu_field: np.ndarray,
        miu_mean: float,
        relax_controller: AdaptiveDampController,
        *,
        converged: bool,
        n_iter: int,
        transient: bool,
        solver_used: str,
        newton_iterations: int = 0,
        newton_residual: float = np.nan,
        newton_line_search_steps: int = 0,
    ):
        model = self.bearing.main_model
        scales = thermal.get("scales")
        self._last_thermal = {
            "t_eff": float(thermal["t_eff"]),
            "viscosity": float(miu_mean),
            "converged": bool(converged),
            "iterations": int(n_iter),
            "viscosity_field": miu_field.copy(),
            "relax": float(relax_controller.value),
            "relax_history": list(relax_controller.history),
            "adaptive_damp_enabled": bool(relax_controller.enabled),
            "solver_used": str(solver_used),
            "newton_iterations": int(newton_iterations),
            "newton_residual": float(newton_residual),
            "newton_line_search_steps": int(newton_line_search_steps),
        }

        result = dict(hydro)
        result.update(
            {
                "t_eff": self._last_thermal["t_eff"],
                "viscosity": self._last_thermal["viscosity"],
                "thermal_converged": self._last_thermal["converged"],
                "thermal_iterations": self._last_thermal["iterations"],
                "thermal_relax": self._last_thermal["relax"],
                "thermal_relax_history": self._last_thermal["relax_history"],
                "thermal_adaptive_damp_enabled": self._last_thermal[
                    "adaptive_damp_enabled"
                ],
                "thermal_solver_used": self._last_thermal["solver_used"],
                "thermal_newton_iterations": self._last_thermal[
                    "newton_iterations"
                ],
                "thermal_newton_residual": self._last_thermal["newton_residual"],
                "thermal_newton_line_search_steps": self._last_thermal[
                    "newton_line_search_steps"
                ],
                "temperature": thermal["temperature"],
                "temperature_film": t_film,
                "temperature_x": thermal["mesh"].p[0].copy(),
                "temperature_z": thermal["mesh"].p[1].copy(),
                "viscosity_field": miu_field.copy(),
                "q_orifice_total": thermal.get("q_orifice_total", 0.0),
                "thermal_transient": bool(transient),
            }
        )
        if "temperature_nondim" in thermal:
            result.update(
                {
                    "temperature_nondim": thermal["temperature_nondim"],
                    "temperature_film_nondim": t_film_nondim,
                    "t_eff_nondim": thermal["t_eff_nondim"],
                    "qx_nondim": thermal["qx_nondim"],
                    "qz_nondim": thermal["qz_nondim"],
                    "heat_source_nondim": thermal["heat_source_nondim"],
                    "beta_nondim": thermal["scales"].beta_nondim,
                    "t_ref_nondim": thermal["scales"].t_ref_nondim,
                    "delta_t": thermal["scales"].delta_t,
                    "miu0": self._miu0,
                    "thermal_config_readonly": self._build_thermal_config_readonly(
                        thermal["scales"]
                    ),
                    "thermal_scales": thermal["scales"],
                }
            )
        result.update(
            self._build_structured_result_fields(
                model,
                t_film,
                miu_field,
                mesh_data,
                t_film_nondim=t_film_nondim,
                scales=scales,
            )
        )
        self.post_process.update(result)
        return result

    def _solve_coupled_fixed_point(
        self,
        *args,
        transient=False,
        temperature_prev=None,
        solver_used="direct",
        initial_miu_field: Optional[np.ndarray] = None,
        **kwargs,
    ):
        model = self.bearing.main_model
        n_nodes = len(model.nodes)

        # Initial viscosity field = uniform reference
        if initial_miu_field is None or np.asarray(initial_miu_field).size != n_nodes:
            miu_field = np.full(n_nodes, self._miu0, dtype=float)
        else:
            miu_field = np.asarray(initial_miu_field, dtype=float).reshape(-1).copy()
        relax_controller = AdaptiveDampController(
            self.config.relax, self.config.adaptive_damp
        )
        converged = False
        n_iter = 0

        # Build mesh once per coupled solve from the current film geometry.
        # Rotor eccentricity and tank updates change node.h through input(), so
        # reusing the grid captured at wrapper construction would make the
        # energy equation use stale film thickness.
        self._thermal_grid = _build_film_grid(model)
        mesh_data = self.thermal_model.build_mesh(model, self._thermal_grid)

        for i in range(self.config.max_iter):
            n_iter = i + 1
            # Apply viscosity field to nodes and keep reference lambda fixed.
            self._apply_miu_ratio_to_nodes(miu_field)
            miu_mean = float(np.mean(miu_field))
            self._sync_reference_film_args()

            # Solve hydrodynamics
            self.bearing.output(*args, **kwargs)

            # Collect orifice flow data (available after hydro solve)
            orifice_data = self._collect_orifice_info()

            # Update pressure gradients only (no mesh rebuild)
            self.thermal_model.update_pressure_gradients(model, mesh_data)
            miu_visc = self._get_thermal_viscosity(miu_field, miu_mean, mesh_data)
            thermal = self.thermal_model.solve(
                model,
                miu_visc,
                mesh_data,
                orifice_data,
                temperature_prev=temperature_prev,
                transient=transient,
            )

            # Map temperature back to film nodes
            _, _, miu_target = self._thermal_target_from_solution(thermal, mesh_data)

            # Relax
            relax = relax_controller.value
            miu_new, rel_err = self._relaxed_miu_update(
                miu_field, miu_target, relax
            )
            miu_field = miu_new
            relax_controller.update(rel_err)

            if rel_err < self.config.tol:
                converged = True
                break

        # Final solve with converged viscosity field
        self._apply_miu_ratio_to_nodes(miu_field)
        miu_mean = float(np.mean(miu_field))
        self._sync_reference_film_args()
        hydro = self.bearing.output(*args, **kwargs)
        orifice_data = self._collect_orifice_info()
        self.thermal_model.update_pressure_gradients(model, mesh_data)
        miu_visc = self._get_thermal_viscosity(miu_field, miu_mean, mesh_data)
        thermal = self.thermal_model.solve(
            model,
            miu_visc,
            mesh_data,
            orifice_data,
            temperature_prev=temperature_prev,
            transient=transient,
        )
        t_film, t_film_nondim, _ = self._thermal_target_from_solution(
            thermal, mesh_data
        )
        return self._build_coupled_result(
            hydro,
            thermal,
            mesh_data,
            t_film,
            t_film_nondim,
            miu_field,
            miu_mean,
            relax_controller,
            converged=converged,
            n_iter=n_iter,
            transient=transient,
            solver_used=solver_used,
        )

    def _solve_coupled_newton(
        self,
        *args,
        transient=False,
        temperature_prev=None,
        solver_used="newton",
        initial_miu_field: Optional[np.ndarray] = None,
        initial_temperature: Optional[np.ndarray] = None,
        **kwargs,
    ):
        model = self.bearing.main_model
        n_nodes = len(model.nodes)
        if initial_miu_field is None or np.asarray(initial_miu_field).size != n_nodes:
            miu_field = np.full(n_nodes, self._miu0, dtype=float)
        else:
            miu_field = np.asarray(initial_miu_field, dtype=float).reshape(-1).copy()
        relax_controller = AdaptiveDampController(
            self.config.relax, self.config.adaptive_damp
        )
        converged = False
        n_iter = 0
        temperature_guess = (
            None
            if initial_temperature is None
            else np.asarray(initial_temperature, dtype=float).reshape(-1).copy()
        )
        newton_iterations_total = 0
        newton_line_search_steps_total = 0
        newton_residual = np.nan

        self._thermal_grid = _build_film_grid(model)
        mesh_data = self.thermal_model.build_mesh(model, self._thermal_grid)

        for i in range(self.config.max_iter):
            n_iter = i + 1
            self._apply_miu_ratio_to_nodes(miu_field)
            miu_mean = float(np.mean(miu_field))
            self._sync_reference_film_args()
            hydro = self.bearing.output(*args, **kwargs)
            orifice_data = self._collect_orifice_info()
            self.thermal_model.update_pressure_gradients(model, mesh_data)
            miu_visc = self._get_thermal_viscosity(miu_field, miu_mean, mesh_data)
            thermal = self.thermal_model.solve_segregated_newton(
                model,
                miu_visc,
                mesh_data,
                orifice_data,
                temperature_prev=temperature_prev,
                transient=transient,
                temperature_initial=temperature_guess,
                miu0=self._miu0,
                t_ref=self._t_ref,
            )
            temperature_guess = np.asarray(thermal["temperature"], dtype=float).copy()
            newton_iterations_total += int(thermal.get("newton_iterations", 0))
            newton_line_search_steps_total += int(
                thermal.get("newton_line_search_steps", 0)
            )
            newton_residual = float(thermal.get("newton_residual", np.nan))
            subsolve_converged = bool(thermal.get("newton_converged", False))
            subsolve_iterations = int(thermal.get("newton_iterations", 0))
            subsolve_hit_limit = (
                subsolve_iterations >= int(self.config.thermal_newton_max_iter)
            )
            hard_residual = max(1e-2, 100.0 * float(self.config.tol))
            hard_failure = (not subsolve_converged) and (
                (not np.isfinite(newton_residual))
                or (subsolve_iterations < int(self.config.thermal_newton_max_iter))
                or (subsolve_hit_limit and newton_residual > hard_residual)
            )
            if hard_failure:
                t_film, t_film_nondim, _ = self._thermal_target_from_solution(
                    thermal, mesh_data
                )
                return self._build_coupled_result(
                    hydro,
                    thermal,
                    mesh_data,
                    t_film,
                    t_film_nondim,
                    miu_field,
                    miu_mean,
                    relax_controller,
                    converged=False,
                    n_iter=n_iter,
                    transient=transient,
                    solver_used=solver_used,
                    newton_iterations=newton_iterations_total,
                    newton_residual=newton_residual,
                    newton_line_search_steps=newton_line_search_steps_total,
                )

            _, _, miu_target = self._thermal_target_from_solution(thermal, mesh_data)

            relax = relax_controller.value
            miu_new, rel_err = self._relaxed_miu_update(
                miu_field, miu_target, relax
            )
            miu_field = miu_new
            relax_controller.update(rel_err)
            if subsolve_converged and rel_err < self.config.tol:
                converged = True
                break

        self._apply_miu_ratio_to_nodes(miu_field)
        miu_mean = float(np.mean(miu_field))
        self._sync_reference_film_args()
        hydro = self.bearing.output(*args, **kwargs)
        orifice_data = self._collect_orifice_info()
        self.thermal_model.update_pressure_gradients(model, mesh_data)
        miu_visc = self._get_thermal_viscosity(miu_field, miu_mean, mesh_data)
        thermal = self.thermal_model.solve_segregated_newton(
            model,
            miu_visc,
            mesh_data,
            orifice_data,
            temperature_prev=temperature_prev,
            transient=transient,
            temperature_initial=temperature_guess,
            miu0=self._miu0,
            t_ref=self._t_ref,
        )
        newton_iterations_total += int(thermal.get("newton_iterations", 0))
        newton_line_search_steps_total += int(
            thermal.get("newton_line_search_steps", 0)
        )
        newton_residual = float(thermal.get("newton_residual", np.nan))
        t_film, t_film_nondim, _ = self._thermal_target_from_solution(
            thermal, mesh_data
        )
        return self._build_coupled_result(
            hydro,
            thermal,
            mesh_data,
            t_film,
            t_film_nondim,
            miu_field,
            miu_mean,
            relax_controller,
            converged=bool(converged and thermal.get("newton_converged", False)),
            n_iter=n_iter,
            transient=transient,
            solver_used=solver_used,
            newton_iterations=newton_iterations_total,
            newton_residual=newton_residual,
            newton_line_search_steps=newton_line_search_steps_total,
        )

    def initialize_thermal_state(self, *args, **kwargs):
        """Solve a steady thermal field and store it as the transient initial state."""
        result = self._solve_coupled(
            *args, transient=False, temperature_prev=None, **kwargs
        )
        self._temperature_prev = np.asarray(result["temperature"], dtype=float).copy()
        return result

    def output(self, *args, nodim: Optional[bool] = None, **kwargs):
        if nodim is None:
            nodim = True
        kwargs["nodim"] = nodim

        if not self.config.transient_enabled:
            return self._solve_coupled(
                *args, transient=False, temperature_prev=None, **kwargs
            )

        if self.config.dt is None or self.config.dt <= 0:
            raise ValueError("Transient thermal output requires ThermalConfig.dt > 0")

        if self._temperature_prev is None:
            return self.initialize_thermal_state(*args, **kwargs)

        result = self._solve_coupled(
            *args,
            transient=True,
            temperature_prev=self._temperature_prev,
            **kwargs,
        )
        self._temperature_prev = np.asarray(result["temperature"], dtype=float).copy()
        return result

    @property
    def thermal_state(self):
        return dict(self._last_thermal)

    def calc_capacity(self, *args, **kwargs):
        return self.bearing.calc_capacity(*args, **kwargs)

    def calc_friction(self, *args, **kwargs):
        return self.bearing.calc_friction(*args, **kwargs)

    def save(self, *args, **kwargs):
        return self.bearing.save(*args, **kwargs)


class ThermalHydroBearing(NodimThermalHydroBearing):
    """Dimensional thermal-hydro bearing wrapper.

    Mirrors the :class:`FilmModel` -> :class:`NodimFilmModel` design: this
    dimensional subclass owns the dim<->nondim translation and delegates the
    actual coupled solve to :class:`NodimThermalHydroBearing` via overrides
    on the validation, pressure-backend, viscosity-sync and thermal-solver
    selection hooks.
    """

    # ------------------------------------------------------------------
    # Validation: accept dimensional inputs only
    # ------------------------------------------------------------------

    def _validate_inputs(self, bearing, cfg: ThermalConfig) -> None:
        if cfg.args_nodim:
            raise TypeError(
                "ThermalHydroBearing requires a dimensional ThermalConfig "
                "(args_nodim=False). Use NodimThermalHydroBearing for "
                "nondimensional inputs."
            )
        film_args = getattr(bearing.main_model, "args", {})
        if film_args.get("args_nodim", False):
            raise TypeError(
                "ThermalHydroBearing requires the wrapped bearing to use a "
                "dimensional film model. Use NodimThermalHydroBearing for "
                "nondimensional film models."
            )

    # ------------------------------------------------------------------
    # Solver selection: use dimensional thermal solver
    # ------------------------------------------------------------------

    def _build_thermal_model(self):
        return SkfemThermalModel(self.config)

    # ------------------------------------------------------------------
    # Pressure backend: keep dimensional viscosity-aware skfem film model
    # ------------------------------------------------------------------

    def _ensure_pressure_backend(self):
        backend = str(self.config.pressure_backend).lower()
        if backend != "skfem":
            raise ValueError(_PRESSURE_BACKEND_ERROR)

        old_model = self.bearing.main_model
        if isinstance(
            old_model, (ViscositySkfemNewtonFilm, NodimViscositySkfemNewtonFilm)
        ):
            return

        save_switch = getattr(old_model, "save_switch", {"p": False, "h": False})
        input_args = self._current_film_input_args(old_model)
        model_kwargs = {key: input_args[key] for key in _FILM_MODEL_PARAM_KEYS}
        new_model = ViscositySkfemNewtonFilm(
            **model_kwargs,
            reynold=old_model.args.get("reynold", True),
            error_set=getattr(old_model, "_error_set", 1e-7),
            damp=getattr(old_model, "_damp", 0.8),
            adaptive_damp=getattr(old_model, "_adaptive_damp_config", None),
            save_p=save_switch.get("p", False),
            save_h=save_switch.get("h", False),
            mesh=old_model.mesh,
            filmboundary=old_model.boundary,
            node_manager=old_model.node_manager,
            elem_manager=old_model.elem_manager,
            matrix_process=old_model.matrix_process,
        )
        new_model._results = [
            np.array(r, dtype=float).copy() for r in old_model.results
        ]

        self.bearing.main_model = new_model
        if hasattr(self.bearing, "_output"):
            self.bearing._output = FilmOutput(new_model)
        if hasattr(self.bearing, "signal") and len(self.bearing.signal.children) > 0:
            self.bearing.signal.children[0] = new_model.signal

    # ------------------------------------------------------------------
    # Viscosity sync: rebuild dim->nondim film args via film_args_trans
    # ------------------------------------------------------------------

    def _sync_reference_film_args(self):
        model = self.bearing.main_model
        input_args = dict(model._input_args)
        input_args["miu"] = float(self._miu0)
        input_args["dxt"] = float(model.args["dxt"])
        input_args["dyt"] = float(model.args["dyt"])

        _, nd_args = _transform_film_args(input_args)

        for k, v in input_args.items():
            model._input_args[k] = v
        for k, v in nd_args.items():
            model.args[k] = v
        lambda0 = float(model.args.get("lambda0", nd_args["lambda0"]))
        model.args["miu0"] = float(self._miu0)
        model.args["miu"] = float(self._miu0)
        model.args["lambda0"] = lambda0
        model.args["lambda"] = lambda0
        model.elem_manager.elems_args = model.args

    # ------------------------------------------------------------------
    # Default to dimensional output unless caller asks for nondim explicitly
    # ------------------------------------------------------------------

    def output(self, *args, nodim: Optional[bool] = None, **kwargs):
        if nodim is None:
            nodim = False
        return super().output(*args, nodim=nodim, **kwargs)
