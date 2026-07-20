# ?coding: utf-8 ?
import math

import numpy as np
import pandas as pd
import scipy.sparse
import scipy.sparse as sp
from matplotlib import pyplot as plt
from numba import njit
from scipy.sparse import linalg as sl
from skfem import (
    Basis,
    BilinearForm,
    ElementQuad1,
    ElementTriP1,
    LinearForm,
    MeshQuad,
    MeshTri,
    asm,
)
from skfem.helpers import grad

from ALB.core.fem import boundary
from ALB.core.fem.base import (
    BaseBoundary,
    BaseElem,
    BaseMainModel,
    BaseNode,
    BaseOutput,
    BasePostProcess,
    BaseSimpleModel,
    BaseSystem,
)
from ALB.core.fem.boundary import (
    couple_boundary_matrix,
    set_continuity_boundary,
    set_value_boundary,
)
from ALB.core.numerics.damping import (
    AdaptiveDampController,
    normalize_adaptive_damp_config,
)
from ALB.core.numerics.iteration import (
    gauss_seidel_iteration_film,
    gauss_seidel_iteration_matrix,
)

# from .logger import delogger, logger
from ALB.core.numerics.static import calc_fe, calc_fe_vf, calc_ke
from ALB.core.fem.mesh import Mesh
from ALB.infrastructure.persistence import DataFrameResult, NpyResult, SaveTreeNode

__all__ = [
    "NodimFilmModel",
    "FilmModel",
    "RectFilmElem",
    "RectFilmNode",
    "FilmBoundary",
    "ThicknessModel",
    "NodimNewtonFilm",
    "NewtonFilm",
    "FilmSystem",
    "FilmPostProcess",
    "PSetFilmBoundary",
    "FilmOutput",
    "GaussSeidelFilm",
    "SkfemNewtonFilm",
]


class RectFilmNode(BaseNode):
    def __init__(self, coords, p=0, h=0):
        """
        define the pressure and film thickness of the film node
        """
        super(RectFilmNode, self).__init__(coords)
        self._p = p
        self._h = h

    @property
    def p(self):
        """
        node pressure
        """
        return self._p

    @p.setter
    def p(self, val: float):
        self._p = val

    @property
    def h(self):
        """
        film thickness
        """
        return self._h

    @h.setter
    def h(self, val: float):
        self._h = val


class RectFilmElem(BaseElem):
    """
    matrixs and rights name should be defined in the subclass, remember to override these two properties
    """

    matrixs_name = ["ke"]
    rights_name = ["fe"]

    def __init__(self, nodes, lr=1, lambda_value=0, lx=None, lz=None):
        """
        define the film element
        :param nodes: nodes
        :param lr: length ratio
        :param lambda_value: dimensionless bearing number in the Reynolds equation.
        :param lx: element length in x direction
        """
        super().__init__(nodes)
        self.args = {"lr": lr, "lambda": lambda_value, "lambda0": lambda_value}
        if lx is None or lz is None:
            self.lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
            self.lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        elif lx is not None and lz is not None:
            self.lx = lx
            self.lz = lz
        else:
            raise ValueError("Either both lx and lz should be provided, or neither.")

    def calc_matrixs(self):
        """
        calculate the left stiffness matrix
        """
        h = np.array([node.h for node in self.nodes.values()])
        lr = self.args["lr"]
        lz = self.lz
        lx = self.lx
        self._matrixs["ke"] = calc_ke(h, lr, lz, lx)

    def calc_rights(self):
        """
        calculate the right force vector
        """

        h = np.array([node.h for node in self.nodes.values()])
        lambda_value = self.args["lambda"]
        lz = self.lz
        lx = self.lx
        x0 = self.nodes[0].coords[0]
        vf = self.args["vf"]
        xct = self.args["xct"]
        yct = self.args["yct"]
        self._rights["fe"] = calc_fe(h, lz, lambda_value) + calc_fe_vf(
            x0, lx, lz, lambda_value, vf, xct, yct
        )

    def intergral(self):
        """
        integral the pressure over the element
        """
        lx = self.lx
        lz = self.lz
        return np.array([node.p for node in self.nodes.values()]).mean() * lx * lz

    def film_exist(self, err=1e-10):
        """
        judge whether the film exsit in this element
        """
        p = np.array([node.p for node in self.nodes.values()])
        if np.all(p > err):
            return True
        else:
            return False

    def friction_force(self, hb=None):
        """
        calculate the friction force of this element
        """
        miu = self.args["miu"]
        w = self.args["w_rad"]
        r = self.args["r"]
        c = self.args["c"]
        ps = self.args["ps"]
        l = self.args["l"]
        hs = np.array([node.h for node in self.nodes.values()]) * c
        lh_mean = np.array([1 / node.h for node in self.nodes.values()]).mean() / c
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0]) * r
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1]) * l / 2
        dp_dx0 = (self.nodes[1].p - self.nodes[0].p) * ps / lx
        dp_dx1 = (self.nodes[3].p - self.nodes[2].p) * ps / lx
        dp_dx = np.array([dp_dx0, dp_dx0, dp_dx1, dp_dx1])
        pt0 = np.sum(dp_dx * hs / 2) / 4 * lx * lz
        if hb is None:
            hb = c
        else:
            hb = hb * c
        if not self.film_exist():
            lh_mean2 = np.array(
                [1 / (node.h * c) ** 2 for node in self.nodes.values()]
            ).mean()
            pt1 = miu * w * r * hb * lh_mean2 * lx * lz
        else:
            pt1 = miu * w * r * lh_mean * lx * lz
        Ff = pt0 + pt1
        return Ff

    def in_this(self, coords):
        """
        judge whether the point is in this element
        """
        return is_point_in_polygon(
            [node.coords for node in self.nodes.values()], coords
        )

    # Placeholder for future pointwise interpolation within this element.
    def interpolation(self, coords):
        pass


def film_args_trans(w, x0, lx, lz, nx, nz, miu, c, r, l, ps, rho, dxt, dyt, vf):
    """
    Transform dimensional film inputs into solver-ready nondimensional arguments.

    Thin wrapper that delegates the scaling formulas to
    :class:`ALB.physics.thermal.FilmNondimScales` so the conversion lives in one place.

    :param w: Rotor speed in rpm.
    :param x0: Start angle in degrees.
    :param lx: Angular span in degrees.
    :param lz: Axial span in nondimensional units.
    :param nx: Number of circumferential grid divisions.
    :param nz: Number of axial grid divisions.
    :param miu: Dynamic viscosity.
    :param c: Radial clearance.
    :param r: Journal radius.
    :param l: Bearing length.
    :param ps: Supply pressure.
    :param rho: Lubricant density.
    :param dxt: Squeeze velocity component along x.
    :param dyt: Squeeze velocity component along y.
    :param vf: Velocity-feed coefficient for squeeze term.
    :return: ``(input_args, args)`` where ``input_args`` is the dimensional
        record and ``args`` is the nondimensional dict consumed by film models.
    """
    from ALB.physics.thermal.scales import FilmNondimScales

    input_args = {
        "w": w,
        "x0": x0,
        "lx": lx,
        "lz": lz,
        "nx": nx,
        "nz": nz,
        "miu": miu,
        "c": c,
        "r": r,
        "l": l,
        "ps": ps,
        "rho": rho,
        "dxt": dxt,
        "dyt": dyt,
        "vf": vf,
    }
    scales = FilmNondimScales.from_dimensional(
        w=w, miu=miu, c=c, r=r, l=l, ps=ps, rho=rho, vf=vf
    )
    args = scales.to_film_args(x0=x0, lx=lx, lz=lz, nx=nx, nz=nz, dxt=dxt, dyt=dyt)
    return input_args, args


def _angle_inputs_to_radians(x0, lx, angle_unit):
    unit = str(angle_unit).lower()
    if unit in {"deg", "degree", "degrees"}:
        return np.deg2rad(x0), np.deg2rad(lx)
    if unit in {"rad", "radian", "radians"}:
        return x0, lx
    raise ValueError("angle_unit must be 'deg' or 'rad'")


