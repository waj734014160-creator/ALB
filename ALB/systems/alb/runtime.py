# coding: utf-8
import copy
from typing import Any, Iterable, Union

import numpy as np
from scipy import sparse as sp
from scipy.sparse import linalg as sl

from ALB.core.component import BaseSimpleModel
from ALB.core.diagnostics import sanitize_exception_message
from ALB.core.lifecycle import RuntimeLifecycle
from ALB.core.time import control_steps_per_period
from ALB.core.validation import limit_signal
from ALB.physics.bearing.solver import (
    four_pads_bearings,
    nodim_four_pads_bearings,
)
from ALB.config import (
    ALBConfig,
    CsoArgs,
    FPBConfig,
    FuzzyPIDConfig,
    NodimALBConfig,
    OrificeConfig,
    PIDConfig,
    TankConfig,
    ThermalConfig,
)
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.blocks import run_controller_step, run_valve_step
from ALB.physics.hydraulics.orifice import CSOrifice, NodimCSOrifice
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    BearingRuntimeProtocol,
    ControllerProtocol,
    ConvergenceStatus,
    DirectSpoolBearingInput,
    LifecycleState,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.control.valve import static_sv
from ALB.physics.thermal.solver import (
    NodimThermalHydroBearing,
    wrap_pad_collection_with_thermal,
)

