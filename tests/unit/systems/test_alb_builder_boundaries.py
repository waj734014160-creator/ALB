"""Boundary regression tests for ALB system construction."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from ALB.config import (
    ALBConfig,
    NodimALBConfig,
    NodimOrificeConfig,
    NodimPadConfig,
    OrificeConfig,
)
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode
from ALB.core import Signal
from ALB.systems.alb import ALB, ALBBuilder, NodimALB, nodim_alb
from ALB.systems.alb.assembly import alb_no_controller


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

    def save(self, tofile=False, path=None, name=None, *args, **kwargs):
        del tofile, args, kwargs
        return SaveTreeNode(
            path or "pad",
            DataFrameResult({name or "pad": pd.DataFrame()}),
        )


def test_alb_init_accepts_explicitly_absent_controller():
    pad = _Pad()
    model = ALB([pad], [], controller=None, alb_config=ALBConfig())

    assert pad.init_calls == 1
    assert model.controller is None


def test_alb_save_accepts_explicitly_absent_controller():
    model = alb_no_controller(ALBConfig())

    result = model.save(tofile=False, path=None, name=None)

    assert model.controller is None
    assert [child.path for child in result.children] == [
        "pad0",
        "pad1",
        "pad2",
        "pad3",
        "servovalves0",
        "servovalves1",
    ]


def test_nondimensional_factory_accepts_explicitly_absent_controller():
    config = NodimALBConfig(
        pad_config=NodimPadConfig(
            lambda_value=1.2,
            lr=1.0,
            lx=90.0,
            lz=2.0,
            nx=5,
            nz=3,
            coe=False,
            max_iter=3,
            error_set=1.0e-5,
        ),
        orifice_config=NodimOrificeConfig(
            position=[[0.5, 0.5]],
            cq0=0.2,
            cq1=1.0,
            cq2=0.1,
        ),
        controller_config=None,
        servo="static",
    )

    model = nodim_alb(config)

    assert isinstance(model, NodimALB)
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
