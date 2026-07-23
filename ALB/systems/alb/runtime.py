# coding: utf-8
import copy
from typing import Any, TYPE_CHECKING, Iterable, Union

import numpy as np
import pandas as pd
from scipy import sparse as sp
from scipy.sparse import linalg as sl

from ALB.core.component import BaseCSystem, BaseSimpleModel
from ALB.core.events import Signal
from ALB.core.diagnostics import sanitize_exception_message
from ALB.core.lifecycle import RuntimeLifecycle
from ALB.physics.bearing import four_pads_bearings, nodim_four_pads_bearings
from ALB.config import (
    ALBConfig,
    CsoArgs,
    FPBConfig,
    FuzzyPIDConfig,
    NodimALBConfig,
    OrificeConfig,
    PIDConfig,
    ServoConfig,
    TankConfig,
    ThermalConfig,
    build_thermal_config,
)
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.adapters import adapt_controller
from ALB.control.blocks import run_controller_step, run_valve_step
from ALB.physics.hydraulics import CSOrifice, NodimCSOrifice
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    BearingRuntimeProtocol,
    ConvergenceStatus,
    DirectSpoolBearingInput,
    LifecycleState,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.control.valve import moog_2nd_servovalve, moog_servovalve, static_sv
from ALB.physics.thermal import (
    NodimThermalHydroBearing,
    wrap_pad_collection_with_thermal,
)

if TYPE_CHECKING:
    from ALB.surrogate.inference import ALBNet

_NODIM_ALB_FORBIDDEN_PAD_KWARGS = {"miu", "c", "r", "l", "ps", "rho", "w", "w_rad"}
_NODIM_ALB_LEGACY_REQUIRED_KEYS = [
    "lambda_value",
    "lr",
    "lx",
    "lz",
    "position",
    "cq0",
    "cq1",
    "cq2",
]
_NODIM_ALB_PAD_MAIN_KEYS = {"lambda_value", "lr", "lx", "lz", "nx", "nz", "bias"}

