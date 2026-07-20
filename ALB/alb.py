# coding: utf-8
import copy
from typing import TYPE_CHECKING, Iterable, Union

import numpy as np
import pandas as pd
from scipy import sparse as sp
from scipy.sparse import linalg as sl

from ALB.base import BaseCSystem, BaseSimpleModel, Signal
from ALB.bearing import four_pads_bearings, nodim_four_pads_bearings
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
)
from ALB.controller import PID, FuzzyPID
from ALB.orifice import CSOrifice, NodimCSOrifice
from ALB.results import DataFrameResult, SaveTreeNode
from ALB.servovalve import moog_2nd_servovalve, moog_servovalve, static_sv
from ALB.thermal import (
    NodimThermalHydroBearing,
    ThermalConfig,
    build_thermal_config,  # noqa: F401  re-exported for backward compatibility
    wrap_pad_collection_with_thermal,
)

if TYPE_CHECKING:
    from ALB.nn import ALBNet

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
        alb_config: ALBConfig = ALBConfig(),
    ):
        """
        This class represents an Active Lubricated Bearing (ALB) system.
        It takes pre-defined servovalves, controllers, orifices, and pads to establish the connections within the ALB.
        """
        super().__init__()
        self._t = None
        self.pads = list(pads)
        self.signal.children = [pad.signal for pad in self.pads]
        if len(self.pads) == 0:
            raise Exception("pads can't be empty")
        self.servovalves = servovalves
        self.static_sv = None
        self.node_link = alb_config.node_link
        self.controller = controller
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
        self._switch = alb_config.switch
        self._t_on = 0
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
        self.controller.init()
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
        """
        if this method is called, the control program will be set to open at t_on in time iter,
        and closed at other times
        :param t_on: float, the time to turn on the control program
        """
        self._t_on = t_on
        self._switch = False

    def _turn_on(self, t: float):
        """
        Switch for the control program.
        """
        if t >= self._t_on:
            self._switch = True

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
            servovalve.input(self._t, self._uv[num], **kwargs)
            servovalve.output()
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
        """
        Control process, receives rotor displacement and velocity. Dimensionality is determined by the input.
        """
        uv = np.dot(self._gxy, uxy) + np.dot(self._gxyt, uxyt)
        u0 = np.zeros_like(uv)
        if self.controller is not None:
            self.controller.input(t, uv - u0)
            output = self.controller.output()
            return output
        else:
            return uv

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
        children.append(
            self.controller.save(path="controller", name="controller_res", tofile=False)
        )
        node.add_children(children)
        if tofile:
            node.save_to_file()
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
        alb_config: ALBConfig = ALBConfig(),
    ):
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
            sv.xv = self._sv[n]
            sv.output()

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
        alb_config: NodimALBConfig = NodimALBConfig(),
    ):
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
            servovalve.input(self._t, self._uv[num], **kwargs)
            servovalve.output()
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
        alb_config: NodimALBConfig = NodimALBConfig(),
    ):
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
            servovalve.xv = self._sv[num]
            servovalve.output()

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


