# coding: utf-8

from typing import Any
from uuid import uuid4

import numpy as np
from ALB.core.lifecycle import LifecycleState
from ALB.core.diagnostics import sanitize_exception_message
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    BearingRuntimeProtocol,
    DirectSpoolBearingInput,
    PendingRecord,
    PendingAwareResultRecorderProtocol,
    RecordingRecovered,
    RecordReceipt,
    ResultBundle,
    RunCloseStatus,
    RunReceipt,
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
from .rotor import RossRotor, UnbalancedExcitation
from .coupling_runtime import (
    CouplingStepRuntime,
    PostCommitObserverError,
    PostCommitRecordingError,
    coupling_snapshot,
)
from .bindings import CoupledBearingBinding, CouplingRuntimeDependencies
from ALB.core.numerics.arrays import vertical_stack_nonempty
from ALB.core.observers import ObserverDispatcher


class _RotorBearingStepRuntime:
    """Internal exactly-once rotor-bearing step runtime.

    The public owner is :class:`ALB.RotorBearingSimulation`. Topology is fixed
    at construction and reset is intentionally an owner-only hook.
    """

    def __init__(self, rotor: RossRotor, time_iter, *bindings, **kwargs):
        """
        options:
            save_path:default="./rotor_bearing_couple"
        """
        self.rotor = rotor
        if any(
            not isinstance(binding, CoupledBearingBinding)
            for binding in bindings
        ):
            raise TypeError(
                "simulation topology accepts only CoupledBearingBinding objects"
            )
        self.bindings = tuple(bindings)
        self.forces = []
        self._time_iter = time_iter
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
        self._dependencies = kwargs.get("dependencies") or CouplingRuntimeDependencies(
            run_id=f"coupling-{uuid4().hex}"
        )
        self._run_id = self._dependencies.run_id
        self._run_started = False
        self._run_closed = False
        self._run_receipt: RunReceipt | None = None
        self._pending_record: PendingRecord | None = None
        self._record_receipt: RecordReceipt | None = None
        self._recording_status = StepRecordingStatus.NOT_CONFIGURED
        self._observer_dispatcher = ObserverDispatcher(
            self._dependencies.observers
        )
        self._failure_result: ResultBundle | None = None
        self._adapter_metadata: tuple[dict[str, object], ...] = ()
        self._pending_accounting_error: str | None = None

    @property
    def bearings(self) -> tuple[BearingRuntimeProtocol[object], ...]:
        """Return the bearing runtimes derived from canonical bindings."""

        return tuple(binding.bearing for binding in self.bindings)

    def _require_valid(self, operation: str) -> None:
        """Reject access to state that may contain a partially applied step."""

        if not self._runtime.is_valid:
            raise RuntimeError(
                f"simulation runtime is invalid; reset the simulation before {operation}"
            )

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the shared coupled-runtime state."""

        return self._runtime.state

    def _invalidate_runtime(self) -> None:
        """Block access after a partial step or a topology change."""

        self._runtime.fail()
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
                "message": sanitize_exception_message(error),
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
                ),
                "pending_accounting_error": self._pending_accounting_error,
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
                "run_close_status": (
                    None
                    if (
                        self._run_receipt is None
                        or self._run_receipt.close_status is None
                    )
                    else self._run_receipt.close_status.value
                ),
            },
        )

    def _begin_recorder_if_needed(self) -> None:
        if self._run_closed:
            raise RuntimeError(
                "coupling run is closed; create a new runtime with a new run_id"
            )
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
                self._pending_accounting_error = None
            except Exception as exc:
                pending_error = exc
                self._recording_status = StepRecordingStatus.PENDING
                self._record_receipt = None
                self._pending_record = PendingRecord(
                    self._run_id,
                    context,
                    bundle,
                    (
                        f"{type(exc).__name__}: "
                        f"{sanitize_exception_message(exc)}"
                    ),
                )
                if isinstance(
                    recorder,
                    PendingAwareResultRecorderProtocol,
                ):
                    try:
                        recorder.register_pending(self._pending_record.key)
                    except Exception as accounting_error:
                        self._pending_accounting_error = (
                            sanitize_exception_message(accounting_error)
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
        if self._run_closed:
            raise RuntimeError("closed recorder runs cannot recover pending records")
        recorder = self._dependencies.recorder
        if recorder is None:
            raise RuntimeError("no recorder is configured")
        pending = self._pending_record
        receipt = recorder.record(pending.context, pending.bundle)
        if isinstance(recorder, PendingAwareResultRecorderProtocol):
            recorder.resolve_pending(pending.key)
        self._pending_record = None
        self._pending_accounting_error = None
        self._record_receipt = receipt
        self._recording_status = StepRecordingStatus.RECORDED
        self._observer_dispatcher.recording_recovered(
            RecordingRecovered(self._run_id, pending.key, receipt)
        )
        return receipt

    def end_run(self, *, allow_incomplete: bool = False) -> RunReceipt:
        """Close recorder state without mislabeling unresolved gaps."""

        if self._run_closed:
            raise RuntimeError("coupling run is already closed")
        recorder = self._dependencies.recorder
        if recorder is None:
            receipt = RunReceipt(
                self._run_id,
                RunCloseStatus.COMPLETE,
                0,
                (),
                None,
                None,
            )
        else:
            if not self._run_started:
                raise RuntimeError("coupling recorder run has not started")
            pending = self._pending_record
            if pending is not None and not allow_incomplete:
                raise RuntimeError(
                    "coupling run has a pending record; recover it or use "
                    "allow_incomplete=True"
                )
            receipt = recorder.end_run(
                self._run_id,
                allow_incomplete=allow_incomplete,
            )
            if pending is not None and pending.key not in receipt.pending_keys:
                pending_keys = tuple(
                    sorted(
                        {*receipt.pending_keys, pending.key},
                        key=lambda key: key.step_index,
                    )
                )
                receipt = RunReceipt(
                    receipt.run_id,
                    RunCloseStatus.INCOMPLETE,
                    receipt.record_count,
                    pending_keys,
                    receipt.first_step_index,
                    receipt.last_step_index,
                )
            self._run_started = False
        self._run_closed = True
        self._run_receipt = receipt
        return receipt

    def _invalidate_topology(self) -> None:
        """Require an owner reset after the force graph changes."""

        self._invalidate_runtime()
        self._fnode_links = None
        self._bnode_links = None

    @staticmethod
    def _evaluate_bearing(
        binding: CoupledBearingBinding,
        displacement,
        velocity,
        context: StepContext,
    ) -> tuple[np.ndarray, dict[str, object] | None]:
        """Evaluate one formally bound bearing runtime."""

        bearing = binding.bearing
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
            adapter = binding.unit_adapter
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
            bearing_unit = UnitSystem.coerce(bearing.unit_system)
            if local_context.unit_system is not bearing_unit:
                raise ValueError(
                    "bearing-local context unit_system must match the runtime"
                )
            if local_input.unit_system is not bearing_unit:
                raise ValueError(
                    "bearing-local input unit_system must match the runtime"
                )
            dto: BearingInput | DirectSpoolBearingInput
            if bearing.input_dto_type is DirectSpoolBearingInput:
                provider = binding.spool_provider
                assert provider is not None
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
            dto_bearing = (
                dto.bearing
                if isinstance(dto, DirectSpoolBearingInput)
                else dto
            )
            if dto_bearing.time != local_context.time:
                raise ValueError(
                    "bearing input time must match the local step context"
                )
            if dto_bearing.unit_system is not bearing_unit:
                raise ValueError(
                    "bearing input unit_system must match the runtime"
                )
            bearing.input(dto)
            bearing.evaluate()
            output = bearing.output()
            if not isinstance(output, BearingOutput):
                raise TypeError("native bearing output must be BearingOutput")
            if output.time != local_context.time:
                raise ValueError(
                    "bearing output time must match the local step context"
                )
            if output.unit_system is not bearing_unit:
                raise ValueError(
                    "bearing output unit_system must match the bearing runtime"
                )
            rotor_output = (
                adapter.bearing_output_to_rotor(output)
                if adapter is not None
                else output
            )
            if rotor_output.time != context.time:
                raise ValueError(
                    "rotor-domain bearing output time must match global context"
                )
            if rotor_output.unit_system is not UnitSystem.DIMENSIONAL:
                raise ValueError(
                    "rotor-domain bearing output must be dimensional"
                )
            metadata = None
            if adapter is not None:
                metadata = adapter.scales.descriptor(
                    applied_transform="bearing_to_rotor",
                    global_context=context,
                    bearing_local_context=local_context,
                )
            return rotor_output.force.copy(), metadata
        raise TypeError("binding bearing must satisfy BearingRuntimeProtocol")

    def _reset_for_owner(self) -> None:
        self._invalidate_runtime()
        try:
            self._begin_recorder_if_needed()
            time_values = [float(value) for value in self._time_iter()]
            if not time_values:
                raise ValueError("rotor-bearing coupling time grid cannot be empty")
            if not self.bindings:
                raise ValueError("rotor-bearing coupling requires at least one binding")
            initial_time = time_values[0]
            self.rotor._reset_for_owner()
            for binding in self.bindings:
                reset = getattr(binding.bearing, "_reset_for_owner", None)
                if not callable(reset):
                    raise TypeError(
                        "binding bearing must provide _reset_for_owner()"
                    )
                reset()
            self._fnode_links = get_all_attribute_values(self.forces, "node_link")
            self._bnode_links = [
                binding.node_link for binding in self.bindings
            ]
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
            self._forcef0 = []
            adapter_metadata = []
            for num, binding in enumerate(self.bindings):
                rp_uxy = self._rp["uxy"][num]
                rp_uxyt = self._rp["uxyt"][num]
                force, metadata = self._evaluate_bearing(
                    binding,
                    rp_uxy,
                    rp_uxyt,
                    StepContext(
                        0,
                        initial_time,
                        self._time_iter.dt,
                        UnitSystem.DIMENSIONAL,
                    ),
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
            self._seal_failure(None, "reset", exc)
            raise

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

    def advance(self, context: StepContext, **kwargs) -> ResultBundle:
        """Advance one coupled physical step and commit it exactly once."""

        self._require_valid("advancing")
        if self._run_closed:
            raise RuntimeError("coupling run is closed")
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
                for num, binding in enumerate(self.bindings):
                    force, metadata = self._evaluate_bearing(
                        binding,
                        uxy_n1[num],
                        uxyt_n1[num],
                        context,
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
