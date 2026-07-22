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

class ALB(BaseCSystem):
    """
    Active Lubricated Bearing (ALB) System
    """

    unit_system = "dimensional"

    def __init__(
        self,
        pads: Iterable,
        servovalves: list,
        controller=None,
        alb_config: ALBConfig | None = None,
    ):
        """
        This class represents an Active Lubricated Bearing (ALB) system.
        It takes pre-defined servovalves, controllers, orifices, and pads to establish the connections within the ALB.
        """
        super().__init__()
        if alb_config is None:
            alb_config = ALBConfig()
        self._t = None
        self.pads = list(pads)
        self.signal.children = [pad.signal for pad in self.pads]
        if len(self.pads) == 0:
            raise Exception("pads can't be empty")
        self.servovalves = servovalves
        self.static_sv = None
        self.node_link = alb_config.node_link
        self.controller = adapt_controller(controller) if controller is not None else None
        self._uv = None
        self._uxy = None
        self._uxyt = None
        self._uxy_nodim = None
        self._uxyt_nodim = None
        self._gxy = alb_config.gxy
        self._gxyt = alb_config.gxyt
        c_scale = getattr(alb_config, "c", None)
        if c_scale is None:
            self._c = self.pads[0].main_model.args["c"]
        else:
            self._c = c_scale
        w_scale = getattr(alb_config, "w", None)
        if w_scale is None:
            self._w = self.pads[0].main_model.args["w"]
        else:
            self._w = w_scale
        self._w_rad = self._w / 60 * 2 * np.pi
        self._vf = self.pads[0].main_model.args["vf"]
        self._control_enabled = bool(alb_config.switch)
        self._t_on: float | None = None
        self._switch = self._control_enabled
        self._results = pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )
        self._create_static_sv()
        self.force = None

    @property
    def gxy(self):
        return self._gxy

    @gxy.setter
    def gxy(self, value):
        self._gxy = value

    @property
    def gxyt(self):
        return self._gxyt

    @gxyt.setter
    def gxyt(self, value):
        self._gxyt = value

    @property
    def results(self):
        return self._results

    def init(self):
        """
        Initialize the ALB system, including pads, servovalves, and controller.
        """
        for pad in self.pads:
            pad.init()
        for servovalve in self.servovalves:
            servovalve.init()
        if self.controller is not None:
            self.controller.init()
        self._switch = self._control_enabled and self._t_on is None
        self._results = pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )

    def _create_static_sv(self, servovalves=None):
        """
        Create static servovalves.
        """
        if servovalves is None:
            servovalves = self.servovalves
        svs = [static_sv(0.5) for _ in servovalves]
        ofs = [sv.simple_models for sv in servovalves]
        for sv, of in zip(svs, ofs):
            sv.simple_models = of
        self.static_sv = svs
        return svs

    def turn_on_at(self, t_on: float):
        """Schedule control activation when the permanent config switch is enabled.

        ``ALBConfig.switch=False`` always wins over this schedule. Positive
        infinity is accepted as an explicit never-enable schedule.
        """
        activation_time = float(t_on)
        if np.isnan(activation_time):
            raise ValueError("t_on must not be NaN")
        self._t_on = activation_time
        self._switch = False

    def _turn_on(self, t: float):
        """Recompute the active control state from config and schedule."""
        if not self._control_enabled:
            self._switch = False
        elif self._t_on is None:
            self._switch = True
        else:
            self._switch = t >= self._t_on

    def input(self, uxy: np.ndarray, uxyt: np.ndarray, t: float, *args, **kwargs):
        """
        input the displacement and velocity with dimension of the rotor
        """
        self._t = t
        nodim = kwargs.get("nodim", False)
        uxy = np.array(uxy)
        uxyt = np.array(uxyt)
        if nodim:
            self._uxy = uxy * self._c
            self._uxyt = uxyt * self._c * (self._vf * self._w_rad)
            self._uxy_nodim = uxy
            self._uxyt_nodim = uxyt
        else:
            self._uxy = uxy
            self._uxyt = uxyt
            self._uxy_nodim = uxy / self._c
            self._uxyt_nodim = uxyt / self._c / (self._vf * self._w_rad)
        self._turn_on(t)

    def output(self, *args, **kwargs) -> dict:
        """
        Output the bearing force.
        """
        nodim = kwargs.pop("nodim", False)
        if self._switch:
            # The control program receives non-dimensional rotor displacement and velocity
            self._uv = self._control_process(self._uxy_nodim, self._uxyt_nodim, self._t)
        else:
            self._uv = np.zeros(2)
        static = kwargs.get("static", False)
        if static:
            sv = self.static_sv
            # TODO: Servovalve initialization
            self.init()
        else:
            sv = self.servovalves
        for num, servovalve in enumerate(sv):
            run_valve_step(servovalve, self._t, self._uv[num])
        forces = []
        frictions = []
        for pad in self.pads:
            pad.input(t=self._t, uxy=self._uxy, uxyt=self._uxyt, nodim=False)
            po = pad.output(nodim=nodim)
            force = po["force"]
            if "friction" in po:
                friction = po["friction"]
            else:
                friction = None
            forces.append(force)
            frictions.append(friction)
        forces = np.array(forces)
        frictions = np.sum(np.array(frictions))
        self.force = np.sum(forces, axis=0)
        self._uv = None
        self.signal.lead_loop("finish_signal")
        return {"force": self.force, "friction": frictions}

    def _control_process(self, uxy: np.ndarray, uxyt: np.ndarray, t: np.float64):
        """Return one controller command, or zero when no controller is installed."""
        uv = np.dot(self._gxy, uxy) + np.dot(self._gxyt, uxyt)
        u0 = np.zeros_like(uv)
        if self.controller is not None:
            return run_controller_step(self.controller, t, uv - u0)
        return np.zeros_like(uv)

    def calc_is_finished(self):
        return all([pad.calc_is_finished() for pad in self.pads]) and all(
            [servovalve.calc_is_finished() for servovalve in self.servovalves]
        )

    def set_thickness(self, *args, **kwargs):
        """
        Set the thickness of the pad, an interface for trajectory calculation.
        """
        for pad in self.pads:
            pad.set_thickness(*args, **kwargs)

    def calc_capacity(self, *args, **kwargs):
        """
        Calculate the bearing capacity, an interface for trajectory calculation.
        """
        ans = np.array([pad.calc_capacity(*args, **kwargs) for pad in self.pads])
        return np.sum(ans, axis=0)

    def solve(self, *args, **kwargs):
        """
        Execute the model solving calculation, an interface for trajectory calculation.
        """
        self.output(*args, **kwargs)

    def save(self, tofile, path, name, *args, **kwargs):
        """
        Save the calculation results.
        """
        if path is None:
            path = "alb"
        if name is None:
            name = "alb"
        res = {name + "_res": self._results}
        res = DataFrameResult(res)
        node = SaveTreeNode(path, res)
        children = []
        for num, pad in enumerate(self.pads):
            children.append(
                pad.save(path="pad" + str(num), name="pad_res", tofile=False)
            )
        for num, servovalve in enumerate(self.servovalves):
            children.append(
                servovalve.save(
                    path="servovalves" + str(num), name="servovalve_res", tofile=False
                )
            )
        if self.controller is not None:
            children.append(
                self.controller.save(
                    path="controller", name="controller_res", tofile=False
                )
            )
        node.add_children(children)
        if tofile:
            return node.persist(kwargs.get("writer"), path)
        return node

    def start_signal(self):
        return True

    def finish_signal(self):
        """
        Add calculation results to the result DataFrame.
        """
        self._results.loc[self._results.shape[0]] = [
            self._t,
            self._uxy[0],
            self._uxy[1],
            self._uxyt[0],
            self._uxyt[1],
            self.force[0],
            self.force[1],
        ]
        return True