class ALB(BaseCSystem):
    """Active lubricated bearing with a strict DTO lifecycle."""

    input_dto_type = BearingInput
    unit_system = UnitSystem.DIMENSIONAL

    def __init__(
        self,
        pads: Iterable,
        servovalves: list,
        controller=None,
        alb_config: ALBConfig | None = None,
    ):
        """
        This class represents an Active Lubricated Bearing (ALB) system.
        It takes pre-defined servovalves, controllers, orifices, and pads to establish the connections within the ALB.
        """
        super().__init__()
        if alb_config is None:
            alb_config = ALBConfig()
        self._t: Any = None
        self.pads = list(pads)
        self.signal.children = [pad.signal for pad in self.pads]
        if len(self.pads) == 0:
            raise Exception("pads can't be empty")
        self.servovalves = servovalves
        self.static_sv: Any = None
        self.node_link = alb_config.node_link
        self.controller = adapt_controller(controller) if controller is not None else None
        self._uv: Any = None
        self._uxy: Any = None
        self._uxyt: Any = None
        self._uxy_nodim: Any = None
        self._uxyt_nodim: Any = None
        self._gxy = alb_config.gxy
        self._gxyt = alb_config.gxyt
        c_scale = getattr(alb_config, "c", None)
        if c_scale is None:
            self._c = self.pads[0].main_model.args["c"]
        else:
            self._c = c_scale
        w_scale = getattr(alb_config, "w", None)
        if w_scale is None:
            self._w = self.pads[0].main_model.args["w"]
        else:
            self._w = w_scale
        self._w_rad = self._w / 60 * 2 * np.pi
        self._vf = self.pads[0].main_model.args["vf"]
        self._control_enabled = bool(alb_config.switch)
        self._t_on: float | None = None
        self._switch = self._control_enabled
        self._lifecycle = RuntimeLifecycle(
            type(self).__name__,
            input_label="bearing input",
        )
        self._latest_output: BearingOutput | None = None
        self._latest_result: ResultBundle | None = None
        self._failure: ResultBundle | None = None
        self._convergence_status = ConvergenceStatus.pending(
            "runtime is not initialized"
        )
        self._friction: float | None = None
        self._results = pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )
        self._create_static_sv()
        self.force: Any = None

    @property
    def gxy(self):
        return self._gxy

    @gxy.setter
    def gxy(self, value):
        self._gxy = value

    @property
    def gxyt(self):
        return self._gxyt

    @gxyt.setter
    def gxyt(self, value):
        self._gxyt = value

    @property
    def results(self):
        self._require_valid("read legacy results")
        return self._results

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the current strict runtime state."""

        return self._lifecycle.state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return cached local convergence without advancing child solvers."""

        return self._convergence_status

    def _initialize_children(self) -> None:
        for pad in self.pads:
            pad.init()
        for servovalve in self.servovalves:
            servovalve.init()
        if self.controller is not None:
            self.controller.init()

    def init(self) -> None:
        """Start a fresh runtime session after every child initializes."""

        self._lifecycle.fail()
        self._latest_output = None
        self._latest_result = None
        self._failure = None
        self.force = None
        self._friction = None
        self._t = None
        self._uxy = None
        self._uxyt = None
        self._uxy_nodim = None
        self._uxyt_nodim = None
        try:
            self._initialize_children()
        except BaseException as exc:
            self._failure = self._build_failure_snapshot(exc, "init")
            raise
        self._switch = self._control_enabled and self._t_on is None
        self._results = pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.reset()

    def _create_static_sv(self, servovalves=None):
        """
        Create static servovalves.
        """
        if servovalves is None:
            servovalves = self.servovalves
        svs = [static_sv(0.5) for _ in servovalves]
        ofs = [sv.simple_models for sv in servovalves]
        for sv, of in zip(svs, ofs):
            sv.simple_models = of
        self.static_sv = svs
        return svs

    def turn_on_at(self, t_on: float):
        """Schedule control activation when the permanent config switch is enabled.

        ``ALBConfig.switch=False`` always wins over this schedule. Positive
        infinity is accepted as an explicit never-enable schedule.
        """
        activation_time = float(t_on)
        if np.isnan(activation_time):
            raise ValueError("t_on must not be NaN")
        self._t_on = activation_time
        self._switch = False

    def _turn_on(self, t: float):
        """Recompute the active control state from config and schedule."""
        if not self._control_enabled:
            self._switch = False
        elif self._t_on is None:
            self._switch = True
        else:
            self._switch = t >= self._t_on

    def _latch_bearing_input(self, dto: BearingInput) -> None:
        if not isinstance(dto, BearingInput):
            raise TypeError("bearing input must be BearingInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("bearing input unit_system does not match runtime")
        self._t = dto.time
        self._uxy = dto.displacement
        self._uxyt = dto.velocity
        self._uxy_nodim = dto.displacement / self._c
        self._uxyt_nodim = (
            dto.velocity / self._c / (self._vf * self._w_rad)
        )
        self._turn_on(dto.time)

    def input(self, dto: BearingInput) -> None:
        """Validate and latch a dimensional bearing sample without solving."""

        self._lifecycle.require_input_slot()
        self._latch_bearing_input(dto)
        self._latest_output = None
        self._latest_result = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.latch()

    def _calculate_output(
        self,
        *,
        nodim: bool,
        static: bool = False,
    ) -> tuple[np.ndarray, float]:
        """Execute the historical child calculation order exactly once."""

        if self._switch:
            self._uv = self._control_process(self._uxy_nodim, self._uxyt_nodim, self._t)
        else:
            self._uv = np.zeros(2)
        if static:
            sv = self.static_sv
            self._initialize_children()
        else:
            sv = self.servovalves
        for num, servovalve in enumerate(sv):
            run_valve_step(servovalve, self._t, self._uv[num])
        forces = []
        frictions = []
        for pad in self.pads:
            force, friction = self._evaluate_pad(
                pad,
                displacement=self._uxy,
                velocity=self._uxyt,
                nodim=nodim,
            )
            forces.append(force)
            frictions.append(friction)
        forces = np.array(forces)
        frictions = np.sum(np.array(frictions))
        self.force = np.sum(forces, axis=0)
        self._uv = None
        return self.force, float(frictions)

    def _evaluate_pad(
        self,
        pad,
        *,
        displacement: np.ndarray,
        velocity: np.ndarray,
        nodim: bool,
    ) -> tuple[np.ndarray, float]:
        """Evaluate one native or legacy pad without changing calculation order."""

        if isinstance(pad, BearingRuntimeProtocol):
            pad.input(
                BearingInput(
                    displacement,
                    velocity,
                    self._t,
                    self.unit_system,
                )
            )
            pad.evaluate()
            output = pad.output()
            result = pad.result_snapshot()
            return output.force, float(result.values.get("friction", 0.0))
        pad.input(
            t=self._t,
            uxy=displacement,
            uxyt=velocity,
            nodim=nodim,
        )
        output = pad.output(nodim=nodim)
        return output["force"], float(output.get("friction", 0.0))

    def _collect_convergence_status(self) -> ConvergenceStatus:
        components = [*self.pads, *self.servovalves]
        completed = all(
            bool(check())
            for component in components
            if callable(check := getattr(component, "calc_is_finished", None))
        )
        if completed:
            return ConvergenceStatus(
                residual=0.0,
                converged=True,
                message="all ALB child calculations finished",
            )
        return ConvergenceStatus.pending("one or more ALB children are incomplete")

    def _evaluate(self, *, static: bool = False) -> None:
        try:
            with self._lifecycle.evaluation():
                force, friction = self._calculate_output(
                    nodim=self.unit_system is UnitSystem.NONDIMENSIONAL,
                    static=static,
                )
                output = BearingOutput(force, self._t, self.unit_system)
                convergence = self._collect_convergence_status()
                self._friction = friction
                bundle = result_snapshot(
                    {
                        "force": output.force,
                        "friction": friction,
                    },
                    {
                        "schema": "alb.bearing-runtime-result.v1",
                        "time": output.time,
                        "unit_system": output.unit_system.value,
                        "converged": convergence.converged,
                    },
                )
                self._latest_output = output
                self._latest_result = bundle
                self._convergence_status = convergence
        except BaseException as exc:
            self._latest_output = None
            self._latest_result = None
            self._failure = self._build_failure_snapshot(exc, "evaluate")
            raise

    def evaluate(self) -> None:
        """Evaluate the latched input exactly once."""

        self._evaluate()

    def evaluate_static(self) -> None:
        """Evaluate one static linearization sample with reset child models."""

        self._evaluate(static=True)

    def output(self) -> BearingOutput:
        """Read the completed force snapshot without numerical work."""

        self._lifecycle.require_output()
        assert self._latest_output is not None
        return self._latest_output

    def step(self, dto: BearingInput) -> BearingOutput:
        """Compose input, evaluate, and output without committing a step."""

        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> ResultBundle:
        """Return the complete immutable result for the latest evaluation."""

        self._lifecycle.require_output()
        assert self._latest_result is not None
        return self._latest_result

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest failure diagnostic while normal output is sealed."""

        if self._failure is None:
            raise RuntimeError("no ALB runtime failure is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return immutable lifecycle and convergence diagnostics."""

        return result_snapshot(
            {},
            {
                "schema": "alb.bearing-runtime-diagnostic.v1",
                "lifecycle_state": self.lifecycle_state.value,
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
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
                "schema": "alb.bearing-runtime-failure.v1",
                "phase": phase,
                "error_type": type(error).__name__,
                "message": sanitize_exception_message(error),
                "unit_system": self.unit_system.value,
                "node_link": self.node_link,
            },
        )

    def _require_valid(self, action: str) -> None:
        if self._lifecycle.state is LifecycleState.FAILED:
            raise RuntimeError(
                f"{type(self).__name__} is failed; call init() before {action}"
            )

    def _control_process(self, uxy: np.ndarray, uxyt: np.ndarray, t: np.float64):
        """Return one controller command, or zero when no controller is installed."""
        uv = np.dot(self._gxy, uxy) + np.dot(self._gxyt, uxyt)
        u0 = np.zeros_like(uv)
        if self.controller is not None:
            return run_controller_step(self.controller, t, uv - u0)
        return np.zeros_like(uv)

    def calc_is_finished(self):
        """Return the cached completion state without querying child solvers."""

        return self._convergence_status.converged

    def set_thickness(self, *args, **kwargs):
        """
        Set the thickness of the pad, an interface for trajectory calculation.
        """
        for pad in self.pads:
            pad.set_thickness(*args, **kwargs)

    def calc_capacity(self, *args, **kwargs):
        """
        Calculate the bearing capacity, an interface for trajectory calculation.
        """
        ans = np.array([pad.calc_capacity(*args, **kwargs) for pad in self.pads])
        return np.sum(ans, axis=0)

    def solve(self, *args, **kwargs):
        """Compatibility alias for explicit evaluation."""

        if args or kwargs:
            raise TypeError("solve() no longer accepts output options")
        self.evaluate()

    def save(self, tofile, path, name, *args, **kwargs):
        """
        Save the calculation results.
        """
        self._require_valid("save")
        if path is None:
            path = "alb"
        if name is None:
            name = "alb"
        res = {name + "_res": self._results}
        res = DataFrameResult(res)
        node = SaveTreeNode(path, res)
        children = []
        for num, pad in enumerate(self.pads):
            children.append(
                pad.save(path="pad" + str(num), name="pad_res", tofile=False)
            )
        for num, servovalve in enumerate(self.servovalves):
            children.append(
                servovalve.save(
                    path="servovalves" + str(num), name="servovalve_res", tofile=False
                )
            )
        if self.controller is not None:
            children.append(
                self.controller.save(
                    path="controller", name="controller_res", tofile=False
                )
            )
        node.add_children(children)
        if tofile:
            return node.persist(kwargs.get("writer"), path)
        return node

    def start_signal(self):
        return True

    def finish_signal(self):
        """
        Add calculation results to the result DataFrame.
        """
        self._results.loc[self._results.shape[0]] = [
            self._t,
            self._uxy[0],
            self._uxy[1],
            self._uxyt[0],
            self._uxyt[1],
            self.force[0],
            self.force[1],
        ]
        return True

class ALBSV(ALB):
    """Direct-spool dimensional ALB runtime."""

    input_dto_type = DirectSpoolBearingInput

    def __init__(
        self,
        pads: Iterable,
        servovalves: list,
        controller=None,
        alb_config: ALBConfig | None = None,
    ):
        if alb_config is None:
            alb_config = ALBConfig()
        super().__init__(pads, servovalves, controller, alb_config)
        self._sv = None

    def input(self, dto: DirectSpoolBearingInput) -> None:
        """Latch state and an explicit normalized spool command."""

        self._lifecycle.require_input_slot()
        if not isinstance(dto, DirectSpoolBearingInput):
            raise TypeError("direct spool input must be DirectSpoolBearingInput")
        self._latch_bearing_input(dto.bearing)
        self._sv = dto.spool.spool
        self._latest_output = None
        self._latest_result = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.latch()

    def _calculate_output(
        self,
        *,
        nodim: bool,
        static: bool = False,
    ) -> tuple[np.ndarray, float]:
        del static
        for n, sv in enumerate(self.servovalves):
            sv.set_spool(self._sv[n])

        forces = []
        frictions = []
        for pad in self.pads:
            force, friction = self._evaluate_pad(
                pad,
                displacement=self._uxy,
                velocity=self._uxyt,
                nodim=nodim,
            )
            forces.append(force)
            frictions.append(friction)
        forces = np.array(forces)
        frictions = np.sum(np.array(frictions))
        self.force = np.sum(forces, axis=0)
        self._uv = None
        return self.force, float(frictions)

    def step(self, dto: DirectSpoolBearingInput) -> BearingOutput:
        """Compose direct-spool input, evaluation, and read-only output."""

        self.input(dto)
        self.evaluate()
        return self.output()

class NodimALB(ALB):
    """ALB assembled from nondimensional pads and driven by nondimensional states."""

    unit_system = UnitSystem.NONDIMENSIONAL

    def __init__(
        self,
        pads: Iterable,
        servovalves: list,
        controller=None,
        alb_config: NodimALBConfig | None = None,
    ):
        if alb_config is None:
            alb_config = NodimALBConfig()
        super().__init__(pads, servovalves, controller, alb_config)

    def _latch_bearing_input(self, dto: BearingInput) -> None:
        if not isinstance(dto, BearingInput):
            raise TypeError("bearing input must be BearingInput")
        if dto.unit_system is not UnitSystem.NONDIMENSIONAL:
            raise ValueError("NodimALB requires nondimensional BearingInput")
        self._t = dto.time
        self._uxy = dto.displacement
        self._uxyt = dto.velocity
        self._uxy_nodim = dto.displacement
        self._uxyt_nodim = dto.velocity
        self._turn_on(dto.time)

    def _calculate_output(
        self,
        *,
        nodim: bool,
        static: bool = False,
    ) -> tuple[np.ndarray, float]:
        if not nodim:
            raise ValueError("NodimALB only evaluates nondimensional force")
        if self._switch:
            self._uv = self._control_process(self._uxy_nodim, self._uxyt_nodim, self._t)
        else:
            self._uv = np.zeros(2)
        if static:
            sv = self.static_sv
            self._initialize_children()
        else:
            sv = self.servovalves
        for num, servovalve in enumerate(sv):
            run_valve_step(servovalve, self._t, self._uv[num])
        forces = []
        frictions = []
        for pad in self.pads:
            force, friction = self._evaluate_pad(
                pad,
                displacement=self._uxy_nodim,
                velocity=self._uxyt_nodim,
                nodim=True,
            )
            forces.append(force)
            frictions.append(friction)
        self.force = np.sum(np.array(forces), axis=0)
        frictions = np.sum(np.array(frictions))
        self._uv = None
        return self.force, float(frictions)

class NodimALBSV(NodimALB):
    """Direct-spool nondimensional ALB runtime."""

    input_dto_type = DirectSpoolBearingInput

    def __init__(
        self,
        pads: Iterable,
        servovalves: list,
        controller=None,
        alb_config: NodimALBConfig | None = None,
    ):
        if alb_config is None:
            alb_config = NodimALBConfig()
        super().__init__(pads, servovalves, controller, alb_config)
        self._sv = None

    def input(self, dto: DirectSpoolBearingInput) -> None:
        """Latch nondimensional state and normalized spool command."""

        self._lifecycle.require_input_slot()
        if not isinstance(dto, DirectSpoolBearingInput):
            raise TypeError("direct spool input must be DirectSpoolBearingInput")
        self._latch_bearing_input(dto.bearing)
        self._sv = dto.spool.spool
        self._latest_output = None
        self._latest_result = None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.latch()

    def _calculate_output(
        self,
        *,
        nodim: bool,
        static: bool = False,
    ) -> tuple[np.ndarray, float]:
        del static
        if not nodim:
            raise ValueError("NodimALBSV only outputs nondimensional force")
        for num, servovalve in enumerate(self.servovalves):
            servovalve.set_spool(self._sv[num])

        forces = []
        frictions = []
        for pad in self.pads:
            force, friction = self._evaluate_pad(
                pad,
                displacement=self._uxy_nodim,
                velocity=self._uxyt_nodim,
                nodim=True,
            )
            forces.append(force)
            frictions.append(friction)
        self.force = np.sum(np.array(forces), axis=0)
        frictions = np.sum(np.array(frictions))
        self._uv = None
        return self.force, float(frictions)

    def step(self, dto: DirectSpoolBearingInput) -> BearingOutput:
        """Compose direct-spool input, evaluation, and read-only output."""

        self.input(dto)
        self.evaluate()
        return self.output()

__all__ = ['ALB', 'ALBSV', 'NodimALB', 'NodimALBSV']
