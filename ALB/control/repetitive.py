# -- coding: utf-8 --
from dataclasses import dataclass

import control as cl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.linalg as la
import skfuzzy as fuzz
import skfuzzy.control as ctrl
from control.matlab import c2d, lqe, lqr, ss
from scipy.linalg import block_diag, pinv, schur

from ALB.core.component import BaseSimpleModel
from ALB.core.lifecycle import RuntimeLifecycle
from ALB.config import FuzzyPIDConfig, LQGConfig, PIDConfig
from ALB.core.validation import finite_real_scalar, finite_real_vector, limit_signal
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode
from .valve import moog_servovalve

@dataclass
class RCConfig:
    dt: float
    freq: float
    k_rc: float | list | np.ndarray
    q_filter: float = 0.998
    m_lead: int = 4
    sensor_angles: list = None

class RepetitiveController(BaseSimpleModel):
    """Discrete repetitive controller for periodic disturbance rejection."""

    def __init__(self, rc_config: RCConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dt = rc_config.dt
        self.freq = rc_config.freq
        self.k_rc = np.array(rc_config.k_rc)
        self.q_filter = rc_config.q_filter
        self.m_lead = rc_config.m_lead

        self.N = int(np.round(1.0 / (self.freq * self.dt)))
        if self.N <= 0:
            raise ValueError("N <= 0")

        if rc_config.sensor_angles is None:
            self.sensor_angles = np.array([0, 90])
        else:
            self.sensor_angles = np.array(rc_config.sensor_angles)

        self.dim = np.size(self.k_rc)
        self.u_buffer = np.zeros((self.N, self.dim))
        self.e_buffer = np.zeros((self.N, self.dim))
        self.ptr = 0

        self.error = None
        self.inp = None
        self.t = None
        self._last_output = None
        self._lifecycle = RuntimeLifecycle(type(self).__name__)
        self._lifecycle.reset()

    def init(self):
        self.u_buffer.fill(0)
        self.e_buffer.fill(0)
        self.ptr = 0
        self.error = None
        self.inp = None
        self.t = None
        self._last_output = None
        self._lifecycle.reset()
        return True

    def input(self, t, error, *args, **kwargs):
        """Validate and latch one periodic error sample without mutation."""

        del args, kwargs
        self._lifecycle.require_input_slot()
        self.t = finite_real_scalar(t, "controller time")
        self.inp = finite_real_vector(error, "controller error", self.dim)
        self.error = limit_signal(self.inp)
        self._last_output = None
        self._lifecycle.latch()

    def evaluate(self, *args, **kwargs):
        """Advance the repetitive buffers exactly once for the latched sample."""

        del args, kwargs
        with self._lifecycle.evaluation():
            assert self.error is not None
            u_prev = self.u_buffer[self.ptr]
            lead_ptr = (self.ptr + self.m_lead) % self.N
            e_lead = self.e_buffer[lead_ptr]

            u_curr = self.q_filter * u_prev + self.k_rc * e_lead

            self.u_buffer[self.ptr] = u_curr
            self.e_buffer[self.ptr] = self.error
            self.ptr = (self.ptr + 1) % self.N
            self._last_output = np.asarray(limit_signal(u_curr), dtype=float).copy()
        return self.output()

    def output(self, *args, **kwargs):
        """Read the completed repetitive command without moving its buffers."""

        del args, kwargs
        self._lifecycle.require_output()
        assert self._last_output is not None
        return self._last_output.copy()

    def step(self, t, error):
        """Compose input, evaluation, and output for one local sample."""

        self.input(t, error)
        self.evaluate()
        return self.output()

    @property
    def lifecycle_state(self):
        """Return the current strict runtime state."""

        return self._lifecycle.state

    def calc_error(self, *args, **kwargs):
        pass

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        pass

__all__ = ["RCConfig", "RepetitiveController"]