class NodimFilmModel(BaseMainModel):
    """Hydrodynamic film model whose constructor accepts solver-ready nondimensional parameters."""

    # delogger_level = 'debug'

    def __init__(
        self,
        lambda_value,
        lr,
        x0,
        lx,  # Length in x direction.
        lz,  # Length in z direction.
        nx,
        nz,
        mesh: Mesh,
        filmboundary,
        node_manager=None,
        elem_manager=None,
        matrix_process=None,
        lambda0=None,
        miu=1.0,
        c=1.0,
        r=1.0,
        l=None,
        ps=1.0,
        rho=1.0,
        w=None,
        w_rad=None,
        dxt=0.0,
        dyt=0.0,
        vf=1.0,
        xct=0.0,
        yct=0.0,
        angle_unit="deg",
        input_args=None,
        **kwargs,
    ):
        """
        Initialize this object with the provided configuration.

        :param lambda_value: Dimensionless bearing number in the Reynolds equation.
        :param lr: Bearing length-radius ratio, l / (2r).
        :param x0: Start angle. Public nondimensional inputs use degrees by default.
        :param lx: Angular span. Public nondimensional inputs use degrees by default.
        :param lz: Axial span or axial interval.
        :param nx: Number of circumferential grid divisions.
        :param nz: Number of axial grid divisions.
        :param mesh: Mesh instance used to build nodes and elements.
        :param filmboundary: Boundary-condition handler for film equations.
        :param node_manager: Node manager object.
        :param elem_manager: Element manager object.
        :param matrix_process: Global matrix assembly and solve helper.
        :param **kwargs: Optional keyword arguments.
        """
        super().__init__(mesh, filmboundary, node_manager, elem_manager, matrix_process)
        if lambda0 is None:
            lambda0 = lambda_value
        if l is None:
            l = 2.0 * lr * r
        if w is None:
            w = 60.0 / (2.0 * np.pi)
        if w_rad is None:
            w_rad = w / 60.0 * 2.0 * np.pi
        x0_rad, lx_rad = _angle_inputs_to_radians(x0, lx, angle_unit)
        self._input_args = dict(input_args or {})
        self.args = {
            "w": w,
            "x0": x0_rad,
            "nx": nx,
            "nz": nz,
            "size": [nx, nz],
            "miu": miu,
            "miu0": miu,
            "c": c,
            "r": r,
            "l": l,
            "ps": ps,
            "w_rad": w_rad,
            "w_hz": w_rad / (2.0 * np.pi),
            "lr": lr,
            "x_lim": np.array([x0_rad, x0_rad + lx_rad]),
            "z_lim": np.array([-1, lz - 1]),
            "lambda": lambda_value,
            "lambda0": lambda0,
            "rho": rho,
            "dxt": dxt,
            "dyt": dyt,
            "vf": vf,
            "xct": xct,
            "yct": yct,
            "args_nodim": True,
            "angle_unit": angle_unit,
        }
        self._all_recalc = True
        # self.delogger_level = kwargs.get('delogger_level', 'debug')
        self.elem_manager.elems_args = self.args
        self.save_switch = {
            "p": kwargs.get("save_p", False),
            "h": kwargs.get("save_h", False),
        }
        self._save_p = []
        self._save_h = []


