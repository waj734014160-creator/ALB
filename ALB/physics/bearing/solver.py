# coding: utf-8
import copy
import logging
import math
import unittest
from typing import Any, cast

import numpy as np
import scipy.sparse as sp

from ALB.core.component import BaseCSystem
from ALB.core.fem import ElemManager, MatrixProcess, Mesh, NodeManager
from ALB.config import (
    FPBConfig,
    HydConfig,
    HybridOrificeConfig,
    NodimPadConfig,
)
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    BearingRuntimeProtocol,
    ConvergenceStatus,
    LifecycleState,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.core.diagnostics import sanitize_exception_message
from ALB.core.lifecycle import RuntimeLifecycle
from ALB.core.validation import get_unit_system, validate_bearing_output
from ALB.physics.film.solver import (
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
    build_explicit_film_mesh,
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
from ALB.physics.hydraulics.orifice import Orifice, Orifices
from ALB.config.parameters import ParameterHub

LOGGER = logging.getLogger("ALB.physics.bearing")


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
        "mesh_type",
        "element_order",
        "triangle_diagonal",
    ]
    kargs = phub.soft_direct(request_key, warning=False)
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


class _DimensionalFilmRuntime(FilmSystem):
    """Dimensional single-pad hydrostatic bearing."""

    unit_system = "dimensional"

    def __init__(self, hyd_config: HydConfig | None = None, **kwargs):
        """
        :param hyd_config: HydConfig, bearing parameters
        """
        hyd_config = HydConfig() if hyd_config is None else copy.deepcopy(hyd_config)
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
        if args.get("mesh_type") is None:
            nds, els = mesh.build_rect(
                RectFilmNode,
                RectFilmElem,
                args["x_lim"],
                args["z_lim"],
                args["size"],
            )
        else:
            nds, els = build_explicit_film_mesh(film_model)
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


class _NondimensionalFilmRuntime(FilmSystem):
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


def _attach_hybrid_orifices(
    bearing,
    orifices: HybridOrificeConfig | None,
) -> None:
    """Attach constructor-supplied orifices before runtime initialization."""

    if orifices is None:
        return
    pressure = (
        bearing.main_model.args["ps"]
        if orifices.pressure is None
        else orifices.pressure
    )
    if orifices.cq is not None:
        cq = orifices.cq
    else:
        assert orifices.radius is not None
        args = bearing.main_model.args
        area = np.pi * orifices.radius**2
        if pressure <= 0.0:
            raise ValueError("radius-based orifices require pressure > 0")
        cq = (
            12.0
            * args["miu"]
            * args["lr"]
            * orifices.discharge_coefficient
            * area
            / args["c"] ** 3
            * math.sqrt(2.0 / args["rho"] / pressure)
        )
    group = Orifices(pressure=pressure, cq=cq)
    group.build_by_positions(orifices.positions)
    bearing.add_simple_model(group)


