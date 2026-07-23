# coding: utf-8

from decimal import Decimal
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from tqdm import tqdm

from ALB.core.component import BaseCSystem, BaseSystem
from ALB.core.lifecycle import LifecycleState
from ALB.core.validation import require_unit_system, validate_bearing_output
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    BearingRuntimeProtocol,
    DirectSpoolBearingInput,
    PendingRecord,
    RecordingRecovered,
    RecordReceipt,
    ResultBundle,
    RotorLoadInput,
    StepCompleted,
    StepContext,
    StepRecordingStatus,
    UnitSystem,
    ValveOutput,
    result_snapshot,
    validate_recordable_bundle,
)
from ALB.dynamics.rotor import Gravity, StaticLoad

# from ALB.infrastructure.logging import logger
from .rotor import RossRotor, SingleRotor, UnbalancedExcitation
from .coupling_runtime import (
    CouplingStepRuntime,
    PostCommitObserverError,
    PostCommitRecordingError,
    coupling_snapshot,
)
from .coupling_results import build_coupling_save_tree
from .bindings import CoupledBearingBinding, CouplingRuntimeDependencies
from ALB.core.numerics.arrays import vertical_stack_nonempty
from ALB.core.observers import ObserverDispatcher


class RotorBearingCouple(BaseSystem):
    """
    Couple a single rotor model with one bearing model for co-simulation.
    """

    def __init__(self, rotor: SingleRotor, bearing, time_iter, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rotor = rotor
        self.bearing = bearing
        self._time_iter = time_iter
        self._result = {"rotor": [], "bearing": []}

    def solve(self, **kwargs):
        self.rotor.set_dt(self._time_iter.dt)
        self.rotor.set_rpm(1000)
        for ts in self._time_iter():
            bearing_output = self.bearing.output()
            force = bearing_output["force"]
            # logger.info("force:{}".format(force))

            w = bearing_output["w"]
            self.rotor.set_rpm(w)

            self.rotor.input(force, **kwargs)

            rotoru = self.rotor.output(ts, **kwargs)
            # logger.info("rotor:{}".format(rotoru))

            self.bearing.input(rotoru, np.zeros_like(rotoru))

            self._result["rotor"].append(rotoru)


class RsRotorBearingCouple(BaseCSystem):
    """Couple a ROSS rotor with bearings using exactly-once step commits.

    A failure after component mutation invalidates the coupler. Call ``init()``
    before reading or advancing again so a partially applied physical step
    cannot be retried as if it were untouched.
    """

    def __init__(self, rotor: RossRotor, time_iter, *bearings, **kwargs):
        """
        options:
            save_path:default="./rotor_bearing_couple"
        """
        super().__init__()
        self.rotor = rotor
        binding_flags = [isinstance(item, CoupledBearingBinding) for item in bearings]
        if any(binding_flags) and not all(binding_flags):
            raise TypeError("cannot mix coupled bindings and legacy bearing objects")
        self.bindings = list(bearings) if all(binding_flags) and bearings else []
        self.bearings = (
            [binding.bearing for binding in self.bindings]
            if self.bindings
            else list(bearings)
        )
        for bearing in self.bearings:
            self._validate_bearing(
                bearing,
                allow_nondimensional=bool(self.bindings),
            )
        if not self.bindings:
            self.signal.children = [bearing.signal for bearing in self.bearings]
            self.signal.add_child(self.rotor.signal)
        self.forces = []
        self._time_iter = time_iter
        self._result = {}
        self._save_path = kwargs.get("save_path", "rotor_bearing_couple")
        self._fnode_links: Any = None
        self._bnode_links: Any = None
        self._forceu0: Any = None
        self._forceu1: Any = None
        self._forcef0: Any = None
        self._forcef1: Any = None
        self._forcen0: Any = None
        self._forcen1: Any = None

        self._rp: Any = None
        self._nt: Any = None
        self._ts: Any = None
        self._last_output: ResultBundle | None = None
        self._runtime = CouplingStepRuntime()
        self._step_ledger = self._runtime.ledger
        self._valid = False
        self._dependencies = kwargs.get("dependencies") or CouplingRuntimeDependencies(
            run_id=f"coupling-{uuid4().hex}"
        )
        self._run_id = self._dependencies.run_id
        self._run_started = False
        self._pending_record: PendingRecord | None = None
        self._record_receipt: RecordReceipt | None = None
        self._recording_status = StepRecordingStatus.NOT_CONFIGURED
        self._observer_dispatcher = ObserverDispatcher(
            self._dependencies.observers
        )
        self._failure_result: ResultBundle | None = None
        self._adapter_metadata: tuple[dict[str, object], ...] = ()

    @property
    def results(self):
        self._require_valid("reading results")
        return self._result

    def _require_valid(self, operation: str) -> None:
        """Reject access to state that may contain a partially applied step."""

        if not self._runtime.is_valid:
            raise RuntimeError(
                f"coupling state is invalid; call init() before {operation}"
            )

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the shared coupled-runtime state."""

        return self._runtime.state

    def _invalidate_runtime(self) -> None:
        """Block access after a partial step or a topology change."""

        self._runtime.fail()
        self._valid = False
        self._last_output = None

    def _seal_failure(
        self,
        context: StepContext | None,
        phase: str,
        error: BaseException,
    ) -> None:
        """Seal a sanitized pre-commit failure before invalidating runtime."""

        last_result = self._last_output
        self._failure_result = result_snapshot(
            {
                "last_committed_result": (
                    None
                    if last_result is None
                    else {
                        "values": last_result.values,
                        "metadata": last_result.metadata,
                    }
                )
            },
            {
                "run_id": self._run_id,
                "attempted_context": (
                    None
                    if context is None
                    else {
                        "step_index": context.step_index,
                        "time": context.time,
                        "dt": context.dt,
                        "unit_system": context.unit_system.value,
                    }
                ),
                "phase": phase,
                "component": "rotor-bearing coupling",
                "error_type": type(error).__name__,
                "message": str(error),
                "physical_step_committed": False,
            },
        )
        self._invalidate_runtime()

    def failure_snapshot(self) -> ResultBundle:
        """Return the latest sanitized pre-commit failure diagnostic."""

        if self._failure_result is None:
            raise RuntimeError("no coupling failure snapshot is available")
        return self._failure_result

    def diagnostic_snapshot(self) -> ResultBundle:
        """Return current post-commit status without exposing mutable state."""

        context = self._step_ledger.last_context
        return result_snapshot(
            {
                "observer_failures": tuple(
                    {
                        "observer_name": failure.observer_name,
                        "event_type": failure.event_type,
                        "error_type": failure.error_type,
                        "message": failure.message,
                    }
                    for failure in self._observer_dispatcher.failures
                )
            },
            {
                "run_id": self._run_id,
                "committed_step_index": (
                    None if context is None else context.step_index
                ),
                "physical_step_committed": context is not None,
                "recording_status": self._recording_status.value,
                "pending_record_key": (
                    None
                    if self._pending_record is None
                    else {
                        "run_id": self._pending_record.run_id,
                        "step_index": self._pending_record.context.step_index,
                    }
                ),
                "next_advance_blocked": self._pending_record is not None,
            },
        )

    def _begin_recorder_if_needed(self) -> None:
        recorder = self._dependencies.recorder
        if recorder is not None and not self._run_started:
            recorder.begin_run(self._run_id)
            self._run_started = True

    def _after_commit(
        self,
        context: StepContext,
        bundle: ResultBundle,
    ) -> None:
        """Record and observe one already committed physical step."""

        recorder = self._dependencies.recorder
        pending_error: BaseException | None = None
        if recorder is None:
            self._recording_status = StepRecordingStatus.NOT_CONFIGURED
            self._record_receipt = None
        else:
            try:
                self._record_receipt = recorder.record(context, bundle)
                self._recording_status = StepRecordingStatus.RECORDED
                self._pending_record = None
            except Exception as exc:
                pending_error = exc
                self._recording_status = StepRecordingStatus.PENDING
                self._record_receipt = None
                self._pending_record = PendingRecord(
                    self._run_id,
                    context,
                    bundle,
                    f"{type(exc).__name__}: {exc}",
                )
        event = StepCompleted(
            self._run_id,
            context,
            bundle,
            self._recording_status,
            self._record_receipt,
            self._pending_record,
        )
        observer_failures = self._observer_dispatcher.step_completed(event)
        if (
            observer_failures
            and self._dependencies.observer_failure_policy == "raise"
        ):
            raise PostCommitObserverError(observer_failures)
        if (
            pending_error is not None
            and self._dependencies.record_failure_policy == "raise"
        ):
            raise PostCommitRecordingError(self._pending_record)

    def retry_pending_record(self) -> RecordReceipt:
        """Retry only post-commit recording without re-running physics."""

        if self._pending_record is None:
            raise RuntimeError("no pending record is available")
        recorder = self._dependencies.recorder
        if recorder is None:
            raise RuntimeError("no recorder is configured")
        pending = self._pending_record
        receipt = recorder.record(pending.context, pending.bundle)
        self._pending_record = None
        self._record_receipt = receipt
        self._recording_status = StepRecordingStatus.RECORDED
        self._observer_dispatcher.recording_recovered(
            RecordingRecovered(self._run_id, pending.key, receipt)
        )
        return receipt

    def _invalidate_topology(self) -> None:
        """Require a fresh init after the coupled component graph changes."""

        self._invalidate_runtime()
        self._fnode_links = None
        self._bnode_links = None

    def add_bearing(self, bearing):
        self._validate_bearing(bearing)
        self.bearings.append(bearing)
        self.signal.children.append(bearing.signal)
        bearing.signal.father = self.signal
        self._invalidate_topology()

    @staticmethod
    def _validate_bearing(bearing, *, allow_nondimensional: bool = False):
        """Validate the minimum dimensional bearing integration contract."""

        for attribute in ("node_link", "init", "input", "output"):
            if not hasattr(bearing, attribute):
                raise TypeError(f"bearing must provide '{attribute}'")
        if hasattr(bearing, "input_dto_type") and not isinstance(
            bearing, BearingRuntimeProtocol
        ):
            raise TypeError("native bearing must satisfy BearingRuntimeProtocol")
        if (
            allow_nondimensional
            and UnitSystem.coerce(bearing.unit_system)
            is UnitSystem.NONDIMENSIONAL
        ):
            return
        require_unit_system(
            bearing,
            "dimensional",
            component_name="rotor-coupled bearing",
        )

    @staticmethod
    def _evaluate_bearing(
        bearing,
        displacement,
        velocity,
        context: StepContext,
        binding: CoupledBearingBinding | None = None,
    ) -> tuple[np.ndarray, dict[str, object] | None]:
        """Evaluate a native bearing runtime or a transitional legacy bearing."""

        if (
            isinstance(bearing, BearingRuntimeProtocol)
            and bearing.input_dto_type in (BearingInput, DirectSpoolBearingInput)
        ):
            global_input = BearingInput(
                displacement=displacement,
                velocity=velocity,
                time=context.time,
                unit_system=UnitSystem.DIMENSIONAL,
            )
            adapter = binding.unit_adapter if binding is not None else None
            local_context = (
                adapter.rotor_context_to_bearing(context)
                if adapter is not None
                else context
            )
            local_input = (
                adapter.rotor_input_to_bearing(global_input)
                if adapter is not None
                else global_input
            )
            dto: BearingInput | DirectSpoolBearingInput
            if bearing.input_dto_type is DirectSpoolBearingInput:
                if binding is None or binding.spool_provider is None:
                    raise TypeError(
                        "direct-spool bearings require an explicit spool provider"
                    )
                provider = binding.spool_provider
                provider.input(context, global_input)
                provider.evaluate()
                spool = provider.output()
                if not isinstance(spool, ValveOutput):
                    raise TypeError("spool provider output must be ValveOutput")
                if spool.time != context.time:
                    raise ValueError("spool command time must match global context")
                global_direct = DirectSpoolBearingInput(global_input, spool)
                dto = (
                    adapter.rotor_direct_spool_to_bearing(global_direct)
                    if adapter is not None
                    else global_direct
                )
            else:
                dto = local_input
            bearing.input(dto)
            bearing.evaluate()
            output = bearing.output()
            if not isinstance(output, BearingOutput):
                raise TypeError("native bearing output must be BearingOutput")
            rotor_output = (
                adapter.bearing_output_to_rotor(output)
                if adapter is not None
                else output
            )
            metadata = None
            if adapter is not None:
                metadata = adapter.scales.descriptor(
                    applied_transform="bearing_to_rotor",
                    global_context=context,
                    bearing_local_context=local_context,
                )
            return rotor_output.force.copy(), metadata
        bearing.input(uxy=displacement, uxyt=velocity, t=context.time)
        return validate_bearing_output(bearing.output()), None

    def init(self, **kwargs):
        self._invalidate_runtime()
        try:
            self._begin_recorder_if_needed()
            time_values = [float(value) for value in self._time_iter()]
            if not time_values:
                raise ValueError("rotor-bearing coupling time grid cannot be empty")
            initial_time = time_values[0]
            self.rotor.init()
            for bearing in self.bearings:
                bearing.init()
            self._fnode_links = get_all_attribute_values(self.forces, "node_link")
            self._bnode_links = (
                [binding.node_link for binding in self.bindings]
                if self.bindings
                else get_all_attribute_values(self.bearings, "node_link")
            )
            self._fnode_links = np.hstack(
                [
                    np.array(self._fnode_links, dtype=np.int32),
                    np.array(self._bnode_links, dtype=np.int32),
                ]
            )
            if len(self.forces) == 0:
                self._forceu0 = []
            else:
                self._forceu0 = np.vstack(
                    [force(t=initial_time) for force in self.forces]
                )
            self._rp = self.rotor.output(self._bnode_links)
            for num, bearing in enumerate(self.bearings):
                self._result["bearing" + str(num)] = pd.DataFrame(
                    columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
                )
            self._forcef0 = []
            adapter_metadata = []
            for num, bearing in enumerate(self.bearings):
                rp_uxy = self._rp["uxy"][num]
                rp_uxyt = self._rp["uxyt"][num]
                force, metadata = self._evaluate_bearing(
                    bearing,
                    rp_uxy,
                    rp_uxyt,
                    StepContext(
                        0,
                        initial_time,
                        self._time_iter.dt,
                        UnitSystem.DIMENSIONAL,
                    ),
                    self.bindings[num] if self.bindings else None,
                )
                self._forcef0.append(force)
                if metadata is not None:
                    adapter_metadata.append(metadata)
            self._adapter_metadata = tuple(adapter_metadata)
            self._forcef0 = np.array(self._forcef0)
            self._forcen0 = vertical_stack_nonempty(
                [np.array(self._forceu0), np.array(self._forcef0)]
            )
            self._nt = 0
            self._runtime.reset_ledger()
            self._step_ledger = self._runtime.ledger
            initial_context = StepContext(
                0, initial_time, self._time_iter.dt, UnitSystem.DIMENSIONAL
            )
            candidate = coupling_snapshot(
                self._rp,
                self._forcef0,
                self._forcen0,
                initial_context,
                initial=True,
                unit_adapters=self._adapter_metadata,
            )
            if self._dependencies.recorder is not None:
                validate_recordable_bundle(candidate)
            self._runtime.publish_initial(initial_context)
            self._last_output = candidate
            self._failure_result = None
            self._after_commit(initial_context, candidate)
        except (PostCommitRecordingError, PostCommitObserverError):
            raise
        except BaseException as exc:
            self._seal_failure(None, "init", exc)
            raise
        self._valid = True

    def add_unbalance(
        self, node_link, phase=0, t_max: float = 1, m=0, freq=0, e=0, no_step=False
    ):
        """
        Add an unbalance excitation load to specified rotor node(s).

        :param node_link: Rotor node index or list of node indices.
        :param phase: Initial phase angle of the unbalance excitation.
        :param t_max: Maximum active time for excitation.
        :param m: Equivalent unbalance mass.
        :param freq: Excitation frequency.
        :param e: Eccentricity radius of the unbalance mass.
        :param no_step: Whether to disable step gating in excitation profile.
        """
        ube = UnbalancedExcitation(phase, t_max, m, freq, e, no_step=no_step)
        ube.node_link = node_link
        self.forces.append(ube)
        self._invalidate_topology()

    def add_static_force(self, force, node_link):
        force = StaticLoad(force)
        force.node_link = node_link
        self.forces.append(force)
        self._invalidate_topology()

    def add_gravity(self, g=9.8):
        rotor = self.rotor._rotor
        she = rotor.shaft_elements
        she_n = list(range(len(she) + 1))
        she_m = [el.m for el in she]
        node_m = np.zeros(len(she_m) + 1)
        for i in range(len(she_m)):
            node_m[i] += she_m[i] / 2
            node_m[i + 1] += she_m[i] / 2
        for el in rotor.disk_elements:
            node_m[el.n] += el.m
        gravity = Gravity(g, node_m)
        self.forces.append(gravity)
        gravity.node_link = she_n
        self._invalidate_topology()

    def solve(self, **kwargs):
        """
        :param kwargs:
        Optional arguments:
            uxy: bool
                Save translational displacement output.
            uxyt: bool
                Save translational velocity output.
            save_all: bool
                Save all intermediate state data.
            init: bool
                Reinitialize rotor-bearing states before solving.
        """
        if kwargs.get("init", True):
            self.init(**kwargs)

        positon = kwargs.get("position", 0)

        time_values = [float(value) for value in self._time_iter()]
        initial_time = time_values[0]
        dt_decimal = Decimal(str(self._time_iter.dt))
        initial_decimal = Decimal(str(initial_time))
        target_times = [
            float(initial_decimal + dt_decimal * index)
            for index in range(1, len(time_values))
        ]
        progress_bar = tqdm(
            enumerate(target_times, start=1),
            total=len(target_times),
            position=positon,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]",
        )
        for nt, ts in progress_bar:
            context = StepContext(
                nt,
                ts,
                self._time_iter.dt,
                UnitSystem.DIMENSIONAL,
            )
            self.advance(context, **kwargs)

    def input(self, *args, **kwargs):
        """
        Input interface reserved for compatibility with BaseCSystem.
        """
        pass

    def advance(self, context: StepContext, **kwargs) -> ResultBundle:
        """Advance one coupled physical step and commit it exactly once."""

        self._require_valid("advancing")
        if self._pending_record is not None:
            raise RuntimeError(
                "result recording is pending; call retry_pending_record()"
            )
        if not isinstance(context, StepContext):
            raise TypeError("context must be StepContext")
        if context.unit_system.value != "dimensional":
            raise ValueError("rotor-bearing coupling requires dimensional units")
        self._runtime.latch(context)
        try:
            with self._runtime.evaluation():
                ts = context.time
                self._ts = ts
                uxy_n1 = self._rp["uxy"]
                uxyt_n1 = self._rp["uxyt"]
                self._forceu1 = vertical_stack_nonempty(
                    [force(ts) for force in self.forces]
                )
                self._forcef1 = []
                adapter_metadata = []
                for num, bearing in enumerate(self.bearings):
                    force, metadata = self._evaluate_bearing(
                            bearing,
                            uxy_n1[num],
                            uxyt_n1[num],
                            context,
                            self.bindings[num] if self.bindings else None,
                        )
                    self._forcef1.append(force)
                    if metadata is not None:
                        adapter_metadata.append(metadata)
                self._forcef1 = np.array(self._forcef1)
                self._adapter_metadata = tuple(adapter_metadata)

                self._forcen0 = vertical_stack_nonempty((self._forceu0, self._forcef0))
                self._forcen1 = vertical_stack_nonempty((self._forceu1, self._forcef1))
                rotor_load = RotorLoadInput(
                    force=self._forcen1,
                    previous_force=self._forcen0,
                    node_links=tuple(
                        int(value) for value in np.asarray(self._fnode_links)
                    ),
                    time=ts,
                    unit_system=UnitSystem.DIMENSIONAL,
                )
                input_load = getattr(self.rotor, "input_load", None)
                if callable(input_load):
                    input_load(rotor_load)
                else:
                    self.rotor.input_force2node(
                        ts,
                        rotor_load.force,
                        rotor_load.node_links,
                        force0=rotor_load.previous_force,
                    )
                self.rotor.advance()
                self._rp = self.rotor.output(self._bnode_links)
                self._forcen0 = self._forcen1
                self._forceu0 = self._forceu1
                self._forcef0 = self._forcef1

                if not self.bindings:
                    self.signal.lead_loop("finish_signal")
                candidate = coupling_snapshot(
                    self._rp,
                    self._forcef1,
                    self._forcen1,
                    context,
                    unit_adapters=self._adapter_metadata,
                )
                if self._dependencies.recorder is not None:
                    validate_recordable_bundle(candidate)
                self._runtime.commit(context)
                self._last_output = candidate
                self._nt += 1
            self._after_commit(context, candidate)
        except (PostCommitRecordingError, PostCommitObserverError):
            raise
        except BaseException as exc:
            self._seal_failure(context, "advance", exc)
            raise
        return self.output()

    def output(self) -> ResultBundle:
        """Read the most recent completed coupled result without advancing."""

        self._require_valid("reading output")
        self._runtime.lifecycle.require_output()
        assert self._last_output is not None
        return self._last_output

    def result_snapshot(self) -> ResultBundle:
        """Return the current immutable coupled result snapshot."""

        return self.output()

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        self._require_valid("saving results")
        if path is None:
            path = self._save_path
        if name is None:
            name = "RBC"
        return build_coupling_save_tree(
            self._result,
            self.rotor,
            self.bearings,
            path,
            name,
            tofile=tofile,
            writer=kwargs.get("writer"),
        )

    def finish_signal(self):
        uxy_n1 = self._rp["uxy"]
        uxyt_n1 = self._rp["uxyt"]
        for num, bearing in enumerate(self.bearings):
            res = self._result["bearing" + str(num)]
            res.loc[len(res)] = np.hstack(
                (
                    self._ts,
                    uxy_n1[num],
                    uxyt_n1[num],
                    self._forcef1[num][0],
                    self._forcef1[num][1],
                )
            )


def get_all_attribute_values(objects, attribute_name):
    """
    Collect an attribute from each object and flatten list-type attributes.
    """
    values = []
    if not isinstance(objects, list):
        raise Exception("objects must be a list")
    for obj in objects:
        attribute_value = getattr(obj, attribute_name)
        if isinstance(attribute_value, list):
            values.extend(attribute_value)
        else:
            values.append(attribute_value)
    return values