class FilmModel(NodimFilmModel):
    """Dimensional compatibility wrapper for :class:`NodimFilmModel`."""

    def __init__(
        self,
        w,
        x0,
        lx,
        lz,
        nx,
        nz,
        miu,
        c,
        r,
        l,
        ps,
        rho,
        dxt,
        dyt,
        vf,
        mesh: Mesh,
        filmboundary,
        node_manager=None,
        elem_manager=None,
        matrix_process=None,
        **kwargs,
    ):
        input_args, nd_args = film_args_trans(
            w, x0, lx, lz, nx, nz, miu, c, r, l, ps, rho, dxt, dyt, vf
        )
        super().__init__(
            lambda_value=nd_args["lambda"],
            lambda0=nd_args["lambda0"],
            lr=nd_args["lr"],
            x0=nd_args["x_lim"][0],
            lx=nd_args["x_lim"][1] - nd_args["x_lim"][0],
            lz=nd_args["z_lim"][1] - nd_args["z_lim"][0],
            nx=nd_args["nx"],
            nz=nd_args["nz"],
            miu=nd_args["miu"],
            c=nd_args["c"],
            r=nd_args["r"],
            l=nd_args["l"],
            ps=nd_args["ps"],
            rho=nd_args["rho"],
            w=nd_args["w"],
            w_rad=nd_args["w_rad"],
            dxt=nd_args["dxt"],
            dyt=nd_args["dyt"],
            vf=nd_args["vf"],
            xct=nd_args["xct"],
            yct=nd_args["yct"],
            angle_unit="rad",
            input_args=input_args,
            mesh=mesh,
            filmboundary=filmboundary,
            node_manager=node_manager,
            elem_manager=elem_manager,
            matrix_process=matrix_process,
            **kwargs,
        )
        self.args["args_nodim"] = False

    # @delogger(" ", delogger_level)
    def update_to_nodes(self, result=None):
        """
        Write the latest solver result vector back to nodal pressure fields.

        :param result: Result vector to be written back to nodes.
        """
        if result is None:
            result = self.results[-1]
        for key, node in self.nodes.items():
            node.p = result[key]

    # Assemble base matrices and apply boundary conditions before each solve.
    def pre_solve(self, *args, **kwargs):
        """
        Assemble matrices and apply boundary conditions before solving.

        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        """
        self.calc_matrixs_rights(self._all_recalc, **kwargs)
        self.set_boundary(self, *args, **kwargs)

    def add_to_matrix(self, datas, posotions, name):
        """
        Accumulate local matrices or vectors into the global matrix process.

        :param datas: Local matrix/vector data to assemble.
        :param posotions: Target positions in the global matrix.
        :param name: Data name used by matrix_process.
        """
        self.matrix_process.add_to_matrix(datas, posotions, name)

    def solve(self, **kwargs):
        """
        Solve the current linear system and update model state.

        :param **kwargs: Optional keyword arguments.
        :return: Computed value(s) for the current operation.
        """
        self.matrixs["ke"] = sp.csc_matrix(self.matrixs["ke"])
        result = sl.spsolve(self.matrixs["ke"], self.rights["fe"])
        self.add_result(result)
        self.update_to_nodes()
        self.signal.lead_loop("finish_signal")
        return result

    def add_result(self, result):
        if len(self.results) < 2:
            self.results.append(result)
        else:
            self.results[-2] = self.results[-1]
            self.results[-1] = result

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        Save film-model results and metadata to structured output nodes.

        :param tofile: Whether to write results to files.
        :param path: Output directory path.
        :param name: Data name used by matrix_process.
        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        """
        if path is None:
            path = "film_results"
        if name is None:
            name = "film"
        info = pd.DataFrame(columns=list(self.args.keys()))
        info.loc[0] = list(self.args.values())
        res0 = {name + "_information": info}
        res0 = DataFrameResult(res0)
        save_p = np.array(self._save_p)
        save_h = np.array(self._save_h)

        res1 = {name + "_p": save_p, name + "_h": save_h}
        res1 = NpyResult(res1)
        node = SaveTreeNode(path, [res0, res1])

        if tofile:
            node.save_to_file()
        return node

    def finish_signal(self):
        freedom = self.node_manager.freedoms
        if self.save_switch["p"]:
            film_p = self.latest_result
            film_p = film_p[0:freedom].reshape(
                (self.args["nx"] + 1, self.args["nz"] + 1)
            )
            self._save_p.append(film_p)
        if self.save_switch["h"]:
            film_h = np.array([node.h for node in self.nodes.values()])
            film_h = film_h[0:freedom].reshape(
                (self.args["nx"] + 1, self.args["nz"] + 1)
            )
            self._save_h.append(film_h)


class NodimNewtonFilm(FilmModel):
    # delogger_level = 'debug'
    # logger_level = logging.INFO

    # Newton-based film solver with damping and residual control.
    def __init__(
        self,
        lambda_value,
        lr,
        x0,
        lx,
        lz,
        nx,
        nz,
        reynold,
        mesh,
        filmboundary,
        node_manager,
        elem_manager,
        matrix_process,
        lambda0=None,
        miu=1.0,
        c=1.0,
        r=1.0,
        l=None,
        ps=1.0,
        rho=1.0,
        w=None,
        w_rad=None,
        dxt=0.0,
        dyt=0.0,
        vf=1.0,
        xct=0.0,
        yct=0.0,
        angle_unit="deg",
        input_args=None,
        **kwargs,
    ):
        """
        Initialize this object with the provided configuration.

        :param lambda_value: Dimensionless bearing number in the Reynolds equation.
        :param lr: Bearing length-radius ratio, l / (2r).
        :param x0: Start angle. Public nondimensional inputs use degrees by default.
        :param lx: Angular span. Public nondimensional inputs use degrees by default.
        :param lz: Axial span or axial interval.
        :param nx: Number of circumferential grid divisions.
        :param nz: Number of axial grid divisions.
        :param reynold: Reynolds-mode flag for cavitation handling.
        :param mesh: Mesh instance used to build nodes and elements.
        :param filmboundary: Boundary-condition handler for film equations.
        :param node_manager: Node manager object.
        :param elem_manager: Element manager object.
        :param matrix_process: Global matrix assembly and solve helper.
        :param **kwargs: Optional keyword arguments.
        """
        NodimFilmModel.__init__(
            self,
            lambda_value=lambda_value,
            lambda0=lambda0,
            lr=lr,
            x0=x0,
            lx=lx,
            lz=lz,
            nx=nx,
            nz=nz,
            miu=miu,
            c=c,
            r=r,
            l=l,
            ps=ps,
            rho=rho,
            w=w,
            w_rad=w_rad,
            dxt=dxt,
            dyt=dyt,
            vf=vf,
            xct=xct,
            yct=yct,
            angle_unit=angle_unit,
            input_args=input_args,
            mesh=mesh,
            filmboundary=filmboundary,
            node_manager=node_manager,
            elem_manager=elem_manager,
            matrix_process=matrix_process,
            **kwargs,
        )
        self.args["reynold"] = reynold
        self._ready_values = {}  # Cache linearized matrices/vectors for iterative corrections.
        self.errors = None  # Record latest residual error for convergence check.
        self._init = True
        if "error_set" in kwargs.keys():
            error_set = kwargs["error_set"]
        else:
            error_set = 1e-7
        self._error_set = error_set
        if "damp" in kwargs.keys():
            damp = kwargs["damp"]
        else:
            damp = 0.8
        self._damp = damp
        self._adaptive_damp_config = normalize_adaptive_damp_config(
            kwargs.get("adaptive_damp")
        )
        self._adaptive_damp = AdaptiveDampController(
            self._damp, self._adaptive_damp_config
        )
        self._dp = []

    # Initialize pressure and cache baseline matrices for Newton iterations.
    def init(self, **kwargs):
        """
        Initialize solver state and cache data for iterative updates.

        :param **kwargs: Optional keyword arguments.
        """
        self.reset_adaptive_damp()
        self.pre_solve(**kwargs)
        result = self.solve()
        self.matrixs_init_for_iter_solve()
        return result

    def reset_adaptive_damp(self):
        """Reset adaptive pressure damping for a fresh pressure solve."""
        self._adaptive_damp.reset(self._damp)

    @property
    def current_damp(self):
        """Return the relaxation value for the next pressure update."""
        return self._adaptive_damp.value

    @property
    def adaptive_damp_history(self):
        """Return recorded pressure adaptive damping decisions."""
        return list(self._adaptive_damp.history)

    def matrixs_init_for_iter_solve(self):
        """Cache baseline matrices and right-hand vectors for iteration."""
        self._ready_values["ke"] = self.matrixs["ke"].copy()
        self._ready_values["fe"] = self.rights["fe"].copy()

    def iter_solve(self, *args, **kwargs):
        """
        Run one nonlinear iteration step according to the selected Reynolds mode.

        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        """
        if self.args["reynold"] is True or self.args["reynold"] == "reynold":
            p = self._iter_solve2()
        elif self.args["reynold"] == "half_reynold" or self.args["reynold"] is False:
            p = self._iter_solve1()
        else:
            raise Exception("Unknown reynold type")
        return p

    def _iter_solve1(self, *args, **kwargs):

        k = self.matrixs["ke"]
        k = scipy.sparse.csc_matrix(k)
        f = self.rights["fe"] - self._ready_values["ke"].dot(self.latest_result)
        self._dp = sl.spsolve(k, f)
        p = self.latest_result + self._dp * self.current_damp
        p = self._reynold_boundary(p)

        self.add_result(p)

        self.matrixs["ke_all"] = self.matrixs["ke"].copy()
        self.rights["fe_all"] = self.rights["fe"].copy()
        self.matrixs["ke"] = self._ready_values["ke"].copy()
        self.rights["fe"] = self._ready_values["fe"].copy()
        self.update_to_nodes()
        return p

    def _iter_solve2(self, *args, **kwargs):
        K = self._ready_values["ke"]
        p = self.latest_result

        epsilon = 1e-20
        dF_dp = self.matrixs["ke"]
        dF_dp = scipy.sparse.csc_matrix(dF_dp)
        q = self.rights["fe"]
        F = K.dot(p) - q
        denom = np.sqrt(p**2 + F**2 + epsilon)

        alpha = (p / denom) - 1.0
        beta = (F / denom) - 1.0

        D_alpha = sp.diags(alpha)
        D_beta = sp.diags(beta)

        J = D_alpha + D_beta.dot(dF_dp)
        Phi = np.sqrt(F**2 + p**2) - F - p

        try:
            # Solve Newton correction step from Jacobian system.
            # Fallback regularization is used when Jacobian is singular.
            self._dp = sl.spsolve(J, -Phi)
        except RuntimeError:
            # Numerical fallback for singular Jacobian.
            # print("Warning: Matrix is singular. Applying regularization...")

            # Add a small diagonal term to stabilize the linear solve.
            # This avoids breakdown near degenerate states.
            reg_value = 1e-6
            n_dof = J.shape[0]
            J_reg = J + sp.eye(n_dof, format="csr") * reg_value

            self._dp = sl.spsolve(J_reg, -Phi)

        p = p + self._dp * self.current_damp
        # p = self._reynold_boundary(p)

        # x_lim = self.args['x_lim']
        # y_lim = self.args['z_lim']
        # if not self.boundary.args['coe']:
        #     r_boundary = self.node_manager.search(0, x_lim[0], number=True)
        #     l_boudary = self.node_manager.search(0, x_lim[1], number=True)
        #     u_boudary = self.node_manager.search(1, y_lim[0], number=True)
        #     d_boudary = self.node_manager.search(1, y_lim[1], number=True)
        # Legacy boundary handling branch kept for reference.
        #     boundary.check_boundary(r_boundary + l_boudary, u_boudary)
        #     boundary.check_boundary(r_boundary + l_boudary, d_boudary)
        #     boundary_nodes = r_boundary + l_boudary + u_boudary + d_boudary
        #     p[boundary_nodes] = 0.0
        # else:
        #     raise ValueError("coe boundary condition is not supported in reynold method, please set coe to False.\n"
        #                      "if you want to set coe=True, please set reynold=half_reynold")
        self.add_result(p)

        self.matrixs["ke_all"] = self.matrixs["ke"].copy()
        self.rights["fe_all"] = self.rights["fe"].copy()
        self.matrixs["ke"] = self._ready_values["ke"].copy()
        self.rights["fe"] = self._ready_values["fe"].copy()
        self.update_to_nodes()
        return p

    def output(self, *args, **kwargs):
        """
        Run solver output step and return updated solution data.

        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        :return: Computed value(s) for the current operation.
        """
        op = self.iter_solve(*args, **kwargs)
        self.signal.lead_loop("finish_signal")
        return op

    def calc_is_finished(self):
        """Check convergence status against the configured error threshold."""
        error = self.calc_error()
        # Save the current scalar error for external diagnostics.
        self.errors = error
        self._adaptive_damp.update(error)
        return error <= self._error_set

    def set_reynold_boundary(self, sw: bool):
        """
        Enable or disable Reynolds non-negative pressure constraint.

        :param sw: Boolean switch for Reynolds boundary clipping.
        """
        self.args["reynold"] = sw

    def _reynold_boundary(self, result):
        """
        Clamp negative pressures when Reynolds constraint is enabled.

        :param result: Result vector to be written back to nodes.
        """
        if self.args["reynold"]:
            result[result < 0] = 0
        return result


class NewtonFilm(NodimNewtonFilm):
    """Dimensional compatibility wrapper for :class:`NodimNewtonFilm`."""

    def __init__(
        self,
        w,
        x0,
        lx,
        lz,
        nx,
        nz,
        miu,
        c,
        r,
        l,
        ps,
        rho,
        dxt,
        dyt,
        vf,
        reynold,
        mesh,
        filmboundary,
        node_manager,
        elem_manager,
        matrix_process,
        **kwargs,
    ):
        input_args, nd_args = film_args_trans(
            w, x0, lx, lz, nx, nz, miu, c, r, l, ps, rho, dxt, dyt, vf
        )
        super().__init__(
            lambda_value=nd_args["lambda"],
            lambda0=nd_args["lambda0"],
            lr=nd_args["lr"],
            x0=nd_args["x_lim"][0],
            lx=nd_args["x_lim"][1] - nd_args["x_lim"][0],
            lz=nd_args["z_lim"][1] - nd_args["z_lim"][0],
            nx=nd_args["nx"],
            nz=nd_args["nz"],
            miu=nd_args["miu"],
            c=nd_args["c"],
            r=nd_args["r"],
            l=nd_args["l"],
            ps=nd_args["ps"],
            rho=nd_args["rho"],
            w=nd_args["w"],
            w_rad=nd_args["w_rad"],
            dxt=nd_args["dxt"],
            dyt=nd_args["dyt"],
            vf=nd_args["vf"],
            xct=nd_args["xct"],
            yct=nd_args["yct"],
            angle_unit="rad",
            input_args=input_args,
            reynold=reynold,
            mesh=mesh,
            filmboundary=filmboundary,
            node_manager=node_manager,
            elem_manager=elem_manager,
            matrix_process=matrix_process,
            **kwargs,
        )
        self.args["args_nodim"] = False


@BilinearForm
def reynolds_lhs(u, v, w):
    """
    Bilinear form of the Reynolds equation left-hand operator.

    :param u: Dynamic viscosity.
    :param v: Test function value at quadrature points.
    :param w: Rotor speed in rpm.
    """
    h3 = w.h**3
    return h3 * (w.lr**2 * grad(u)[0] * grad(v)[0] + grad(u)[1] * grad(v)[1])


@LinearForm
def reynolds_rhs(v, w):
    """
    Linear form of the Reynolds equation source term.

    :param v: Test function value at quadrature points.
    :param w: Rotor speed in rpm.
    """
    dh_dx = grad(w.h)[0]
    return (-w.lambda_value * dh_dx - 2.0 * w.lambda_value * w.vf * w.dh_dt) * v


class SkfemNewtonFilm(NewtonFilm):
    """Newton film solver variant based on scikit-fem matrix assembly."""

    def __init__(self, *args, **kwargs):
        # Reuse NewtonFilm behavior and add skfem-specific cache.
        super().__init__(*args, **kwargs)

        self._skfem_initialized = False
        self.mesh_skfem = None
        self.basis = None

    def _init_skfem(self):
        num_nodes = self.node_manager.non
        coords = np.zeros((2, num_nodes))

        # Collect nodal coordinates for skfem mesh construction.
        for i in range(num_nodes):
            coords[:, i] = self.node_manager.nodes[i].coords

        # Build element connectivity matrix from internal element mappings.
        num_elems = self.elem_manager.noe
        nodes_per_elem = len(self.elem_manager.elems[0].mapping)
        connectivity = np.zeros((nodes_per_elem, num_elems), dtype=int)

        for i in range(num_elems):
            connectivity[:, i] = self.elem_manager.elems[i].mapping

        # Initialize triangle or quadrilateral basis according to element topology.
        if nodes_per_elem == 3:
            self.mesh_skfem = MeshTri(coords, connectivity)
            self.basis = Basis(self.mesh_skfem, ElementTriP1())
        elif nodes_per_elem == 4:
            connectivity[[2, 3], :] = connectivity[[3, 2], :]
            self.mesh_skfem = MeshQuad(coords, connectivity)
            self.basis = Basis(self.mesh_skfem, ElementQuad1())
        else:
            raise ValueError(
                f"Skfem does not support elements with {nodes_per_elem} nodes."
            )

        self._skfem_initialized = True

    def calc_matrixs_rights(self, calc=True, csc=True):

        if not self._skfem_initialized:
            self._init_skfem()

        if calc:
            # Build nodal thickness and squeeze-term arrays.
            num_nodes = self.node_manager.non
            h_nodal = np.zeros(num_nodes)
            dh_dt_nodal = np.zeros(num_nodes)

            xct = self.args["xct"]
            yct = self.args["yct"]

            for i in range(num_nodes):
                node = self.node_manager.nodes[i]
                h_nodal[i] = node.h

                # Circumferential coordinate for time-varying film term.
                theta = node.coords[0]
                dh_dt_nodal[i] = xct * np.sin(theta) - yct * np.cos(theta)

            # Interpolate nodal fields to quadrature points.
            h_qp = self.basis.interpolate(h_nodal)
            dh_dt_qp = self.basis.interpolate(dh_dt_nodal)

            # 3.
            lambda_value = self.args["lambda"]
            vf = self.args["vf"]
            lr = self.args["lr"]

            # Assemble global linear system using skfem forms.
            K = asm(reynolds_lhs, self.basis, h=h_qp, lr=lr)
            F = asm(
                reynolds_rhs,
                self.basis,
                h=h_qp,
                dh_dt=dh_dt_qp,
                lambda_value=lambda_value,
                vf=vf,
            )

            # 5. matrix_process
            if csc:
                self.matrixs = {"ke": K.tocsc()}
            else:
                self.matrixs = {"ke": K.toarray()}
            self.rights = {"fe": F}

        return self.matrixs, self.rights


class GaussSeidelFilm(NewtonFilm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._n = kwargs.get("ngauss", 30)
        self._err = kwargs.get("err", 1e-6)  # Gauss-Seidel convergence threshold.
        self._gdamp = kwargs.get("gdamp", 1.2)  # Relaxation factor for GS update.
        self._gmf = kwargs.get(
            "gmf", False
        )  # Switch between matrix and film GS kernels.

    def iter_solve(self, *args, **kwargs):
        """
        Run one nonlinear iteration step according to the selected Reynolds mode.

        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        """
        # save_all = kwargs.get('save_all', True)
        save_dp = kwargs.get("save_dp", False)
        k = self.matrixs["ke"]
        f = self.rights["fe"] - self._ready_values["ke"].dot(self.latest_result)
        dp, n, err = gauss_seidel_iteration_film(
            k,
            f,
            np.zeros_like(f),
            self.latest_result,
            n=self._n,
            damp=self._gdamp,
            reynold=self.args["reynold"],
            error_set=self._err,
        )
        # else: dp = gauss_seidel_iteration_film(k, f, self._dp[-1], self.latest_result , n=self._n, damp=self._damp,
        # reynold=self.args['reynold'], error_set=self._err)
        if save_dp:
            self._dp.append(dp)
        p = self.latest_result + dp * self._damp

        self.add_result(p)
        self.matrixs["ke_all"] = self.matrixs["ke"].copy()
        self.rights["fe_all"] = self.rights["fe"].copy()
        self.matrixs["ke"] = self._ready_values["ke"].copy()
        self.rights["fe"] = self._ready_values["fe"].copy()
        self.update_to_nodes()

    def solve(self, **kwargs):
        """
        Solve the current linear system and update model state.

        :param **kwargs: Optional keyword arguments.
        :return: Computed value(s) for the current operation.
        """
        save_dp = kwargs.get("save_dp", False)
        x0 = np.zeros_like(self.rights["fe"])
        if self._gmf is True:
            result, n, err = gauss_seidel_iteration_matrix(
                self.matrixs["ke"],
                self.rights["fe"],
                x0,
                x0,
                n=self._n,
                damp=self._gdamp,
                reynold=self.args["reynold"],
                error_set=self._err,
            )
        else:
            result, n, err = gauss_seidel_iteration_film(
                self.matrixs["ke"],
                self.rights["fe"],
                x0,
                x0,
                n=self._n,
                damp=self._gdamp,
                reynold=self.args["reynold"],
                error_set=self._err,
            )
        if save_dp:
            self._dp.append(x0)
        self.add_result(result)
        self.update_to_nodes()
        return result

    def init(self):
        self.pre_solve(csc=False)
        result = self.solve()
        self.matrixs_init_for_iter_solve()
        return result


class LsqFilm(NewtonFilm):
    def iter_solve(self, *args, **kwargs):
        """
        Run one nonlinear iteration step according to the selected Reynolds mode.

        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        """
        k = self.matrixs["ke"]
        k = scipy.sparse.csc_matrix(k)
        f = self.rights["fe"] - self._ready_values["ke"].dot(self.latest_result)
        res = scipy.optimize.lsq_linear(k, f, bounds=(-self.latest_result, np.inf))
        self._dp = res.x
        p = self.latest_result + self._dp
        p = self._reynold_boundary(p)
        print(res.cost)
        self.add_result(p)

        self.matrixs["ke_all"] = self.matrixs["ke"].copy()
        self.rights["fe_all"] = self.rights["fe"].copy()
        self.matrixs["ke"] = self._ready_values["ke"].copy()
        self.rights["fe"] = self._ready_values["fe"].copy()
        self.update_to_nodes()


class PSetFilmBoundary(BaseBoundary):
    """Penalty-based boundary helper for fixed-pressure constraints."""

    def __init__(self, penalty=1e10, p_set=0):
        """
        Initialize this object with the provided configuration.

        :param penalty: Penalty coefficient used for fixed-pressure constraints.
        :param p_set: Prescribed boundary pressure value.
        """
        super().__init__()
        self.penalty = penalty
        self.p_set = p_set

    def set(self, model: FilmModel, *args, **kwargs):
        up_down = kwargs.get("up_down", True)
        left_right = kwargs.get("left_right", True)
        if up_down:
            self.set_up_down_to_zero(model)
        if left_right:
            self.set_left_right_to_zero(model)

    def set_up_down_to_zero(self, model: FilmModel):
        """
        Apply fixed-pressure constraints to upper and lower boundaries.

        :param model: Film model instance.
        """
        z_lim = model.args["z_lim"]
        u_boundary = model.node_manager.search(1, z_lim[0], number=True)
        d_boundary = model.node_manager.search(1, z_lim[1], number=True)
        boundary_nodes = u_boundary + d_boundary
        model.matrixs["ke"][boundary_nodes, boundary_nodes] = self.penalty
        model.rights["fe"][boundary_nodes] = self.penalty * self.p_set

    def set_left_right_to_zero(self, model: FilmModel):
        x_lim = model.args["x_lim"]
        l_boundary = model.node_manager.search(0, x_lim[0], number=True)
        r_boundary = model.node_manager.search(0, x_lim[1], number=True)
        boundary_nodes = l_boundary + r_boundary
        model.matrixs["ke"][boundary_nodes, boundary_nodes] = self.penalty
        model.rights["fe"][boundary_nodes] = self.penalty * self.p_set


class ThicknessModel(BaseSimpleModel):
    """Apply and combine film-thickness modification methods."""

    # logger_level = 'debug'

    def __init__(self, **thickness_args):
        """
        Initialize this object with the provided configuration.

        :param **thickness_args: Thickness-model configuration arguments.
        """
        super().__init__()
        self._thickness_args = thickness_args
        self._methods = {
            "e_angle": self.set_thickness_with_e_angle,
            "ex_ey": self._set_thickness_with_ex_ey,
            "add_tank": self._add_tank,
        }
        self._useing_methods = {"e_angle": self.set_thickness_with_e_angle}

    def init(self):
        pass

    def input(self, method: str = None, **kwargs):
        """
        :param method:options:'ex_ey','e_angle'

        if choose 'ex_ey', ex,ey must be input in kwargs

        if choose 'e_angle', e,angle must be input in kwargs
        """
        if method is None:
            return

        self._set_method(method)
        for key, value in kwargs.items():
            self._thickness_args[key] = value

    # Reset and re-apply all active thickness modifiers to the model.
    def output(self, model: FilmModel):
        """
        Run solver output step and return updated solution data.

        :param model: Film model instance.
        :return: Computed value(s) for the current operation.
        """
        self._reset_thickness(model)
        self._apply_method(model)

    def set_thickness_with_e_angle(self, model):
        """
        Apply thickness distribution from eccentricity magnitude and angle.

        :param model: Film model instance.
        """
        e = self._thickness_args["e"]
        angle = self._thickness_args["angle"]
        for node in model.nodes.values():
            node.h += 1 + e * np.cos(node.coords[0] - angle)

    # Apply eccentricity components directly in x/y form.
    def _set_thickness_with_ex_ey(self, model):
        """
        Apply thickness distribution from x/y eccentricity components.

        :param model: Film model instance.
        """
        ex = self._thickness_args["ex"]
        ey = self._thickness_args["ey"]
        for node in model.nodes.values():
            node.h += 1 + ex * np.sin(node.coords[0]) - ey * np.cos(node.coords[0])

    def _set_method(self, method_name: str):
        """
        set the method to calculate the thickness, the method name 'e_angle' or 'ex_ey' is conflict.
        """
        if method_name == "e_angle" and "ex_ey" in self._useing_methods.keys():
            self._useing_methods.pop("ex_ey")
        elif method_name == "ex_ey" and "e_angle" in self._useing_methods.keys():
            self._useing_methods.pop("e_angle")
        self._useing_methods[method_name] = self._methods[method_name]

    @staticmethod
    def _reset_thickness(model):
        """
        reset the thickness of the film to zero
        """
        for node in model.nodes.values():
            node.h = 0

    def _add_tank(self, model):
        """
        add the tank in the film
        """
        x_lim = model.args["x_lim"]
        z_lim = model.args["z_lim"]
        xrange = self._thickness_args["xrange"]
        xrange = np.array(xrange).reshape((-1, 2))
        zrange = self._thickness_args["zrange"]
        zrange = np.array(zrange).reshape((-1, 2))
        h = self._thickness_args["h_tank"]
        for xr, zr in zip(xrange, zrange):
            xr = [
                x_lim[0] + xr[0] * (x_lim[1] - x_lim[0]),
                x_lim[0] + xr[1] * (x_lim[1] - x_lim[0]),
            ]
            zr = [
                z_lim[0] + zr[0] * (z_lim[1] - z_lim[0]),
                z_lim[0] + zr[1] * (z_lim[1] - z_lim[0]),
            ]
            for node in model.nodes.values():
                if xr[0] < node.coords[0] < xr[1] and zr[0] < node.coords[1] < zr[1]:
                    node.h += h

    def _apply_method(self, model):
        for method in self._useing_methods.values():
            method(model)

    def calc_error(self, *args, **kwargs):
        return 0.0

    def calc_is_finished(self):
        return True

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        pass


class FilmPostProcess(BasePostProcess):
    """Post-processing utilities for pressure, capacity, and friction."""

    def __init__(self, model: FilmModel):
        super().__init__()
        self.model = model
        size = model.args["size"]
        y = [node.coords[0] for node in model.nodes.values()]
        x = [node.coords[1] for node in model.nodes.values()]
        self.X, self.Y = np.array(x), np.array(y)
        self.X = self.X.reshape(size[0] + 1, size[1] + 1)
        self.Y = self.Y.reshape(size[0] + 1, size[1] + 1)

    @property
    def p(self):
        size = self.model.args["size"]
        result = self.model.results[-1][0 : len(self.model.nodes)].reshape(
            size[0] + 1, size[1] + 1
        )
        return result

    @property
    def h(self):
        size = self.model.args["size"]
        result = np.array([node.h for node in self.model.nodes.values()]).reshape(
            size[0] + 1, size[1] + 1
        )
        return result

    def plot_p_mesh(self, save_path=None, show=True, **save_args):
        """
        Plot pressure distribution as a surface mesh.

        :param save_path: Figure output path.
        :param show: Whether to display the generated figure.
        :param **save_args: Optional keyword arguments.
        """
        result = self.p
        return self._plot_surface(result, save_path, show, **save_args)

    def plot_h_mesh(self):
        """Plot film-thickness distribution as a surface mesh."""
        result = self.h
        return self._plot_surface(result)

    def _plot_surface(self, result, save_path=None, show=True, **save_args):
        """
        Render a generic 3D surface plot for field data.

        :param result: Result vector to be written back to nodes.
        :param save_path: Figure output path.
        :param show: Whether to display the generated figure.
        :param **save_args: Optional keyword arguments.
        """
        # TODO:fix
        fig = plt.figure()
        ax = plt.axes(projection="3d")
        ax.plot_surface(
            self.Y.T,
            self.X.T,
            result.T,
            rstride=1,  # Row sampling step for surface mesh.
            cstride=1,  # Column sampling step for surface mesh.
            cmap="rainbow",
        )
        if show:
            plt.show()
        if save_path is not None:
            fig.savefig(save_path, **save_args)
            plt.close(fig)
        return fig, ax

    def plot_p_x(self, coord_x, error=1e-6, **kwargs):
        # TODO:fix
        """
        Plot pressure profile along a specified circumferential position.

        :param coord_x: Normalized circumferential position for profile extraction.
        :param error: Tolerance used for coordinate matching.
        :param **kwargs: Optional keyword arguments.
        """
        lx = (
            self.model.args["x_lim"][1] - self.model.args["x_lim"][0]
        ) / self.model.args["nx"]
        coord_x = (
            np.round(self.model.args["size"][0] * coord_x) * lx
            + self.model.args["x_lim"][0]
        )
        nodes = [
            node
            for node in self.model.nodes.values()
            if abs(node.coords[0] - coord_x) < error
        ]
        coord_zs = [node.coords[1] for node in nodes]
        p = [node.p for node in nodes]
        if kwargs.get("show", True):
            plt.plot(coord_zs, p)
            plt.show()
        return coord_zs, p

    def plot_p_z(self, coord_z, error=1e-6, **kwargs):
        """
        Plot pressure profile along a specified axial position.

        :param coord_z: Normalized axial position for profile extraction.
        :param error: Tolerance used for coordinate matching.
        :param **kwargs: Optional keyword arguments.
        """
        z_lim = self.model.args["z_lim"]
        coord_z = z_lim[0] + coord_z * (z_lim[1] - z_lim[0])
        nodes = [
            node
            for node in self.model.nodes.values()
            if abs(node.coords[1] - coord_z) < error
        ]
        coord_xs = [node.coords[0] for node in nodes]
        p = [node.p for node in nodes]
        if kwargs.get("show", True):
            plt.plot(coord_xs, p)
            plt.show()
        return coord_xs, p

    def calc_capacity(self, calc=True, nodim=True):
        if nodim:
            return self.calc_capacity_nodim(calc)
        else:
            return self.calc_capacity_dim(calc)

    def calc_capacity_nodim(self, calc=True):
        if calc:
            f = np.array([elem.intergral() for elem in self.model.elems.values()])
            mean_coords = np.array(
                [elem.mean_coords()[0] for elem in self.model.elems.values()]
            )
            fx = (f.dot(np.sin(mean_coords))).sum()
            fy = -(f.dot(np.cos(mean_coords))).sum()
            self.postprocess_result["fx"] = fx
            self.postprocess_result["fy"] = fy
            return np.array((fx, fy))
        else:
            fx = self.postprocess_result["fx"]
            fy = self.postprocess_result["fy"]
            return np.array((fx, fy))

    def calc_capacity_dim(self, calc=True):
        """
        Convert nondimensional load to dimensional force values.

        :param calc: Whether to recalculate instead of using cached values.
        :return: Computed value(s) for the current operation.
        """
        fx, fy = self.calc_capacity_nodim(calc)
        dim = self.model.args["ps"] * self.model.args["l"] / 2 * self.model.args["r"]
        fx = fx * dim
        fy = fy * dim
        self.postprocess_result["fx_dim"] = fx
        self.postprocess_result["fy_dim"] = fy
        return np.array((fx, fy))

    # def calc_friction(self, calc=True, nodim=True):
    #     """
    #     :param calc: if recalculate
    #     :param nodim: if nodim, the friction will be nondimensionalized to the dimensionless friction power,
    #                   else the friction force (N)
    #     """
    #     model = self.model
    #     elems = model.elems.values()
    #     elems = np.array(list(elems))
    #     nx = model.args['nx']
    #     nz = model.args['nz']
    #     elems = elems.reshape((nx, nz))
    #     friction = 0
    #     for i in range(nz):
    #         # calculate the film thickness of the broken film
    #         hs = [np.mean([node.h for node in elem.nodes.values()]) for elem in elems[:, i] if not elem.film_exist()]
    #         if len(hs) > 0:
    #             hb = np.min(hs)
    #         else:
    #             hb = 1
    #         # if film break, the hb is input to the friction_force
    #         pt0 = np.sum([elem.friction_force(hb=hb) for elem in elems[:, i] if not elem.film_exist()])
    #         # if film exist, as usual
    #         pt1 = np.sum([elem.friction_force() for elem in elems[:, i] if elem.film_exist()])
    #         friction += pt0 + pt1
    #     if nodim:
    #         args1 = model.args
    #         P = friction * args1['w_rad'] * args1['r']
    #         friction = P * args1['c'] / (
    #                 np.pi ** 3 * args1['u'] * args1['w_hz'] ** 2 * args1['l'] * (2 * args1['r']) ** 3)
    #     return friction

    def calc_friction(self, calc=True, nodim=True):
        """
        Compute film friction with cavitation-aware element integration.

        :param calc: Whether to recalculate instead of using cached values.
        :param nodim: Whether to output nondimensional results.
        :return: Computed value(s) for the current operation.
        """
        model = self.model
        args = model.args
        nx = args["nx"]
        nz = args["nz"]

        # ==========================================
        # Load physical constants used by friction-force model.
        # ==========================================
        miu = args["miu"]
        w = args["w_rad"]
        r = args["r"]
        c = args["c"]
        ps = args["ps"]
        l_scale = args["l"]

        # ==========================================
        # Read latest nodal pressure/thickness/coordinates into vectors.
        # ==========================================
        num_nodes = (nx + 1) * (nz + 1)
        # Exclude extra DOFs and keep only pressure node unknowns.
        p_1d = model.latest_result[:num_nodes]
        h_1d = np.array([node.h for node in model.node_manager.nodes.values()])
        x_1d = np.array([node.coords[0] for node in model.node_manager.nodes.values()])
        z_1d = np.array([node.coords[1] for node in model.node_manager.nodes.values()])

        P = p_1d.reshape((nx + 1, nz + 1))
        H = h_1d.reshape((nx + 1, nz + 1))
        X = x_1d.reshape((nx + 1, nz + 1))
        Z = z_1d.reshape((nx + 1, nz + 1))

        # ==========================================
        # Build per-element corner arrays from nodal fields.
        # The suffix 0..3 denotes the local node index in one element.
        # ==========================================
        P0 = P[:-1, :-1]
        P1 = P[1:, :-1]
        P2 = P[:-1, 1:]
        P3 = P[1:, 1:]
        H0 = H[:-1, :-1]
        H1 = H[1:, :-1]
        H2 = H[:-1, 1:]
        H3 = H[1:, 1:]
        X0 = X[:-1, :-1]
        X3 = X[1:, 1:]
        Z0 = Z[:-1, :-1]
        Z3 = Z[1:, 1:]

        # ==========================================
        # Convert local element spans from nondimensional to dimensional scales.
        # ==========================================
        lx = np.abs(X3 - X0) * r
        lz = np.abs(Z3 - Z0) * l_scale / 2

        # Approximate x-direction pressure gradients on the two element sides.
        dp_dx0 = (P1 - P0) * ps / lx
        dp_dx1 = (P3 - P2) * ps / lx

        # ?
        h0 = H0 * c
        h1 = H1 * c
        h2 = H2 * c
        h3 = H3 * c

        # ==========================================
        # Pressure-driven shear contribution integrated over each element.
        # ==========================================
        # Average two side gradients over four local nodes.
        pt0_matrix = (
            ((dp_dx0 * h0 + dp_dx0 * h1 + dp_dx1 * h2 + dp_dx1 * h3) / 2 / 4) * lx * lz
        )

        # ==========================================
        # Velocity-driven shear term for full-film and cavitated regions.
        # ==========================================
        lh_mean = (1 / h0 + 1 / h1 + 1 / h2 + 1 / h3) / 4
        lh_mean2 = (1 / (h0**2) + 1 / (h1**2) + 1 / (h2**2) + 1 / (h3**2)) / 4

        # Cavitation mask: True means all local nodal pressures are positive.
        err = 1e-10
        film_exist_mask = (P0 > err) & (P1 > err) & (P2 > err) & (P3 > err)

        # hb:
        # Mean nondimensional thickness per element.
        h_mean_nodim = (H0 + H1 + H2 + H3) / 4
        # Keep only cavitated elements when searching fallback thickness.
        h_cav_nodim = np.where(film_exist_mask, np.inf, h_mean_nodim)

        hb_col_nodim = np.min(h_cav_nodim, axis=0)
        # Use default fallback thickness when no cavitation exists in a column.
        hb_col_nodim[np.isinf(hb_col_nodim)] = 1.0

        # Broadcast column fallback thickness to full element grid.
        hb_matrix_nodim = np.tile(hb_col_nodim, (nx, 1))
        hb_matrix = hb_matrix_nodim * c

        # Full-film and cavitated viscous contributions.
        pt1_full = miu * w * r * lh_mean * lx * lz
        pt1_cav = miu * w * r * hb_matrix * lh_mean2 * lx * lz

        # Select contribution by local film-existence state.
        pt1_matrix = np.where(film_exist_mask, pt1_full, pt1_cav)

        # ==========================================
        # Integrate total friction over all elements.
        # ==========================================
        Ff_total = np.sum(pt0_matrix + pt1_matrix)

        if nodim:
            P_power = Ff_total * w * r
            Ff_total = (
                P_power
                * c
                / (np.pi**3 * miu * args["w_hz"] ** 2 * l_scale * (2 * r) ** 3)
            )

        return Ff_total


