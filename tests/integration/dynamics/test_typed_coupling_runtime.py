"""Integration tests for typed coupling bindings and post-commit recovery."""

import importlib

import numpy as np
import pytest

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    DirectSpoolBearingInput,
    ResultBundle,
    RunCloseStatus,
    StepContext,
    StepRecordingStatus,
    UnitSystem,
    ValveOutput,
)
from ALB.core import LifecycleState, RuntimeLifecycle, Signal, TimeIterDt
from ALB.dynamics import CoupledBearingBinding, CouplingRuntimeDependencies
from ALB.dynamics.coupling import RsRotorBearingCouple
from ALB.dynamics.coupling_runtime import (
    PostCommitObserverError,
    PostCommitRecordingError,
)
from ALB.infrastructure import InMemoryResultRecorder
from ALB.physics.bearing import BearingScaleSet, BearingUnitAdapter


class _NativeBearing:
    node_link = 0
    unit_system = UnitSystem.DIMENSIONAL
    input_dto_type = BearingInput

    def __init__(self) -> None:
        self._lifecycle = RuntimeLifecycle("test bearing")
        self._input = None
        self._output = None
        self.output_time_offset = 0.0
        self.output_unit = None
        self.fail_evaluate = False
        self.init_calls = 0
        self.evaluate_calls = 0

    @property
    def lifecycle_state(self):
        return self._lifecycle.state

    @property
    def convergence_status(self):
        return ConvergenceStatus(0.0, True)

    def init(self) -> None:
        self.init_calls += 1
        self._lifecycle.reset()
        self._input = None
        self._output = None

    def input(self, dto) -> None:
        self._lifecycle.require_input_slot()
        self._input = dto
        self._lifecycle.latch()

    def evaluate(self) -> None:
        with self._lifecycle.evaluation():
            self.evaluate_calls += 1
            if self.fail_evaluate:
                raise RuntimeError("injected bearing failure")
            dto = self._input
            self._output = BearingOutput(
                [1.0, -2.0],
                dto.time + self.output_time_offset,
                self.unit_system if self.output_unit is None else self.output_unit,
            )

    def output(self):
        self._lifecycle.require_output()
        return self._output

    def step(self, dto):
        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self):
        return ResultBundle({"force": self.output().force}, {})

    def failure_snapshot(self):
        raise RuntimeError("no failure")

    def diagnostic_snapshot(self):
        return self.result_snapshot()


class _DirectBearing(_NativeBearing):
    input_dto_type = DirectSpoolBearingInput

    def evaluate(self) -> None:
        with self._lifecycle.evaluation():
            dto = self._input
            self._output = BearingOutput(
                dto.spool.spool, dto.bearing.time, self.unit_system
            )


class _SpoolProvider:
    def __init__(self) -> None:
        self.fail_evaluate = False

    def input(self, context, bearing_input) -> None:
        self.context = context
        self.bearing_input = bearing_input

    def evaluate(self) -> None:
        if self.fail_evaluate:
            raise RuntimeError("injected spool provider failure")
        self.value = ValveOutput(
            [0.25, -0.5],
            self.context.time,
            UnitSystem.NONDIMENSIONAL,
        )

    def output(self):
        return self.value


class _Rotor:
    def __init__(self) -> None:
        self.signal = Signal(sys=self)
        self.state = np.zeros((1, 2))
        self.advance_calls = 0
        self.init_calls = 0
        self.fail_advance = False

    def init(self) -> None:
        self.init_calls += 1
        self.state[:] = 0.0
        self.advance_calls = 0

    def input_force2node(self, time, force, node_links, force0=None) -> None:
        del time, force, node_links, force0

    def advance(self) -> None:
        if self.fail_advance:
            raise RuntimeError("injected rotor failure")
        self.advance_calls += 1
        self.state += 1.0

    def output(self, node_links):
        count = len(np.asarray(node_links).reshape(-1))
        return {
            "uxy": np.repeat(self.state, count, axis=0),
            "uxyt": np.zeros((count, 2)),
        }


class _FailSecondRecord:
    def __init__(self) -> None:
        self.inner = InMemoryResultRecorder()
        self.failed = False

    def begin_run(self, run_id):
        return self.inner.begin_run(run_id)

    def record(self, context, bundle):
        if context.step_index == 1 and not self.failed:
            self.failed = True
            raise OSError("injected recorder failure")
        return self.inner.record(context, bundle)

    def end_run(self, run_id, *, allow_incomplete=False):
        return self.inner.end_run(run_id, allow_incomplete=allow_incomplete)


