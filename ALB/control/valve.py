# coding: utf-8
import copy
from typing import Union

# from ALB.infrastructure.logging import logger
import control as cl
import numpy as np
import pandas as pd

from ALB.core.component import BaseSystem
from ALB.core.validation import limit_signal as _limit_signal
from .state_space import BaseLti, TSDlti

# from ALB.infrastructure.logging import logger


class BaseValve(BaseSystem):
    @property
    def xout(self):
        return np.array(self.main_model.xout)

    @property
    def yout(self):
        return np.array(self.main_model.yout)

    @property
    def ts(self):
        return np.array(self.main_model.ts)

    def init(self, *args, **kwargs):
        self.main_model.init()

    def input(self, t, uv, *args, **kwargs):
        uv = np.array(uv)
        uv = uv.reshape([uv.size, 1])
        self.uv = uv
        self.main_model.input(t, uv)

    def output(self, *args, **kwargs):
        return self.solve()

    def calc_is_finished(self):
        return True

    def solve(self):
        return self.main_model.output()

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        return self.main_model.save(tofile, path, name, *args, **kwargs)


class ServoValve2(BaseValve):
    def __init__(self, lti, ofs=None):
        """
        Servo valve model based on a given LTI system with optional simple models in parallel.
        :param lti: an instance of BaseLti representing the valve dynamics
        """
        lti = copy.copy(lti)
        self.simple_models = [] if ofs is None else ofs
        self.uv = 0
        self.xv = 0
        if issubclass(type(lti), BaseLti):
            super().__init__(lti)
        else:
            raise TypeError("lti must be BaseLti")

    @property
    def results(self):
        t = self.main_model.ts
        xout = self.main_model.xout
        yout = self.main_model.yout
        return pd.DataFrame({"t": t, "xout": xout, "yout": yout})

    def input(self, t, uv, *args, **kwargs):
        uv = np.array(uv)
        uv = uv.reshape([-1, 1])
        self.uv = limit_signal(uv)
        self.main_model.input(t, uv, *args, **kwargs)
        self.main_model.output()
        self.xv = self.yout[-1]
        self.xv = limit_signal(self.xv)
        return True

    def output(self, *orifice, **kwargs):
        # pada aseSystem pada ada.main_model
        if len(orifice) == 0:
            orifice = self.simple_models
        else:
            orifice = list(orifice)
        for of in orifice:
            of.input(self.xv)
        return self.xv

    def calc_is_finished(self):
        return True


# class ServoOrifice(HybirdOrifice):
#     """
#     """
#
#     def __init__(self, pa, pb, position, l=0.02, d=0.003, w=4.9153e-7, q_leak=0, model=None):
#         """
#         """
#         super().__init__(pa, position, l, d, w, q_leak)
#         self._pa = pa
#         self._pb = pb
#         self._xv = 0
#         self._model = model
#         temp_df = pd.DataFrame(columns=['pa', 'pb'])
#         temp_df.loc[0] = [pa, pb]
#         self._information = pd.concat([self._information, temp_df], axis=1).reindex(self._information.index)
#
#     def input(self, xv=None):
#         """
#         """
#         if xv is None:
#             xv = self._xv
#         if xv > 0:
#             self._pressure = self._pa
#         else:
#             self._pressure = self._pb
#         self._xv = xv
#         return True
#
#     def _add_result(self, model, q, qdp, **kwargs):
#         new_data = pd.DataFrame({'node_p': [model.latest_result[self._add_node.number]], 'pa': [self._pa],
#                                  'pb': [self._pb], 'q': [q / self.f1], 'nq': [q], 'qdp': [qdp]})
#         self._results = pd.concat([self._results, new_data], ignore_index=True)


MOOG_2ND_NATURAL_FREQ_HZ = 166.0
MOOG_2ND_TW = 9.587647174210562e-4
MOOG_2ND_ZETA = 0.7


def moog_servovalve(dt, delay=0, tw=1.5059e-8, zeta=0.0039795, tp3=0.0017924):
    """
    moog servovalve model with optional delay. If delay is zero, returns a standard second-order system. If delay is greater than zero, includes a Pade approximation of the delay in the transfer function.
    """
    if delay == 0:
        kp = 1
        tf0 = cl.tf(kp, [tw**2, 2 * tw * zeta, 1])
        tf1 = cl.tf(kp, [tp3, 1])
        tf2 = cl.series(tf0, tf1)
        ss2 = cl.tf2ss(tf2)
        lti = BaseLti(ss2, dt)
        sv = ServoValve2(lti, [])
        return sv
    else:
        return moog_servovalve_with_delay(dt, delay, tw, zeta, tp3)


def moog_2nd_servovalve(
    dt, delay=0.0, tw=MOOG_2ND_TW, zeta=MOOG_2ND_ZETA
):
    """
    Moog-style servovalve with only the second-order core dynamics.

    The transfer function is
    ``1 / (tw**2 * s**2 + 2 * zeta * tw * s + 1)``.  This omits the legacy
    ``tp3`` first-order pole used by :func:`moog_servovalve`.
    """

    kp = 1
    tf_final = cl.tf(kp, [tw**2, 2 * tw * zeta, 1])
    if delay > 0:
        num_pade, den_pade = cl.pade(delay, n=1)
        tf_delay = cl.tf(num_pade, den_pade)
        tf_final = cl.series(tf_final, tf_delay)
    ss_final = cl.tf2ss(tf_final)
    lti = BaseLti(ss_final, dt)
    sv = ServoValve2(lti, [])
    return sv


def moog_servovalve_with_delay(
    dt, delay=0.0, tw=1.5059e-8, zeta=0.0039795, tp3=0.0017924
):
    """
    moog servovalve model with delay. The delay is approximated using a first-order Pade approximation.
    :param dt: sampling time step
    :param delay: time delay in seconds
    :return: an instance of ServoValve2 representing the delayed servovalve
    """

    kp = 1

    tf0 = cl.tf(kp, [tw**2, 2 * tw * zeta, 1])
    tf1 = cl.tf(1, [tp3, 1])
    if delay > 0:
        num_pade, den_pade = cl.pade(delay, n=1)
        tf_delay = cl.tf(num_pade, den_pade)

        tf_final = cl.series(tf0, tf1, tf_delay)
    else:
        tf_final = cl.series(tf0, tf1)
    ss_final = cl.tf2ss(tf_final)

    lti = BaseLti(ss_final, dt)
    sv = ServoValve2(lti, [])
    return sv


def static_sv(dt):
    """
    Static servovalve model.
    :param dt: sampling time step
    """
    kp = 1
    tf = cl.tf(kp, [1])
    lti = TSDlti(tf, dt)
    sv = ServoValve2(lti, [])
    return sv


def limit_signal(uv: Union[float, np.ndarray], up=1, down=-1):
    """
    Limits the input signal to a specified range.
    :param uv: input signal, can be a float or a numpy array
    :param up: upper limit, default is 1
    :param down: lower limit, default is -1
    :return: limited signal
    """
    return _limit_signal(uv, up=up, down=down)