class FilmOutput(BaseOutput):
    """Output adapter that exposes force and friction results."""

    def __init__(self, model: FilmModel):
        super().__init__()
        self._model = model
        self.post_process = FilmPostProcess(model)

    def __call__(self, calc, **kwargs):
        """
        Call this output adapter and return current film outputs.

        :param calc: Whether to recalculate instead of using cached values.
        :param **kwargs: Optional keyword arguments.
        """
        return self.output(calc, **kwargs)

    def output(self, calc, **kwargs):
        """
        Run solver output step and return updated solution data.

        :param calc: Whether to recalculate instead of using cached values.
        :param **kwargs: Optional keyword arguments.
        :return: Computed value(s) for the current operation.
        """
        nodim = kwargs.get("nodim", False)
        force = self.post_process.calc_capacity(calc, nodim=nodim)
        friction = self.post_process.calc_friction(calc, nodim=nodim)
        return {"force": force, "w": self._model.args["w"], "friction": friction}


class FilmInput(dict):
    def __init__(
        self,
        w=1000,
        x0=0.0,
        lx=360.0,
        lz=2.0,
        nx=59,
        nz=39,
        miu=0.0195,
        c=80e-6,
        rho=872.0,
        r=0.04,
        l=0.06,
        ps=1e6,
        reynold=True,
    ):
        """
        Initialize film-input parameters and build normalized solver inputs.

        :param w: Rotor speed in rpm.
        :param x0: Start angle in degrees.
        :param lx: Angular span in degrees.
        :param lz: Axial length ratio used by the film grid.
        :param nx: Number of circumferential grid divisions.
        :param nz: Number of axial grid divisions.
        :param miu: Dynamic viscosity.
        :param c: Radial clearance.
        :param rho: Lubricant density.
        :param r: Journal radius.
        :param l: Bearing length.
        :param ps: Supply pressure.
        :param reynold: Reynolds-mode flag for cavitation handling.
        """
        super().__init__()
        self.input(w, x0, lx, lz, nx, nz, miu, c, rho, r, l, ps, reynold)

    def input(self, w, x0, lx, lz, nx, nz, miu, c, rho, r, l, ps, reynold):
        x0 = x0 / 180 * math.pi  # Convert start angle from degree to radian.
        lx = lx / 180 * math.pi  # Convert angular length from degree to radian.
        lr = l / 2 / r  # Aspect ratio in the Reynolds formulation.
        self["lx"] = lx / nx
        self["lz"] = lz / nz
        self["lr"] = lr
        lambda_value = 3 / 2 * miu * (w * 2 * math.pi / 60) * l**2 / ps / c**2
        self["lambda"] = lambda_value
        self["lambda0"] = lambda_value
        self["x_lim"] = [x0, x0 + lx]
        self["y_lim"] = [-1, -1 + lz]
        self["size"] = [nx, nz]
        self["ps"] = ps
        self["reynold"] = reynold
        self["l"] = l
        self["r"] = r
        self["w"] = w
        self["c"] = c
        self["miu"] = miu
        self["miu0"] = miu
        self["rho"] = rho


