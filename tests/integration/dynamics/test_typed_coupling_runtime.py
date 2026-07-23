"""Integration tests for typed coupling bindings and post-commit recovery."""

import numpy as np
import pytest

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    DirectSpoolBearingInput,
    ResultBundle,
    StepContext,
    StepRecordingStatus,
    UnitSystem,
    ValveOutput,
)
from ALB.core import RuntimeLifecycle, Signal, TimeIterDt
from ALB.dynamics import CoupledBearingBinding, CouplingRuntimeDependencies
from ALB.dynamics.coupling import RsRotorBearingCouple
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

    @property
    def lifecycle_state(self):
        return self._lifecycle.state

    @property
    def convergence_status(self):
        return ConvergenceStatus(0.0, True)

    def init(self) -> None:
        self._lifecycle.reset()
        self._input = None
        self._output = None

    def input(self, dto) -> None:
        self._lifecycle.require_input_slot()
        self._input = dto
        self._lifecycle.latch()

    def evaluate(self) -> None:
        with self._lifecycle.evaluation():
            dto = self._input
            self._output = BearingOutput(
                [1.0, -2.0], dto.time, self.unit_system
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
    def input(self, context, bearing_input) -> None:
        self.context = context
        self.bearing_input = bearing_input

    def evaluate(self) -> None:
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

    def init(self) -> None:
        self.state[:] = 0.0
        self.advance_calls = 0

    def input_force2node(self, time, force, node_links, force0=None) -> None:
        del time, force, node_links, force0

    def advance(self) -> None:
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
    DirectSpoolBearingInput,