class ALBSV(ALB):
    """
    ALB with servovalve input, this class is used to control the servovalve directly
    """

    def __init__(
        self,
        pads: Iterable,
        servovalves: list,
        controller=None,
        alb_config: ALBConfig | None = None,
    ):
        if alb_config is None:
            alb_config = ALBConfig()
        super().__init__(pads, servovalves, controller, alb_config)
        self._sv = None

    def input(
        self, uxy: np.ndarray, uxyt: np.ndarray, t: float, sv=None, *args, **kwargs
    ):
        if sv is None:
            sv = np.zeros(2)
        sv = np.array(sv)
        if sv.shape != (2,):
            raise ValueError("sv must be a 2-element array")
        self._sv = sv
        super().input(uxy, uxyt, t, *args, **kwargs)

    def output(self, *args, **kwargs) -> dict:
        nodim = kwargs.pop("nodim", False)
        for n, sv in enumerate(self.servovalves):
            sv.set_spool(self._sv[n])

        forces = []
        frictions = []
        for pad in self.pads:
            pad.input(t=self._t, uxy=self._uxy, uxyt=self._uxyt)
            po = pad.output(nodim=nodim)
            force = po["force"]
            friction = po["friction"]
            forces.append(force)
            frictions.append(friction)
        forces = np.array(forces)
        frictions = np.sum(np.array(frictions))
        self.force = np.sum(forces, axis=0)
        self._uv = None
        self.signal.lead_loop("finish_signal")
        return {"force": self.force, "friction": frictions}

