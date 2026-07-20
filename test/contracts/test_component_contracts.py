"""Contract and compatibility tests for the reorganized ALB package."""

import importlib
from types import SimpleNamespace

import numpy as np
import pytest

from ALB.adapters import BearingDecoratorBase, LegacyBearingAdapter
from ALB.core import BaseSystem, Signal, TimeIterDt
from ALB.bearing import MultiPad
from ALB.config import CsoArgs as ConfigCsoArgs
from ALB.contracts import (
    BearingProtocol,
    ConvergenceStatus,
    NotifierProtocol,
    TimeGridProtocol,
)
from ALB.core import BearingComponentBase
from ALB.core.validation import require_unit_system, validate_bearing_output
from ALB.couple import RsRotorBearingCouple
from ALB.film import FilmSystem
from ALB.orifice import CsoArgs as OrificeCsoArgs
from ALB.results import DataFrameResult, SaveTreeNode


class _Bearing(BearingComponentBase):
    """Small deterministic bearing used to exercise structural contracts."""

    def __init__(self, node_link=1, unit_system="dimensional"):
        super().__init__()
        self.node_link = node_link
        self.unit_system = unit_system
        self.force = np.array([1.0, -2.0])

    def init(self):
        return True

    def input(self, uxy, uxyt, t, *args, **kwargs):
        self.uxy, self.uxyt = self.validate_state(uxy, uxyt)
        self.t = float(t)
        return True

    def output(self, *args, **kwargs):
        return {"force": self.force.copy(), "friction": 0.0}

    def calc_error(self, *args, **kwargs):
        return 0.0

    def calc_is_finished(self, *args, **kwargs):
        return True

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        return SaveTreeNode(path or "bearing", DataFrameResult({}))


class _Recorder:
    def __init__(self):
        self.messages = []

    def notify(self, message, subject=None):
        self.messages.append((subject, message))


def test_protocols_and_specialized_bearing_template_are_runtime_checkable():
    bearing = _Bearing()
    time_grid = TimeIterDt(0.01, 2)

    assert isinstance(bearing, BearingProtocol)
    assert isinstance(time_grid, TimeGridProtocol)
    np.testing.assert_array_equal(
        validate_bearing_output(bearing.output()), np.array([1.0, -2.0])
    )
    assert require_unit_system(bearing, "dimensional") == "dimensional"


def test_decorator_and_legacy_adapter_preserve_standard_bearing_contract():
    bearing = _Bearing(node_link=4)
    decorated = BearingDecoratorBase(bearing)
    adapted = LegacyBearingAdapter(bearing, node_link=7)

    assert isinstance(decorated, BearingProtocol)
    assert decorated.node_link == 4
    assert adapted.node_link == 7
    np.testing.assert_array_equal(decorated.output()["force"], bearing.force)


def test_signal_and_base_system_attach_each_child_once():
    events = []
    parent = SimpleNamespace(signal=Signal(), finish_signal=lambda: events.append("parent"))
    parent.signal.sys = parent
    child = SimpleNamespace(signal=Signal(), finish_signal=lambda: events.append("child"))
    child.signal.sys = child

    system = BaseSystem()
    system.finish_signal = lambda: events.append("system")
    system.add_simple_model([parent, child])
    system.add_simple_model(parent)
    system.signal.lead_loop("finish_signal")

    assert len(system.simple_models) == 2
    assert len(system.signal.children) == 2
    assert events == ["system", "parent", "child"]


def test_convergence_status_rejects_ambiguous_invalid_residuals():
    status = ConvergenceStatus(residual=0.0, converged=True, iterations=3)
    assert status.converged is True
    with pytest.raises(TypeError, match="not boolean"):
        ConvergenceStatus(residual=True, converged=True)
    with pytest.raises(TypeError, match="converged must be boolean"):
        ConvergenceStatus(residual=0.1, converged=1)
    with pytest.raises(ValueError, match="finite nonnegative"):
        ConvergenceStatus(residual=np.nan, converged=False)
    with pytest.raises(ValueError, match="nonnegative"):
        ConvergenceStatus(residual=0.1, converged=False, iterations=-1)


def test_cso_args_has_one_canonical_owner():
    assert OrificeCsoArgs is ConfigCsoArgs
    assert OrificeCsoArgs._fields == (
        "d",
        "l",
        "q_leak",
        "w",
        "cd",
        "cq1_nondim",
    )


def test_multipad_rejects_empty_and_mixed_unit_collections():
    with pytest.raises(ValueError, match="at least one"):
        MultiPad()
    with pytest.raises(ValueError, match="same unit_system"):
        MultiPad(_Bearing(unit_system="dimensional"), _Bearing(unit_system="nondimensional"))


def test_rotor_coupling_rejects_explicit_nondimensional_bearing():
    rotor = SimpleNamespace(signal=Signal())
    bearing = _Bearing(unit_system="nondimensional")
    with pytest.raises(TypeError, match="unit_system='dimensional'"):
        RsRotorBearingCouple(rotor, TimeIterDt(0.01, 1), bearing)


def test_film_failure_uses_injected_notifier_without_infrastructure_import():
    recorder = _Recorder()
    film = object.__new__(FilmSystem)
    film.main_model = SimpleNamespace(args={"c": 1.0})
    film.notifier = recorder

    assert isinstance(recorder, NotifierProtocol)
    with pytest.raises(ValueError, match="less than 1"):
        film._input_rotoru(np.array([1.1, 0.0]))
    assert recorder.messages == [
        ("Calculation error", "Input eccentricity is greater than 1.")
    ]


def test_classification_namespaces_preserve_implementation_identity():
    from ALB.alb import ALB
    from ALB.bearing import HydrostaticBearing
    from ALB.controller import PID
    from ALB.control import PID as CategorizedPID
    from ALB.physics import HydrostaticBearing as CategorizedBearing
    from ALB.systems import ALB as CategorizedALB

    assert CategorizedPID is PID
    assert CategorizedBearing is HydrostaticBearing
    assert CategorizedALB is ALB

    for module_name in (
        "ALB.physics",
        "ALB.control",
        "ALB.dynamics",
        "ALB.systems",
        "ALB.surrogate",
    ):
        module = importlib.import_module(module_name)
        for name in module.__all__:
            assert getattr(module, name) is not None
