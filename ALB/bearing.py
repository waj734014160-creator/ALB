# coding: utf-8
import copy
import logging
import math
import unittest
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import scipy.sparse as sp
from tqdm import tqdm

from ALB.core.component import BaseCSystem
from ALB.core.fem import ElemManager, MatrixProcess, Mesh, NodeManager
from ALB.config import FPBConfig, HydConfig
from ALB.core.validation import get_unit_system
from ALB.physics.film import (
    FilmBoundary,
    FilmModel,
    FilmPostProcess,
    FilmSystem,
    GaussSeidelFilm,
    LsqFilm,
    NewtonFilm,
    NodimNewtonFilm,
    PSetFilmBoundary,
    RectFilmElem,
    RectFilmNode,
    SkfemNewtonFilm,
    ThicknessModel,
)
from ALB.core.numerics.dynamic import (
    calc_fe_dx,
    calc_fe_dxt,
    calc_fe_dy,
    calc_fe_dyt,
    calc_ke_dx,
    calc_ke_dy,
)
from ALB.core.numerics.static import calc_ke
from ALB.orifice import Orifice, Orifices
from ALB.results import DataFrameResult, SaveTreeNode
from ALB.tool import ParameterHub

LOGGER = logging.getLogger("ALB.bearing")


def _create_model(phub: ParameterHub, mesh, node_manager, elem_manager, matrix_process):
    """
    Create a film model based on the specified iteration method.
    :param phub: ParameterHub containing model parameters.
    :param mesh: The mesh object.
    :param node_manager: The node manager.
    :param elem_manager: The element manager.
    :param matrix_process: The matrix process object.
    :return: A film model instance.
    """
    iter_method = phub["iter_method"]
    if iter_method == "newton":
        fm = _create_newton_model(
            phub, mesh, node_manager, elem_manager, matrix_process
        )
    elif iter_method == "lsq":
        fm = _create_lsq_model(phub, mesh, node_manager, elem_manager, matrix_process)
    elif iter_method == "gauss":
        fm = _create_gauss_model(phub, mesh, node_manager, elem_manager, matrix_process)
    elif iter_method == "skfem_newton":
        fm = _create_skfem_model(phub, mesh, node_manager, elem_manager, matrix_process)
    else:
        raise Exception("iter_method must be gauss or newton")
    return fm


def _create_newton_model(
    phub: ParameterHub, mesh, node_manager, elem_manager, matrix_process
):
    """
    Create a Newton-Raphson based film model.
    :param phub: ParameterHub containing model parameters.
    :param mesh: The mesh object.
    :param node_manager: The node manager.
    :param elem_manager: The element manager.
    :param matrix_process: The matrix process object.
    :return: A NewtonFilm model instance.
    """
    boundary_key = ["coe", "p_set"]
    bkey = phub.direct(boundary_key)
    film_boundary = FilmBoundary(**bkey)
    request_key = [
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
        "reynold",
        "dxt",
        "dyt",
        "vf",
        "error_set",
        "damp",
        "adaptive_damp",
        "save_p",
        "save_h",
    ]
    kargs = phub.direct(request_key)
    film_model = NewtonFilm(
        **kargs,
        mesh=mesh,
        filmboundary=film_boundary,
        node_manager=node_manager,
        elem_manager=elem_manager,
        matrix_process=matrix_process,
    )
    return film_model


def _create_skfem_model(
    phub: ParameterHub, mesh, node_manager, elem_manager, matrix_process
):
    boundary_key = ["coe", "p_set"]
    bkey = phub.direct(boundary_key)
    film_boundary = FilmBoundary(**bkey)
    request_key = [
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
        "reynold",
        "dxt",
        "dyt",
        "vf",
        "error_set",
        "damp",
        "adaptive_damp",
        "save_p",
        "save_h",
    ]
    kargs = phub.direct(request_key)
    film_model = SkfemNewtonFilm(
        **kargs,
        mesh=mesh,
        filmboundary=film_boundary,
        node_manager=node_manager,
        elem_manager=elem_manager,
        matrix_process=matrix_process,
    )
    return film_model


def _create_lsq_model(
    phub: ParameterHub, mesh, node_manager, elem_manager, matrix_process
):
    """
    Create a least-squares based film model.
    :param phub: ParameterHub containing model parameters.
    :param mesh: The mesh object.
    :param node_manager: The node manager.
    :param elem_manager: The element manager.
    :param matrix_process: The matrix process object.
    :return: A LsqFilm model instance.
    """
    boundary_key = ["coe", "p_set"]
    bkey = phub.direct(boundary_key)
    film_boundary = FilmBoundary(**bkey)
    request_key = [
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
        "reynold",
        "dxt",
        "dyt",
        "vf",
        "error_set",
        "damp",
        "save_p",
        "save_h",
    ]
    kargs = phub.direct(request_key)
    film_model = LsqFilm(
        **kargs,
        mesh=mesh,
        filmboundary=film_boundary,
        node_manager=node_manager,
        elem_manager=elem_manager,
        matrix_process=matrix_process,
    )
    return film_model


def _create_gauss_model(
    phub: ParameterHub, mesh, node_manager, elem_manager, matrix_process
):
    """
    Create a Gauss-Seidel based film model.
    :param phub: ParameterHub containing model parameters.
    :param mesh: The mesh object.
    :param node_manager: The node manager.
    :param elem_manager: The element manager.
    :param matrix_process: The matrix process object.
    :return: A GaussSeidelFilm model instance.
    """
    film_boundary = PSetFilmBoundary()
    request_key = [
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
        "reynold",
        "dxt",
        "dyt",
        "vf",
        "error_set",
        "damp",
        "save_p",
        "save_h",
        "err",
        "ngauss",
        "gdamp",
    ]
    kargs = phub.soft_direct(request_key)
    film_model = GaussSeidelFilm(
        **kargs,
        mesh=mesh,
        filmboundary=film_boundary,
        node_manager=node_manager,
        elem_manager=elem_manager,
        matrix_process=matrix_process,
    )
    return film_model