class ALBLinear:
    def __init__(self, alb: ALB):
        if not isinstance(alb, ALB):
            raise TypeError("alb must be ALB")
        self.alb = alb
        self.alb.init()
        self.pads = alb.pads
        conclum = [
            "fx",
            "fy",
            "fxdxv",
            "fydxv",
            "kxx",
            "kxy",
            "kyx",
            "kyy",
            "cxx",
            "cxy",
            "cyx",
            "cyy",
        ]
        self._results = pd.DataFrame(columns=conclum)

    def _static_calc(self, uxy):
        """
        Calculate the static force and reinitialize the model.
        """
        self.alb.input(t=0, uxy=uxy, uxyt=np.zeros_like(uxy))
        force = self.alb.output(static=True, nodim=False)["force"]
        return force

    def _record_results(self, force, fdxv, K, C):
        """
        Record the linearization results.
        """
        res = np.concatenate(
            [force, fdxv.reshape(-1), K.reshape(-1), C.reshape(-1)], axis=0
        )
        self._results.loc[len(self._results)] = res

    def linearize(self, uxy):
        """
        Linearize the ALB model at a given rotor position.
        :param uxy: Rotor position (x, y).
        :return: A dictionary containing the linearized parameters.
        """
        from ALB.bearing import BearingDynamicChar

        force = self._static_calc(uxy)
        fdxv = np.zeros((2, 2))
        K = np.zeros((2, 2))
        C = np.zeros((2, 2))
        for num, pad in enumerate(self.pads):
            fdxv_tp = self.linearize_pad(pad)
            bdc = BearingDynamicChar(pad)
            K_tp = bdc.calc_k(nodim=False)
            C_tp = bdc.calc_c(nodim=False)
            K += K_tp
            C += C_tp
            self._record_results(force, fdxv_tp, K_tp, C_tp)
        fdxv[1] += self._results[["fxdxv", "fydxv"]].iloc[0].to_numpy()
        fdxv[1] += self._results[["fxdxv", "fydxv"]].iloc[1].to_numpy()
        fdxv[0] += self._results[["fxdxv", "fydxv"]].iloc[2].to_numpy()
        fdxv[0] += self._results[["fxdxv", "fydxv"]].iloc[3].to_numpy()
        fdxv = fdxv.T
        xv0 = np.array([of.xv for of in self.alb.static_sv])
        res = {"force": force, "fdxv": fdxv, "K": K, "C": C, "xv0": xv0, "uxy0": uxy}
        return res

    @staticmethod
    def linearize_pad(pad):
        """
        Linearize a single pad.
        :param pad: The pad object to be linearized.
        :return: The derivative of force with respect to valve spool displacement (fdxv).
        """
        of = pad.simple_models[0]
        if not isinstance(of, CSOrifice):
            raise TypeError("of must be CSOrifice")
        AD1 = pad.main_model.matrixs["ke"]
        fr = pad.main_model.node_manager.freedoms
        K = AD1[0:fr, 0:fr]
        qa = of._results["q"].iloc[-1]
        ofn = len(of.node)
        qn = np.abs(of._results.iloc[-1, -1 - ofn : -1].to_numpy())
        cq0 = of.cq0
        cq1 = of.cq1_h2
        cq2 = of.cq2
        xv = of.xv
        if qa >= 0:
            lamda = 1
        else:
            lamda = -1
        a = 2 * lamda * qa / cq0**2 / xv**2
        L0 = 2 * cq1 * qn + cq2
        Le = np.diag(L0)
        A0 = a * np.ones((ofn, ofn)) + Le
        A0_inv = np.linalg.inv(A0)
        B = 2 * lamda * qa**2 / cq0**2 / xv**3 * np.ones(ofn)
        C = np.eye(ofn)
        B0 = A0_inv.dot(B)
        C0 = A0_inv.dot(C)
        nms = np.array([node.number for node in of.node])
        cols = np.repeat(nms.reshape((1, -1)), 3, axis=0)
        rows = cols.T
        C0_coo = sp.coo_matrix(
            (C0.reshape(-1), (rows.reshape(-1), cols.reshape(-1))), shape=(fr, fr)
        )
        NK = K + C0_coo
        B_fe = np.zeros(fr)
        B_fe[nms] = B0
        p = pad.main_model._results[-1]
        p = p[0:fr]
        lam = []
        for n in range(fr):
            if abs(p[n]) < 1e-10:
                constraint_row = np.zeros(fr)
                constraint_row[n] = 1
                lam.append(constraint_row)
        lam = np.array(lam)
        lamT = lam.T
        lamT = sp.coo_matrix(lamT)
        zm = np.zeros((lam.shape[0], lam.shape[0]))
        za = np.zeros(lam.shape[0])
        A = sp.hstack([NK, lamT])
        Ap = np.hstack([lam, zm])
        Ap = sp.coo_matrix(Ap)
        A = sp.vstack([A, Ap])
        B_fe = np.hstack((B_fe, za))
        A = A.tocsr()
        ans = sl.spsolve(A, B_fe)
        temp = pad.main_model._results[-1]
        pad.main_model._results[-1] = ans
        pad.main_model.update_to_nodes()
        fdxv = pad.postprocess.calc_capacity(nodim=False)
        pad.main_model._results[-1] = temp
        pad.main_model.update_to_nodes()
        return fdxv