class _MixedFilmRuntimeMixin:
    """Add the public DTO lifecycle to a concrete film solver.

    The mixin owns only lifecycle state, immutable result snapshots, and error
    diagnostics. Numerical state and film operations remain on the concrete
    ``FilmSystem`` base class, avoiding a proxy that repeats every solver
    property and method.
    """

    input_dto_type = BearingInput
    _hybrid_nodim: bool

    def __getattribute__(self, name: str) -> Any:
        if name == "init":
            raise AttributeError(
                "bearing runtimes are ready after construction; use the owner reset"
            )
        return super().__getattribute__(name)

    def _configure_hybrid_runtime(
        self,
        orifices: HybridOrificeConfig | None,
    ) -> None:
        if orifices is not None and not isinstance(
            orifices,
            HybridOrificeConfig,
        ):
            raise TypeError("orifices must be HybridOrificeConfig or None")
        _attach_hybrid_orifices(self, orifices)
        self.orifice_config = orifices
        self._lifecycle = RuntimeLifecycle(
            type(self).__name__,
            input_label="bearing input",
        )
        self._pending_input: BearingInput | None = None
        self._latest_output: BearingOutput | None = None
        self._latest_result: ResultBundle | None = None
        self._failure: ResultBundle | None = None
        self._convergence_status = ConvergenceStatus.pending(
            "runtime is not initialized"
        )
        self._reset_for_owner()

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the current initialized runtime state."""

        return self._lifecycle.state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return cached convergence without advancing the film solver."""

        return self._convergence_status

    def _reset_for_owner(self) -> None:
        """Reset this runtime when invoked by its owning composite module."""

        self._lifecycle.fail()
        self._pending_input = None
        self._latest_output = None
        self._latest_result = None
        self._failure = None
        try:
            FilmSystem._reset_for_owner(cast(FilmSystem, self))
        except BaseException as exc:
            self._failure = self._build_failure_snapshot(exc, "reset")
            raise
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.reset()

    def input(self, dto: BearingInput) -> None:
        """Latch one typed bearing input without running the film solve."""

        self._lifecycle.require_input_slot()
        if not isinstance(dto, BearingInput):
            raise TypeError("hybrid bearing input must be BearingInput")
        expected = (
            UnitSystem.NONDIMENSIONAL
            if self._hybrid_nodim
            else UnitSystem.DIMENSIONAL
        )
        if dto.unit_system is not expected:
            raise ValueError(
                "hybrid bearing input unit_system does not match runtime"
            )
        self._pending_input = dto
        self._latest_output = None
        self._latest_result = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.latch()

    def _prepare_raw(self, dto: BearingInput) -> None:
        """Apply one typed sample to the internal film solver."""

        FilmSystem.input(
            cast(FilmSystem, self),
            dto.displacement,
            dto.velocity,
            t=dto.time,
            nodim=self._hybrid_nodim,
        )

    def _solve_raw(self) -> dict[str, Any]:
        """Run the internal film solver without publishing runtime state."""

        return FilmSystem.output(
            cast(FilmSystem, self),
            nodim=self._hybrid_nodim,
        )

    def _film_field_snapshot(
        self,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        """Return pressure and film thickness in the public runtime units.

        The native Reynolds solver stores pressure as ``p / ps`` and film
        thickness as ``h / c``. Dimensional runtimes convert those arrays to Pa
        and m; nondimensional runtimes preserve the ratios. Both arrays follow
        the mesh layout ``(circumferential_nodes, axial_nodes)`` when the native
        node count matches the configured structured mesh.
        """

        args = self.main_model.args
        pressure = np.asarray(
            self.main_model.latest_result,
            dtype=float,
        ).copy()
        thickness = np.asarray(
            [node.h for node in self.main_model.nodes.values()],
            dtype=float,
        )
        shape = (int(args["nx"]) + 1, int(args["nz"]) + 1)
        if pressure.size == shape[0] * shape[1]:
            pressure = pressure.reshape(shape)
        if thickness.size == shape[0] * shape[1]:
            thickness = thickness.reshape(shape)
        if self.unit_system is UnitSystem.DIMENSIONAL:
            pressure *= float(args["ps"])
            thickness *= float(args["c"])
            pressure_unit = "Pa"
            thickness_unit = "m"
        else:
            pressure_unit = "nondimensional"
            thickness_unit = "nondimensional"
        return (
            {
                "pressure": pressure,
                "film_thickness": thickness,
            },
            {
                "field_shape": tuple(int(value) for value in pressure.shape),
                "pressure_unit": pressure_unit,
                "film_thickness_unit": thickness_unit,
            },
        )

    def evaluate(self) -> None:
        """Run exactly one mixed film/restrictor calculation."""

        dto = self._pending_input
        try:
            with self._lifecycle.evaluation():
                assert dto is not None
                self._prepare_raw(dto)
                raw_output = self._solve_raw()
                force = validate_bearing_output(raw_output)
                self._latest_output = BearingOutput(
                    force,
                    dto.time,
                    dto.unit_system,
                )
                converged = bool(self.last_converged)
                self._convergence_status = (
                    ConvergenceStatus(
                        0.0,
                        True,
                        iterations=int(self.final_iter) + 1,
                        message="hybrid bearing calculation finished",
                    )
                    if converged
                    else ConvergenceStatus.pending(
                        "hybrid bearing calculation did not converge"
                    )
                )
                field_values, field_metadata = self._film_field_snapshot()
                self._latest_result = result_snapshot(
                    {
                        "force": self._latest_output.force,
                        "friction": float(raw_output.get("friction", 0.0)),
                        **field_values,
                    },
                    {
                        "schema": "alb.hybrid-bearing-result.v1",
                        "time": dto.time,
                        "unit_system": dto.unit_system.value,
                        "orifice_count": (
                            0
                            if self.orifice_config is None
                            else len(self.orifice_config.positions)
                        ),
                        "converged": converged,
                        **field_metadata,
                    },
                )
                self._pending_input = None
        except BaseException as exc:
            self._latest_output = None
            self._latest_result = None
            self._failure = self._build_failure_snapshot(exc, "evaluate")
            raise

    def output(self) -> BearingOutput:
        """Return the completed immutable port output without recalculation."""

        self._lifecycle.require_output()
        assert self._latest_output is not None
        return self._latest_output

    def step(self, dto: BearingInput) -> BearingOutput:
        """Compose input, evaluation, and output without committing time."""

        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> ResultBundle:
        """Return the current immutable mixed-bearing result."""

        self._lifecycle.require_output()
        assert self._latest_result is not None
        return self._latest_result

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest sealed mixed-bearing failure."""

        if self._failure is None:
            raise RuntimeError("no hybrid bearing failure is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable lifecycle and topology diagnostics."""

        return result_snapshot(
            {},
            {
                "schema": "alb.hybrid-bearing-diagnostic.v1",
                "lifecycle_state": self.lifecycle_state.value,
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
                "orifice_count": (
                    0
                    if self.orifice_config is None
                    else len(self.orifice_config.positions)
                ),
                "converged": self._convergence_status.converged,
                "has_result": self._latest_result is not None,
                "has_failure": self._failure is not None,
            },
        )

    def _build_failure_snapshot(
        self,
        error: BaseException,
        phase: str,
    ) -> ResultBundle:
        return result_snapshot(
            {},
            {
                "schema": "alb.hybrid-bearing-failure.v1",
                "phase": phase,
                "error_type": type(error).__name__,
                "message": sanitize_exception_message(error),
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
            },
        )

class _DimensionalMixedFilmRuntime(  # type: ignore[misc]
    _MixedFilmRuntimeMixin,
    _DimensionalFilmRuntime,
):
    """Dimensional mixed bearing selected by constructor-time orifice topology."""

    unit_system = UnitSystem.DIMENSIONAL
    _hybrid_nodim = False

    def __init__(
        self,
        config: HydConfig | None = None,
        *,
        orifices: HybridOrificeConfig | None = None,
    ) -> None:
        if config is None:
            config = HydConfig()
        if not isinstance(config, HydConfig):
            raise TypeError("config must be HydConfig")
        super().__init__(config)
        self._configure_hybrid_runtime(orifices)


class _NondimensionalMixedFilmRuntime(  # type: ignore[misc]
    _MixedFilmRuntimeMixin,
    _NondimensionalFilmRuntime,
):
    """Nondimensional mixed bearing with the same topology-driven semantics."""

    unit_system = UnitSystem.NONDIMENSIONAL
    _hybrid_nodim = True

    def __init__(
        self,
        config: NodimPadConfig | None = None,
        *,
        x0: float = 0.0,
        orifices: HybridOrificeConfig | None = None,
    ) -> None:
        if config is None:
            config = NodimPadConfig()
        if not isinstance(config, NodimPadConfig):
            raise TypeError("config must be NodimPadConfig")
        pad = copy.deepcopy(config)
        super().__init__(
            lambda_value=pad.lambda_value,
            lambda0=pad.lambda0,
            lr=pad.lr,
            lx=pad.lx,
            lz=pad.lz,
            x0=x0,
            nx=pad.nx,
            nz=pad.nz,
            reynold=pad.reynold,
            coe=pad.coe,
            p_set=pad.p_set,
            error_set=pad.error_set,
            max_iter=pad.max_iter,
            damp=pad.damp,
            adaptive_damp=pad.adaptive_damp,
            e=pad.e,
            angle=pad.angle,
            node_link=pad.node_link,
            save_p=pad.save_p,
            save_h=pad.save_h,
            miu=pad.scale_miu,
            c=pad.scale_c,
            r=pad.scale_r,
            l=pad.scale_l,
            ps=pad.scale_ps,
            rho=pad.scale_rho,
            w=pad.scale_w,
            dxt=pad.dxt,
            dyt=pad.dyt,
            vf=pad.vf,
            xct=pad.xct,
            yct=pad.yct,
            path=pad.path,
        )
        self._configure_hybrid_runtime(orifices)


def _build_liquid_film_runtime(
    config: HydConfig | NodimPadConfig,
    *,
    orifices: HybridOrificeConfig | None = None,
    x0: float | None = None,
) -> _DimensionalMixedFilmRuntime | _NondimensionalMixedFilmRuntime:
    """Build an initialized mixed bearing without a hydrostatic mode flag."""

    if isinstance(config, HydConfig):
        if x0 is not None:
            dimensional_config = copy.deepcopy(config)
            dimensional_config.x0 = float(x0)
        else:
            dimensional_config = config
        return _DimensionalMixedFilmRuntime(
            dimensional_config,
            orifices=orifices,
        )
    if isinstance(config, NodimPadConfig):
        return _NondimensionalMixedFilmRuntime(
            config,
            x0=0.0 if x0 is None else float(x0),
            orifices=orifices,
        )
    raise TypeError("config must be HydConfig or NodimPadConfig")


class MultiPad:
    """Strict composite runtime that aggregates multiple film-bearing pads."""

    input_dto_type = BearingInput

    def __init__(self, *bearings):
        """Build and initialize one composite from compatible child pads."""

        if len(bearings) == 0:
            raise ValueError("MultiPad requires at least one bearing")
        children = tuple(bearings)
        if any(
            not isinstance(bearing, BearingRuntimeProtocol)
            for bearing in children
        ):
            raise TypeError(
                "MultiPad accepts only native BearingRuntimeProtocol children"
            )
        self._children = children
        unit_systems = {get_unit_system(bearing) for bearing in self._children}
        if len(unit_systems) != 1:
            raise ValueError("All MultiPad bearings must use the same unit_system")
        self.unit_system = UnitSystem.coerce(unit_systems.pop())
        node_links = {
            getattr(bearing, "node_link", None) for bearing in self._children
        }
        if len(node_links) != 1:
            raise ValueError("All MultiPad bearings must use the same node_link")
        self.node_link = node_links.pop()
        self.dyc = []
        self._lifecycle = RuntimeLifecycle(
            type(self).__name__,
            input_label="bearing input",
        )
        self._pending_input: BearingInput | None = None
        self._latest_output: BearingOutput | None = None
        self._latest_result: ResultBundle | None = None
        self._failure: ResultBundle | None = None
        self._latest_friction = 0.0
        self._convergence_status = ConvergenceStatus.pending(
            "runtime is not initialized"
        )
        self._reset_for_owner()

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the current composite runtime state."""

        return self._lifecycle.state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return cached child convergence without advancing any pad."""

        return self._convergence_status

    def set_thickness(self, method, **kwargs):
        """
        Set the bearing thickness.
        :param method:options:'ex_ey','e_angle'

        if choose 'ex_ey', ex,ey must be input in kwargs

        if choose 'e_angle', e,angle must be input in kwargs

        """
        for bearing in self._children:
            bearing.set_thickness(method, **kwargs)

    @property
    def margs(self):
        bearing = self._children[0]
        main_model = getattr(bearing, "main_model", None)
        if main_model is not None:
            return main_model.args
        return bearing.args

    def _reset_for_owner(self):
        """Reset child pads and start a fresh composite runtime session."""

        self._lifecycle.fail()
        self._pending_input = None
        self._latest_output = None
        self._latest_result = None
        self._failure = None
        self._latest_friction = 0.0
        try:
            for bearing in self._children:
                reset = getattr(bearing, "_reset_for_owner", None)
                if not callable(reset):
                    raise TypeError(
                        "MultiPad child must provide _reset_for_owner()"
                    )
                reset()
        except BaseException as exc:
            self._failure = self._build_failure_snapshot(exc, "reset")
            raise
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.reset()

    def input(self, dto: BearingInput) -> None:
        """Latch one typed input without evaluating child pads."""

        self._lifecycle.require_input_slot()
        if not isinstance(dto, BearingInput):
            raise TypeError("MultiPad input must be BearingInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("MultiPad input unit_system does not match runtime")
        self._pending_input = dto
        self._latest_output = None
        self._latest_result = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.latch()

    def evaluate(self) -> None:
        """Evaluate every child exactly once and publish one aggregate force."""

        dto = self._pending_input
        try:
            with self._lifecycle.evaluation():
                assert dto is not None
                forces = []
                frictions = []
                child_convergence = []
                child_results = []
                for bearing in self._children:
                    child_output = bearing.step(dto)
                    force = child_output.force
                    result = bearing.result_snapshot()
                    child_results.append(result)
                    friction = float(result.values.get("friction", 0.0))
                    child_convergence.append(
                        bearing.convergence_status.converged
                    )
                    forces.append(force)
                    frictions.append(friction)

                aggregate_force = np.sum(forces, axis=0)
                self._latest_friction = float(np.sum(frictions))
                self._latest_output = BearingOutput(
                    aggregate_force,
                    dto.time,
                    dto.unit_system,
                )
                converged = all(child_convergence)
                self._convergence_status = (
                    ConvergenceStatus(
                        0.0,
                        True,
                        message="all MultiPad children finished",
                    )
                    if converged
                    else ConvergenceStatus.pending(
                        "one or more MultiPad children are incomplete"
                    )
                )
                result_values: dict[str, Any] = {
                    "force": self._latest_output.force,
                    "friction": self._latest_friction,
                    "pad_force": np.vstack(forces),
                }
                if all("pressure" in result.values for result in child_results):
                    result_values["pad_pressure"] = np.stack(
                        [
                            np.asarray(result.values["pressure"], dtype=float)
                            for result in child_results
                        ]
                    )
                if all(
                    "film_thickness" in result.values
                    for result in child_results
                ):
                    result_values["pad_film_thickness"] = np.stack(
                        [
                            np.asarray(
                                result.values["film_thickness"],
                                dtype=float,
                            )
                            for result in child_results
                        ]
                    )
                self._latest_result = result_snapshot(
                    result_values,
                    {
                        "schema": "alb.multi-pad-result.v1",
                        "time": dto.time,
                        "unit_system": dto.unit_system.value,
                        "pad_count": len(self._children),
                        "converged": converged,
                    },
                )
                self._pending_input = None
        except BaseException as exc:
            self._latest_output = None
            self._latest_result = None
            self._failure = self._build_failure_snapshot(exc, "evaluate")
            raise

    def output(self) -> BearingOutput:
        """Return the completed immutable aggregate without recalculation."""

        self._lifecycle.require_output()
        assert self._latest_output is not None
        return self._latest_output

    def step(self, dto: BearingInput) -> BearingOutput:
        """Compose input, evaluation, and output for one local calculation."""

        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> ResultBundle:
        """Return the current immutable aggregate result."""

        self._lifecycle.require_output()
        assert self._latest_result is not None
        return self._latest_result

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest sealed composite failure."""

        if self._failure is None:
            raise RuntimeError("no MultiPad failure is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable lifecycle and topology diagnostics."""

        return result_snapshot(
            {},
            {
                "schema": "alb.multi-pad-diagnostic.v1",
                "lifecycle_state": self.lifecycle_state.value,
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
                "pad_count": len(self._children),
                "converged": self._convergence_status.converged,
                "has_result": self._latest_result is not None,
                "has_failure": self._failure is not None,
            },
        )

    def _build_failure_snapshot(
        self,
        error: BaseException,
        phase: str,
    ) -> ResultBundle:
        return result_snapshot(
            {},
            {
                "schema": "alb.multi-pad-failure.v1",
                "phase": phase,
                "error_type": type(error).__name__,
                "message": sanitize_exception_message(error),
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
            },
        )

    def calc_capacity(self, **kwargs):
        forces = []
        for bearing in self._children:
            force = bearing.calc_capacity(**kwargs)
            forces.append(force)
        force = np.sum(forces, axis=0)
        return force

    def calc_friction(self, **kwargs):
        """
        :param kwargs: nodim: if True, return nodim friction power, default True
        """
        forces = []
        for bearing in self._children:
            force = bearing.calc_friction(**kwargs)
            forces.append(force)
        force = np.sum(forces)
        return force

    def calc_is_finished(self):
        return self._convergence_status.converged

    def calc_k(self, **kwargs):
        """
        Calculate the stiffness matrix.
        Options:
        nodim : bool, default True
        """
        k = []
        for bearing in self._children:
            bdc = _FilmDynamicAnalyzer(bearing)
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
        for bearing in self._children:
            bdc = _FilmDynamicAnalyzer(bearing)
            self.dyc.append(bdc)
            c.append(bdc.calc_c(**kwargs))
        c = np.sum(c, axis=0)
        return c

class _FilmDynamicAnalyzer:
    def __init__(self, bearing: _DimensionalFilmRuntime, **kwargs):
        """
        Calculates the dynamic characteristics of a hydrostatic bearing.
        :param bearing: The hydrostatic bearing object.
        :param kwargs: Additional arguments.
        """
        if not bearing.calc_is_finished():
            raise ValueError("bearing is not calc finished")
        self.main_model = bearing.main_model
        # Analysis callers provide a dedicated runtime, so copying here is both
        # unnecessary and invalid once immutable result snapshots are attached.
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
    """Build four ready native mixed-bearing pads."""
    pad_configs = [copy.deepcopy(pad_config) for _ in range(4)]
    x0s = pad_config.x0s
    for x0, pc in zip(x0s, pad_configs):
        pc.x0 = x0
    bearings = [_DimensionalMixedFilmRuntime(pc) for pc in pad_configs]
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
        _NondimensionalFilmRuntime(
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


def get_pad_pressure_fields(pads):
    """Return a ``label -> pressure_field`` dict for an iterable/dict of pads."""
    if isinstance(pads, dict):
        return {label: pad.postprocess.p for label, pad in pads.items()}
    return {f"pad_{i}": pad.postprocess.p for i, pad in enumerate(pads)}


if __name__ == "__main__":
    unittest.main()