class _FailingObserver:
    def on_step_completed(self, event) -> None:
        raise RuntimeError("monitor unavailable")

    def on_recording_recovered(self, event) -> None:
        return None


class _FailInitialRecord:
    def __init__(self) -> None:
        self.inner = InMemoryResultRecorder()
        self.failed = False

    def begin_run(self, run_id):
        return self.inner.begin_run(run_id)

    def record(self, context, bundle):
        if context.step_index == 0 and not self.failed:
            self.failed = True
            raise OSError("injected initial recorder failure")
        return self.inner.record(context, bundle)

    def end_run(self, run_id, *, allow_incomplete=False):
        return self.inner.end_run(run_id, allow_incomplete=allow_incomplete)


class _FailInitialObserver:
    def __init__(self) -> None:
        self.failed = False

    def on_step_completed(self, event) -> None:
        if event.context.step_index == 0 and not self.failed:
            self.failed = True
            raise RuntimeError("injected initial observer failure")

    def on_recording_recovered(self, event) -> None:
        return None


def test_typed_binding_has_no_hidden_history_and_uses_native_dto() -> None:
    binding = CoupledBearingBinding(_NativeBearing(), node_link=0)
    coupling = RsRotorBearingCouple(_Rotor(), TimeIterDt(0.01, 1), binding)
    coupling.init()
    result = coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))
    np.testing.assert_array_equal(result.values["bearing_force"], [[1.0, -2.0]])
    assert coupling.results["bearing0"].empty


def test_record_failure_blocks_next_advance_and_retry_does_not_repeat_physics() -> None:
    recorder = _FailSecondRecord()
    rotor = _Rotor()
    coupling = RsRotorBearingCouple(
        rotor,
        TimeIterDt(0.01, 2),
        CoupledBearingBinding(_NativeBearing(), node_link=0),
        dependencies=CouplingRuntimeDependencies("run", recorder=recorder),
    )
    coupling.init()
    first = StepContext(1, 0.01, 0.01, "dimensional")
    coupling.advance(first)
    assert rotor.advance_calls == 1
    assert (
        coupling.diagnostic_snapshot().metadata["recording_status"]
        == StepRecordingStatus.PENDING.value
    )
    with pytest.raises(RuntimeError, match="pending"):
        coupling.advance(StepContext(2, 0.02, 0.01, "dimensional"))
    coupling.retry_pending_record()
    assert rotor.advance_calls == 1
    coupling.advance(StepContext(2, 0.02, 0.01, "dimensional"))
    assert rotor.advance_calls == 2


def test_pending_record_prevents_complete_run_receipt() -> None:
    recorder = _FailSecondRecord()
    coupling = RsRotorBearingCouple(
        _Rotor(),
        TimeIterDt(0.01, 1),
        CoupledBearingBinding(_NativeBearing(), node_link=0),
        dependencies=CouplingRuntimeDependencies("run-close", recorder=recorder),
    )
    coupling.init()
    coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))

    with pytest.raises(RuntimeError, match="pending record"):
        coupling.end_run()
    receipt = coupling.end_run(allow_incomplete=True)
    assert receipt.close_status is RunCloseStatus.INCOMPLETE
    assert [(key.run_id, key.step_index) for key in receipt.pending_keys] == [
        ("run-close", 1)
    ]
    with pytest.raises(RuntimeError, match="closed"):
        coupling.retry_pending_record()


def test_observer_failure_is_post_commit_and_does_not_invalidate_runtime() -> None:
    coupling = RsRotorBearingCouple(
        _Rotor(),
        TimeIterDt(0.01, 1),
        CoupledBearingBinding(_NativeBearing(), node_link=0),
        dependencies=CouplingRuntimeDependencies(
            "run",
            observers=(_FailingObserver(),),
        ),
    )
    coupling.init()
    coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))
    diagnostic = coupling.diagnostic_snapshot()
    assert diagnostic.metadata["physical_step_committed"] is True
    assert len(diagnostic.values["observer_failures"]) == 2