class FakeOf:
    """
    A fake orifice class for testing purposes.
    """

    def __init__(self):
        """
        Initialize the fake orifice.
        """
        self.xv = 0

    def input(self, xv):
        """
        Set the spool valve displacement.
        """
        self.xv = xv

    def output(self):
        """
        Return None as there is no real output.
        """
        return None


class ALBLinearAgent(BaseSimpleModel):
    def __init__(self, force, fdxv, K, C, xv0, uxy0, *args, **kwargs):
        if not map(lambda x: isinstance(x, np.ndarray), [force, fdxv, K, C, xv0, uxy0]):
            raise TypeError("force, fdxv, K, C must be np.ndarray")
        super().__init__(*args, **kwargs)
        self.static_force = force
        self.force = None
        self.fdxv = fdxv
        self.K = K
        self.C = C
        self.xv0 = xv0
        self.xv = xv0
        self.t = 0
        self.uxy0 = uxy0
        self.uxy = None
        self.uxyt = None
        self._results = pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )

        self.of = [FakeOf() for _ in range(2)]

    def init(self):
        self._results = pd.DataFrame(
            columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
        )
        self.t = 0
        self.uxy = None
        self.uxyt = None

    def input(self, t, uxy, uxyt, *args, **kwargs):
        self.t = t
        self.uxy = uxy
        self.uxyt = uxyt
        self.xv = np.array([of.xv for of in self.of])

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
        dxv = self.xv - self.xv0
        duxy = self.uxy - self.uxy0
        self.force = (
            self.static_force
            + np.dot(self.fdxv, dxv)
            + np.dot(self.K, -duxy)
            + np.dot(self.C, -self.uxyt)
        )
        self.signal.lead_loop("finish_signal")
        return {"force": self.force}

    def calc_error(self, *args, **kwargs):
        return True

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        return True

    def finish_signal(self):
        """
        Record results at the end of a simulation step.
        """
        self._record_results(self.t, self.uxy, self.uxyt, self.force)


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
            node.save_to_file()
        return node

    def finish_signal(self):
        """
        Record results at the end of a simulation step.
        """
        self._record_results(self.t, self.uxy, self.uxyt, self.force)


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


