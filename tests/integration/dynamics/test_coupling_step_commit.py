"""Coupler-level regression for exactly-once physical step commits."""

import numpy as np
import pytest

from ALB import StepContext
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    UnitSystem,
    result_snapshot,
)
from ALB.core import LifecycleState, RuntimeLifecycle, TimeIterDt
from ALB.dynamics.coupling import RsRotorBearingCouple


class _Bearing:
    node_link = 0
    unit_system = UnitSystem.DIMENSIONAL
    input_dto_type = BearingInput

    def __init__(self):
        self._lifecycle = RuntimeLifecycle("test bearing")
        self._input = None
        self._output = None
        self.init()

    @property
    def lifecycle_state(self):
        return self._lifecycle.state

    @property
    def convergence_status(self):
        return ConvergenceStatus(0.0, True)

    def init(self):
        self._input = None
        self._output = None
        self._lifecycle.reset()

    def input(self, dto):
        self._lifecycle.require_input_slot()
        self._input = dto
        self._lifecycle.latch()

    def evaluate(self):
        with self._lifecycle.evaluation():
            self._output = BearingOutput(
                [0.0, 0.0],
                self._input.time,
                self.unit_system,
            )

    def output(self):
        self._lifecycle.require_output()
        return self._output

    def step(self, dto):
        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self):
        return result_snapshot({"force": self.output().force}, {})

    def failure_snapshot(self):
        raise RuntimeError("no failure")

    def diagnostic_snapshot(self):
        return result_snapshot({}, {"state": self.lifecycle_state.value})

    def save(self, *args, **kwargs):
        del args, kwargs
        raise AssertionError("save is outside this test")


class _Rotor:
    def __init__(self):
        self.input_calls = 0
        self.state = np.zeros((1, 2))
        self.fail_after_advance = False

    def init(self):
        self.input_calls = 0
        self.state = np.zeros((1, 2))

    def input_force2node(self, time, force, node_links, force0=None):
        del time, force, node_links, force0
        self.input_calls += 1

    def advance(self):
        self.state = self.state + 1.0
        if self.fail_after_advance:
            raise RuntimeError("injected rotor failure")

    def output(self, node_links):
        count = len(np.asarray(node_links).reshape(-1))
        return {
            "uxy": np.repeat(self.state, count, axis=0),
            "uxyt": np.zeros((count, 2)),
        }

def _coupling(rotor, bearing):
    coupling = RsRotorBearingCouple(rotor, TimeIterDt(0.01, 1))
    coupling.add_bearing(bearing, node_link=0)
    return coupling


def test_duplicate_context_is_rejected_before_second_mutation():
    rotor = _Rotor()
    coupling = _coupling(rotor, _Bearing())
    coupling.init()
    assert coupling.lifecycle_state is LifecycleState.READY
    initial = coupling.output()
    assert initial.metadata["step_index"] == 0
    assert initial.metadata["time"] == 0.0
    assert initial.metadata["initial_snapshot"] is True

    context = StepContext(1, 0.01, 0.01, "dimensional")
    first = coupling.advance(context)
    assert coupling.lifecycle_state is LifecycleState.READY
    assert first.metadata["step_index"] == 1
    assert rotor.input_calls == 1

    with pytest.raises(RuntimeError, match="already"):
        coupling.advance(context)
    assert rotor.input_calls == 1


def test_add_unbalance_forwards_soft_start_selection():
    rotor = _Rotor()
    coupling = _coupling(rotor, _Bearing())

    coupling.add_unbalance(
        node_link=0,
        phase=0.0,
        t_max=1.0,
        m=1.0,
        freq=1.0,
        e=1.0,
        no_step=True,
    )

    excitation = coupling.forces[-1]
    assert excitation._no_step_set is True
    np.testing.assert_array_equal(excitation(0.0), [0.0, 0.0])


def test_mid_step_failure_invalidates_coupler_until_explicit_reinitialization():
    bearing = _Bearing()
    rotor = _Rotor()
    coupling = _coupling(rotor, bearing)
    coupling.init()
    context = StepContext(1, 0.01, 0.01, "dimensional")
    rotor.fail_after_advance = True

    with pytest.raises(RuntimeError, match="injected rotor failure"):
        coupling.advance(context)
    assert coupling.lifecycle_state is LifecycleState.FAILED
    assert rotor.input_calls == 1

    with pytest.raises(RuntimeError, match="invalid"):
        coupling.advance(context)
    with pytest.raises(RuntimeError, match="invalid"):
        coupling.output()
    with pytest.raises(RuntimeError, match="invalid"):
        _ = coupling.results
    with pytest.raises(RuntimeError, match="invalid"):
        coupling.save(tofile=False)
    assert rotor.input_calls == 1

    rotor.fail_after_advance = False
    coupling.init()
    result = coupling.advance(context)

    assert rotor.input_calls == 1
    assert result.metadata["step_index"] == 1


@pytest.mark.parametrize(
    "mutate_topology",
    [
        lambda coupling: coupling.add_bearing(_Bearing(), node_link=0),
        lambda coupling: coupling.add_static_force([1.0, -2.0], node_link=0),
        lambda coupling: coupling.add_unbalance(
            node_link=0,
            phase=0.0,
            t_max=1.0,
            m=0.1,
            freq=2.0,
            e=0.01,
            no_step=True,
        ),
    ],
    ids=["bearing", "static-force", "unbalance"],
)
def test_topology_change_requires_reinitialization(mutate_topology):
    coupling = _coupling(_Rotor(), _Bearing())
    coupling.init()
    assert coupling.output().metadata["initial_snapshot"] is True

    mutate_topology(coupling)

    with pytest.raises(RuntimeError, match="invalid"):
        coupling.output()
    with pytest.raises(RuntimeError, match="invalid"):
        _ = coupling.results
    with pytest.raises(RuntimeError, match="invalid"):
        coupling.save(tofile=False)
    with pytest.raises(RuntimeError, match="invalid"):
        coupling.advance(StepContext(1, 0.01, 0.01, "dimensional"))

    coupling.init()
    restored = coupling.output()

    assert restored.metadata["initial_snapshot"] is True
    assert coupling._fnode_links is not None