def test_direct_spool_binding_requires_and_uses_explicit_provider() -> None:
    with pytest.raises(ValueError, match="spool_provider"):
        CoupledBearingBinding(_DirectBearing(), node_link=0)
    coupling = RsRotorBearingCouple(
        _Rotor(),
        TimeIterDt(0.01, 1),
        CoupledBearingBinding(
            _DirectBearing(),
            node_link=0,
            spool_provider=_SpoolProvider(),
        ),
    )
    coupling.init()
    result = coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))
    np.testing.assert_array_equal(result.values["bearing_force"], [[0.25, -0.5]])


def test_nondimensional_binding_converts_force_back_to_rotor_domain() -> None:
    bearing = _NativeBearing()
    bearing.unit_system = UnitSystem.NONDIMENSIONAL
    scales = BearingScaleSet(
        UnitSystem.DIMENSIONAL,
        UnitSystem.NONDIMENSIONAL,
        Sx=2.0,
        St=4.0,
        Sv=0.5,
        Sf=10.0,
        Sp=100.0,
        scale_id="test",
        pressure_scale_source="test",
        velocity_definition_id="Sx/St",
        residual_definition_id="local",
        provenance="test",
    )
    coupling = RsRotorBearingCouple(
        _Rotor(),
        TimeIterDt(0.01, 1),
        CoupledBearingBinding(
            bearing,
            node_link=0,
            unit_adapter=BearingUnitAdapter(scales),
        ),
    )
    coupling.init()
    result = coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))
    np.testing.assert_array_equal(result.values["bearing_force"], [[10.0, -20.0]])
    descriptor = result.metadata["unit_adapters"][0]
    assert descriptor["scale_definition"] == "dimensional_per_nondimensional"
    assert descriptor["applied_transform"] == "bearing_to_rotor"


def test_add_bearing_creates_binding_and_requires_reinitialization() -> None:
    first = _NativeBearing()
    second = _NativeBearing()
    coupling = RsRotorBearingCouple(
        _Rotor(),
        TimeIterDt(0.01, 1),
        CoupledBearingBinding(first, node_link=0),
    )
    coupling.init()

    binding = coupling.add_bearing(second, node_link=0)
    assert binding is coupling.bindings[-1]
    assert coupling.bearings == (first, second)
    assert coupling.lifecycle_state is LifecycleState.FAILED
    with pytest.raises(RuntimeError, match="invalid"):
        coupling.output()

    coupling.init()
    result = coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))
    np.testing.assert_array_equal(
        result.values["bearing_force"],
        [[1.0, -2.0], [1.0, -2.0]],
    )


def test_simple_add_bearing_rejects_advanced_topologies_immediately() -> None:
    coupling = RsRotorBearingCouple(_Rotor(), TimeIterDt(0.01, 1))
    with pytest.raises(TypeError, match="node_link"):
        coupling.add_bearing(_NativeBearing())
    with pytest.raises(TypeError, match="integer"):
        coupling.add_bearing(_NativeBearing(), node_link=None)

    nondimensional = _NativeBearing()
    nondimensional.unit_system = UnitSystem.NONDIMENSIONAL
    with pytest.raises(TypeError, match="unit_system='dimensional'"):
        coupling.add_bearing(nondimensional, node_link=0)
    with pytest.raises(TypeError, match="ordinary BearingInput"):
        coupling.add_bearing(_DirectBearing(), node_link=0)
    with pytest.raises(TypeError, match="CoupledBearingBinding"):
        RsRotorBearingCouple(
            _Rotor(),
            TimeIterDt(0.01, 1),
            _NativeBearing(),
        )


def test_initial_record_failure_keeps_committed_runtime_ready() -> None:
    recorder = _FailInitialRecord()
    rotor = _Rotor()
    bearing = _NativeBearing()
    coupling = RsRotorBearingCouple(
        rotor,
        TimeIterDt(0.01, 2),
        CoupledBearingBinding(bearing, node_link=0),
        dependencies=CouplingRuntimeDependencies(
            "initial-record",
            recorder=recorder,
            record_failure_policy="raise",
        ),
    )

    with pytest.raises(PostCommitRecordingError):
        coupling.init()
    assert coupling.lifecycle_state is LifecycleState.READY
    assert rotor.init_calls == 1
    assert bearing.init_calls == 1
    assert bearing.evaluate_calls == 1

    coupling.retry_pending_record()
    coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))
    assert rotor.init_calls == 1
    assert bearing.init_calls == 1
    assert bearing.evaluate_calls == 2