class ALBBuilder:
    """
    Builder class for constructing an ALB (Active Lubricated Bearing) system.
    Refactored from ALBCreator to provide a robust, type-safe, and fluent interface.
    """

    def __init__(self, alb_config: ALBConfig = None):
        """
        Initialize the builder. If alb_config is provided, it populates the sub-configs automatically.
        """
        self.alb_config = alb_config

        # Sub-configurations (can be overridden manually)
        self.pad_config: Union[FPBConfig, None] = (
            alb_config.pad_config if alb_config else None
        )
        self.servo_config: Union[ServoConfig, None] = (
            alb_config.servo_config if alb_config else None
        )
        self.orifice_config: Union[OrificeConfig, None] = (
            alb_config.orifice_config if alb_config else None
        )
        self.tank_config: Union[TankConfig, None] = (
            alb_config.tank_config if alb_config else None
        )
        self.controller_config: Union[PIDConfig, FuzzyPIDConfig, None] = (
            alb_config.controller_config if alb_config else None
        )

        # Internal components storage
        self._pads = []
        self._servovalves = []
        self._static_svs = []
        self._controller = None
        self._orifices = {}  # stores soa_x, sob_x, etc.

        self.wiring_strategy = None

    # -------------------------- Configuration Steps --------------------------

    def set_pads_config(self, config: FPBConfig):
        self.pad_config = config
        return self

    def set_servo_config(self, config: ServoConfig):
        self.servo_config = config
        return self

    def set_orifice_config(self, config: OrificeConfig):
        self.orifice_config = config
        return self

    def set_tank_config(self, config: TankConfig):
        self.tank_config = config
        return self

    def set_controller_config(self, config: Union[PIDConfig, FuzzyPIDConfig]):
        self.controller_config = config
        return self

    def set_wiring_strategy(self, strategy_func):
        """
        Set a custom wiring strategy for pads, servos, and orifices.
        Expected signature: (pads, servos, orifices) -> None.
        """
        self.wiring_strategy = strategy_func
        return self

    def _create_pads(self):
        if not self.pad_config:
            raise ValueError("Pad configuration is missing.")
        return four_pads_bearings(self.pad_config)

    def _create_servos(self, servo_type: str):
        if not self.servo_config:
            raise ValueError("Servo configuration is missing.")

        # Create Dynamic Servos (for control)
        if servo_type == "moog":
            sv_x = moog_servovalve(
                self.servo_config.dt,
                self.servo_config.delay,
                self.servo_config.tw,
                self.servo_config.zeta,
                self.servo_config.tp3,
            )
            sv_y = moog_servovalve(
                self.servo_config.dt,
                self.servo_config.delay,
                self.servo_config.tw,
                self.servo_config.zeta,
                self.servo_config.tp3,
            )
        elif servo_type == "moog_2nd":
            sv_x = moog_2nd_servovalve(
                self.servo_config.dt,
                self.servo_config.delay,
                self.servo_config.tw,
                self.servo_config.zeta,
            )
            sv_y = moog_2nd_servovalve(
                self.servo_config.dt,
                self.servo_config.delay,
                self.servo_config.tw,
                self.servo_config.zeta,
            )
        elif servo_type == "static":
            sv_x = static_sv(self.servo_config.dt)
            sv_y = static_sv(self.servo_config.dt)
        else:
            raise ValueError(f"Unknown servo type: {servo_type}")

        # Create Static Servos (for static equilibrium calculation)
        # Note: ALB class expects static_sv to be available implicitly or created internally,
        # but creating them here ensures consistency.
        # Logic matches original ALBCreator._static_servo
        ssv_x = static_sv(self.servo_config.dt)
        ssv_y = static_sv(self.servo_config.dt)

        return [sv_x, sv_y], [ssv_x, ssv_y]

    def _create_orifices(self):
        if not self.orifice_config:
            raise ValueError("Orifice configuration is missing.")

        ps = self.orifice_config.ps
        position = self.orifice_config.position
        csorifice_args = CsoArgs()

        soa_x = CSOrifice(ps=ps, cso_args=csorifice_args, position=position)
        sob_x = CSOrifice(ps=0, p0=ps, cso_args=csorifice_args, position=position)
        soa_y = copy.deepcopy(soa_x)
        sob_y = copy.deepcopy(sob_x)

        return {"soa_x": soa_x, "sob_x": sob_x, "soa_y": soa_y, "sob_y": sob_y}

    def _create_controller(self):
        if not self.controller_config:
            # Return None or a dummy controller if allowed
            return None

        if isinstance(self.controller_config, FuzzyPIDConfig):
            # Original code copied args before creation, keeping that behavior
            fargs = copy.copy(self.controller_config)
            return FuzzyPID(fargs)
        elif isinstance(self.controller_config, PIDConfig):
            return PID(self.controller_config)
        else:
            raise TypeError(
                f"Unknown controller config type: {type(self.controller_config)}"
            )

    def _create_thermal_config(self):
        """Resolve the pad-level thermal config and apply ALB-level defaults."""
        thermal_config = getattr(self.alb_config.pad_config, "thermal_config", None)
        if thermal_config is None:
            return None
        thermal_args = vars(thermal_config).copy()
        if thermal_args.get("dt") is None:
            thermal_args["dt"] = self.alb_config.dt
        if not thermal_args.get("transient_enabled"):
            thermal_args["transient_enabled"] = self.alb_config.servo != "static"
        return ThermalConfig.from_dict(thermal_args)

    # -------------------------- Wiring / Assembly --------------------------

    def _apply_tank_settings(self, bearings: dict):
        if self.tank_config:
            for bearing in bearings.values():
                bearing.set_thickness(
                    method="add_tank",
                    xrange=self.tank_config.xrange,
                    zrange=self.tank_config.zrange,
                    h_tank=self.tank_config.h_tank,
                )
        return bearings

    def _couple_components(self, pads, servos, orifices):
        if hasattr(self, "wiring_strategy") and self.wiring_strategy:
            self.wiring_strategy(pads, servos, orifices)
        else:
            self._default_wiring(pads, servos, orifices)

    @staticmethod
    def _default_wiring(pads_dict, servos, orifices):
        sv_x, sv_y = servos

        # Couple Orifice to Servo
        sv_x.add_simple_model([orifices["soa_x"], orifices["sob_x"]])
        sv_y.add_simple_model([orifices["soa_y"], orifices["sob_y"]])

        # Couple Orifice to Bearing Pads
        pads_dict["up"].add_simple_model(orifices["soa_y"])
        pads_dict["down"].add_simple_model(orifices["sob_y"])
        pads_dict["right"].add_simple_model(orifices["soa_x"])
        pads_dict["left"].add_simple_model(orifices["sob_x"])

        return pads_dict

    # -------------------------- Main Build Method --------------------------

    def build(self) -> ALB:
        """
        Constructs the ALB system based on the current configuration.
        """
        if not self.alb_config:
            raise ValueError("ALBConfig is required to build the final system.")

        # 1. Create Components
        pads_dict = self._create_pads()
        servos, static_servos = self._create_servos(self.alb_config.servo)
        orifices = self._create_orifices()
        controller = self._create_controller()

        # 2. Wire Components (Hydraulic connections)
        self._couple_components(pads_dict, servos, orifices)

        # 3. Apply Tank Settings (Geometry modification)
        self._apply_tank_settings(pads_dict)

        # 4. Instantiate ALB (System Assembly)
        pads_list = wrap_pad_collection_with_thermal(
            list(pads_dict.values()), self._create_thermal_config()
        )

        # Determine ALB Class type
        alb_type = self.alb_config.alb
        if alb_type == "ALB" or alb_type is None:
            alb_system = ALB(
                pads_list, servos, controller=controller, alb_config=self.alb_config
            )
        elif alb_type == "ALBSV":
            alb_system = ALBSV(
                pads_list, servos, controller=controller, alb_config=self.alb_config
            )
        else:
            raise ValueError(f"Unknown ALB type: {alb_type}")

        # Inject the static servos created earlier (optional, but maintains consistency with original logic)
        # The ALB class creates its own static_sv internally in _create_static_sv,
        # but if we wanted to enforce the ones we built:
        # alb_system.static_sv = static_servos

        return alb_system