class HydrostaticBearing(FilmSystem):
    """Dimensional single-pad hydrostatic bearing."""

    unit_system = "dimensional"

    def __init__(self, hyd_config: HydConfig = HydConfig(), **kwargs):
        """
        :param hyd_config: HydConfig, bearing parameters
        """
        mesh = Mesh()
        elems = ElemManager()
        nodes = NodeManager()
        matrix_process = MatrixProcess()

        vib = hyd_config.vib
        dxt = hyd_config.dxt
        dyt = hyd_config.dyt
        e = hyd_config.e
        c = hyd_config.c
        vf = hyd_config.vf
        freq = hyd_config.freq
        angle_rad = hyd_config.angle_rad
        if vib:
            if dxt is None or dyt is None:
                hyd_config.dxt = -e * c * vf * (freq * 2 * np.pi) * np.cos(angle_rad)
                hyd_config.dyt = -e * c * vf * (freq * 2 * np.pi) * np.sin(angle_rad)
        else:
            hyd_config.dxt = hyd_config.dyt = 0
            hyd_config.vf = 1

        self.input_args = hub = ParameterHub(hyd_config)
        film_model = _create_model(hub, mesh, nodes, elems, matrix_process)
        args = film_model.args
        nds, els = mesh.build_rect(
            RectFilmNode, RectFilmElem, args["x_lim"], args["z_lim"], args["size"]
        )
        nodes.adds(nds)
        elems.adds(els)
        self.thickness = ThicknessModel(e=hyd_config.e, angle=hyd_config.angle_rad)
        self.thickness.set_thickness_with_e_angle(film_model)
        path = hyd_config.path
        max_iter = hyd_config.max_iter
        node_link = hyd_config.node_link
        if path != "":
            self._path = path
        else:
            self._path = "bearing_result"
        super().__init__(film_model, max_iter=max_iter, node_link=node_link)

    def update_args(self, **kwargs):
        """
        Update parameters.
        """

    def add_orifice(self, position, r, pressure=None, cd=0.6):
        """
        Add an orifice.
        :param position: Orifice position.
        :param r: Orifice radius.
        :param pressure: Orifice pressure, defaults to non-dimensional pressure.
        :param cd: Orifice throttle coefficient, 0.6.
        """
        miu = self.main_model.args["miu"]
        lr = self.main_model.args["lr"]
        c = self.main_model.args["c"]
        rho = self.main_model.args["rho"]
        if pressure is None:
            pressure = self.main_model.args["ps"]
        a0 = np.pi * r**2  # Orifice area
        cq = (
            12 * miu * lr * cd * a0 / c**3 * math.sqrt(2 / rho / pressure)
        )  # Non-dimensional orifice throttle coefficient
        # Build orifice
        orifice_args = {"position": position, "pressure": pressure, "cq": cq}
        orifice = Orifice(**orifice_args)
        self.add_simple_model(orifice)

    def add_orifices(self, positions, r, pressure=None, cd=0.6):
        """
        Add multiple orifices.
        :param positions: Orifice positions.
        :param pressure: Orifice pressure.
        :param r: Orifice radius.
        :param cd: Orifice throttle coefficient, 0.6.
        """
        miu = self.main_model.args["miu"]
        lr = self.main_model.args["lr"]
        c = self.main_model.args["c"]
        rho = self.main_model.args["rho"]
        if pressure is None:
            pressure = self.main_model.args["ps"]
        a0 = np.pi * r**2  # Orifice area
        cq = (
            12 * miu * lr * cd * a0 / c**3 * math.sqrt(2 / rho / pressure)
        )  # Non-dimensional orifice throttle coefficient
        # Build orifice
        orifice_args = {"pressure": pressure, "cq": cq}
        orifices = Orifices(**orifice_args)
        orifices.build_by_positions(positions)
        self.add_simple_model(orifices)

    def add_orifices_by_cq(self, positions, pressure=None, cq=0.1):
        """
        Add multiple orifices using the non-dimensional throttle coefficient.
        """
        # Build orifice
        orifices = Orifices(pressure, cq)
        orifices.build_by_positions(positions)
        self.add_simple_model(orifices)

    def set_thickness(self, method, **kwargs):
        """
        Set the bearing thickness.
        :param method:options:'ex_ey','e_angle'

        if choose 'ex_ey', ex,ey must be input in kwargs

        if choose 'e_angle', e,angle must be input in kwargs

        """
        self.thickness.input(method, **kwargs)
        self.thickness.output(self.main_model)

    def reynold_boundary(self, reynold=True):
        """
        Set the Reynolds boundary condition.
        :param reynold:
        :return:
        """
        self.main_model.args["reynold"] = reynold


class NodimHydrostaticBearing(FilmSystem):
    """Single-pad bearing assembled directly from nondimensional film parameters.

    ``x0`` and ``lx`` are public angle inputs in degrees, matching ``HydConfig``.
    """

    unit_system = "nondimensional"

    def __init__(
        self,
        lambda_value,
        lr,
        lx,
        lz,
        x0=0.0,
        nx=59,
        nz=39,
        reynold=True,
        coe=True,
        p_set=0.0,
        error_set=1e-10,
        max_iter=120,
        damp=0.8,
        adaptive_damp=None,
        e=0.0,
        angle=0.0,
        node_link=None,
        save_p=False,
        save_h=False,
        mesh=None,
        node_manager=None,
        elem_manager=None,
        matrix_process=None,
        miu=1.0,
        c=1.0,
        r=1.0,
        l=None,
        ps=1.0,
        rho=1.0,
        w=None,
        dxt=0.0,
        dyt=0.0,
        vf=1.0,
        xct=0.0,
        yct=0.0,
        **kwargs,
    ):
        mesh = Mesh() if mesh is None else mesh
        elems = ElemManager() if elem_manager is None else elem_manager
        nodes = NodeManager() if node_manager is None else node_manager
        matrix_process = MatrixProcess() if matrix_process is None else matrix_process
        film_boundary = FilmBoundary(coe=coe, p_set=p_set)
        film_model = NodimNewtonFilm(
            lambda_value=lambda_value,
            lambda0=kwargs.get("lambda0", lambda_value),
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
            dxt=dxt,
            dyt=dyt,
            vf=vf,
            xct=xct,
            yct=yct,
            reynold=reynold,
            error_set=error_set,
            damp=damp,
            adaptive_damp=adaptive_damp,
            save_p=save_p,
            save_h=save_h,
            mesh=mesh,
            filmboundary=film_boundary,
            node_manager=nodes,
            elem_manager=elems,
            matrix_process=matrix_process,
        )
        args = film_model.args
        nds, els = mesh.build_rect(
            RectFilmNode, RectFilmElem, args["x_lim"], args["z_lim"], args["size"]
        )
        nodes.adds(nds)
        elems.adds(els)
        self.thickness = ThicknessModel(e=e, angle=angle)
        self.thickness.set_thickness_with_e_angle(film_model)
        self._path = kwargs.get("path", "bearing_result")
        super().__init__(film_model, max_iter=max_iter, node_link=node_link)

    def set_thickness(self, method, **kwargs):
        self.thickness.input(method, **kwargs)
        self.thickness.output(self.main_model)

    def reynold_boundary(self, reynold=True):
        self.main_model.args["reynold"] = reynold


