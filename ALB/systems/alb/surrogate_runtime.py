# coding: utf-8
import copy
from typing import TYPE_CHECKING, Iterable, Union

import numpy as np
import pandas as pd
from scipy import sparse as sp
from scipy.sparse import linalg as sl

from ALB.core.component import BaseCSystem, BaseSimpleModel
from ALB.core.events import Signal
from ALB.physics.bearing import four_pads_bearings, nodim_four_pads_bearings
from ALB.config import (
    ALBConfig,
    CsoArgs,
    FPBConfig,
    FuzzyPIDConfig,
    NodimALBConfig,
    OrificeConfig,
    PIDConfig,
    ServoConfig,
    TankConfig,
    ThermalConfig,
    build_thermal_config,
)
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.adapters import adapt_controller
from ALB.control.blocks import run_controller_step, run_valve_step
from ALB.physics.hydraulics import CSOrifice, NodimCSOrifice
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode
from ALB.control.valve import moog_2nd_servovalve, moog_servovalve, static_sv
from ALB.physics.thermal import (
    NodimThermalHydroBearing,
    wrap_pad_collection_with_thermal,
)

if TYPE_CHECKING:
    from ALB.surrogate.inference import ALBNet

_NODIM_ALB_FORBIDDEN_PAD_KWARGS = {"miu", "c", "r", "l", "ps", "rho", "w", "w_rad"}
_NODIM_ALB_LEGACY_REQUIRED_KEYS = [
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

class ALBNNAgent(BaseSimpleModel):
    def __init__(self, net: "ALBNet", agent=None, *args, **kwargs):
        """
        ALBNNAgent is an agent for ALB system using neural network to predict the force
        :param net: ALBNet, the neural network model for ALB
        :param agent: str, the agent name, default is 'ALBNNAgent',
                      can be 'HydroNNAgent' or 'HybridNNAgent' for specific use cases
        """
        super().__init__(*args, **kwargs)
        self.alb_net = net
        self.uxy = None
        self.uxyt = None
        self.t = 0
        self.xv = None
        self.force = np.zeros(2)
        self._results = pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )
        self.signal = Signal(sys=self)
        self.of = [FakeOf() for _ in range(2)]
        self.agent = "ALBNNAgent" if agent is None else agent

    def init(self):
        self._results = pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )
        self.t = 0
        self.uxy = None
        self.uxyt = None

    def input(self, t, uxy, uxyt, *args, **kwargs):
        nodim = kwargs.get("nodim", False)
        self.t = t
        self.uxy = uxy
        self.uxyt = uxyt
        if self.agent == "ALBNNAgent":
            self.xv = np.array([of.xv for of in self.of])
        elif self.agent == "HydroNNAgent":
            self.xv = np.zeros(2)
        elif self.agent == "HybridNNAgent":
            self.xv = np.ones(2)
        self.alb_net.input(self.uxy, self.uxyt, self.xv, nodim=nodim)

    def _record_results(self, t, uxy, uxyt, force):
        """
        Record the simulation results.
        """
        self._results.loc[len(self._results)] = [
            t,
            uxy[0],
            uxy[1],
            uxyt[0],
            uxyt[1],
            force[0],
            force[1],
        ]

    def output(self, *args, **kwargs):
        nodim = kwargs.pop("nodim", False)
        self.force = self.alb_net.output(nodim=nodim).reshape(-1)
        self.signal.lead_loop("finish_signal")
        return {"force": self.force}

    def calc_capacity(self, *args, **kwargs):
        return self.output(*args, **kwargs)["force"]

    def calc_error(self, *args, **kwargs):
        return True

    def save(self, tofile=False, path=None, name=None, *args, **kwargs):
        if name is None:
            name = "alb_nn"
        if path is None:
            path = "result"
        res = DataFrameResult({name: self._results})
        node = SaveTreeNode(path, res)
        if tofile:
            return node.persist(kwargs.get("writer"), path)
        return node

    def finish_signal(self):
        """
        Record results at the end of a simulation step.
        """
        self._record_results(self.t, self.uxy, self.uxyt, self.force)

__all__ = ["ALBNNAgent"]