def alb2(alb_config: ALBConfig) -> ALB:
    """
    Standard factory for ALB system (PID + Moog/Static based on config).
    """
    return ALBBuilder(alb_config).build()


def alb2_fuzzy(alb_config: ALBConfig) -> ALB:
    """
    Factory for ALB system with Fuzzy PID.
    """
    # Ensure the config is set to use Fuzzy Logic context if not already
    # This might be redundant if alb_config.controller_config is already FuzzyPIDConfig
    # but serves as a safeguard.
    if not isinstance(alb_config.controller_config, FuzzyPIDConfig):
        # If the user called alb2_fuzzy but passed a PIDConfig, we might need to handle it.
        # For now, we assume the config matches the intent.
        pass

    return ALBBuilder(alb_config).build()


def alb2_static(alb_config: ALBConfig) -> ALB:
    """
    Factory for ALB system with Static Servovalves.
    """
    # Force the servo type to static
    alb_config_copy = copy.deepcopy(alb_config)
    alb_config_copy.servo = "static"
    return ALBBuilder(alb_config_copy).build()


def _nodim_alb_config_from_legacy(args, kwargs, alb_config):
    """Build a NodimALBConfig from the pre-refactor flat nodim_alb arguments."""
    config = copy.deepcopy(alb_config) if alb_config is not None else NodimALBConfig()
    positional = dict(zip(_NODIM_ALB_LEGACY_REQUIRED_KEYS, args))
    if len(args) > len(_NODIM_ALB_LEGACY_REQUIRED_KEYS):
        raise TypeError("too many positional arguments for nodim_alb")

    for key in _NODIM_ALB_LEGACY_REQUIRED_KEYS[len(args) :]:
        if key not in kwargs:
            raise TypeError("nodim_alb legacy arguments are incomplete")
        positional[key] = kwargs.pop(key)

    dimensional_keys = _NODIM_ALB_FORBIDDEN_PAD_KWARGS.intersection(kwargs)
    if dimensional_keys:
        keys = ", ".join(sorted(dimensional_keys))
        raise ValueError(
            f"nodim_alb does not accept dimensional pad parameters: {keys}"
        )

    # Split the flat legacy signature into the nested pad/orifice config pieces.
    pad_args = {
        "lambda_value": positional["lambda_value"],
        "lr": positional["lr"],
        "lx": positional["lx"],
        "lz": positional["lz"],
        "nx": kwargs.pop("nx", config.pad_config.nx),
        "nz": kwargs.pop("nz", config.pad_config.nz),
        "bias": kwargs.pop("bias", config.pad_config.bias),
    }
    orifice_args = {
        "position": positional["position"],
        "cq0": positional["cq0"],
        "cq1": positional["cq1"],
        "cq2": positional["cq2"],
        "ps": kwargs.pop("orifice_ps", config.orifice_config.ps),
        "p0": kwargs.pop("orifice_p0", config.orifice_config.p0),
        "q_leak": kwargs.pop("q_leak", config.orifice_config.q_leak),
    }

    # Allow the remaining flat kwargs to override pad-level nondimensional options.
    pad_update_keys = set(config.pad_config.to_dict()) - {"x0s"}
    for key in list(kwargs):
        if key in pad_update_keys:
            pad_args[key] = kwargs.pop(key)
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected nodim_alb arguments: {unknown}")

    current_pad_args = config.pad_config.to_dict()
    current_pad_args.pop("x0s", None)
    config.pad_config = type(config.pad_config)(**{**current_pad_args, **pad_args})
    # Orifice config has no computed fields, so its dict can be reused directly.
    config.orifice_config = type(config.orifice_config)(
        **{**config.orifice_config.to_dict(), **orifice_args}
    )
    return config


