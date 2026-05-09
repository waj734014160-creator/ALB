# coding: utf-8
import numpy as np
from scipy.sparse.linalg import spsolve
from skfem import BilinearForm, LinearForm, asm
from skfem.helpers import grad

from ALB.base import BaseSimpleModel, ElemManager, MatrixProcess, NodeManager
from ALB.config import GasConfig
from ALB.film import (
    FilmBoundary,
    FilmSystem,
    RectFilmElem,
    RectFilmNode,
    SkfemNewtonFilm,
    ThicknessModel,
)
from ALB.mesh import Mesh

# no validation！！！


def _paper_texture_distribution(texture_type: int) -> dict:
    distributions = {
        1: {
            "theta_cells": 12,
            "z_cells": 3,
            "theta_ratio": 0.4,
            "z_ratio": 2.0 / 3.0,
        },
        2: {
            "theta_cells": 24,
            "z_cells": 6,
            "theta_ratio": 0.4,
            "z_ratio": 2.0 / 3.0,
        },
        3: {
            "theta_cells": 48,
            "z_cells": 12,
            "theta_ratio": 0.4,
            "z_ratio": 2.0 / 3.0,
        },
    }
    if texture_type not in distributions:
        raise ValueError("Unsupported texture_type, expected one of: 1, 2, 3")
    return distributions[texture_type]


