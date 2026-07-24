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

from .pid import PID

class FuzzyPID(PID):
    """
    A Fuzzy PID controller that adjusts PID parameters based on fuzzy logic rules.
    """

    def __init__(self, fuzzy_pid_config: FuzzyPIDConfig, *args, **kwargs):
        """
        FuzzyPID controller
        :param fuzzy_pid_config: Configuration object for the Fuzzy PID controller.
        """

        # Helper function to set default ranges
        def set_range(param, default_range):
            """Creates an inclusive range from start, end, and step."""

            def inclusive_range(start, end, step):
                num_elements = (
                    int(abs(end - start) / step) + 1
                )  # Calculate number of elements including end
                return np.linspace(start, end, num_elements)

            return (
                inclusive_range(*param)
                if param is not None
                else inclusive_range(*default_range)
            )

        def check_range(*params):
            """Checks if the range parameters have 3 elements."""
            for param in params:
                if param is not None and len(param) != 3:
                    raise ValueError(
                        f"range should be tuple with 3 elements, (start, stop, step)"
                    )

        pid_config = PIDConfig(
            kp=0,
            ki=0,
            kd=0,
            freq=fuzzy_pid_config.freq,
            sensor_angles=fuzzy_pid_config.sensor_angles,
            dt=fuzzy_pid_config.dt,
        )
        super().__init__(pid_config, *args, **kwargs)
        error_range = fuzzy_pid_config.error_range
        derror_range = fuzzy_pid_config.delta_error_range
        kp_range = fuzzy_pid_config.kp_range
        ki_range = fuzzy_pid_config.ki_range
        kd_range = fuzzy_pid_config.kd_range
        rule_path = fuzzy_pid_config.rule_path
        check_range(error_range, derror_range, kp_range, ki_range, kd_range)
        # Use helper function to simplify initialization
        self.error_range = set_range(error_range, (-1, 1, 0.01))
        self.delta_error_range = set_range(derror_range, (-1, 1, 0.01))
        self.kp_range = set_range(kp_range, (0, 1, 0.01))
        self.ki_range = set_range(ki_range, (0, 1, 0.01))
        self.kd_range = set_range(kd_range, (0, 1, 0.01))
        error_range, derror_range, kp_range, ki_range, kd_range = map(
            lambda x: np.array(
                [
                    min(x),
                    max(x),
                    (max(x) - min(x)) / (len(x) - 1) if len(x) > 1 else 0.01,
                ]
            ),
            [
                self.error_range,
                self.delta_error_range,
                self.kp_range,
                self.ki_range,
                self.kd_range,
            ],
        )
        # Define the fuzzy args
        self.input_fuzzy_define = ["NB", "NM", "ZO", "PM", "PB"]
        self.output_fuzzy_define = ["L", "M", "H"]
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
                "kp",
                "ki",
                "kd",
                "ki_nodim",
                "kd_nodim",
            ]
        )
        # define the membership functions
        self.error_length = kwargs.get("error_length", 0.5)
        if rule_path is None:
            self.rules = default_rules()
        else:
            self.rules = pd.read_csv(rule_path, index_col=0)
        self.pid_sim = self._create_pid_sim()
        self.info = pd.DataFrame(
            columns=[
                "dt",
                "error_range",
                "delta_error_range",
                "kp_range",
                "ki_range",
                "kd_range",
            ]
        )
        self.info.loc[0] = [
            self.dt,
            error_range,
            derror_range,
            kp_range,
            ki_range,
            kd_range,
        ]
        self.config = fuzzy_pid_config

    @staticmethod
    def _assign_gaussmf(arg, define, means, sigma):
        """Assigns Gaussian membership functions to a fuzzy variable."""
        for i, mean in enumerate(means):
            arg[define[i]] = fuzz.gaussmf(arg.universe, mean, sigma)

    def _create_pid_sim(self):
        """Creates the fuzzy control system simulation."""
        # create the fuzzy args
        error = ctrl.Antecedent(np.sort(self.error_range), "error")
        delta_error = ctrl.Antecedent(np.sort(self.delta_error_range), "delta_error")

        error_means = np.linspace(min(self.error_range), max(self.error_range), 5)
        delta_error_means = np.linspace(
            min(self.delta_error_range), max(self.delta_error_range), 5
        )
        error_length, delta_error_length = map(
            lambda x: (np.max(x) - np.min(x)) / 12,
            [self.error_range, self.delta_error_range],
        )
        self._assign_gaussmf(error, self.input_fuzzy_define, error_means, error_length)
        self._assign_gaussmf(
            delta_error, self.input_fuzzy_define, delta_error_means, delta_error_length
        )

        output_specs = {
            "kp": (self.kp_range, 2),
            "ki": (self.ki_range, 3),
            "kd": (self.kd_range, 4),
        }
        self._fixed_fuzzy_outputs = {}
        self._variable_fuzzy_outputs = {}
        for name, (values, _) in output_specs.items():
            minimum = float(np.min(values))
            maximum = float(np.max(values))
            if minimum == maximum:
                self._fixed_fuzzy_outputs[name] = minimum
                continue
            consequent = ctrl.Consequent(np.sort(values), name)
            means = np.linspace(minimum, maximum, 3)
            self._assign_gaussmf(
                consequent,
                self.output_fuzzy_define,
                means,
                (maximum - minimum) / 6,
            )
            self._variable_fuzzy_outputs[name] = consequent

        if not self._variable_fuzzy_outputs:
            return None
        rules = [
            ctrl.rule.Rule(
                error[rule[0]] & delta_error[rule[1]],
                tuple(
                    consequent[rule[output_specs[name][1]]]
                    for name, consequent in self._variable_fuzzy_outputs.items()
                ),
            )
            for rule in self.rules.values
        ]
        pid_ctrl = ctrl.ControlSystem(rules)
        pid_sim = ctrl.ControlSystemSimulation(pid_ctrl)
        return pid_sim

    def _reset_for_owner(self):
        """Reset fuzzy inference, gains, PID memory, and result history."""
        self._reset_runtime_state()
        self.kp = np.asarray(0.0)
        self.ki = np.asarray(0.0)
        self.kd = np.asarray(0.0)
        self.ki_nodim = np.asarray(0.0)
        self.kd_nodim = np.asarray(0.0)
        if self.pid_sim is not None:
            self.pid_sim.reset()
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
                "kp",
                "ki",
                "kd",
                "ki_nodim",
                "kd_nodim",
            ]
        )
        return True

    def evaluate(self, *args, **kwargs):
        """
        Calculate one Fuzzy PID command from the currently latched input.
        :return: The controller output signal.
        """
        with self._lifecycle.evaluation():
            assert self.error is not None
            self.fuzzy_pid(self.error, self.delta_error)
            output = self.decrete_pid(self.error, self.delta_error)
            self.results.loc[self.results.shape[0]] = [
                self.t,
                self.inp,
                output,
                self.error,
                self.delta_error,
                self.kp_calc,
                self.ki_calc,
                self.kd_calc,
                self.kp,
                self.ki,
                self.kd,
                self.ki_nodim,
                self.kd_nodim,
            ]
            self._committed_error = np.asarray(self.error, dtype=float).copy()
            self._last_output = np.asarray(output, dtype=float).copy()
        return self.output()

    def fuzzy_pid(self, error, delta_error):
        """
        Calculates PID parameters using the fuzzy logic system.
        :param error: The current error.
        :param delta_error: The change in error.
        """
        gains = {
            name: np.full_like(error, self._fixed_fuzzy_outputs.get(name, 0.0))
            for name in ("kp", "ki", "kd")
        }
        for i, (err, delta_err) in enumerate(zip(error, delta_error)):
            if self.pid_sim is not None:
                self.pid_sim.input["error"] = err
                # notice: input of delta_error should be non-dimensional
                self.pid_sim.input["delta_error"] = delta_err / (self.dt / self.t0)
                self.pid_sim.compute()
                for name in self._variable_fuzzy_outputs:
                    gains[name][i] = self.pid_sim.output[name]
        kp, ki, kd = (gains[name] for name in ("kp", "ki", "kd"))
        kp, ki, kd = map(lambda x: np.nan_to_num(x), [kp, ki, kd])
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.ki_nodim = ki / self.t0
        self.kd_nodim = kd * self.t0

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        Saves the controller results.
        :param tofile: Whether to save to a file.
        :param path: The directory path.
        :param name: The name of the file.
        :return: A SaveTreeNode object.
        """
        if name is None:
            name = "fuzzy_pid"
        return super().save(tofile, path, name, *args, **kwargs)

def default_rules():
    """
    Provides a default set of fuzzy rules for the PID controller.
    :return: A pandas DataFrame containing the default fuzzy rules.
    """
    rules = pd.DataFrame(columns=["error", "delta_error", "kp", "ki", "kd"])
    rules.loc[0] = ["NB", "NB", "H", "L", "H"]
    rules.loc[1] = ["NB", "NM", "H", "L", "H"]
    rules.loc[2] = ["NB", "ZO", "H", "L", "L"]
    rules.loc[3] = ["NB", "PM", "H", "L", "H"]
    rules.loc[4] = ["NB", "PB", "H", "L", "H"]
    rules.loc[5] = ["NM", "NB", "M", "L", "H"]
    rules.loc[6] = ["NM", "NM", "M", "L", "H"]
    rules.loc[7] = ["NM", "ZO", "M", "L", "L"]
    rules.loc[8] = ["NM", "PM", "M", "L", "H"]
    rules.loc[9] = ["NM", "PB", "M", "L", "H"]
    rules.loc[10] = ["ZO", "NB", "L", "M", "H"]
    rules.loc[11] = ["ZO", "NM", "L", "M", "M"]
    rules.loc[12] = ["ZO", "ZO", "L", "M", "L"]
    rules.loc[13] = ["ZO", "PM", "L", "M", "M"]
    rules.loc[14] = ["ZO", "PB", "L", "M", "H"]
    rules.loc[15] = ["PM", "NB", "M", "L", "H"]
    rules.loc[16] = ["PM", "NM", "M", "L", "H"]
    rules.loc[17] = ["PM", "ZO", "M", "L", "L"]
    rules.loc[18] = ["PM", "PM", "M", "L", "H"]
    rules.loc[19] = ["PM", "PB", "M", "L", "H"]
    rules.loc[20] = ["PB", "NB", "H", "L", "H"]
    rules.loc[21] = ["PB", "NM", "H", "L", "H"]
    rules.loc[22] = ["PB", "ZO", "H", "L", "L"]
    rules.loc[23] = ["PB", "PM", "H", "L", "H"]
    rules.loc[24] = ["PB", "PB", "H", "L", "H"]
    return rules

__all__ = ["FuzzyPID", "default_rules"]