def _coerce_nodim_alb_config(args, kwargs, alb_config):
    """Normalize all supported nodim_alb call styles to a NodimALBConfig."""
    if alb_config is not None and not isinstance(alb_config, NodimALBConfig):
        if (
            getattr(alb_config, "c", None) is not None
            or getattr(alb_config, "w", None) is not None
        ):
            raise ValueError(
                "nodim_alb does not accept dimensional ALBConfig.c/w scales"
            )
        raise TypeError("nodim_alb only accepts NodimALBConfig")

    if args and isinstance(args[0], NodimALBConfig):
        if alb_config is not None:
            raise TypeError("nodim_alb received NodimALBConfig twice")
        if len(args) > 1:
            raise TypeError("nodim_alb accepts only NodimALBConfig in config mode")
        if kwargs:
            unknown = ", ".join(sorted(kwargs))
            raise TypeError(f"unexpected nodim_alb arguments: {unknown}")
        return copy.deepcopy(args[0])

    if args or any(key in kwargs for key in _NODIM_ALB_LEGACY_REQUIRED_KEYS):
        return _nodim_alb_config_from_legacy(args, kwargs, alb_config)

    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected nodim_alb arguments: {unknown}")
    return copy.deepcopy(alb_config) if alb_config is not None else NodimALBConfig()


