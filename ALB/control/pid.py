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

class PID(BaseSimpleModel):
    """Proportional-integral-derivative controller with explicit evaluation.

    ``input()`` only latches the next error, ``evaluate()`` updates the PID
    memory once, and ``output()`` reads the completed command without another
    integration or history write.
    """

    def __init__(self, pid_config: PIDConfig, *args, **kwargs):
        """
        PID controller, kd_dim is a non-dimensional argument. t0 = 1 / (2 * np.pi * freq), self.kd_nodim = kd * t0
        :param pid_config: Configuration object for the PID controller.
        """

        super().__init__(*args, **kwargs)

        self.kp = np.array(pid_config.kp)
        self.ki = np.array(pid_config.ki)
        self.freq = pid_config.freq
        t0 = 1 / (2 * np.pi * self.freq)
        self.t0 = t0  # non-dimensional time
        self.kd = np.array(pid_config.kd)
        if np.size(self.kd) != np.size(self.ki) or np.size(self.kd) != np.size(self.kp):
            raise ValueError("The length of kp, ki, kd should be the same")
        if np.size(self.kd) > 1 and np.size(self.kd) != np.size(
            pid_config.sensor_angles
        ):
            raise ValueError(
                "The length of kp, ki, kd should be the same as bias if size > 1"
            )
        self.kd_nodim = self.kd * t0
        self.ki_nodim = self.ki / t0
        self.info = pd.DataFrame(columns=["kp", "ki", "kd", "ki_nodim", "kd_nodim"])
        self.info.loc[0] = [self.kp, self.ki, self.kd, self.ki_nodim, self.kd_nodim]
        self.dt = pid_config.dt
        self.error = None
        self.delta_error = None
        self.inp = None
        self.t = None
        self._results = pd.DataFrame(
            columns=[
                "t",
                "input",
                "output",
                "error",
                "delta_error",
                "kp_calc",
                "ki_calc",
                "kd_calc",
            ]
        )
        self.uf = pid_config.uf
        self.ki_intergral = 0
        self.kp_calc = 0
        self.ki_calc = 0
        self.kd_calc = 0
        self._committed_error = None
        self._last_output = None
        self._lifecycle = RuntimeLifecycle(
            "controller", input_label="controller input"
        )
        self._lifecycle.reset()
        if pid_config.sensor_angles is None:
            self.sensor_angles = np.array([0, 90])
        else:
            if len(pid_config.sensor_angles) != 2:
                raise ValueError("The length of sensor_angels should be 2")
            self.sensor_angles = np.array(pid_config.sensor_angles)
        self.config = pid_config

    def _sensor(self, error):
        """
        Transforms the error based on sensor angles.
        :param error: The error vector [ex, ey].
        :return: The projected error.
        """
        bias = self.sensor_angles / 180 * np.pi
        err = error[0] * np.cos(bias) + error[1] * np.sin(bias)
        return err

    def init(self):
        """
        Initializes the controller, clearing any saved data.
        """
        self._reset_runtime_state()
        self._results = pd.DataFrame(
            columns=[
                "t",
                "input",
                "output",
                "error",
                "delta_error",
                "kp_calc",
                "ki_calc",
                "kd_calc",
            ]
        )
        return True

    def _reset_runtime_state(self):
        """Clear all latched PID inputs, errors, terms, and integral memory."""
        self.error = None
        self.delta_error = None
        self.inp = None
        self.t = None
        self.ki_intergral = 0
        self.kp_calc = 0
        self.ki_calc = 0
        self.kd_calc = 0
        self._committed_error = None
        self._last_output = None
        self._lifecycle.reset()

    def input(self, t, error, *args, **kwargs):
        """
        Provides input to the PID controller.
        :param t: The current time.
        :param error: The error signal.
        """
        self._lifecycle.require_input_slot()
        time = finite_real_scalar(t, "controller time")
        inp = finite_real_vector(error, "controller error", 2)
        projected_error = self._sensor(inp)
        bounded_error = limit_signal(projected_error)
        self.inp = inp
        if self._committed_error is None:
            self.delta_error = np.zeros_like(bounded_error)
        else:
            self.delta_error = bounded_error - self._committed_error
        self.error = bounded_error
        self.t = time
        self._last_output = None
        self._lifecycle.latch()

    def evaluate(self, *args, **kwargs):
        """
        Calculate one PID command from the currently latched input.
        :return: The controller output signal.
        """
        with self._lifecycle.evaluation():
            assert self.error is not None
            output = self.decrete_pid(self.error, self.delta_error)
            output = limit_signal(output)
            self.results.loc[self.results.shape[0]] = [
                self.t,
                self.inp,
                output,
                self.error,
                self.delta_error,
                self.kp_calc,
                self.ki_calc,
                self.kd_calc,
            ]
            self._committed_error = np.asarray(self.error, dtype=float).copy()
            self._last_output = np.asarray(output, dtype=float).copy()
        return self.output()

    def output(self, *args, **kwargs):
        """Read the completed PID command without integrating again."""
        self._lifecycle.require_output()
        assert self._last_output is not None
        return self._last_output.copy()

    @property
    def lifecycle_state(self):
        """Return the current strict runtime state."""

        return self._lifecycle.state

    def decrete_pid(self, error, delta_error):
        """
        Calculates the discrete PID control signal.
        :param error: The current error.
        :param delta_error: The change in error.
        :return: The control signal.
        """
        # Discrete PID controller
        error = np.array(error)
        delta_error = np.array(delta_error)
        self.kp_calc = self.kp * error
        self.ki_calc = self.ki_intergral + self.ki_nodim * error * self.dt
        self.ki_intergral = self.ki_calc
        self.kd_calc = self.kd_nodim * delta_error / self.dt
        u = self.ki_calc + self.kd_calc + self.kp_calc
        return u

    def calc_error(self, *args, **kwargs):
        return 1

    def calc_is_finished(self):
        return True

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        Saves the controller results.
        :param tofile: Whether to save to a file.
        :param path: The directory path.
        :param name: The name of the file.
        :return: A SaveTreeNode object.
        """
        if path is None:
            path = "controller"
        if name is None:
            name = "pid"
        res = {name: self.results, "information": self.info}
        res = DataFrameResult(res)
        node = SaveTreeNode(path, res)
        if tofile:
            return node.persist(kwargs.get("writer"), path)
        return node

__all__ = ["PID"]