class GasFoilTextureCoupling(BaseSimpleModel):
    """Apply textured top-foil geometry and spring-backed foil deformation."""

    def __init__(self, gas_config: GasConfig):
        """
        Initialize the gas foil-texture coupling model.

        :param gas_config: GasConfig, gas bearing configuration object
        """
        super().__init__()
        self.config = gas_config
        self._last_deformation = None
        self._texture_delta = None
        self._latest_pressure = None
        self._latest_total_h = None
        self._error = np.inf

    def init(self):
        """
        Reset all internal state to initial values.

        Clears all internal cache fields such as deformation, texture delta,
        pressure, and film thickness. Resets the error flag to infinity,
        returning the model to an unsolved initial state.

        :return: None
        """
        self._last_deformation = None
        self._texture_delta = None
        self._latest_pressure = None
        self._latest_total_h = None
        self._error = np.inf

    def input(self, *args, **kwargs):
        """
        Set input parameters (no external input needed for this model).

        :param *args: optional positional arguments
        :param **kwargs: optional keyword arguments
        :return: None
        """
        return None

    def _build_texture_delta(self, model) -> np.ndarray:
        """
        Build the nodal texture depth increment field from configured texture parameters.

        :param model: FilmModel, the main model object used to obtain nodal coordinates
        :return: np.ndarray, texture depth increment array of shape (num_nodes,)
        """
        num_nodes = model.node_manager.non
        delta = np.zeros(num_nodes, dtype=float)
        if not self.config.texture_enabled:
            return delta

        texture_depth = self.config.texture_depth_abs / self.config.c
        if texture_depth <= 0:
            return delta

        distribution = _paper_texture_distribution(self.config.texture_type)
        theta_cells = distribution["theta_cells"]
        z_cells = distribution["z_cells"]
        active_theta = int(np.round(theta_cells * self.config.texture_circ_fraction))
        active_z = int(np.round(z_cells * self.config.texture_axial_fraction))
        if active_theta <= 0 or active_z <= 0:
            return delta

        theta_start = min(self.config.texture_start_theta_index - 1, theta_cells - 1)
        z_start = min(self.config.texture_start_z_index - 1, z_cells - 1)
        active_theta = min(active_theta, theta_cells - theta_start)
        active_z = min(active_z, z_cells - z_start)
        if active_theta <= 0 or active_z <= 0:
            return delta

        theta_min, theta_max = model.args["x_lim"]
        z_min, z_max = model.args["z_lim"]
        theta_cell_size = (theta_max - theta_min) / theta_cells
        z_cell_size = (z_max - z_min) / z_cells
        theta_texture_half = 0.5 * distribution["theta_ratio"] * theta_cell_size
        z_texture_half = 0.5 * distribution["z_ratio"] * z_cell_size

        theta_centers = theta_min + (np.arange(theta_cells) + 0.5) * theta_cell_size
        z_centers = z_min + (np.arange(z_cells) + 0.5) * z_cell_size

        for index in range(num_nodes):
            node = model.node_manager.nodes[index]
            theta = float(node.coords[0])
            z = float(node.coords[1])

            for i_theta in range(theta_start, theta_start + active_theta):
                if abs(theta - theta_centers[i_theta]) > theta_texture_half:
                    continue
                for i_z in range(z_start, z_start + active_z):
                    if abs(z - z_centers[i_z]) <= z_texture_half:
                        delta[index] = texture_depth
                        break
                if delta[index] > 0:
                    break

        return delta

    def output(self, model, *args, **kwargs):
        """
        Compute texture depth and foil deformation, then update nodal film thickness.

        :param model: FilmModel, the main model object
        :param *args: optional positional arguments
        :param **kwargs: optional keyword arguments
        :return: np.ndarray, updated total film thickness field
        """
        num_nodes = model.node_manager.non
        baseline_h = np.array(
            [float(model.node_manager.nodes[i].h) for i in range(num_nodes)],
            dtype=float,
        )

        if self._texture_delta is None or self._texture_delta.shape[0] != num_nodes:
            self._texture_delta = self._build_texture_delta(model)

        if len(model.results) == 0:
            boundary_pressure = float(model.boundary.args.get("p_set", 1.0))
            pressure = np.full(num_nodes, boundary_pressure, dtype=float)
        else:
            pressure = np.asarray(model.latest_result, dtype=float)[:num_nodes]

        if self.config.foil_enabled:
            target = (
                np.maximum(pressure - self.config.p_set, 0.0)
                / self.config.resolved_foil_stiffness
            )
            if (
                self._last_deformation is None
                or self._last_deformation.shape[0] != num_nodes
            ):
                self._last_deformation = np.zeros(num_nodes, dtype=float)
            deformation = (
                self.config.foil_relaxation * target
                + (1.0 - self.config.foil_relaxation) * self._last_deformation
            )
            self._error = np.linalg.norm(deformation - self._last_deformation) / max(
                np.linalg.norm(deformation), 1e-12
            )
            self._last_deformation = deformation
        else:
            deformation = np.zeros(num_nodes, dtype=float)
            self._error = 0.0

        total_h = np.maximum(baseline_h + self._texture_delta + deformation, 1e-6)
        for index in range(num_nodes):
            model.node_manager.nodes[index].h = float(total_h[index])

        self._latest_pressure = pressure
        self._latest_total_h = total_h
        return total_h

    def calc_error(self, *args, **kwargs):
        """
        Compute the iterative residual of foil deformation.

        :param *args: optional positional arguments
        :param **kwargs: optional keyword arguments
        :return: float, current relative deformation error
        """
        return self._error

    def calc_is_finished(self):
        """
        Determine whether the foil deformation iteration has converged.

        :return: bool, True if foil is disabled or error is within tolerance
        """
        if not self.config.foil_enabled:
            return True
        return self._error <= self.config.foil_tol

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        Save computation results (no persistence needed for this model).

        :param tofile: bool, whether to write to a file
        :param path: str or None, save path
        :param name: str or None, file name
        :param *args: optional positional arguments
        :param **kwargs: optional keyword arguments
        :return: None
        """
        return None


@LinearForm
def gas_reynolds_residual(v, w):
    """Residual form of the nondimensional gas Reynolds equation."""
    p = w.p
    dp_dtheta = grad(w.p)[0]
    dp_dz = grad(w.p)[1]
    dv_dtheta = grad(v)[0]
    dv_dz = grad(v)[1]

    diffusion = w.h3 * p * (w.lr2 * dp_dtheta * dv_dtheta + dp_dz * dv_dz)
    convection = w.lam * (w.h * dp_dtheta + w.h_source * p) * v
    return diffusion - convection


@BilinearForm
def gas_reynolds_jacobian(u, v, w):
    """Newton Jacobian form linearized around the current pressure field."""
    p = w.p
    dp_dtheta = grad(w.p)[0]
    dp_dz = grad(w.p)[1]
    du_dtheta = grad(u)[0]
    du_dz = grad(u)[1]
    dv_dtheta = grad(v)[0]
    dv_dz = grad(v)[1]

    diffusion = w.h3 * (
        w.lr2 * (u * dp_dtheta + p * du_dtheta) * dv_dtheta
        + (u * dp_dz + p * du_dz) * dv_dz
    )
    convection = w.lam * (w.h * du_dtheta + w.h_source * u) * v
    return diffusion - convection


class GasSkfemNewtonFilm(SkfemNewtonFilm):
    """Gas film pressure solver using scikit-fem assembly and Newton iteration."""

    def __init__(self, *args, **kwargs):
        """
        Initialize the gas film Newton solver.

        Extracts gas-specific parameters pa and gamma from kwargs, and computes
        the nondimensional Reynolds number lambda_gas.

        :param *args: positional arguments forwarded to SkfemNewtonFilm
        :param **kwargs: keyword arguments, must include pa (ambient pressure)
                         and gamma (specific heat ratio)
        """
        pa = kwargs.pop("pa")
        gamma = kwargs.pop("gamma")
        super().__init__(*args, **kwargs)
        self.args["pa"] = float(pa)
        self.args["gamma"] = float(gamma)
        self.args["pressure_floor"] = 0.0
        self.args["lambda_gas"] = self._calc_lambda_number()
        # Film post-processing uses args['ps'] as dimensional pressure scale.
        self.args["ps"] = float(pa)

    def _calc_lambda_number(self):
        """
        Compute the gas Reynolds number lambda = 6 * miu * omega * r^2 / (pa * c^2).

        :return: float, nondimensional gas Reynolds number
        """
        miu = self.args["miu"]
        omega = self.args["w_rad"]
        radius = self.args["r"]
        clearance = self.args["c"]
        pa = self.args["pa"]
        return 6.0 * miu * omega * radius**2 / (pa * clearance**2)

    @staticmethod
    def _nearest_index(sorted_axis: np.ndarray, values: np.ndarray) -> np.ndarray:
        """
        Find the index of the nearest element on a sorted axis for each query value.

        :param sorted_axis: np.ndarray, ascending coordinate axis array
        :param values: np.ndarray, array of query values
        :return: np.ndarray, nearest index in sorted_axis for each query value
        """
        idx = np.searchsorted(sorted_axis, values)
        idx = np.clip(idx, 0, len(sorted_axis) - 1)
        left = np.clip(idx - 1, 0, len(sorted_axis) - 1)
        use_left = np.abs(values - sorted_axis[left]) < np.abs(
            values - sorted_axis[idx]
        )
        return np.where(use_left, left, idx)

    def _build_nodal_fields(self):
        """
        Build thickness, squeeze term, and circumferential derivative fields at nodes.

        :return: tuple[np.ndarray, np.ndarray, np.ndarray],
                 (h_nodal, dh_dt_nodal, dh_dtheta_nodal) — nodal thickness,
                 time-varying squeeze term, and circumferential thickness gradient
        """
        num_nodes = self.node_manager.non
        h_nodal = np.zeros(num_nodes, dtype=float)
        theta = np.zeros(num_nodes, dtype=float)
        z = np.zeros(num_nodes, dtype=float)

        xct = self.args["xct"]
        yct = self.args["yct"]
        dh_dt_nodal = np.zeros(num_nodes, dtype=float)

        for i in range(num_nodes):
            node = self.node_manager.nodes[i]
            h_nodal[i] = float(node.h)
            theta[i] = float(node.coords[0])
            z[i] = float(node.coords[1])
            dh_dt_nodal[i] = xct * np.sin(theta[i]) - yct * np.cos(theta[i])

        theta_axis = np.unique(np.round(theta, 12))
        z_axis = np.unique(np.round(z, 12))
        ix = self._nearest_index(theta_axis, theta)
        iz = self._nearest_index(z_axis, z)

        h_grid = np.zeros((theta_axis.size, z_axis.size), dtype=float)
        h_grid[ix, iz] = h_nodal

        edge_order = 2 if theta_axis.size >= 3 else 1
        dh_dtheta_grid = np.gradient(h_grid, theta_axis, axis=0, edge_order=edge_order)
        dh_dtheta_nodal = dh_dtheta_grid[ix, iz]

        return h_nodal, dh_dt_nodal, dh_dtheta_nodal

    @staticmethod
    def _apply_pressure_floor(pressure: np.ndarray, floor: float) -> np.ndarray:
        """
        Clip pressure values below the floor to the floor value.

        :param pressure: np.ndarray, pressure field array
        :param floor: float, pressure lower bound
        :return: np.ndarray, copy of the pressure field with floor applied
        """
        pressure = np.asarray(pressure, dtype=float).copy()
        pressure[pressure < floor] = floor
        return pressure

    def init(self, **kwargs):
        """
        Initialize the pressure field to the boundary pressure and update nodes.

        :param **kwargs: optional keyword arguments
        :return: np.ndarray, initialized pressure field
        """
        boundary_pressure = float(self.boundary.args.get("p_set", 1.0))
        p0 = np.full(
            self.node_manager.freedoms,
            boundary_pressure,
            dtype=float,
        )
        self._results = [p0]
        self._dp = np.zeros_like(p0)
        self.update_to_nodes(result=p0)
        return p0

    def calc_matrixs_rights(self, calc=True, csc=True):
        """
        Assemble the Newton residual vector and Jacobian matrix for the gas Reynolds equation.

        Uses scikit-fem to interpolate nodal fields (thickness, pressure, source term)
        at integration points, then assembles via gas_reynolds_residual and
        gas_reynolds_jacobian.

        :param calc: bool, whether to reassemble the matrix and right-hand side
        :param csc: bool, whether to store the matrix in CSC format
        :return: tuple[dict, dict], (matrixs, rights)
        """
        if not self._skfem_initialized:
            self._init_skfem()

        if calc:
            h_nodal, dh_dt_nodal, dh_dtheta_nodal = self._build_nodal_fields()

            if len(self.results) == 0:
                boundary_pressure = float(self.boundary.args.get("p_set", 1.0))
                p_nodal = np.full_like(h_nodal, boundary_pressure)
            else:
                p_nodal = np.asarray(self.latest_result, dtype=float)

            h_qp = self.basis.interpolate(h_nodal)
            p_qp = self.basis.interpolate(p_nodal)
            h3_qp = self.basis.interpolate(h_nodal**3)
            h_source_qp = self.basis.interpolate(
                dh_dtheta_nodal + 2.0 * self.args["gamma"] * dh_dt_nodal
            )

            lam = self.args["lambda_gas"]
            lr2 = self.args["lr"] ** 2

            residual = asm(
                gas_reynolds_residual,
                self.basis,
                p=p_qp,
                h=h_qp,
                h3=h3_qp,
                lam=lam,
                lr2=lr2,
                h_source=h_source_qp,
            )
            jacobian = asm(
                gas_reynolds_jacobian,
                self.basis,
                p=p_qp,
                h=h_qp,
                h3=h3_qp,
                lam=lam,
                lr2=lr2,
                h_source=h_source_qp,
            )

            if csc:
                self.matrixs = {"ke": jacobian.tocsc()}
            else:
                self.matrixs = {"ke": jacobian.toarray()}
            self.rights = {"fe": residual}

        return self.matrixs, self.rights

    def iter_solve(self, *args, **kwargs):
        """
        Perform one Newton iteration: assemble system → apply boundary conditions → solve → update nodes.

        :param *args: optional positional arguments
        :param **kwargs: optional keyword arguments
        :return: np.ndarray, pressure field after the iteration
        """
        p_last = np.asarray(self.latest_result, dtype=float)

        self.calc_matrixs_rights(calc=True, csc=True)
        jacobian = self.matrixs["ke"]
        residual = np.asarray(self.rights["fe"], dtype=float)

        rhs = jacobian.dot(p_last) - residual
        self.matrixs = {"ke": jacobian}
        self.rights = {"fe": rhs}

        boundary_pressure = float(self.boundary.args.get("p_set", 1.0))
        pressure_floor = float(self.args.get("pressure_floor", 0.0))
        coe = bool(self.boundary.args.get("coe", True))
        self.set_boundary(self, method="round", p_set=boundary_pressure, coe=coe)

        p_trial = spsolve(self.matrixs["ke"], self.rights["fe"])
        p_new = p_last + self.current_damp * (p_trial - p_last)
        p_new = self._apply_pressure_floor(p_new, pressure_floor)

        self._dp = p_new - p_last
        self.add_result(p_new)
        self.update_to_nodes(result=p_new)
        return p_new


class GasBearing(FilmSystem):
    """Gas bearing system with Newton iteration and scikit-fem assembly."""

    def __init__(self, gas_config: GasConfig = GasConfig()):
        if gas_config.thermal_enabled:
            raise NotImplementedError(
                "Thermal coupling interface is reserved but not enabled in this version."
            )

        mesh = Mesh()
        elems = ElemManager()
        nodes = NodeManager()
        matrix_process = MatrixProcess()

        if gas_config.vib:
            if gas_config.dxt is None or gas_config.dyt is None:
                gas_config.dxt = (
                    -gas_config.e
                    * gas_config.c
                    * gas_config.vf
                    * (gas_config.freq * 2.0 * np.pi)
                    * np.cos(gas_config.angle_rad)
                )
                gas_config.dyt = (
                    -gas_config.e
                    * gas_config.c
                    * gas_config.vf
                    * (gas_config.freq * 2.0 * np.pi)
                    * np.sin(gas_config.angle_rad)
                )
        else:
            gas_config.dxt = 0.0
            gas_config.dyt = 0.0
            gas_config.vf = 1.0

        film_boundary = FilmBoundary(coe=gas_config.coe, p_set=gas_config.p_set)
        film_model = GasSkfemNewtonFilm(
            w=gas_config.w,
            x0=gas_config.x0,
            lx=gas_config.lx,
            lz=gas_config.lz,
            nx=gas_config.nx,
            nz=gas_config.nz,
            miu=gas_config.miu,
            c=gas_config.c,
            r=gas_config.r,
            l=gas_config.l,
            ps=gas_config.pa,
            rho=gas_config.rho,
            dxt=gas_config.dxt,
            dyt=gas_config.dyt,
            vf=gas_config.vf,
            reynold=gas_config.reynold,
            mesh=mesh,
            filmboundary=film_boundary,
            node_manager=nodes,
            elem_manager=elems,
            matrix_process=matrix_process,
            pa=gas_config.pa,
            gamma=gas_config.gamma,
            error_set=gas_config.error_set,
            damp=gas_config.damp,
            adaptive_damp=gas_config.adaptive_damp,
            save_p=gas_config.save_p,
            save_h=gas_config.save_h,
        )

        args = film_model.args
        nds, els = mesh.build_rect(
            RectFilmNode, RectFilmElem, args["x_lim"], args["z_lim"], args["size"]
        )
        nodes.adds(nds)
        elems.adds(els)

        self.thickness = ThicknessModel(e=gas_config.e, angle=gas_config.angle_rad)
        self.thickness.set_thickness_with_e_angle(film_model)

        self._thermal_model = None
        self._foil_model = None
        simple_models = [self.thickness]
        if gas_config.foil_enabled or gas_config.texture_enabled:
            self._foil_model = GasFoilTextureCoupling(gas_config)
            simple_models.append(self._foil_model)
        self._path = gas_config.path if gas_config.path != "" else "gas_bearing_result"

        super().__init__(
            film_model,
            *simple_models,
            max_iter=gas_config.max_iter,
            node_link=gas_config.node_link,
        )

    def set_thermal_model(self, model):
        """Reserve thermal interface for future coupling."""
        self._thermal_model = model

    def set_foil_model(self, model):
        """Reserve compliant-foil interface for future coupling."""
        self._foil_model = model