def _nodim_controller_from_config(alb_config, controller):
    """Create the controller instance used by the nondimensional ALB entry."""
    if controller is not None:
        return controller
    controller_config = copy.deepcopy(alb_config.controller_config)
    # Keep the controller time step aligned with the top-level ALB time step.
    if hasattr(controller_config, "dt"):
        controller_config.dt = alb_config.dt
    if isinstance(controller_config, FuzzyPIDConfig):
        return FuzzyPID(controller_config)
    return PID(controller_config)


def _nodim_thermal_config(alb_config, thermal_config):
    """Resolve the thermal config and force the nondimensional argument mode."""
    if thermal_config is None:
        thermal_config = getattr(alb_config, "thermal_config", None)
    if thermal_config is None:
        return None
    thermal_args = vars(thermal_config).copy()
    if thermal_args.get("dt") is None:
        thermal_args["dt"] = alb_config.dt
    if not thermal_args.get("transient_enabled"):
        thermal_args["transient_enabled"] = alb_config.servo != "static"
    # The nodim entry always drives the thermal wrapper with nondimensional states.
    thermal_args["args_nodim"] = True
    return ThermalConfig.from_dict(thermal_args)


def nodim_alb(
    *args,
    alb_config: NodimALBConfig = None,
    servo_config: ServoConfig = None,
    controller=None,
    thermal_config: ThermalConfig = None,
    **kwargs,
) -> ALB:
    """Assemble an ALB model from a NodimALBConfig."""
    alb_config = _coerce_nodim_alb_config(args, kwargs, alb_config)
    if (
        getattr(alb_config, "c", None) is not None
        or getattr(alb_config, "w", None) is not None
    ):
        raise ValueError("nodim_alb does not accept dimensional ALBConfig.c/w scales")

    if servo_config is None:
        servo_config = copy.deepcopy(alb_config.servo_config)
    servo_config.dt = alb_config.dt
    controller = _nodim_controller_from_config(alb_config, controller)

    pad_config = alb_config.pad_config
    pad_args = pad_config.to_dict()
    # nodim_four_pads_bearings takes the geometric core arguments explicitly and
    # the remaining nondimensional film options as keyword arguments.
    pad_kwargs = {
        key: value
        for key, value in pad_args.items()
        if key not in _NODIM_ALB_PAD_MAIN_KEYS and key != "x0s" and value is not None
    }
    scale_arg_map = {
        "scale_miu": "miu",
        "scale_c": "c",
        "scale_r": "r",
        "scale_l": "l",
        "scale_ps": "ps",
        "scale_rho": "rho",
        "scale_w": "w",
    }
    for scale_key, film_key in scale_arg_map.items():
        value = pad_kwargs.pop(scale_key, None)
        if value is not None:
            pad_kwargs[film_key] = value

    pads_dict = nodim_four_pads_bearings(
        lambda_value=pad_config.lambda_value,
        lr=pad_config.lr,
        lx=pad_config.lx,
        lz=pad_config.lz,
        nx=pad_config.nx,
        nz=pad_config.nz,
        bias=pad_config.bias,
        **pad_kwargs,
    )

    if alb_config.servo == "moog":
        servos = [
            moog_servovalve(
                servo_config.dt,
                servo_config.delay,
                servo_config.tw,
                servo_config.zeta,
                servo_config.tp3,
            )
            for _ in range(2)
        ]
    elif alb_config.servo == "moog_2nd":
        servos = [
            moog_2nd_servovalve(
                servo_config.dt,
                servo_config.delay,
                servo_config.tw,
                servo_config.zeta,
            )
            for _ in range(2)
        ]
    elif alb_config.servo == "static":
        servos = [static_sv(servo_config.dt) for _ in range(2)]
    else:
        raise ValueError("servo must be 'moog', 'moog_2nd', or 'static'")

    orifice_config = alb_config.orifice_config
    # X and Y branches share the same nondimensional slot model, while the
    # return-side branch is created by swapping supply and ambient pressures.
    soa_x = NodimCSOrifice(
        position=orifice_config.position,
        cq0=orifice_config.cq0,
        cq1=orifice_config.cq1,
        cq2=orifice_config.cq2,
        ps=orifice_config.ps,
        p0=orifice_config.p0,
        q_leak=orifice_config.q_leak,
    )
    sob_x = NodimCSOrifice(
        position=orifice_config.position,
        cq0=orifice_config.cq0,
        cq1=orifice_config.cq1,
        cq2=orifice_config.cq2,
        ps=orifice_config.p0,
        p0=orifice_config.ps,
        q_leak=orifice_config.q_leak,
    )
    orifices = {
        "soa_x": soa_x,
        "sob_x": sob_x,
        "soa_y": copy.deepcopy(soa_x),
        "sob_y": copy.deepcopy(sob_x),
    }

    # Reuse the standard hydraulic wiring so the nodim entry stays behaviorally
    # aligned with the dimensional ALB builder.
    ALBBuilder._default_wiring(pads_dict, servos, orifices)

    tank_config = getattr(alb_config, "tank_config", None)
    if tank_config is not None:
        for pad in pads_dict.values():
            pad.set_thickness(
                method="add_tank",
                xrange=tank_config.xrange,
                zrange=tank_config.zrange,
                h_tank=tank_config.h_tank,
            )

    pads = list(pads_dict.values())
    thermal_config = _nodim_thermal_config(alb_config, thermal_config)
    if thermal_config is not None:
        pads = [NodimThermalHydroBearing(pad, thermal_config) for pad in pads]

    alb_type = alb_config.alb
    if alb_type == "ALBSV":
        return NodimALBSV(pads, servos, controller=controller, alb_config=alb_config)
    if alb_type in {"ALB", None}:
        return NodimALB(pads, servos, controller=controller, alb_config=alb_config)
    raise ValueError(f"Unknown ALB type: {alb_type}")