_NODIM_ALB_FORBIDDEN_PAD_KWARGS = {"miu", "c", "r", "l", "ps", "rho", "w", "w_rad"}
_NODIM_ALB_REQUIRED_KEYS = [
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

def _control_steps_per_period(alb_config) -> int:
    """Return the validated number of evaluations per controller sample."""

    controller_config = getattr(alb_config, "controller_config", None)
    period = getattr(controller_config, "control_period", None)
    if controller_config is None or period is None:
        return 1
    steps = control_steps_per_period(period, alb_config.dt)
    if steps is None:
        raise ValueError(
            "controller control_period must be an integer multiple of the "
            f"active-bearing dt {alb_config.dt!r}; got {period!r}"
        )
    return steps


class ALB:
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
        if alb_config is None:
            alb_config = ALBConfig()
        self._t: Any = None
        self._pads = tuple(pads)
        if len(self._pads) == 0:
            raise Exception("pads can't be empty")
        self._servovalves = tuple(servovalves)
        self.static_sv: Any = None
        self.node_link = alb_config.node_link
        if controller is not None and not isinstance(
            controller,
            ControllerProtocol,
        ):
            raise TypeError("controller must satisfy ControllerProtocol")
        self._controller = controller
        self._uv: Any = None
        self._uxy: Any = None
        self._uxyt: Any = None
        self._uxy_nodim: Any = None
        self._uxyt_nodim: Any = None
        self._gxy = alb_config.gxy
        self._gxyt = alb_config.gxyt
        c_scale = getattr(alb_config, "c", None)
        if c_scale is None:
            self._c = self._pads[0].main_model.args["c"]
        else:
            self._c = c_scale
        w_scale = getattr(alb_config, "w", None)
        if w_scale is None:
            self._w = self._pads[0].main_model.args["w"]
        else:
            self._w = w_scale
        self._w_rad = self._w / 60 * 2 * np.pi
        self._vf = self._pads[0].main_model.args["vf"]
        self._control_enabled = (
            alb_config.control_mode in {"pid", "fuzzy_pid"}
        )
        self._control_steps = _control_steps_per_period(alb_config)
        self._control_counter = 0
        self._held_command: np.ndarray | None = None
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
        self._create_static_sv()
        self.force: Any = None
        self._reset_for_owner()

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
    def lifecycle_state(self) -> LifecycleState:
        """Return the current strict runtime state."""

        return self._lifecycle.state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return cached local convergence without advancing child solvers."""

        return self._convergence_status

    @property
    def control_steps_per_period(self) -> int:
        """Return ``m = Ts / dt``, the evaluations per controller sample.

        ``1`` reproduces the historical behavior in which the controller runs
        on every evaluation. Larger values hold the controller command for
        ``m`` consecutive evaluations (zero-order hold) while the valves keep
        advancing with ``dt``.
        """

        return self._control_steps

    def _initialize_children(self) -> None:
        for pad in self._pads:
            reset = getattr(pad, "_reset_for_owner", None)
            if not callable(reset):
                raise TypeError(
                    "active-bearing pads must provide _reset_for_owner()"
                )
            reset()
        for servovalve in self._servovalves:
            servovalve._reset_for_owner()
        for servovalve in self.static_sv:
            servovalve._reset_for_owner()
        if self._controller is not None:
            self._controller._reset_for_owner()

    def _reset_for_owner(self) -> None:
        """Reset a fresh session when invoked by the owning composite."""

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
        self._control_counter = 0
        self._held_command = None
        try:
            self._initialize_children()
        except BaseException as exc:
            self._failure = self._build_failure_snapshot(exc, "reset")
            raise
        self._switch = self._control_enabled and self._t_on is None
        self._convergence_status = ConvergenceStatus.pending(
            "input not evaluated"
        )
        self._lifecycle.reset()

    def _create_static_sv(self, servovalves=None):
        """
        Create static servovalves.
        """
        if servovalves is None:
            servovalves = self._servovalves
        svs = [static_sv(0.5) for _ in servovalves]
        ofs = [sv.simple_models for sv in servovalves]
        for sv, of in zip(svs, ofs):
            sv.simple_models = of
        self.static_sv = svs
        return svs

    def turn_on_at(self, t_on: float):
        """Schedule control activation when the permanent config switch is enabled.

        Uncontrolled and external-spool configurations always disable this
        schedule. Positive
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

        self._uv = self._sampled_control_command(static=static)
        if static:
            sv = self.static_sv
            self._initialize_children()
        else:
            sv = self._servovalves
        for num, servovalve in enumerate(sv):
            run_valve_step(servovalve, self._t, self._uv[num])
        forces = []
        frictions = []
        for pad in self._pads:
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
        """Evaluate one native pad without changing calculation order."""

        if not isinstance(pad, BearingRuntimeProtocol):
            raise TypeError(
                "active-bearing pads must satisfy BearingRuntimeProtocol"
            )
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

    def _collect_convergence_status(self) -> ConvergenceStatus:
        components = [*self._pads, *self._servovalves]
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
                pad_results = [pad.result_snapshot() for pad in self._pads]
                pad_forces = np.vstack(
                    [
                        np.asarray(result.values["force"], dtype=float)
                        for result in pad_results
                    ]
                )
                result_values = {
                    "force": output.force,
                    "friction": friction,
                    "pad_force": pad_forces,
                }
                if all("pressure" in result.values for result in pad_results):
                    result_values["pad_pressure"] = np.stack(
                        [
                            np.asarray(result.values["pressure"], dtype=float)
                            for result in pad_results
                        ]
                    )
                if all(
                    "film_thickness" in result.values
                    for result in pad_results
                ):
                    result_values["pad_film_thickness"] = np.stack(
                        [
                            np.asarray(
                                result.values["film_thickness"],
                                dtype=float,
                            )
                            for result in pad_results
                        ]
                    )
                thermal_t_eff = [
                    float(result.values["t_eff"])
                    for result in pad_results
                    if "t_eff" in result.values
                ]
                if thermal_t_eff:
                    result_values["thermal_t_eff"] = np.asarray(
                        thermal_t_eff,
                        dtype=float,
                    )
                bundle = result_snapshot(
                    result_values,
                    {
                        "schema": "alb.bearing-runtime-result.v1",
                        "time": output.time,
                        "unit_system": output.unit_system.value,
                        "converged": convergence.converged,
                        **(
                            self._pads[0]
                            .bearing.main_model.discretization_metadata()
                            if hasattr(self._pads[0], "bearing")
                            and hasattr(
                                self._pads[0].bearing.main_model,
                                "discretization_metadata",
                            )
                            else {}
                        ),
                        "temperature_dofs": int(
                            pad_results[0].metadata.get("temperature_dofs", 0)
                        ),
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
                f"{type(self).__name__} is failed; rebuild it or let its "
                f"owner reinitialize it before {action}"
            )

    def _require_ready(self, action: str) -> None:
        if self._lifecycle.state is not LifecycleState.READY:
            raise RuntimeError(
                f"{type(self).__name__} must be ready before {action}"
            )

    def _sampled_control_command(self, *, static: bool) -> np.ndarray:
        """Return the controller command for the latched input.

        With one evaluation per control period, or for static linearization
        samples, the controller runs on every call exactly as before 0.4.6.
        Otherwise it runs only when the evaluation counter is a multiple of
        ``m`` and the previous command is held in between. A disabled
        controller (``turn_on_at`` not reached) commands zero.
        """

        if static or self._control_steps == 1:
            if not static:
                self._control_counter += 1
            if self._switch:
                return self._control_process(
                    self._uxy_nodim, self._uxyt_nodim, self._t
                )
            return np.zeros(2)
        sample = self._control_counter % self._control_steps == 0
        self._control_counter += 1
        if not self._switch:
            self._held_command = np.zeros(2)
            return np.zeros(2)
        if sample or self._held_command is None:
            self._held_command = np.asarray(
                self._control_process(
                    self._uxy_nodim, self._uxyt_nodim, self._t
                ),
                dtype=float,
            ).copy()
        return self._held_command.copy()

    def _control_process(self, uxy: np.ndarray, uxyt: np.ndarray, t: np.float64):
        """Return one controller command, or zero when no controller is installed."""
        uv = np.dot(self._gxy, uxy) + np.dot(self._gxyt, uxyt)
        u0 = np.zeros_like(uv)
        if self._controller is not None:
            return run_controller_step(self._controller, t, uv - u0)
        return np.zeros_like(uv)

    def actuator_state_space(self) -> tuple[tuple[np.ndarray, ...], ...]:
        """Return continuous ``(A, B, C, D)`` for each servovalve channel.

        Matrices use the valve time unit (seconds for dimensional bearings,
        bearing-local time for nondimensional ones). A static valve has no
        states and only a feedthrough ``D``.
        """

        channels = []
        for servovalve in self._servovalves:
            model = servovalve.main_model
            channels.append(
                tuple(
                    np.array(matrix, dtype=float, copy=True)
                    for matrix in (model.A, model.B, model.C, model.D)
                )
            )
        return tuple(channels)

    def sample_actuator_command(self, dto: BearingInput) -> np.ndarray:
        """Run one controller sample for ``dto`` and return the valve command.

        This is the sampled-control hook used by an integrator that owns the
        valve states (ROS2). It applies the same control switch, sensor
        transform, and nondimensional scaling as :meth:`evaluate` and limits
        the command to ``[-1, 1]`` exactly as the valve input does. It does not
        publish bearing output.
        """

        self._require_ready("sampling the controller")
        self._latch_bearing_input(dto)
        if self._switch:
            command = self._control_process(
                self._uxy_nodim, self._uxyt_nodim, self._t
            )
        else:
            command = np.zeros(2)
        return np.asarray(limit_signal(np.asarray(command, dtype=float)), dtype=float)

    def probe_force_with_spool(
        self,
        dto: BearingInput,
        spool: np.ndarray,
    ) -> np.ndarray:
        """Return the pad force for an explicit spool opening.

        The spool is published to the restrictors through each valve's
        direct-spool port (no valve dynamics are advanced) and every pad is
        evaluated through its side-effect-free ``probe_force``. Lifecycle and
        result snapshots of this runtime are unchanged.
        """

        self._require_ready("probing force")
        if not isinstance(dto, BearingInput):
            raise TypeError("bearing input must be BearingInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("bearing input unit_system does not match runtime")
        values = np.asarray(spool, dtype=float).reshape(-1)
        if values.shape != (len(self._servovalves),):
            raise ValueError("spool must contain one value per servovalve")
        for servovalve, value in zip(self._servovalves, values):
            servovalve.set_spool(value)
        return self._probe_pads(dto)

    def _probe_pads(self, dto: BearingInput) -> np.ndarray:
        forces = []
        for pad in self._pads:
            probe = getattr(pad, "probe_force", None)
            if not callable(probe):
                raise TypeError(
                    f"active-bearing pad {type(pad).__name__} cannot evaluate "
                    "force without side effects"
                )
            forces.append(
                np.asarray(
                    probe(
                        BearingInput(
                            dto.displacement,
                            dto.velocity,
                            dto.time,
                            self.unit_system,
                        )
                    ),
                    dtype=float,
                ).reshape(2)
            )
        return np.sum(np.array(forces), axis=0)

    def calc_is_finished(self):
        """Return the cached completion state without querying child solvers."""

        return self._convergence_status.converged

    def set_thickness(self, *args, **kwargs):
        """
        Set the thickness of the pad, an interface for trajectory calculation.
        """
        for pad in self._pads:
            pad.set_thickness(*args, **kwargs)

    def calc_capacity(self, *args, **kwargs):
        """
        Calculate the bearing capacity, an interface for trajectory calculation.
        """
        ans = np.array([pad.calc_capacity(*args, **kwargs) for pad in self._pads])
        return np.sum(ans, axis=0)

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
        for n, sv in enumerate(self._servovalves):
            sv.set_spool(self._sv[n])

        forces = []
        frictions = []
        for pad in self._pads:
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

    def probe_force(self, dto: DirectSpoolBearingInput) -> np.ndarray:
        """Return the force for one direct-spool DTO without side effects."""

        if not isinstance(dto, DirectSpoolBearingInput):
            raise TypeError("direct spool input must be DirectSpoolBearingInput")
        return self.probe_force_with_spool(dto.bearing, dto.spool.spool)

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
        self._uv = self._sampled_control_command(static=static)
        if static:
            sv = self.static_sv
            self._initialize_children()
        else:
            sv = self._servovalves
        for num, servovalve in enumerate(sv):
            run_valve_step(servovalve, self._t, self._uv[num])
        forces = []
        frictions = []
        for pad in self._pads:
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
        for num, servovalve in enumerate(self._servovalves):
            servovalve.set_spool(self._sv[num])

        forces = []
        frictions = []
        for pad in self._pads:
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

    def probe_force(self, dto: DirectSpoolBearingInput) -> np.ndarray:
        """Return the force for one direct-spool DTO without side effects."""

        if not isinstance(dto, DirectSpoolBearingInput):
            raise TypeError("direct spool input must be DirectSpoolBearingInput")
        return self.probe_force_with_spool(dto.bearing, dto.spool.spool)

__all__ = ['ALB', 'ALBSV', 'NodimALB', 'NodimALBSV']
