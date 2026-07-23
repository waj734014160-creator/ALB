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

from .runtime import ALB
from ALB.contracts import BearingInput, UnitSystem

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
        self.alb.input(
            BearingInput(
                displacement=uxy,
                velocity=np.zeros_like(uxy),
                time=0.0,
                unit_system=UnitSystem.DIMENSIONAL,
            )
        )
        self.alb.evaluate_static()
        return self.alb.output().force

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
        from ALB.physics.bearing import BearingDynamicChar

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

__all__ = ['ALBLinear', 'FakeOf', 'ALBLinearAgent']