def alb_no_controller(alb_config: ALBConfig) -> ALB:
    """
    Factory for ALB system without a controller.
    """
    builder = ALBBuilder(alb_config)
    # Explicitly remove controller config to prevent controller creation
    builder.set_controller_config(None)
    return builder.build()


def linear_alb(alb, uxy) -> ALB:
    """
    Create a linear model of an ALB system.
    This uses Moog servovalves and CSOrifices.
    :param alb: The original ALB object.
    :param uxy: The linearization position of the bearing.
    :return: A new ALB object representing the linearized system.
    """
    # establish the alb2 model and replace its pads and orifice model
    bearing = alb
    cb = copy.deepcopy(bearing)
    al = ALBLinear(bearing)
    lan = al.linearize(uxy)
    ala = ALBLinearAgent(**lan)
    # the ala model has the fake orifice model to get the xv from servo valve
    cb.servovalves[0].simple_models = [ala.of[0]]
    cb.servovalves[1].simple_models = [ala.of[1]]
    cb.pads = [ala]
    return cb


def nn_agent(alb, albnet_config) -> ALB:
    """
    Create an ALB agent using a neural network.
    :param alb: The original ALB object.
    :param albnet_config: Configuration for the ALB neural network.
    :return: A new ALB object with the NN agent.
    """
    from ALB.nn import alb_agent_nn

    alb = copy.deepcopy(alb)
    nn = alb_agent_nn(albnet_config)
    ala = ALBNNAgent(nn, agent=albnet_config.agent)
    alb.servovalves[0].simple_models = [ala.of[0]]
    alb.servovalves[1].simple_models = [ala.of[1]]
    alb.pads = [ala]
    alb.signal.children = [pad.signal for pad in alb.pads]
    return alb