class NodimALB(ALB):
    """ALB assembled from nondimensional pads and driven by nondimensional states."""

    unit_system = "nondimensional"

    def __init__(
        self,
        pads: Iterable,
        servovalves: list,
        controller=None,
        alb_config: NodimALBConfig | None = None,
    ):
        if alb_config is None:
            alb_config = NodimALBConfig()
        super().__init__(pads, servovalves, controller, alb_config)

    def input(self, uxy: np.ndarray, uxyt: np.ndarray, t: float, *args, **kwargs):
        nodim = kwargs.pop("nodim", True)
        if not nodim:
            raise ValueError("NodimALB only accepts nondimensional rotor input")
        self._t = t
        self._uxy = np.array(uxy)
        self._uxyt = np.array(uxyt)
        self._uxy_nodim = self._uxy
        self._uxyt_nodim = self._uxyt
        self._turn_on(t)

    def output(self, *args, **kwargs) -> dict:
        nodim = kwargs.pop("nodim", True)
        if not nodim:
            raise ValueError("NodimALB only outputs nondimensional force")
        if self._switch:
            self._uv = self._control_process(self._uxy_nodim, self._uxyt_nodim, self._t)
        else:
            self._uv = np.zeros(2)
        static = kwargs.get("static", False)
        if static:
            sv = self.static_sv
            self.init()
        else:
            sv = self.servovalves
        for num, servovalve in enumerate(sv):
            run_valve_step(servovalve, self._t, self._uv[num])
        forces = []
        frictions = []
        for pad in self.pads:
            pad.input(t=self._t, uxy=self._uxy_nodim, uxyt=self._uxyt_nodim, nodim=True)
            po = pad.output(nodim=True)
            forces.append(po["force"])
            frictions.append(po.get("friction"))
        self.force = np.sum(np.array(forces), axis=0)
        frictions = np.sum(np.array(frictions))
        self._uv = None
        self.signal.lead_loop("finish_signal")
        return {"force": self.force, "friction": frictions}

class NodimALBSV(NodimALB):
    """Nondimensional ALB with direct servovalve input."""

    def __init__(
        self,
        pads: Iterable,
        servovalves: list,
        controller=None,
        alb_config: NodimALBConfig | None = None,
    ):
        if alb_config is None:
            alb_config = NodimALBConfig()
        super().__init__(pads, servovalves, controller, alb_config)
        self._sv = None

    def input(
        self, uxy: np.ndarray, uxyt: np.ndarray, t: float, sv=None, *args, **kwargs
    ):
        if sv is None:
            sv = np.zeros(2)
        sv = np.array(sv)
        if sv.shape != (2,):
            raise ValueError("sv must be a 2-element array")
        self._sv = sv
        super().input(uxy, uxyt, t, *args, **kwargs)

    def output(self, *args, **kwargs) -> dict:
        nodim = kwargs.pop("nodim", True)
        if not nodim:
            raise ValueError("NodimALBSV only outputs nondimensional force")
        for num, servovalve in enumerate(self.servovalves):
            servovalve.set_spool(self._sv[num])

        forces = []
        frictions = []
        for pad in self.pads:
            pad.input(t=self._t, uxy=self._uxy_nodim, uxyt=self._uxyt_nodim, nodim=True)
            po = pad.output(nodim=True)
            forces.append(po["force"])
            frictions.append(po.get("friction"))
        self.force = np.sum(np.array(forces), axis=0)
        frictions = np.sum(np.array(frictions))
        self._uv = None
        self.signal.lead_loop("finish_signal")
        return {"force": self.force, "friction": frictions}

__all__ = ['ALB', 'ALBSV', 'NodimALB', 'NodimALBSV']
