"""Boundary regression tests for ALB system construction."""

from __future__ import annotations

from types import SimpleNamespace

from ALB.config import ALBConfig, OrificeConfig
from ALB.core import Signal
from ALB.systems.alb import ALB, ALBBuilder


class _Pad:
    """Small pad contract used to exercise controller-free initialization."""

    def __init__(self) -> None:
        self.signal = Signal(sys=self)
        self.main_model = SimpleNamespace(
            args={"c": 1.0e-4, "w": 3000.0, "vf": 0.5}
        )
        self.init_calls = 0

    def init(self) -> None:
        self.init_calls += 1


def test_alb_init_accepts_explicitly_absent_controller():
    pad = _Pad()
    model = ALB([pad], [], controller=None, alb_config=ALBConfig())

    model.init()

    assert pad.init_calls == 1
    assert model.controller is None


def test_dimensional_builder_routes_return_pressure_and_cq1_override():
    config = ALBConfig(
        orifice_config=OrificeConfig(
            ps=7.0e6,
            p0=1.2e5,
            cq1_nondim=0.125,
        )
    )

    orifices = ALBBuilder(config)._create_orifices()

    for supply_name in ("soa_x", "soa_y"):
        supply = orifices[supply_name]
        assert supply.pa == 7.0e6
        assert supply.pb == 1.2e5
        assert supply.args.cq1_nondim == 0.125
    for return_name in ("sob_x", "sob_y"):
        return_orifice = orifices[return_name]
        assert return_orifice.pa == 1.2e5
        assert return_orifice.pb == 7.0e6
        assert return_orifice.args.cq1_nondim == 0.125
