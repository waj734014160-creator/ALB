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

class TimerSwitch:
    """
    A switch that activates at a specific time.
    """

    def __init__(self, t: Union[float, np.ndarray]):
        """
        :param t: The activation time.
        """
        self._t = t

    def __call__(self, t, *args, **kwargs):
        """
        Check if the switch should be active at time t.
        :param t: Current time.
        :return: True if t is greater than the activation time, False otherwise.
        """
        if t > self._t:
            return True
        else:
            return False

__all__ = ["TimerSwitch"]