class MultiPad(BaseCSystem):
    """
    Multi-pad bearing.
    """

    def __init__(self, *bearings):
        """
        :param bearings: List of bearings, [HydroStaticBearing]
        """
        if len(bearings) == 0:
            raise ValueError("MultiPad requires at least one bearing")
        super().__init__()
        self.bearings = tuple(bearings)
        self.signal.children = [b.signal for b in self.bearings]
        unit_systems = {get_unit_system(bearing) for bearing in self.bearings}
        if len(unit_systems) != 1:
            raise ValueError("All MultiPad bearings must use the same unit_system")
        self.unit_system = unit_systems.pop()
        node_links = {getattr(bearing, "node_link", None) for bearing in self.bearings}
        if len(node_links) != 1:
            raise ValueError("All MultiPad bearings must use the same node_link")
        self.node_link = node_links.pop()
        self.dyc = []
        self.result = pd.DataFrame(columns=["t", "fx", "fy"])
        self.t = None
        self.force = None

    @property
    def results(self):
        """Return the aggregate multi-pad force history."""

        return self.result

    def solve(self):
        for bearing in self.bearings:
            bearing.solve()

    def set_thickness(self, method, **kwargs):
        """
        Set the bearing thickness.
        :param method:options:'ex_ey','e_angle'

        if choose 'ex_ey', ex,ey must be input in kwargs

        if choose 'e_angle', e,angle must be input in kwargs

        """
        for bearing in self.bearings:
            bearing.set_thickness(method, **kwargs)

    @property
    def margs(self):
        return self.bearings[0].args

    def init(self):
        for bearing in self.bearings:
            bearing.init()

    def input(self, uxy, uxyt, *args, **kwargs):
        self.t = kwargs.get("t", 0)
        for bearing in self.bearings:
            bearing.input(uxy=uxy, uxyt=uxyt, *args, **kwargs)

    def output(self, **kwargs):
        ops = []
        for bearing in self.bearings:
            ops.append(bearing.output(**kwargs))
        forces = [op["force"] for op in ops]
        frictions = [op.get("friction", 0.0) for op in ops]
        force = np.sum(forces, axis=0)
        frictions = np.sum(frictions, axis=0)
        op = dict(ops[0])
        op["force"] = force
        op["friction"] = frictions
        logging.info("Total load of multi-pad bearing is: {}".format(force))
        self.force = force
        self.signal.lead_loop("finish_signal")
        return op

    def finish_signal(self):
        self.result.loc[self.result.shape[0]] = [self.t, self.force[0], self.force[1]]

    def calc_capacity(self, **kwargs):
        forces = []
        for bearing in self.bearings:
            force = bearing.calc_capacity(**kwargs)
            forces.append(force)
        force = np.sum(forces, axis=0)
        return force

    def calc_friction(self, **kwargs):
        """
        :param kwargs: nodim: if True, return nodim friction power, default True
        """
        forces = []
        for bearing in self.bearings:
            force = bearing.calc_friction(**kwargs)
            forces.append(force)
        force = np.sum(forces)
        return force

    def calc_is_finished(self):
        return all([bearing.calc_is_finished() for bearing in self.bearings])

    def calc_k(self, **kwargs):
        """
        Calculate the stiffness matrix.
        Options:
        nodim : bool, default True
        """
        k = []
        for bearing in self.bearings:
            bdc = BearingDynamicChar(bearing)
            self.dyc.append(bdc)
            k.append(bdc.calc_k(**kwargs))
        k = np.sum(k, axis=0)
        return k

    def calc_c(self, **kwargs):
        """
        Calculate the damping matrix.
        Options:
        nodim : bool, default True
        """
        c = []
        for bearing in self.bearings:
            bdc = BearingDynamicChar(bearing)
            self.dyc.append(bdc)
            c.append(bdc.calc_c(**kwargs))
        c = np.sum(c, axis=0)
        return c

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        Save results to a local file.
        """
        if path is None:
            path = "multipads"
        result = DataFrameResult({"multipads_result": self.result})
        parent_node = SaveTreeNode(path, result)
        child_node = [
            sm.save(
                path="pad" + str(num), name=type(sm).__name__ + str(num), tofile=False
            )
            for num, sm in enumerate(self.bearings)
        ]
        parent_node.add_children(child_node)
        if tofile:
            parent_node.save_to_file()
        return parent_node


class StaticPosition:
    def __init__(
        self,
        bearing,
        kx=5,
        ky=5,
        iter_num=30,
        error_set=1e-4,
        damp=0.05,
        delta=1e-2,
        newton_stall_patience=5,
        stall_rel_tol=0.0,
    ):
        """
        Calculates the static equilibrium position of a bearing.
        :param bearing: The bearing object.
        :param kx: Stiffness in the x-direction for iteration.
        :param ky: Stiffness in the y-direction for iteration.
        :param iter_num: Maximum number of iterations.
        :param error_set: Convergence error tolerance.
        :param damp: Damping factor for iteration.
        :param newton_stall_patience: Number of consecutive Newton iterations
            that fail to improve the best residual before the solver switches
            permanently to the fixed-stiffness kx/ky fixed-point update. Set to
            0 (or negative) to disable the switch and always use Newton.
        :param stall_rel_tol: Minimum relative reduction of the residual that
            counts as an improvement when detecting Newton stall. 0.0 means any
            strictly new minimum residual resets the stall counter.
        """
        self.bearing = bearing
        self.data = pd.DataFrame(
            columns=[
                "ex",
                "ey",
                "Fx",
                "Fy",
                "F",
                "error",
                "finished",
                "iter_num",
                "inner_converged",
                "stop_reason",
                "dim_Fx",
                "dim_Fy",
                "dim_F",
            ]
        )
        self.kx = kx
        self.ky = ky
        self.iter_num = iter_num
        self.error_set = error_set
        self.child_nodes = []
        self.damp = damp
        self.delta = delta
        self.newton_stall_patience = newton_stall_patience
        self.stall_rel_tol = stall_rel_tol

    def _limit_eccentricity_step(
        self,
        ex,
        ey,
        dex,
        dey,
        limit=1.0,
        margin=1.0e-6,
        min_scale=1.0e-6,
    ):
        """
        Keep a Newton update inside the valid nondimensional eccentricity disk.

        The film model accepts eccentricity only when sqrt(ex**2 + ey**2) < 1.
        This helper preserves the Newton direction and backs off the step size
        until the candidate point is inside that disk.
        """
        current = np.array([ex, ey], dtype=float)
        step = np.array([dex, dey], dtype=float)
        safe_limit = float(limit) - float(margin)

        if not np.all(np.isfinite(step)):
            return float(current[0]), float(current[1]), 0.0

        candidate = current + step
        if np.linalg.norm(candidate) < safe_limit:
            return float(candidate[0]), float(candidate[1]), 1.0

        scale = 0.5
        while scale >= min_scale:
            candidate = current + scale * step
            if np.linalg.norm(candidate) < safe_limit:
                return float(candidate[0]), float(candidate[1]), scale
            scale *= 0.5

        current_norm = np.linalg.norm(current)
        if current_norm >= safe_limit and current_norm > 0.0:
            current = current / current_norm * safe_limit
        return float(current[0]), float(current[1]), 0.0

    def _calc_static_error(self, wx, wy, force):
        """Return the load-balance residual normalized by the applied load."""
        w_norm = np.sqrt(wx**2 + wy**2)
        return (
            np.sqrt((wx + force[0]) ** 2 + (wy + force[1]) ** 2) / w_norm
            if w_norm > 0
            else 0.0
        )

    def _inner_is_finished(self):
        """Return whether the latest nested bearing solve reported convergence."""
        if not hasattr(self.bearing, "calc_is_finished"):
            return True
        status = self.bearing.calc_is_finished()
        if status is None:
            return True
        return bool(status)

    def _evaluate_static_force(self, wx, wy, ex, ey, nodim=True, include_dim=False):
        """Evaluate force and convergence diagnostics at one static position."""
        self.bearing.input(uxy=[ex, ey], uxyt=[0, 0], t=0, nodim=nodim)
        self.bearing.output(nodim=nodim)
        force = np.asarray(self.bearing.calc_capacity(calc=True, nodim=nodim))
        dim_force = (
            np.asarray(self.bearing.calc_capacity(calc=True, nodim=False))
            if include_dim
            else np.full(2, np.nan)
        )
        return {
            "ex": float(ex),
            "ey": float(ey),
            "force": force,
            "dim_force": dim_force,
            "total_force": float(np.sqrt(force[0] ** 2 + force[1] ** 2)),
            "error": float(self._calc_static_error(wx, wy, force)),
            "inner_converged": self._inner_is_finished(),
        }

    def run(self, wx, wy, ex=0, ey=0, nodim=True):
        """
        :param wx: Load in the x-direction.
        :param wy: Load in the y-direction.
        :param ex: Initial eccentricity ratio in the x-direction.
        :param ey: Initial eccentricity ratio in the y-direction.
        :param nodim: Whether to use non-dimensional units.
        """
        force = np.zeros(2)
        dim_force = np.zeros(2)
        total_force = 0
        error = 1
        delta = self.delta
        finished = False
        inner_converged = True
        stop_reason = "max_iter"
        i = 0
        current_eval = None
        state_matches_current_eval = False
        last_jacobian = None
        best_error = np.inf
        stall_count = 0
        use_kxky = False
        if hasattr(self.bearing, "init"):
            self.bearing.init()
        LOGGER.info("Static position iteration started: wx=%s, wy=%s", wx, wy)
        pbar = tqdm(range(self.iter_num), desc="Static Track", ncols=100)
        for i in pbar:
            if hasattr(self.bearing, "init"):
                self.bearing.init()
            # print("Iteration {}".format(i))
            current_eval = self._evaluate_static_force(
                wx, wy, ex, ey, nodim=nodim, include_dim=True
            )
            force = current_eval["force"]
            dim_force = current_eval["dim_force"]
            total_force = current_eval["total_force"]
            error = current_eval["error"]
            inner_converged = current_eval["inner_converged"]
            state_matches_current_eval = True
            if i % 5 == 0:
                pbar.set_description(
                    f"Iter:{i + 1} Error:{error:.2e} Force:({force[0]:.2e},{force[1]:.2e}) "
                    f"Exy:({ex:.2e},{ey:.2e})"
                )
            if not inner_converged:
                stop_reason = "inner_not_converged"
                LOGGER.warning(
                    "Static position stopped because the inner solve did not converge"
                )
                break
            if error < self.error_set:
                finished = True
                stop_reason = "converged"
                break
            # Stall detection: track the best residual seen so far. When the
            # Newton (Jacobian) update fails to improve it for
            # ``newton_stall_patience`` consecutive iterations, switch
            # permanently to the simpler fixed-stiffness kx/ky fixed-point
            # update. The finite-difference Jacobian can become ill-conditioned
            # or oscillate on hard cases; the kx/ky update is slower but more
            # robust and needs no probe solves.
            if error < best_error * (1.0 - self.stall_rel_tol):
                best_error = error
                stall_count = 0
            else:
                stall_count += 1
            if (
                not use_kxky
                and self.newton_stall_patience > 0
                and stall_count >= self.newton_stall_patience
            ):
                use_kxky = True
                LOGGER.warning(
                    "Static position switching to kx/ky fixed-point update after "
                    "%d non-improving Newton iterations (best error=%.3e)",
                    stall_count,
                    best_error,
                )
            res = np.array([wx + force[0], wy + force[1]])
            if use_kxky:
                # Fixed-stiffness kx/ky fixed-point update (previously the
                # commented-out method): the displacement increment is the load
                # residual scaled by the configured stiffness and (1 + |e|). No
                # Jacobian probe solves are needed, so the inner film model is
                # evaluated only once per iteration at the current point.
                dex = res[0] / (self.kx * (1.0 + abs(ex)))
                dey = res[1] / (self.ky * (1.0 + abs(ey)))
            else:
                # Build the force Jacobian with forward finite differences. If a
                # perturbed probe's inner (coupled film) solve fails to converge,
                # reuse the most recent successfully built Jacobian ("frozen
                # Jacobian") and continue the Newton step instead of aborting the
                # whole static iteration. Only when no Jacobian has been built yet
                # does a non-converged probe stop the iteration.
                jacobian_built = True
                eval_dx = self._evaluate_static_force(
                    wx, wy, ex + delta, ey, nodim=nodim
                )
                state_matches_current_eval = False
                if not eval_dx["inner_converged"]:
                    jacobian_built = False
                eval_dy = None
                if jacobian_built:
                    eval_dy = self._evaluate_static_force(
                        wx, wy, ex, ey + delta, nodim=nodim
                    )
                    state_matches_current_eval = False
                    if not eval_dy["inner_converged"]:
                        jacobian_built = False
                if jacobian_built:
                    force_dx = eval_dx["force"]
                    force_dy = eval_dy["force"]
                    dfx_dex = (force_dx[0] - force[0]) / delta
                    dfy_dex = (force_dx[1] - force[1]) / delta
                    dfx_dey = (force_dy[0] - force[0]) / delta
                    dfy_dey = (force_dy[1] - force[1]) / delta
                    J = np.array([[dfx_dex, dfx_dey], [dfy_dex, dfy_dey]])
                    last_jacobian = J
                elif last_jacobian is not None:
                    # Frozen Jacobian: a probe inner solve did not converge, so
                    # keep the previous Jacobian and continue the Newton step.
                    J = last_jacobian
                    LOGGER.warning(
                        "Static position reusing frozen Jacobian because a perturbed "
                        "probe inner solve did not converge"
                    )
                else:
                    stop_reason = (
                        "inner_not_converged_dx"
                        if not eval_dx["inner_converged"]
                        else "inner_not_converged_dy"
                    )
                    LOGGER.warning(
                        "Static position stopped because a probe inner solve did not "
                        "converge and no previous Jacobian is available"
                    )
                    break
                try:
                    delta_e = np.linalg.solve(J, -res)
                except np.linalg.LinAlgError:
                    LOGGER.warning(
                        "Jacobian is singular, fallback to default stiffness"
                    )
                    delta_e = -res / np.array([self.kx, self.ky])
                dex, dey = delta_e * self.damp
            ex, ey, _ = self._limit_eccentricity_step(ex, ey, dex, dey)
            state_matches_current_eval = False
            # print("Current iteration residual is: {}".format(error))
            e_norm = np.sqrt(ex**2 + ey**2)
            if e_norm >= 1:
                ex = ex / 2
                ey = ey / 2
        if current_eval is None or not np.allclose(
            [current_eval["ex"], current_eval["ey"]], [ex, ey]
        ) or not state_matches_current_eval:
            current_eval = self._evaluate_static_force(
                wx, wy, ex, ey, nodim=nodim, include_dim=True
            )
            force = current_eval["force"]
            dim_force = current_eval["dim_force"]
            total_force = current_eval["total_force"]
            error = current_eval["error"]
            inner_converged = current_eval["inner_converged"]
            if inner_converged and error < self.error_set:
                finished = True
                stop_reason = "converged"
            elif not inner_converged and stop_reason == "max_iter":
                stop_reason = "inner_not_converged_final"
        LOGGER.info(
            "Static position finished: iter=%s, converged=%s, residual=%s",
            i,
            finished,
            error,
        )
        if finished is False:
            LOGGER.warning("Static position did not converge")
        self.data.loc[len(self.data)] = [
            ex,
            ey,
            force[0],
            force[1],
            total_force,
            error,
            finished,
            i,
            inner_converged,
            stop_reason,
            dim_force[0],
            dim_force[1],
            np.sqrt(dim_force[0] ** 2 + dim_force[1] ** 2),
        ]
        child_node = copy.deepcopy(
            self.bearing.save(
                path="wx{}_wy{}".format(wx, wy), name="bearing", tofile=False
            )
        )
        self.child_nodes.append(child_node)
        return ex, ey

    def run_track(self, wxs, wys, ex=0, ey=0, nodim=True):
        """
        :param wxs: Loads in the x-direction.
        :param wys: Loads in the y-direction.
        :param ex: Initial eccentricity ratio in the x-direction.
        :param ey: Initial eccentricity ratio in the y-direction.
        """
        if len(wxs) != len(wys):
            raise ValueError("wxs and wys must be same length")
        exs = []
        eys = []
        for i in range(len(wxs)):
            ex, ey = self.run(wxs[i], wys[i], ex, ey, nodim=nodim)
            exs.append(ex)
            eys.append(ey)
        return np.array(exs), np.array(eys)

    def save(self, tofile=True, path=None, name=None):
        """
        Save the results.
        :param tofile: Whether to save to a file.
        :param path: The path to save to.
        :param name: The name of the result file.
        :return: A SaveTreeNode object.
        """
        if path is None:
            path = "track_result"
        if name is None:
            name = "track_output"
        res = {name: self.data}
        res = DataFrameResult(res)
        node = SaveTreeNode(path, res)
        node.add_children(self.child_nodes)
        if tofile:
            node.save_to_file()
        return node


class BearingDynamicChar:
    def __init__(self, bearing: HydrostaticBearing, **kwargs):
        """
        Calculates the dynamic characteristics of a hydrostatic bearing.
        :param bearing: The hydrostatic bearing object.
        :param kwargs: Additional arguments.
        """
        if not bearing.calc_is_finished():
            raise ValueError("bearing is not calc finished")
        self.main_model = bearing.main_model
        bearing = copy.deepcopy(bearing)
        nm = bearing.main_model.node_manager
        for sm in bearing.simple_models:
            sm.input()
            sm.output(bearing.main_model)
        matrix = bearing.main_model.matrixs
        A = matrix["ke_all"]
        A0 = matrix["ke"]
        if np.sum(A0 - A) != 0:
            LOGGER.info("A0 != A, orifice contribution detected")
        else:
            LOGGER.info("A0 == A, no orifice contribution detected")
        A = sp.csc_matrix(A)
        self.A = A[0 : nm.freedoms, 0 : nm.freedoms]
        self.p = bearing.main_model.latest_result[0 : nm.freedoms]
        self.fms = []
        self.node_err = kwargs.get("node_err", 1e-12)
        self.nodes_number = [
            node.number for node in nm.nodes.values() if node.p <= self.node_err
        ]
        self.K = None
        self.C = None

    def calc_k(self, nodim=True):
        """
        Calculate bearing stiffness.
        :param nodim: Whether to non-dimensionalize.
        return: [[kxx,kxy],[kyx,kyy]]
        """
        k0 = self._calc_k(Dkxelem, nodim=nodim)
        k1 = self._calc_k(Dkyelem, nodim=nodim)
        K = np.array([k0, k1])
        self.K = K
        return K.reshape((2, 2)).T

    def calc_c(self, nodim=True):
        """
        Calculate bearing damping.
        :param nodim: Whether to non-dimensionalize.
        return: [[cxx,cxy],[cyx,cyy]]
        """
        c0 = self._calc_c(DCxelem, nodim=nodim)
        c1 = self._calc_c(DCyelem, nodim=nodim)
        C = np.array([c0, c1])
        self.C = C
        return C.reshape((2, 2)).T

    def _calc_k(self, dyelem_class, **kwargs):
        """
        Internal method to calculate stiffness components.
        :param dyelem_class: The dynamic element class to use.
        :param kwargs: Additional arguments.
        :return: Stiffness component.
        """
        fm = self.build_dymodel(dyelem_class)
        Adxc, Bdxc = fm.calc_matrixs_rights()
        Bdxc = Bdxc["fe"] - Adxc["ke"].dot(self.p)
        fm.matrixs["ke"] = self.A
        fm.rights["fe"] = Bdxc
        fm.set_boundary(method="nodes_p", nodes_number=self.nodes_number)
        fm.solve()
        fp = FilmPostProcess(fm)
        k = np.array(fp.calc_capacity_nodim())
        args = self.main_model.args
        if kwargs.get("nodim", True):
            k = -k
        else:
            k = -k * args["r"] * args["l"] / 2 * args["ps"] / args["c"]
        return k

    def _calc_c(self, dyelem_class, **kwargs):
        """
        Internal method to calculate damping components.
        :param dyelem_class: The dynamic element class to use.
        :param kwargs: Additional arguments.
        :return: Damping component.
        """
        fm = self.build_dymodel(dyelem_class)
        Adxc, Bdxc = fm.calc_matrixs_rights()
        # TODO:Modification marked
        # fm.matrixs['ke'] = Adxc['ke']
        fm.matrixs["ke"] = self.A
        fm.rights["fe"] = Bdxc["fe"]
        fm.set_boundary(method="nodes_p", nodes_number=self.nodes_number)
        fm.solve()
        fp = FilmPostProcess(fm)
        c = np.array(fp.calc_capacity_nodim())
        args = self.main_model.args
        if kwargs.get("nodim", True):
            c = -c
        else:
            c = (
                -c
                * args["r"]
                * args["l"]
                / 2
                * args["ps"]
                / args["c"]
                / (args["w"] * 2 * np.pi / 60 * args["vf"])
            )
        return c

    def build_dymodel(self, dyelem_class):
        """
        Build a dynamic model for characterization.
        :param dyelem_class: The dynamic element class to use.
        :return: A FilmModel instance.
        """
        x_lim = self.main_model.args["x_lim"]
        z_lim = self.main_model.args["z_lim"]
        size = self.main_model.args["size"]
        mesh = Mesh()
        nodes, elems = mesh.build_rect(
            RectFilmNode, dyelem_class, x_lim=x_lim, y_lim=z_lim, size=size
        )
        elems = ElemManager(elems)
        nodes = NodeManager(nodes)
        for i in range(len(nodes())):
            nodes.nodes[i].h = self.main_model.node_manager.nodes[i].h
        matrix_process = MatrixProcess()
        fb = FilmBoundary(coe=False, p_set=0)
        w = self.main_model.args["w"]
        x0 = self.main_model.args["x0"] / np.pi * 180
        lx = (x_lim[1] - x_lim[0]) / np.pi * 180
        lz = z_lim[1] - z_lim[0]
        nx = size[0]
        nz = size[1]
        miu = self.main_model.args["miu"]
        c = self.main_model.args["c"]
        rho = self.main_model.args["rho"]
        r = self.main_model.args["r"]
        l = self.main_model.args["l"]
        ps = self.main_model.args["ps"]
        dxt = self.main_model.args["dxt"]
        dyt = self.main_model.args["dyt"]
        vf = self.main_model.args["vf"]
        fm = FilmModel(
            w=w,
            x0=x0,
            lx=lx,
            lz=lz,
            nx=nx,
            nz=nz,
            miu=miu,
            c=c,
            rho=rho,
            r=r,
            l=l,
            ps=ps,
            mesh=mesh,
            elem_manager=elems,
            node_manager=nodes,
            matrix_process=matrix_process,
            filmboundary=fb,
            dxt=dxt,
            dyt=dyt,
            vf=vf,
        )
        self.fms.append(fm)
        return fm


class Dkxelem(RectFilmElem):
    def calc_matrixs(self):
        """
        Calculate stiffness matrix.
        """
        h = np.array([node.h for node in self.nodes.values()])
        lr = self.args["lr"]
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
        x0 = self.nodes[0].coords[0]
        self.matrixs["ke"] = calc_ke_dx(x0, lr, lx, lz, h)

    def calc_rights(self):
        """
        Calculate right-hand side vector.
        """
        x0 = self.nodes[0].coords[0]
        lambda_value = self.args["lambda"]
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        self.rights["fe"] = calc_fe_dx(x0, lx, lz, lambda_value)


class Dkyelem(RectFilmElem):
    def calc_matrixs(self):
        """
        Calculate stiffness matrix.
        """
        h = np.array([node.h for node in self.nodes.values()])
        lr = self.args["lr"]
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
        x0 = self.nodes[0].coords[0]
        self.matrixs["ke"] = calc_ke_dy(x0, lr, lx, lz, h)

    def calc_rights(self):
        """
        Calculate right-hand side vector.
        """
        x0 = self.nodes[0].coords[0]
        lambda_value = self.args["lambda"]
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        self.rights["fe"] = calc_fe_dy(x0, lx, lz, lambda_value)


class DCxelem(RectFilmElem):
    def calc_matrixs(self):
        """
        Calculate stiffness matrix.
        """
        h = np.array([node.h for node in self.nodes.values()])
        lr = self.args["lr"]
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
        self.matrixs["ke"] = calc_ke(h, lr, lz, lx)

    def calc_rights(self):
        """
        Calculate right-hand side vector.
        """
        vf = self.args["vf"]
        lambda_value = self.args["lambda"]
        x0 = self.nodes[0].coords[0]
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        self.rights["fe"] = calc_fe_dxt(x0, lx, lz, vf, lambda_value)


class DCyelem(RectFilmElem):
    def calc_matrixs(self):
        """
        Calculate stiffness matrix.
        """
        h = np.array([node.h for node in self.nodes.values()])
        lr = self.args["lr"]
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        self.args["lz"] = lz
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
        self.args["lx"] = lx
        self.matrixs["ke"] = calc_ke(h, lr, lz, lx)

    def calc_rights(self):
        """
        Calculate the right-hand side term.
        """
        x0 = self.nodes[0].coords[0]
        vf = self.args["vf"]
        lambda_value = self.args["lambda"]
        lx = np.abs(self.nodes[3].coords[0] - self.nodes[0].coords[0])
        lz = np.abs(self.nodes[3].coords[1] - self.nodes[0].coords[1])
        self.rights["fe"] = calc_fe_dyt(x0, lx, lz, vf, lambda_value)


def four_pads_bearings(pad_config: FPBConfig):
    """
    Define a four-pad bearing, returning four pads.
    """
    pad_configs = [copy.deepcopy(pad_config) for _ in range(4)]
    x0s = pad_config.x0s
    for x0, pc in zip(x0s, pad_configs):
        pc.x0 = x0
    bearings = [HydrostaticBearing(pc) for pc in pad_configs]
    directions = ["up", "down", "right", "left"]
    return dict(zip(directions, bearings))


def nodim_four_pads_bearings(
    lambda_value,
    lr,
    lx,
    lz,
    nx=59,
    nz=39,
    bias=0.0,
    **kwargs,
):
    """Build four pads directly from nondimensional film parameters.

    ``bias`` and ``lx`` are angles in degrees.
    """
    x0s = [
        bias - lx / 2.0,
        bias + 180.0 - lx / 2.0,
        bias + 270.0 - lx / 2.0,
        bias + 90.0 - lx / 2.0,
    ]
    bearings = [
        NodimHydrostaticBearing(
            lambda_value=lambda_value,
            lr=lr,
            lx=lx,
            lz=lz,
            x0=x0,
            nx=nx,
            nz=nz,
            **kwargs,
        )
        for x0 in x0s
    ]
    directions = ["up", "down", "right", "left"]
    return dict(zip(directions, bearings))


def four_pads_bearing(pad_config: FPBConfig):
    """
    Define a four-pad bearing.
    """
    pads = four_pads_bearings(pad_config)
    return MultiPad(*pads.values())


def nodim_four_pads_bearing(*args, **kwargs):
    pads = nodim_four_pads_bearings(*args, **kwargs)
    return MultiPad(*pads.values())


# no validation yet, use with caution！！！！！！！
class TiltingPadHydrodynamicPad(HydrostaticBearing):
    """Single pad with linear tilt correction and self-contained tilt update."""

    def __init__(
        self,
        hyd_config: HydConfig,
        tilt_x: float = 0.0,
        tilt_z: float = 0.0,
        pivot_x: Optional[float] = None,
        pivot_z: Optional[float] = None,
        min_h: float = 1e-8,
        **kwargs,
    ):
        super().__init__(hyd_config, **kwargs)
        self.tilt_x = float(tilt_x)
        self.tilt_z = float(tilt_z)
        self.pivot_x = pivot_x
        self.pivot_z = pivot_z
        self.min_h = float(min_h)

    def set_pad_tilt(
        self,
        tilt_x: float,
        tilt_z: float,
        pivot_x: Optional[float] = None,
        pivot_z: Optional[float] = None,
    ):
        self.tilt_x = float(tilt_x)
        self.tilt_z = float(tilt_z)
        self.pivot_x = pivot_x
        self.pivot_z = pivot_z

    @staticmethod
    def _circ_diff(a, b):
        return np.arctan2(np.sin(a - b), np.cos(a - b))

    # ------------------------------------------------------------------
    # Pivot / mesh / pressure helpers (instance API).
    # ------------------------------------------------------------------
    def resolved_pivot(self):
        """Return the effective pivot (px, pz), filling defaults from the mesh."""
        args = self.main_model.args
        px = self.pivot_x
        pz = self.pivot_z
        if px is None:
            x_lim = args["x_lim"]
            px = 0.5 * (x_lim[0] + x_lim[1])
        if pz is None:
            z_lim = args["z_lim"]
            pz = 0.5 * (z_lim[0] + z_lim[1])
        return float(px), float(pz)

    def coord_mesh(self):
        size = self.main_model.args["size"]
        nodes = self.main_model.nodes.values()
        x = np.array([node.coords[0] for node in nodes]).reshape(
            size[0] + 1, size[1] + 1
        )
        z = np.array(
            [node.coords[1] for node in self.main_model.nodes.values()]
        ).reshape(size[0] + 1, size[1] + 1)
        return x, z

    def pressure_center(self):
        p = np.maximum(np.asarray(self.postprocess.p, dtype=float), 0.0)
        x, z = self.coord_mesh()
        denom = float(np.sum(p)) + 1e-18
        sx = float(np.sum(p * np.sin(x)))
        cx_ = float(np.sum(p * np.cos(x)))
        cx = float(np.arctan2(sx, cx_))
        cz = float(np.sum(p * z) / denom)
        return cx, cz

    def moment_terms(self, px=None, pz=None):
        if px is None or pz is None:
            px, pz = self.resolved_pivot()
        p = np.maximum(np.asarray(self.postprocess.p, dtype=float), 0.0)
        x, z = self.coord_mesh()
        xr = np.arctan2(np.sin(x - px), np.cos(x - px))
        zr = z - pz
        wsum = float(np.sum(p)) + 1e-18
        mx = float(np.sum(p * xr))
        mz = float(np.sum(p * zr))
        jx = float(np.sum(p * xr * xr)) + 1e-18
        jz = float(np.sum(p * zr * zr)) + 1e-18
        return mx, mz, jx, jz, wsum

    def update_tilt_step(self, gain_x, gain_z, tilt_clip):
        """Quasi-Newton tilt update from the current pressure field.

        Returns a dict with the diagnostic state for this step.
        """
        px, pz = self.resolved_pivot()
        cx, cz = self.pressure_center()
        mx, mz, jx, jz, wsum = self.moment_terms(px, pz)
        dx = float(mx / wsum)
        dz = float(mz / wsum)

        dtx = -float(gain_x) * (mx / jx)
        dtz = -float(gain_z) * (mz / jz)
        tx = float(np.clip(self.tilt_x + dtx, -tilt_clip, tilt_clip))
        tz = float(np.clip(self.tilt_z + dtz, -tilt_clip, tilt_clip))
        self.set_pad_tilt(tx, tz, self.pivot_x, self.pivot_z)

        return {
            "pivot_x": px,
            "pivot_z": pz,
            "center_x": cx,
            "center_z": cz,
            "offset_x": dx,
            "offset_z": dz,
            "moment_x": mx,
            "moment_z": mz,
            "tilt_x": tx,
            "tilt_z": tz,
        }

    def _apply_tilt_thickness(self):
        px, pz = self.resolved_pivot()
        for node in self.main_model.nodes.values():
            dx = self._circ_diff(node.coords[0], px)
            dz = node.coords[1] - pz
            node.h += self.tilt_x * dx + self.tilt_z * dz
            if node.h < self.min_h:
                node.h = self.min_h

    def input(self, uxy, uxyt, *args, **kwargs):
        # Base eccentricity/squeeze thickness is applied first, then pad tilt.
        super().input(uxy=uxy, uxyt=uxyt, *args, **kwargs)
        self._apply_tilt_thickness()


def _build_tilting_pads(
    pad_config: FPBConfig,
    x0s: Optional[Sequence[float]] = None,
    tilts: Optional[Sequence[Tuple[float, float]]] = None,
    pivots: Optional[Sequence[Tuple[Optional[float], Optional[float]]]] = None,
):
    """Construct labelled :class:`TiltingPadHydrodynamicPad` instances."""
    if x0s is None:
        x0s = list(pad_config.x0s)
    n_pad = len(x0s)
    if n_pad == 0:
        raise ValueError("x0s must contain at least one pad start angle")

    if tilts is None:
        tilts = [(0.0, 0.0) for _ in range(n_pad)]
    if len(tilts) != n_pad:
        raise ValueError("tilts length must match x0s length")

    if pivots is None:
        pivots = [(None, None) for _ in range(n_pad)]
    if len(pivots) != n_pad:
        raise ValueError("pivots length must match x0s length")

    base_labels = ["up", "down", "right", "left"]
    labels = []
    pads = []
    for i, (x0, tilt, pivot) in enumerate(zip(x0s, tilts, pivots)):
        pc = copy.deepcopy(pad_config)
        pc.x0 = float(x0)
        labels.append(base_labels[i] if i < len(base_labels) else f"pad_{i}")
        tx, tz = float(tilt[0]), float(tilt[1])
        px, pz = pivot
        pads.append(
            TiltingPadHydrodynamicPad(
                pc,
                tilt_x=tx,
                tilt_z=tz,
                pivot_x=px,
                pivot_z=pz,
            )
        )
    return labels, pads


def tilting_pads_bearings(
    pad_config: FPBConfig,
    x0s: Optional[Sequence[float]] = None,
    tilts: Optional[Sequence[Tuple[float, float]]] = None,
    pivots: Optional[Sequence[Tuple[Optional[float], Optional[float]]]] = None,
):
    """Build tilting pads and return as a ``label -> pad`` dict."""
    labels, pads = _build_tilting_pads(pad_config, x0s, tilts, pivots)
    return dict(zip(labels, pads))


def tilting_pads_bearing(
    pad_config: FPBConfig,
    x0s: Optional[Sequence[float]] = None,
    tilts: Optional[Sequence[Tuple[float, float]]] = None,
    pivots: Optional[Sequence[Tuple[Optional[float], Optional[float]]]] = None,
):
    """Build a tilting-pad bearing as a plain :class:`MultiPad`.

    The returned ``MultiPad`` is augmented with a ``pads`` attribute that maps
    canonical pad labels (``up``/``down``/``right``/``left``/...) to the
    underlying :class:`TiltingPadHydrodynamicPad` instances. Use
    :func:`get_pad_pressure_fields` and :func:`solve_tilting_pad_equilibrium`
    for the tilt-pad specific operations.
    """
    labels, pads = _build_tilting_pads(pad_config, x0s, tilts, pivots)
    mp = MultiPad(*pads)
    mp.pads = dict(zip(labels, pads))
    return mp


def get_pad_pressure_fields(pads):
    """Return a ``label -> pressure_field`` dict for an iterable/dict of pads."""
    if isinstance(pads, dict):
        return {label: pad.postprocess.p for label, pad in pads.items()}
    return {f"pad_{i}": pad.postprocess.p for i, pad in enumerate(pads)}


def solve_tilting_pad_equilibrium(
    multipad: "MultiPad",
    pads,
    uxy,
    uxyt,
    *,
    t: float = 0.0,
    nodim: bool = False,
    max_iter: int = 12,
    tol: float = 1e-3,
    gain: float = 0.2,
    gain_max: float = 0.35,
    tilt_clip: float = 0.15,
):
    """Iterate pad tilts on a :class:`MultiPad` of tilting pads to equilibrium.

    Parameters
    ----------
    multipad : MultiPad
        The multi-pad container that drives ``init``/``input``/``output``.
    pads : dict[str, TiltingPadHydrodynamicPad] | Sequence[TiltingPadHydrodynamicPad]
        The tilting pads to iterate. A dict provides stable labels in the
        diagnostic history; a sequence is auto-labelled ``pad_i``.

    The single-pad tilt update is delegated to
    :meth:`TiltingPadHydrodynamicPad.update_tilt_step`.
    """
    if isinstance(pads, dict):
        pad_items = list(pads.items())
    else:
        pad_items = [(f"pad_{i}", p) for i, p in enumerate(pads)]

    history = []
    converged = False
    gain_state = {
        label: {"gx": float(gain), "gz": float(gain), "mx_prev": None, "mz_prev": None}
        for label, _ in pad_items
    }

    for i in range(int(max_iter)):
        multipad.init()
        multipad.input(uxy=uxy, uxyt=uxyt, t=t, nodim=nodim)
        multipad.output()

        max_offset = 0.0
        iter_state = {"iter": i + 1, "pads": {}}
        for label, pad in pad_items:
            state = gain_state[label]
            gx = state["gx"]
            gz = state["gz"]

            px, pz = pad.resolved_pivot()
            mx, mz, _, _, _ = pad.moment_terms(px, pz)

            if state["mx_prev"] is not None:
                if abs(mx) > abs(state["mx_prev"]):
                    gx = -0.5 * gx
                else:
                    gx = np.sign(gx) * min(abs(gx) * 1.05, gain_max)
            if state["mz_prev"] is not None:
                if abs(mz) > abs(state["mz_prev"]):
                    gz = -0.5 * gz
                else:
                    gz = np.sign(gz) * min(abs(gz) * 1.05, gain_max)

            step = pad.update_tilt_step(gx, gz, tilt_clip)
            step["gain_x"] = float(gx)
            step["gain_z"] = float(gz)

            state["gx"] = float(gx)
            state["gz"] = float(gz)
            state["mx_prev"] = float(mx)
            state["mz_prev"] = float(mz)

            max_offset = max(max_offset, abs(step["offset_x"]), abs(step["offset_z"]))
            iter_state["pads"][label] = step

        iter_state["max_offset"] = float(max_offset)
        history.append(iter_state)
        if max_offset < tol:
            converged = True
            break

    multipad.init()
    multipad.input(uxy=uxy, uxyt=uxyt, t=t, nodim=nodim)
    out = multipad.output()
    out["tilt_equilibrium"] = {
        "converged": converged,
        "iterations": len(history),
        "tol": float(tol),
        "history": history,
        "tilts": {
            label: (float(pad.tilt_x), float(pad.tilt_z)) for label, pad in pad_items
        },
    }
    return out


if __name__ == "__main__":
    unittest.main()
