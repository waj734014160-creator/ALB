# coding: utf-8
import copy
from typing import Union

# from ALB.infrastructure.logging import logger
import control as cl
import numpy as np

from ALB.core.component import BaseSystem
from ALB.core.lifecycle import LifecycleState, RuntimeLifecycle
from ALB.core.validation import (
    finite_real_scalar,
    finite_real_vector,
    limit_signal as _limit_signal,
)
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

    def _reset_for_owner(self, *args, **kwargs):
        self.main_model._reset_for_owner()

    def input(self, t, uv, *args, **kwargs):
        """Latch one servovalve input without advancing the main model."""

        uv = np.array(uv)
        uv = uv.reshape([uv.size, 1])
        self.uv = uv
        self.main_model.input(t, uv)

    def output(self, *args, **kwargs):
        return self.main_model.output()

    def calc_is_finished(self):
        return True

class ServoValve2(BaseValve):
    """Second-order servovalve with a strict input/evaluate/output lifecycle."""

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
        self._lifecycle = RuntimeLifecycle(type(self).__name__)
        self._last_output = None
        self._lifecycle.reset()

    @property
    def lifecycle_state(self):
        """Return the current strict runtime state."""

        return self._lifecycle.state

    def _reset_for_owner(self, *args, **kwargs):
        """Reset valve dynamics and invalidate any previously readable spool."""

        self.main_model._reset_for_owner(*args, **kwargs)
        self.uv = 0
        self.xv = 0
        self._last_output = None
        self._lifecycle.reset()
        return True

    def input(self, t, uv, *args, **kwargs):
        """Validate and latch one command without advancing valve state."""

        self._lifecycle.require_input_slot()
        time = finite_real_scalar(t, "servovalve time")
        input_count = int(self.main_model.B.shape[1])
        command = finite_real_vector(uv, "servovalve command", input_count)
        limited = np.asarray(limit_signal(command), dtype=float).reshape(-1, 1)
        self.main_model.input(time, limited, *args, **kwargs)
        self.uv = limited.copy()
        self._last_output = None
        self._lifecycle.latch()
        return True

    def evaluate(self):
        """Advance the valve and connected orifices exactly once."""

        with self._lifecycle.evaluation():
            self.main_model.evaluate()
            output_count = int(self.main_model.C.shape[0])
            completed = finite_real_vector(
                self.main_model.output(), "servovalve spool", output_count
            )
            self.xv = np.asarray(limit_signal(completed), dtype=float)
            for orifice in self.simple_models:
                orifice.input(self.xv.copy())
            self._last_output = self.xv.copy()
        return self.output()

    def set_spool(self, value):
        """Publish an explicit direct-spool state without advancing valve dynamics.

        This capability is reserved for ``ALBSV`` direct-input assemblies. It
        still uses the lifecycle publication boundary and updates configured
        orifices exactly once.
        """

        self._lifecycle.require_input_slot()
        output_count = int(self.main_model.C.shape[0])
        spool = finite_real_vector(value, "direct servovalve spool", output_count)
        spool = np.asarray(limit_signal(spool), dtype=float)
        self._lifecycle.latch()
        with self._lifecycle.evaluation():
            self.xv = float(spool[0]) if output_count == 1 else spool.copy()
            for orifice in self.simple_models:
                orifice.input(self.xv)
            self._last_output = spool.copy()
        return self.output()

    def output(self, *orifice, **kwargs):
        """Read the completed spool without evaluating or mutating orifices."""

        del kwargs
        if orifice:
            raise TypeError(
                "output() no longer accepts orifices; configure simple_models before evaluate()"
            )
        self._lifecycle.require_output()
        assert self._last_output is not None
        return self._last_output.copy()

    def calc_is_finished(self):
        return self._lifecycle.state is LifecycleState.READY


# class ArchivedServoRestrictorEquation:
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


def second_order_servovalve(
    dt,
    natural_frequency_hz=MOOG_2ND_NATURAL_FREQ_HZ,
    damping_ratio=MOOG_2ND_ZETA,
    delay=0.0,
):
    """Build a unity-gain second-order servovalve from physical parameters.

    ``natural_frequency_hz`` is converted to the historical time-scale form
    ``tw = 1 / (2*pi*f_n)`` before the validated transfer function is built.
    """

    frequency = float(natural_frequency_hz)
    damping = float(damping_ratio)
    delay_value = float(delay)
    if not np.isfinite(frequency) or frequency <= 0.0:
        raise ValueError("natural_frequency_hz must be finite and > 0")
    if not np.isfinite(damping) or damping <= 0.0:
        raise ValueError("damping_ratio must be finite and > 0")
    if not np.isfinite(delay_value) or delay_value < 0.0:
        raise ValueError("delay must be finite and >= 0")
    tw = 1.0 / (2.0 * np.pi * frequency)
    return moog_2nd_servovalve(
        dt,
        delay=delay_value,
        tw=tw,
        zeta=damping,
    )


def transfer_function_servovalve(dt, numerator, denominator):
    """Build a SISO servovalve from continuous-time polynomial coefficients.

    Coefficients use descending powers of ``s``. The numerator includes the
    complete gain and any rational delay approximation. Static proper systems
    use the discrete wrapper so ``[1] / [1]`` remains exactly equivalent to
    the established static valve behavior.
    """

    num = np.asarray(numerator)
    den = np.asarray(denominator)
    if np.iscomplexobj(num) or np.iscomplexobj(den):
        raise TypeError("servovalve coefficients must be real")
    try:
        num = np.asarray(numerator, dtype=float)
        den = np.asarray(denominator, dtype=float)
    except (TypeError, ValueError) as exc:
        raise TypeError("servovalve coefficients must be real sequences") from exc
    if num.ndim != 1 or num.size == 0:
        raise ValueError("numerator must be a nonempty one-dimensional sequence")
    if den.ndim != 1 or den.size == 0:
        raise ValueError("denominator must be a nonempty one-dimensional sequence")
    if not np.all(np.isfinite(num)) or not np.all(np.isfinite(den)):
        raise ValueError("servovalve coefficients must be finite")
    if num[0] == 0.0 or den[0] == 0.0:
        raise ValueError("leading polynomial coefficients must be nonzero")
    if np.all(num == 0.0):
        raise ValueError("numerator must not be the zero polynomial")
    if num.size > den.size:
        raise ValueError("servovalve transfer function must be proper")

    transfer = cl.tf(num, den)
    lti = TSDlti(transfer, dt) if den.size == 1 else BaseLti(transfer, dt)
    return ServoValve2(lti, [])


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
    ``1 / (tw**2 * s**2 + 2 * zeta * tw * s + 1)``.  This omits the
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