def test_initial_strict_observer_failure_keeps_committed_runtime_ready() -> None:
    rotor = _Rotor()
    bearing = _NativeBearing()
    coupling = RsRotorBearingCouple(
        rotor,
        TimeIterDt(0.01, 2),
        CoupledBearingBinding(bearing, node_link=0),
        dependencies=CouplingRuntimeDependencies(
            "initial-observer",
            observers=(_FailInitialObserver(),),
            observer_failure_policy="raise",
        ),
    )

    with pytest.raises(PostCommitObserverError):
        coupling.init()
    assert coupling.lifecycle_state is LifecycleState.READY
    coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))
    assert rotor.init_calls == 1
    assert bearing.init_calls == 1
    assert bearing.evaluate_calls == 2


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("output_time_offset", 0.001, "output time"),
        ("output_unit", UnitSystem.NONDIMENSIONAL, "unit_system"),
    ],
)
def test_coupling_rejects_stale_or_wrong_unit_bearing_output(
    field,
    value,
    message,
) -> None:
    bearing = _NativeBearing()
    coupling = RsRotorBearingCouple(
        _Rotor(),
        TimeIterDt(0.01, 1),
        CoupledBearingBinding(bearing, node_link=0),
    )
    coupling.init()
    setattr(bearing, field, value)

    with pytest.raises(ValueError, match=message):
        coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))
    assert coupling.failure_snapshot().metadata["physical_step_committed"] is False
    with pytest.raises(RuntimeError, match="invalid"):
        coupling.output()


def test_typed_coupling_save_does_not_require_component_save_methods() -> None:
    coupling = RsRotorBearingCouple(
        _Rotor(),
        TimeIterDt(0.01, 1),
        CoupledBearingBinding(_NativeBearing(), node_link=0),
    )
    coupling.init()

    tree = coupling.save(tofile=False, path="typed", name="case")

    assert tree.get_dir() == {"typed": {"_NativeBearing0": None}}


def test_binding_and_runtime_dependencies_reject_missing_capabilities_early() -> None:
    with pytest.raises(TypeError, match="spool_provider"):
        CoupledBearingBinding(
            _DirectBearing(),
            node_link=0,
            spool_provider=object(),
        )
    with pytest.raises(TypeError, match="recorder"):
        CouplingRuntimeDependencies("run", recorder=object())
    with pytest.raises(TypeError, match="observers"):
        CouplingRuntimeDependencies("run", observers=(object(),))
    with pytest.raises(ValueError, match="record_failure_policy"):
        CouplingRuntimeDependencies("run", record_failure_policy="invalid")
    with pytest.raises(ValueError, match="observer_failure_policy"):
        CouplingRuntimeDependencies("run", observer_failure_policy="invalid")


@pytest.mark.parametrize(
    "failure_point",
    ["bearing", "rotor", "spool-provider", "candidate-result"],
)
def test_precommit_failure_points_seal_without_committing_or_retrying(
    failure_point,
    monkeypatch,
) -> None:
    rotor = _Rotor()
    provider = _SpoolProvider()
    bearing = _DirectBearing() if failure_point == "spool-provider" else _NativeBearing()
    binding = CoupledBearingBinding(
        bearing,
        node_link=0,
        spool_provider=provider if failure_point == "spool-provider" else None,
    )
    coupling = RsRotorBearingCouple(
        rotor,
        TimeIterDt(0.01, 1),
        binding,
    )
    coupling.init()
    if failure_point == "bearing":
        bearing.fail_evaluate = True
    elif failure_point == "rotor":
        rotor.fail_advance = True
    elif failure_point == "spool-provider":
        provider.fail_evaluate = True
    else:
        module = importlib.import_module("ALB.dynamics.coupling")

        def fail_candidate(*args, **kwargs):
            del args, kwargs
            raise RuntimeError("injected candidate construction failure")

        monkeypatch.setattr(module, "coupling_snapshot", fail_candidate)

    context = StepContext(1, 0.01, 0.01, "dimensional")
    with pytest.raises(RuntimeError, match="injected"):
        coupling.advance(context)

    assert coupling._step_ledger.last_context.step_index == 0
    assert coupling.failure_snapshot().metadata["physical_step_committed"] is False
    with pytest.raises(RuntimeError, match="invalid"):
        coupling.advance(context)
