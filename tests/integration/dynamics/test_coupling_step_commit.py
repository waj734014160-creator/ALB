"""Coupler-level regression for exactly-once physical step commits."""

import numpy as np
import pytest

from ALB import StepContext
from ALB.core import Signal, TimeIterDt
from ALB.dynamics.coupling import RsRotorBearingCouple


class _Bearing:
    node_link = 0
    unit_system = "dimensional"

    def __init__(self):
        self.signal = Signal(sys=self)

    def init(self):
        return None

    def input(self, uxy, uxyt, t):
        del uxy, uxyt, t

    def output(self):
        return {"force": np.array([0.0, 0.0])}

    def finish_signal(self):
        return None

    def save(self, *args, **kwargs):
        del args, kwargs
        raise AssertionError("save is outside this test")


class _Rotor:
    def __init__(self):
        self.signal = Signal(sys=self)
        self.input_calls = 0
        self.state = np.zeros((1, 2))

    def init(self):
        self.input_calls = 0
        self.state = np.zeros((1, 2))

    def input_force2node(self, time, force, node_links, force0=None):
        del time, force, node_links, force0
        self.input_calls += 1

    def advance(self):
        self.state = self.state + 1.0

    def output(self, node_links):
        count = len(np.asarray(node_links).reshape(-1))
        return {
            "uxy": np.repeat(self.state, count, axis=0),
            "uxyt": np.zeros((count, 2)),
        }

    def finish_signal(self):
        return None


def test_duplicate_context_is_rejected_before_second_mutation():
    rotor = _Rotor()
    coupling = RsRotorBearingCouple(rotor, TimeIterDt(0.01, 1), _Bearing())
    coupling.init()
    with pytest.raises(RuntimeError, match="unavailable"):
        coupling.output()

    context = StepContext(0, 0.0, 0.01, "dimensional")
    first = coupling.advance(context)
    assert first.metadata["step_index"] == 0
    assert rotor.input_calls == 1

    with pytest.raises(RuntimeError, match="already"):
        coupling.advance(context)
    assert rotor.input_calls == 1