class FilmSystem(BaseSystem):
    # delogger_level = 'info'

    # Film system wrapper that coordinates main and auxiliary models.
    def __init__(self, film_model: NewtonFilm, *simple_models, **args):
        """
        Initialize this object with the provided configuration.

        :param film_model: Main film solver model.
        :param *simple_models: Auxiliary simple models coupled with the film model.
        :param **args: Optional positional arguments.
        """
        super().__init__(film_model, *simple_models, **args)
        self._output = FilmOutput(film_model)
        self.node_link = args.get("node_link", None)
        self.max_iter = args.get("max_iter", 30)
        self.notifier = args.get("notifier")
        self._temp_res = {}
        self._result = pd.DataFrame()
        self.final_iter = 0

    @property
    def postprocess(self):
        return self._output.post_process

    def calc_capacity(self, **kwargs):
        """
        Compute bearing load capacity in nondimensional or dimensional form.

        :param **kwargs: Optional keyword arguments.
        :return: Computed value(s) for the current operation.
        """
        calc = kwargs.get("calc", True)
        nodim = kwargs.get("nodim", True)
        return self._output.post_process.calc_capacity(calc=calc, nodim=nodim)

    def calc_friction(self, **kwargs):
        """
        Compute film friction with cavitation-aware element integration.

        :param **kwargs: Optional keyword arguments.
        :return: Computed value(s) for the current operation.
        """
        calc = kwargs.get("calc", True)
        nodim = kwargs.get("nodim", True)
        return self._output.post_process.calc_friction(calc=calc, nodim=nodim)

    def plot_p_mesh(self, **kwargs):
        return self._output.post_process.plot_p_mesh(**kwargs)

    def init(self):
        """Initialize solver state and cache data for iterative updates."""
        self._result = pd.DataFrame()
        self.main_model.init()
        for simple_model in self.simple_models:
            if hasattr(simple_model, "init"):
                simple_model.init()

    # Couple one main film model with optional auxiliary sub-models.
    def solve(self, init: bool = True, **kwargs):
        """
        Solve the current linear system and update model state.

        :param init: Whether to run initialization before solving.
        :param **kwargs: Optional keyword arguments.
        :return: Computed value(s) for the current operation.
        """
        if init:
            self.main_model.init()
            for simple_model in self.simple_models:
                if hasattr(simple_model, "init"):
                    simple_model.init()
        if hasattr(self.main_model, "reset_adaptive_damp"):
            self.main_model.reset_adaptive_damp()
        for i in range(self.max_iter):
            # Update auxiliary models before each film solve step.
            for simple_model in self.simple_models:
                simple_model.input()
                simple_model.output(self.main_model)
            self.main_model.output(**kwargs)
            if self.calc_is_finished():
                self.final_iter = i
                break
        else:
            self.final_iter = self.max_iter
            print("iter of filmsystem is max")
        self.main_model.update_to_nodes()

    def calc_is_finished(self):
        simple_flags = [
            simple_model.calc_is_finished() for simple_model in self.simple_models
        ]
        simple_flag = all(simple_flags) if simple_flags else True
        return self.main_model.calc_is_finished() and simple_flag

    def _input_rotoru(self, uxy: np.ndarray, *args, **kwargs):
        """
        Inject displacement input and update eccentricity state.

        :param uxy: Rotor displacement input [ux, uy].
        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        """
        if np.size(uxy) != 2:
            raise Exception("size of uxy must be 2")
        ux = uxy[0]
        uy = uxy[1]
        nodim = kwargs.get("nodim", False)
        if nodim:
            ex = ux
            ey = uy
        else:
            ex = ux / self.main_model.args["c"]
            ey = uy / self.main_model.args["c"]
        if np.sqrt(ex**2 + ey**2) > 1:
            message = "Input eccentricity is greater than 1."
            if self.notifier is not None:
                notify = getattr(self.notifier, "notify", None)
                if notify is None:
                    raise TypeError("notifier must implement notify(message, subject=None)")
                notify(message, subject="Calculation error")
            raise ValueError("ex^2 + ey^2 must be less than 1")
        # Apply eccentricity to the active thickness model.
        if hasattr(self, "thickness"):
            thickness = self.thickness
        else:
            thickness = ThicknessModel()
        thickness.input("ex_ey", ex=ex, ey=ey)
        thickness.output(self.main_model)

    def _input_rotorut(self, uxyt: np.ndarray, *args, **kwargs):
        """
        Inject velocity input and update squeeze-term parameters.

        :param uxyt: Rotor velocity input [ux_dot, uy_dot].
        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        """
        if np.size(uxyt) != 2:
            raise Exception("size of uxyt must be 2")
        dxt = uxyt[0]
        dyt = uxyt[1]
        c = self.main_model.args["c"]
        vf = self.main_model.args["vf"]
        w = self.main_model.args["w"]
        nodim = kwargs.get("nodim", False)
        if nodim:
            self.main_model.args["dxt"] = dxt * c * (vf * w / 60 * 2 * np.pi)
            self.main_model.args["dyt"] = dyt * c * (vf * w / 60 * 2 * np.pi)
            self.main_model.args["xct"] = dxt
            self.main_model.args["yct"] = dyt
        else:
            self.main_model.args["dxt"] = dxt
            self.main_model.args["dyt"] = dyt
            self.main_model.args["xct"] = dxt / c / (vf * w / 60 * 2 * np.pi)
            self.main_model.args["yct"] = dyt / c / (vf * w / 60 * 2 * np.pi)
        # logger.info(
        # Keep optional logging disabled by default.

    def input(self, uxy, uxyt, *args, **kwargs):
        self._input_rotoru(uxy, *args, **kwargs)
        self._input_rotorut(uxyt, *args, **kwargs)

    def output(self, calc=True, **kwargs):
        """
        Run solver output step and return updated solution data.

        :param calc: Whether to recalculate instead of using cached values.
        :param **kwargs: Optional keyword arguments.
        :return: Computed value(s) for the current operation.
        """
        self.solve(**kwargs)
        output = self._output(calc, **kwargs)
        self._temp_res.update(output)
        self.signal.lead_loop("finish_signal")
        return output

    def clear_simple_models(self):
        """Remove all attached auxiliary simple models."""
        self.simple_models.clear()

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        Save film-model results and metadata to structured output nodes.

        :param tofile: Whether to write results to files.
        :param path: Output directory path.
        :param name: Data name used by matrix_process.
        :param *args: Optional positional arguments.
        :param **kwargs: Optional keyword arguments.
        """
        if path is None:
            path = "pad"
        if name is None:
            name = "pad_output"
        res = self._result
        res = DataFrameResult({name: res})
        parent_node = SaveTreeNode(path, res)
        child_node = [
            sm.save(path=None, name=type(sm).__name__ + str(num), tofile=False)
            for num, sm in enumerate(self.simple_models)
        ]
        child_node.append(
            self.main_model.save(
                path=None, name=type(self.main_model).__name__, tofile=False
            )
        )
        parent_node.add_children(child_node)
        if tofile:
            parent_node.save_to_file()
        return parent_node

    def finish_signal(self):
        if self._result.shape[0] == 0:
            self._result = pd.DataFrame(columns=list(self._temp_res.keys()))
        self._result.loc[self._result.shape[0]] = list(self._temp_res.values())


class FilmBoundary(BaseBoundary):
    def __init__(self, **boundary_args):
        """
        boundary_args = {'coe':bool,'p_set':float}

        if coe is True, the boudaries of left and right are connected.

        p_set is the air pressure

        default:coe=True, p_set=0

        """
        self._boundary_args = {
            "coe": boundary_args.get("coe", True),
            "p_set": boundary_args.get("p_set", 0),
        }

    @property
    def args(self):
        return self._boundary_args

    def set_coe(self, coe: bool):
        """
        Enable or disable circumferential continuity between left and right boundaries.
        """
        self._boundary_args["coe"] = coe

    def set_p(self, p_set: [int, float]):
        """
        Set the boundary pressure value used by fixed-pressure boundary conditions.
        """
        # Ensure scalar numeric pressure value.
        if not isinstance(p_set, (int, float)):
            raise Exception("p_set must be a number")
        self._boundary_args["p_set"] = p_set

    def set(self, model: FilmModel, *args, **kwargs):
        """
        Apply boundary conditions to the film model matrix and right-hand side.
        Options:
        method:default = 'round', 'round' or 'nodes_p'
        p_set: fixed pressure value applied to selected boundary nodes.

        Notes:
        - For half-Reynolds mode, side boundaries can be coupled when coe=True.
        - For Reynolds mode, coe=True is not supported.
        """
        method = kwargs.get("method", "round")
        all_freedoms = model.node_manager.freedoms
        matrix = model.matrix_process.matrixs["ke"]
        right = model.matrix_process.rights["fe"]

        reynold = model.args.get("reynold", False)

        if reynold in [False, "half_reynold"]:
            if "p_set" in kwargs.keys():
                p_set = kwargs["p_set"]
            else:
                p_set = np.float64(0)
            if method == "round":
                x_lim = model.args["x_lim"]
                y_lim = model.args["z_lim"]
                r_boundary = model.node_manager.search(0, x_lim[0], number=True)
                l_boudary = model.node_manager.search(0, x_lim[1], number=True)
                u_boudary = model.node_manager.search(1, y_lim[0], number=True)
                d_boudary = model.node_manager.search(1, y_lim[1], number=True)
                # Ensure side boundaries do not overlap with top/bottom boundaries.
                boundary.check_boundary(r_boundary + l_boudary, u_boudary)
                boundary.check_boundary(r_boundary + l_boudary, d_boudary)

                kwargs = self._boundary_args

                if "coe" in kwargs.keys():
                    coe = kwargs["coe"]
                else:
                    coe = False

                kp1, fp1 = set_value_boundary(all_freedoms, u_boudary, p_set=p_set)
                kp2, fp2 = set_value_boundary(all_freedoms, d_boudary, p_set=p_set)
                if coe:
                    kp3, fp3 = set_continuity_boundary(
                        r_boundary, l_boudary, all_freedoms
                    )
                    # Coupled side boundaries with fixed top/bottom pressures.
                    (
                        model.matrix_process.matrixs["ke"],
                        model.matrix_process.rights["fe"],
                    ) = self.couple_boundary_matrix(
                        matrix, right, [kp1, kp2, kp3], [fp1, fp2, fp3]
                    )
                elif not coe:
                    kp3, fp3 = set_value_boundary(all_freedoms, r_boundary, p_set=p_set)
                    kp4, fp4 = set_value_boundary(all_freedoms, l_boudary, p_set=p_set)
                    (
                        model.matrix_process.matrixs["ke"],
                        model.matrix_process.rights["fe"],
                    ) = self.couple_boundary_matrix(
                        matrix, right, [kp1, kp2, kp3, kp4], [fp1, fp2, fp3, fp4]
                    )
            elif method == "nodes_p":
                kp1, fp1 = set_value_boundary(
                    all_freedoms, kwargs["nodes_number"], p_set=p_set
                )
                (
                    model.matrix_process.matrixs["ke"],
                    model.matrix_process.rights["fe"],
                ) = self.couple_boundary_matrix(matrix, right, [kp1], [fp1])
        elif reynold in [True, "reynold"]:
            if method == "round":
                p_set = kwargs.get("p_set", np.float64(0))
                coe = kwargs.get("coe", self._boundary_args.get("coe", False))

                x_lim = model.args["x_lim"]
                y_lim = model.args["z_lim"]
                r_boundary = model.node_manager.search(0, x_lim[0], number=True)
                l_boudary = model.node_manager.search(0, x_lim[1], number=True)
                u_boudary = model.node_manager.search(1, y_lim[0], number=True)
                d_boudary = model.node_manager.search(1, y_lim[1], number=True)

                # Reynolds-FB solve should avoid Lagrange-multiplier augmentation;
                # use penalty form to keep the unknown dimension unchanged.
                pset_boundary = PSetFilmBoundary(penalty=1e10, p_set=p_set)
                pset_boundary.set_up_down_to_zero(model)

                if coe:
                    # Enforce p_right == p_left by penalty coupling.
                    ke = model.matrix_process.matrixs["ke"]
                    if not sp.isspmatrix_lil(ke):
                        ke = ke.tolil()
                    penalty = 1e8
                    for rn, ln in zip(r_boundary, l_boudary):
                        ke[rn, rn] += penalty
                        ke[ln, ln] += penalty
                        ke[rn, ln] -= penalty
                        ke[ln, rn] -= penalty
                    model.matrix_process.matrixs["ke"] = ke.tocsc()
                else:
                    pset_boundary.set_left_right_to_zero(model)

    @staticmethod
    def couple_boundary_matrix(
        matrix: np.ndarray, right: np.ndarray, kps: list, fps: list
    ):
        return couple_boundary_matrix(matrix, right, kps, fps)


def _find_film_zone(xs, ps):
    """
    Return the first and last x-locations where pressure is non-zero.

    :param xs: Coordinate array along one profile.
    :param ps: Supply pressure.
    :return: Computed value(s) for the current operation.
    """
    ps = np.array(ps)
    xs = np.array(xs)
    nonzero_idx = np.nonzero(ps)[0]
    ps = ps[nonzero_idx]
    xs = xs[nonzero_idx]
    if len(ps) == 0:
        return None
    else:
        return xs[0], xs[-1]


@njit
def area(x1, y1, x2, y2, x3, y3):
    """
    Compute triangle area from three points.

    :param x1: x-coordinate of first point.
    :param y1: y-coordinate of first point.
    :param x2: x-coordinate of second point.
    :param y2: y-coordinate of second point.
    :param x3: x-coordinate of third point.
    :param y3: y-coordinate of third point.
    :return: Computed value(s) for the current operation.
    """
    return np.abs((x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)) / 2.0)


@njit
def order_vertices(vertices):
    """
    Sort quadrilateral vertices in counter-clockwise order.

    :param vertices: Polygon vertices array.
    :return: Computed value(s) for the current operation.
    """
    # Compute polygon center.
    center_x = np.sum(vertices[:, 0]) / 4
    center_y = np.sum(vertices[:, 1]) / 4
    center = (center_x, center_y)

    # Compute angle of each vertex around center.
    angles = np.arctan2(vertices[:, 1] - center[1], vertices[:, 0] - center[0])

    # Sort vertices in counter-clockwise order.
    sorted_indices = np.argsort(angles)

    # Reordered vertices.
    sorted_vertices = vertices[sorted_indices]

    return sorted_vertices


@njit
def is_point_in_polygon(px, py, v1, v2, v3, v4, tolerance=1e-9):
    """
    Check whether a point lies inside a quadrilateral polygon.

    :param px: x-coordinate of the query point.
    :param py: y-coordinate of the query point.
    :param v1: First polygon vertex.
    :param v2: Second polygon vertex.
    :param v3: Third polygon vertex.
    :param v4: Fourth polygon vertex.
    :param tolerance: Numerical tolerance for geometric comparison.
    :return: Computed value(s) for the current operation.
    """
    x1, y1 = v1
    x2, y2 = v2
    x3, y3 = v3
    x4, y4 = v4
    # Polygon area from two triangles.
    A_polygon = area(x1, y1, x2, y2, x3, y3) + area(x1, y1, x3, y3, x4, y4)

    # Areas of four triangles with test point.
    A1 = area(px, py, x1, y1, x2, y2)
    A2 = area(px, py, x2, y2, x3, y3)
    A3 = area(px, py, x3, y3, x4, y4)
    A4 = area(px, py, x4, y4, x1, y1)

    # Point is inside if summed triangle area matches polygon area.
    return np.abs(A_polygon - (A1 + A2 + A3 + A4)) < tolerance


def check_point_in_polygon(vertices, point, tolerance=1e-9):
    """
    Validate polygon input and run inside-polygon test.

    :param vertices: Polygon vertices array.
    :param point: Query point coordinates.
    :param tolerance: Numerical tolerance for geometric comparison.
    :return: Computed value(s) for the current operation.
    """
    if len(vertices) != 4:
        raise ValueError("Four vertex coordinates are required.")
    vertices = np.array(vertices, dtype=np.float64)
    point = np.array(point, dtype=np.float64)
    # Ensure a consistent vertex ordering before inside-polygon test.
    ordered_vertices = order_vertices(vertices)

    return is_point_in_polygon(point[0], point[1], *ordered_vertices, tolerance)
