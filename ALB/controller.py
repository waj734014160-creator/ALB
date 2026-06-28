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

from ALB.base import BaseSimpleModel
from ALB.config import FuzzyPIDConfig, PIDConfig
from ALB.results import DataFrameResult, SaveTreeNode
from ALB.servovalve import limit_signal, moog_servovalve


class PID(BaseSimpleModel):
    """
    A Proportional-Integral-Derivative (PID) controller.
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

    def input(self, t, error, *args, **kwargs):
        """
        Provides input to the PID controller.
        :param t: The current time.
        :param error: The error signal.
        """
        error = np.array(error).reshape(-1)
        self.inp = error
        error = self._sensor(error)
        if self.error is None:
            self.delta_error = np.zeros_like(error)
        else:
            self.delta_error = error - self.error
        self.error = limit_signal(error)
        self.t = t

    def output(self, *args, **kwargs):
        """
        Calculates the PID controller output.
        :return: The controller output signal.
        """
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
        return output

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
            node.save_to_file()
        return node


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
        Kp = ctrl.Consequent(np.sort(self.kp_range), "kp")
        Ki = ctrl.Consequent(np.sort(self.ki_range), "ki")
        Kd = ctrl.Consequent(np.sort(self.kd_range), "kd")

        error_means = np.linspace(min(self.error_range), max(self.error_range), 5)
        delta_error_means = np.linspace(
            min(self.delta_error_range), max(self.delta_error_range), 5
        )
        kp_means = np.linspace(self.kp_range[0], self.kp_range[-1], 3)
        ki_means = np.linspace(self.ki_range[0], self.ki_range[-1], 3)
        kd_means = np.linspace(self.kd_range[0], self.kd_range[-1], 3)
        error_length, delta_error_length = map(
            lambda x: (np.max(x) - np.min(x)) / 12,
            [self.error_range, self.delta_error_range],
        )
        kp_length, ki_length, kd_length = map(
            lambda x: (np.max(x) - np.min(x)) / 6,
            [self.kp_range, self.ki_range, self.kd_range],
        )
        self._assign_gaussmf(error, self.input_fuzzy_define, error_means, error_length)
        self._assign_gaussmf(
            delta_error, self.input_fuzzy_define, delta_error_means, delta_error_length
        )
        self._assign_gaussmf(Kp, self.output_fuzzy_define, kp_means, kp_length)
        self._assign_gaussmf(Ki, self.output_fuzzy_define, ki_means, ki_length)
        self._assign_gaussmf(Kd, self.output_fuzzy_define, kd_means, kd_length)

        rules = [
            ctrl.rule.Rule(
                error[rule[0]] & delta_error[rule[1]],
                (Kp[rule[2]], Ki[rule[3]], Kd[rule[4]]),
            )
            for rule in self.rules.values
        ]
        pid_ctrl = ctrl.ControlSystem(rules)
        pid_sim = ctrl.ControlSystemSimulation(pid_ctrl)
        return pid_sim

    def init(self):
        """
        Initializes the Fuzzy PID controller.
        TODO: Rewrite the initialization function.
        """
        return True

    def output(self, *args, **kwargs):
        """
        Calculates the Fuzzy PID controller output.
        :return: The controller output signal.
        """
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
        return output

    def fuzzy_pid(self, error, delta_error):
        """
        Calculates PID parameters using the fuzzy logic system.
        :param error: The current error.
        :param delta_error: The change in error.
        """
        kp = np.zeros_like(error)
        ki = np.zeros_like(error)
        kd = np.zeros_like(error)
        for i, (err, delta_err) in enumerate(zip(error, delta_error)):
            self.pid_sim.input["error"] = err
            # notice: input of delta_error should be non-dimensional
            self.pid_sim.input["delta_error"] = delta_err / (self.dt / self.t0)
            self.pid_sim.compute()
            kp[i] = self.pid_sim.output["kp"]
            ki[i] = self.pid_sim.output["ki"]
            kd[i] = self.pid_sim.output["kd"]
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


class BearingContent:
    __slots__ = ("valve", "K", "C", "dxv", "act_node", "sensor_node")

    def __init__(self, valve, K, C, dxv, act_node, sensor_node):
        self.valve = valve
        self.K = np.array(K).reshape(2, 2)
        self.C = np.array(C).reshape(2, 2)
        self.dxv = np.array(dxv).reshape(2)
        self.act_node = act_node
        self.sensor_node = sensor_node


class ALBLQGController(BaseSimpleModel):
    """
    LQG controller for active lubrication bearing systems.

    This class builds the coupled rotor-valve plant, designs an LQG controller
    (optionally with an ESO disturbance branch), and supports model reduction
    for both plant and controller stages.
    """

    # Public API.

    def __init__(self, rotor, dt, freq=50.0, eso_enable=True):
        super().__init__()
        # Core simulation settings.
        self.rotor = rotor
        self.dt = dt
        self.freq = freq
        self.omega = 2 * np.pi * freq
        self.eso_enable = eso_enable

        # User-defined bearing and disturbance configuration.
        self.bearings: list[BearingContent] = []
        self.unbalance_nodes: list[int] = []

        # Built plant/controller models.
        self.A_nom = None
        self.B_nom = None
        self.C_nom = None
        self.B_d = None
        self.ctrl_sys_full_c = None
        self.active_ctrl_sys_d = None

        # Build flag for runtime use.
        self.is_built = False

    # Configuration helpers.

    def add_bearing(self, valve, K, C, dxv, act_node, sensor_node):
        """Register one active bearing channel with valve and local dynamics."""
        self.bearings.append(BearingContent(valve, K, C, dxv, act_node, sensor_node))
        return self

    def add_unbalance_node(self, node):
        """Register a rotor node used as disturbance input in the plant model."""
        self.unbalance_nodes.append(node)
        return self

    # Internal helpers.

    def _effective_unbalance_nodes(self):
        """
        Return effective disturbance nodes for ESO modeling.

        If ESO is enabled and no disturbance nodes are specified, actuator nodes
        are inferred as disturbance input locations.
        """
        nodes = list(self.unbalance_nodes)
        if self.eso_enable and not nodes:
            for b in self.bearings:
                if b.act_node not in nodes:
                    nodes.append(b.act_node)
        return nodes

    def get_dimensions(self, rotor_order=None, verbose=True):
        """
        Compute key state-space dimensions before building the plant.

        Useful for sizing LQR/LQE weighting matrices.
        """
        lti_r = self.rotor._rotor._lti(self.freq)
        n_rotor = rotor_order if rotor_order is not None else lti_r.A.shape[0]

        n_valve = 0
        for b in self.bearings:
            Av_s = b.valve.main_model.A
            n_valve += Av_s.shape[0] * 2  # One valve model per x/y channel.

        n_inputs = len(self.bearings) * 2  # x/y actuator command channels.
        n_outputs = len(self.bearings) * 2  # x/y displacement sensor channels.

        n_nom_states = n_rotor + n_valve

        eff_nodes = self._effective_unbalance_nodes()
        # Each disturbance node contributes a 2-state sinusoidal exosystem.
        n_dist = len(eff_nodes) * 4 if self.eso_enable else 0
        n_aug_states = n_nom_states + n_dist

        dims = {
            "n_rotor": n_rotor,
            "n_valve": n_valve,
            "n_inputs": n_inputs,
            "n_outputs": n_outputs,
            "n_nom_states": n_nom_states,
            "n_aug_states": n_aug_states,
            "n_dist": n_dist,
        }

        if verbose:
            print("--- System Dimension Summary ------------------------")
            print(f"  Rotor states (reduced)      : {n_rotor}")
            print(f"  Servo-valve total states    : {n_valve}")
            print(f"  Nominal states n_nom        : {n_nom_states}")
            print(f"  Disturbance states n_dist   : {n_dist}")
            print(f"  Augmented states n_aug      : {n_aug_states}")
            print(f"  LQR  Q : [{n_nom_states} x {n_nom_states}]")
            print(f"  LQR  R : [{n_inputs} x {n_inputs}]")
            print(f"  KF   Qn: [{n_aug_states} x {n_aug_states}]")
            print(f"  KF   Rn: [{n_outputs} x {n_outputs}]")
            print("-----------------------------------------------------")

        return dims

    def get_built_dimensions(self):
        """
        Return dimensions after plant assembly/reduction.

        Includes both physical-state dimensions and reduced model dimensions.
        """
        if not getattr(self, "is_plant_built", False):
            raise RuntimeError(
                "Please call build_plant() before requesting built dimensions."
            )

        # Reduced model dimensions used by controller design.
        n_nom_states_red = self.A_nom.shape[0]
        n_inputs = self.B_nom.shape[1]
        n_outputs = self.C_nom.shape[0]

        n_dist = (
            self.B_d.shape[1] * 2 if (self.eso_enable and self.B_d.shape[1] > 0) else 0
        )
        n_aug_states_red = n_nom_states_red + n_dist

        # Physical rotor state count before any model reduction.
        n_rotor_phys = self._Ar_full.shape[0]

        n_valve = 0
        for b in self.bearings:
            n_valve += b.valve.main_model.A.shape[0] * 2

        n_nom_states_phys = n_rotor_phys + n_valve
        n_aug_states_phys = n_nom_states_phys + n_dist

        return {
            # Physical model dimensions.
            "n_nom_states_phys": n_nom_states_phys,
            "n_aug_states_phys": n_aug_states_phys,
            "n_rotor_phys": n_rotor_phys,
            "n_valve": n_valve,
            # Reduced model dimensions.
            "n_nom_states_red": n_nom_states_red,
            "n_aug_states_red": n_aug_states_red,
            # Input/output channel counts.
            "n_inputs": n_inputs,
            "n_outputs": n_outputs,
            "n_dist": n_dist,
        }

    # Plant modeling.

    def build_plant(self, rotor_reduce_func=None, rotor_reduce_kwargs=None):
        """
        Build the coupled plant model used for controller synthesis.

        Optionally applies rotor model reduction before valve coupling.
        """
        rotor_reduce_kwargs = rotor_reduce_kwargs or {}
        print("=== Stage 1: Build Coupled Plant ===")
        print(
            f"  Rotor reduction strategy: {rotor_reduce_func.__name__ if rotor_reduce_func else 'full-order'}"
        )

        # Auto-infer disturbance nodes from actuator nodes when ESO is enabled.
        if self.eso_enable and not self.unbalance_nodes:
            print(
                "  [auto-infer] treat bearing actuation nodes as disturbance input nodes"
            )
            for b in self.bearings:
                if b.act_node not in self.unbalance_nodes:
                    self.unbalance_nodes.append(b.act_node)

        # Assemble rotor-only open-loop model.
        sys_rotor_full = self.assemble_open_loop()

        # Apply optional rotor reduction.
        if rotor_reduce_func is not None:
            result = rotor_reduce_func(sys_rotor_full, **rotor_reduce_kwargs)
            if isinstance(result, tuple):
                sys_rotor_use, self.rotor_reduce_info = result
            else:
                sys_rotor_use, self.rotor_reduce_info = result, None
            print(
                f"  Rotor reduction complete: {sys_rotor_full.A.shape[0]} -> {sys_rotor_use.A.shape[0]} states"
            )
        else:
            sys_rotor_use = sys_rotor_full
            self.rotor_reduce_info = None

        # Couple bearings/valves and finalize nominal plant matrices.
        self._couple_bearings(sys_rotor_use)
        self.is_plant_built = True
        return self

    # Controller design flow.

    def design_controller(
        self,
        Q_phys,
        R,
        Qn_phys,
        Rn,
        ctrl_reduce_func=None,
        ctrl_reduce_kwargs=None,
        plot_bode=False,
    ):
        """
        Design LQG/ESO controller and optionally reduce/discretize it.
        """
        if not getattr(self, "is_plant_built", False):
            raise RuntimeError(
                "Please call build_plant() before designing the controller."
            )

        ctrl_reduce_kwargs = ctrl_reduce_kwargs or {}
        print("=== Stage 2: Controller Design and Reduction ===")
        print(
            f"  Controller reduction strategy: {ctrl_reduce_func.__name__ if ctrl_reduce_func else 'full-order'}"
        )

        # Project physical weighting matrices into the active model basis.
        self.Q, self.Qn = self._project_weights(Q_phys, Qn_phys)
        self.R = R
        self.Rn = Rn

        # Build continuous controller, then reduce/discretize for runtime.
        self._design_controller()
        self.apply_reduction_and_discretize(
            reduce_func=ctrl_reduce_func,
            reduce_kwargs=ctrl_reduce_kwargs,
            plot_bode=plot_bode,
        )
        self.is_built = True

        print("== Build complete ==\n")
        return self

    # Plant assembly helpers.

    def assemble_open_loop(self):
        """
        Assemble open-loop rotor model with actuator/sensor/disturbance ports.

        Returns a continuous-time state-space system.
        """
        from ALB.rotor import location_mapping_matrix

        self.ndof = self.rotor._rotor.ndof
        lti_r = self.rotor._rotor._lti(self.freq)
        self._Ar_full, self._Br_full = lti_r.A, lti_r.B

        Ar, Br = self._Ar_full, self._Br_full
        B_all_list = []
        C_disp_act_list, C_vel_act_list, C_sen_list = [], [], []

        for b in self.bearings:
            act_loc = [[b.act_node, "x"], [b.act_node, "y"]]
            sen_loc = [[b.sensor_node, "x"], [b.sensor_node, "y"]]

            T_act = location_mapping_matrix(self.ndof, act_loc)
            B_all_list.append(Br @ T_act)

            H_sen_disp = location_mapping_matrix(self.ndof * 2, sen_loc).T
            H_act_disp = location_mapping_matrix(self.ndof * 2, act_loc).T
            H_act_vel = np.roll(H_act_disp, self.ndof, axis=1)

            C_disp_act_list.append(H_act_disp)
            C_vel_act_list.append(H_act_vel)
            C_sen_list.append(H_sen_disp)

        for node in self.unbalance_nodes:
            loc = [[node, "x"], [node, "y"]]
            T_d = location_mapping_matrix(self.ndof, loc)
            B_all_list.append(Br @ T_d)

        B_all = np.hstack(B_all_list) if B_all_list else np.zeros((Ar.shape[0], 0))
        C_all = (
            np.vstack(C_disp_act_list + C_vel_act_list + C_sen_list)
            if self.bearings
            else np.zeros((0, Ar.shape[1]))
        )

        D_all = np.zeros((C_all.shape[0], B_all.shape[1]))
        return ss(Ar, B_all, C_all, D_all)

    # Coupling between rotor dynamics and valve subsystems.

    def _couple_bearings(self, sys_rotor):
        """Build nominal coupled matrices from rotor and bearing valve models."""
        Arr = np.array(sys_rotor.A)
        Brr = np.array(sys_rotor.B)
        Crr = np.array(sys_rotor.C)

        Nb = len(self.bearings)
        Ar_closed = Arr.copy()

        A_rv_list, Av_list, Bv_list, Cv_list = [], [], [], []
        H_sensor_list = []

        for i, b in enumerate(self.bearings):
            # Per-bearing actuator/sensor channel slices.
            B_act_i = Brr[:, 2 * i : 2 * i + 2]
            C_disp_i = Crr[2 * i : 2 * i + 2, :]
            C_vel_i = Crr[2 * Nb + 2 * i : 2 * Nb + 2 * i + 2, :]
            C_sen_i = Crr[4 * Nb + 2 * i : 4 * Nb + 2 * i + 2, :]

            # Closed-loop structural stiffness/damping feedback.
            Ar_closed -= B_act_i @ b.K @ C_disp_i + B_act_i @ b.C @ C_vel_i

            # Local valve state-space matrices.
            Av_s = b.valve.main_model.A
            Bv_s = b.valve.main_model.B
            Cv_s = b.valve.main_model.C

            Av_list.append(block_diag(Av_s, Av_s))
            Bv_list.append(block_diag(Bv_s, Bv_s))
            Cv_list.append(block_diag(Cv_s, Cv_s))

            A_rv_list.append(B_act_i @ np.diag(b.dxv) @ block_diag(Cv_s, Cv_s))
            H_sensor_list.append(C_sen_i)

        Av_global = block_diag(*Av_list)
        Bv_global = block_diag(*Bv_list)
        A_rv_global = np.hstack(A_rv_list)

        nr = Ar_closed.shape[0]
        nv = Av_global.shape[0]

        self.A_nom = np.block(
            [[Ar_closed, A_rv_global], [np.zeros((nv, nr)), Av_global]]
        )
        self.B_nom = np.block([[np.zeros((nr, Bv_global.shape[1]))], [Bv_global]])
        n_sensor_rows = sum(h.shape[0] for h in H_sensor_list)
        self.C_nom = np.block(
            [[np.vstack(H_sensor_list), np.zeros((n_sensor_rows, nv))]]
        )

        # Disturbance input matrix (for ESO branch), if configured.
        if self.unbalance_nodes:
            B_d_rotor = Brr[:, 2 * Nb : 2 * Nb + 2 * len(self.unbalance_nodes)]
            self.B_d = np.block([[B_d_rotor], [np.zeros((nv, B_d_rotor.shape[1]))]])
        else:
            self.B_d = np.zeros((self.A_nom.shape[0], 0))

    # Core controller synthesis.

    def _design_controller(self):
        """Design continuous-time controller matrices for the configured branch."""
        alpha_shift = 1e-5
        A_design = self.A_nom - alpha_shift * np.eye(self.A_nom.shape[0])

        K_lqr, _, _ = lqr(A_design, self.B_nom, self.Q, self.R)
        self.K_lqr = K_lqr

        if self.eso_enable and self.B_d.shape[1] > 0:
            Ak, Bk, Ck, Dk = self._design_eso_branch(alpha_shift)
        else:
            Ak, Bk, Ck, Dk = self._design_standard_branch(A_design)

        self.ctrl_sys_full_c = ss(Ak, Bk, Ck, Dk)

    def _design_eso_branch(self, alpha_shift):
        """Build augmented ESO branch and corresponding observer feedback."""
        print("  [ESO] enable disturbance-augmented observer")
        n_dist_channels = self.B_d.shape[1]

        # 2-state sinusoidal disturbance model for each disturbance channel.
        Ad_block = np.array([[0, self.omega], [-self.omega, 0]])
        A_dist = block_diag(*[Ad_block for _ in range(n_dist_channels)])

        Cd_block = np.array([[1, 0]])
        C_dist = block_diag(*[Cd_block for _ in range(n_dist_channels)])

        # Augmented model dimensions.
        n_nom = self.A_nom.shape[0]
        n_d = A_dist.shape[0]

        A_aug = np.block(
            [[self.A_nom, self.B_d @ C_dist], [np.zeros((n_d, n_nom)), A_dist]]
        )
        B_aug = np.block([[self.B_nom], [np.zeros((n_d, self.B_nom.shape[1]))]])
        C_aug = np.block([[self.C_nom, np.zeros((self.C_nom.shape[0], n_d))]])

        A_aug_design = A_aug - alpha_shift * np.eye(A_aug.shape[0])
        G_aug = np.eye(A_aug.shape[0])
        L_kf, _, _ = lqe(A_aug_design, G_aug, C_aug, self.Qn, self.Rn)

        # Disturbance estimate feedback projected to actuator space.
        self.K_dob = pinv(self.B_nom) @ (self.B_d @ C_dist)
        K_aug = np.hstack([self.K_lqr, self.K_dob])

        Ak = A_aug - B_aug @ K_aug - L_kf @ C_aug
        Bk = L_kf
        Ck = -K_aug
        Dk = np.zeros((Ck.shape[0], Bk.shape[1]))  # (n_output n_input)

        return Ak, Bk, Ck, Dk

    def _design_standard_branch(self, A_design):
        """Build standard LQG branch without disturbance-state augmentation."""
        print("  [LQG] use standard full-order observer")
        G = np.eye(self.A_nom.shape[0])
        L_kf, _, _ = lqe(A_design, G, self.C_nom, self.Qn, self.Rn)

        Ak = self.A_nom - self.B_nom @ self.K_lqr - L_kf @ self.C_nom
        Bk = L_kf
        Ck = -self.K_lqr
        Dk = np.zeros((self.B_nom.shape[1], self.C_nom.shape[0]))

        return Ak, Bk, Ck, Dk

    def _project_weights(self, Q_phys, Qn_phys):
        """
        Project physical-domain weighting matrices to the active model basis.

        Parameters
        ----
        Q_phys : ndarray
            State weighting in the physical model basis.
        Qn_phys : ndarray
            Process-noise weighting in the physical/augmented basis.

        Returns
        ----
        Q_red, Qn_red : tuple(ndarray, ndarray)
            Weighting matrices mapped to the currently active model basis.
        """
        # Total valve states (x/y channels included).
        n_valve = 0
        for b in self.bearings:
            n_valve += b.valve.main_model.A.shape[0] * 2

        n_dist = (
            self.B_d.shape[1] * 2 if (self.eso_enable and self.B_d.shape[1] > 0) else 0
        )

        # If no rotor reduction is used, weights are already in the active basis.
        if not hasattr(self, "rotor_reduce_info") or self.rotor_reduce_info is None:
            # Direct pass-through.
            return Q_phys, Qn_phys

        # Reduction projection matrices.
        W_rotor = self.rotor_reduce_info.get("W")
        V_rotor = self.rotor_reduce_info.get("V")

        if W_rotor is None or V_rotor is None:
            raise ValueError(
                "The rotor reduction function did not return projection matrices W and V, so physical-weight mapping cannot be performed."
            )

        # Valve states are not reduced.
        # Compose projection from physical nominal states to reduced nominal states.
        I_valve = np.eye(n_valve) if n_valve > 0 else np.empty((0, 0))
        V_nom = block_diag(V_rotor, I_valve)

        # Disturbance states are also not reduced.
        I_dist = np.eye(n_dist) if n_dist > 0 else np.empty((0, 0))
        W_aug = block_diag(W_rotor, I_valve, I_dist)

        # Similarity transform for LQR state weighting.
        # Keep dimensions consistent with the reduced nominal model.
        Q_red = V_nom.T @ Q_phys @ V_nom

        # Similarity transform for Kalman process-noise weighting.
        Qn_red = W_aug @ Qn_phys @ W_aug.T

        return Q_red, Qn_red

    # Controller reduction and discretization.

    def apply_reduction_and_discretize(
        self, reduce_func=None, reduce_kwargs=None, plot_bode=False
    ):
        """
        Reduce the continuous controller (optional) and discretize it.

        Parameters
        ----
        reduce_func : callable | None
            Optional reduction function applied to the continuous controller.
        reduce_kwargs : dict
            Extra keyword arguments forwarded to reduce_func.
        plot_bode : bool
            Plot Bode comparison between full and reduced controllers.
        """
        reduce_kwargs = reduce_kwargs or {}

        if reduce_func is not None:
            result = reduce_func(self.ctrl_sys_full_c, **reduce_kwargs)
            if isinstance(result, tuple):
                sys_c, self.ctrl_reduce_info = result
            else:
                sys_c, self.ctrl_reduce_info = result, None
            print(
                f"  Controller reduction: {self.ctrl_sys_full_c.A.shape[0]} -> {sys_c.A.shape[0]} states"
                f"  ({reduce_func.__name__})"
            )

            if plot_bode:
                self._plot_bode_comparison(
                    self.ctrl_sys_full_c,
                    sys_c,
                    title_suffix=f"({reduce_func.__name__})",
                )
        else:
            sys_c = self.ctrl_sys_full_c
            self.ctrl_reduce_info = None
            print("  Controller kept at full order")

        # Runtime controller uses a bilinear (Tustin) discretization.
        self.active_ctrl_sys_d = c2d(sys_c, self.dt, method="tustin")
        self._init_runtime_state()

    def _plot_bode_comparison(self, sys_full, sys_red, title_suffix=""):
        """Plot Bode magnitude/phase comparison for full vs reduced controller."""
        n_red = sys_red.A.shape[0]
        plt.figure(figsize=(10, 7))
        cl.bode_plot(
            [sys_full, sys_red],
            dB=True,
            Hz=True,
            label=["Full", f"Reduced (n={n_red})"],
        )
        plt.legend()
        plt.suptitle(f"Controller Bode Comparison {title_suffix}")
        plt.tight_layout()
        plt.show()

    # Runtime state update.

    def _init_runtime_state(self):
        """Initialize observer/controller runtime states and history buffers."""
        n = self.active_ctrl_sys_d.A.shape[0]
        self.t_prev = -1.0
        self.x_hat = np.zeros((n, 1))
        self.x_next = np.zeros((n, 1))
        self.y_current = np.zeros((self.active_ctrl_sys_d.B.shape[1], 1))
        self.u_current = np.zeros((self.active_ctrl_sys_d.C.shape[0], 1))
        # Logged per control step for analysis/debug.
        self._history = {"t": [], "y": [], "u": [], "x_hat": []}

    def init(self):
        """Reset runtime state for a new simulation run."""
        self._init_runtime_state()

    def input(self, t, y_disp):
        """Update measured displacement input for the current time step."""
        self.y_current = np.array(y_disp).reshape(-1, 1)
        if t > self.t_prev:
            self.x_hat = self.x_next
            self.t_prev = t

    def output(self):
        """Compute control output and propagate observer state one step ahead."""
        Ad = self.active_ctrl_sys_d.A
        Bd = self.active_ctrl_sys_d.B
        Cd = self.active_ctrl_sys_d.C
        Dd = self.active_ctrl_sys_d.D

        # Static output equation.
        self.u_current = Cd @ self.x_hat + Dd @ self.y_current

        # Save history after time has started advancing.
        if self.t_prev >= 0:  # Skip initial pre-step state.
            self._history["t"].append(self.t_prev)
            self._history["y"].append(self.y_current.flatten())
            self._history["u"].append(self.u_current.flatten())
            self._history["x_hat"].append(self.x_hat.flatten())

        # State update equation.
        self.x_next = Ad @ self.x_hat + Bd @ self.y_current

        return self.u_current.flatten()

    def get_history(self, to_dataframe=True):
        """
        Return runtime history as either raw arrays or a DataFrame.

        Parameters
        ----
        to_dataframe : bool
            If True, return a flattened pandas DataFrame.
        """
        res = {
            "t": np.array(self._history["t"]),
            "y": np.array(self._history["y"]),
            "u": np.array(self._history["u"]),
            "x_hat": np.array(self._history["x_hat"]),
        }

        if to_dataframe:
            import pandas as pd

            # Flatten vector channels into scalar DataFrame columns.
            df = pd.DataFrame({"t": res["t"]})
            for i in range(res["y"].shape[1]):
                df[f"y_{i}"] = res["y"][:, i]
            for i in range(res["u"].shape[1]):
                df[f"u_{i}"] = res["u"][:, i]
            for i in range(res["x_hat"].shape[1]):
                df[f"x_hat_{i}"] = res["x_hat"][:, i]
            return df

        return res

    def calc_error(self, *args, **kwargs):
        return 0

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        pass

    # Analysis helpers.
    def print_open_loop_modes(self):
        """Print modal information of the nominal open-loop plant matrix."""
        if self.A_nom is None:
            raise RuntimeError(
                "Please call build_plant() before printing open-loop modes."
            )
        modes, _ = compute_modal_info(self.A_nom)
        print_modal_table(
            [
                {
                    "freq_hz": m["freq_hz"],
                    "freq_rad": m["freq_rad"],
                    "damping": m["damping"],
                    "is_oscillatory": m["is_oscillatory"],
                }
                for m in modes
            ],
            title="Nominal open-loop system (A_nom) modes",
        )

    def summary(self):
        """Print a compact summary of the built controller configuration."""
        if not self.is_built:
            print("Controller is not built yet; please call build() first.")
            return
        n_full = self.ctrl_sys_full_c.A.shape[0]
        n_disc = self.active_ctrl_sys_d.A.shape[0]
        print("\n==== ALBLQGController Summary ====")
        print(f"Bearings              : {len(self.bearings)}")
        print(f"ESO enabled           : {self.eso_enable}")
        print(f"Nominal plant order   : {self.A_nom.shape[0]}")
        print(f"Full controller order : {n_full}")
        print(f"Discrete order        : {n_disc}")
        print(f"Sampling time         : {self.dt:g}")
        print(f"Operating frequency   : {self.freq:g} Hz")
        print("==================================\n")

    def plot_rotor_reduction(self, reduce_func, reduce_kwargs=None, channel=(0, 0)):
        """
        Compare full-order and reduced-order rotor open-loop responses.

        Parameters
        ----
        reduce_func : callable
            Reduction function to apply on the open-loop rotor model.
        reduce_kwargs : dict, optional
            Extra keyword arguments forwarded to reduce_func.
        channel : tuple (out_idx, in_idx), optional
            SISO channel used for Bode plotting.
        """
        reduce_kwargs = reduce_kwargs or {}

        print("  [validation] assembling full-order rotor open-loop model...")
        sys_full = self.assemble_open_loop()
        n_full = sys_full.A.shape[0]

        print(f"  [validation] applying {reduce_func.__name__} for model reduction...")
        result = reduce_func(sys_full, **reduce_kwargs)
        if isinstance(result, tuple):
            sys_reduced, info = result
        else:
            sys_reduced, info = result, None

        n_red = sys_reduced.A.shape[0]
        out_idx, in_idx = channel

        # Validate selected SISO channel indices.
        if out_idx >= sys_full.C.shape[0] or in_idx >= sys_full.B.shape[1]:
            raise ValueError(
                f"Channel index out of range. Current system has {sys_full.B.shape[1]} inputs and {sys_full.C.shape[0]} outputs."
            )

        print(f"  [validation] plotting channel: output {out_idx} <- input {in_idx}")

        # Extract comparable SISO channels from full/reduced models.
        sys_full_siso = sys_full[out_idx, in_idx]
        sys_reduced_siso = sys_reduced[out_idx, in_idx]

        plt.figure(figsize=(10, 7))
        cl.bode_plot(
            [sys_full_siso, sys_reduced_siso],
            dB=True,
            Hz=True,
            label=[f"Full Rotor (n={n_full})", f"Reduced Rotor (n={n_red})"],
        )
        plt.legend()
        plt.suptitle(
            f"Rotor Open-Loop Bode Comparison\nMethod: {reduce_func.__name__} | Channel: Out {out_idx} <- In {in_idx}"
        )
        plt.tight_layout()
        plt.show()


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

    def init(self):
        self.u_buffer.fill(0)
        self.e_buffer.fill(0)
        self.ptr = 0
        self.error = None
        return True

    def input(self, t, error, *args, **kwargs):
        error = np.array(error).reshape(-1)
        self.inp = error
        self.error = limit_signal(error)
        self.t = t

    def output(self, *args, **kwargs):
        if self.error is None:
            return np.zeros(self.dim)

        u_prev = self.u_buffer[self.ptr]
        lead_ptr = (self.ptr + self.m_lead) % self.N
        e_lead = self.e_buffer[lead_ptr]

        u_curr = self.q_filter * u_prev + self.k_rc * e_lead

        self.u_buffer[self.ptr] = u_curr
        self.e_buffer[self.ptr] = self.error
        self.ptr = (self.ptr + 1) % self.N

        return limit_signal(u_curr)

    def calc_error(self, *args, **kwargs):
        pass

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        pass


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


def alpha_shift(sys, alpha):
    """Shift system A-matrix by -alpha*I for numerically safer reduction."""
    A_shifted = np.array(sys.A) - alpha * np.eye(sys.A.shape[0])
    return ss(A_shifted, sys.B, sys.C, sys.D)


def alpha_unshift(sys, alpha):
    """Restore a previously alpha-shifted system by adding alpha*I back."""
    A_restored = np.array(sys.A) + alpha * np.eye(sys.A.shape[0])
    return ss(A_restored, sys.B, sys.C, sys.D)


# Balanced truncation notes:
# Use alpha-shift before balancing to avoid unstable Gramians.
# The helper returns both reduced model and projection matrices.
# For python-control StateSpace inputs, dimensions remain consistent.


def balanced_truncation(sys, order, alpha=1e-2):
    """
    Balanced truncation with optional alpha-shift stabilization.

    Returns the reduced state-space model and projection matrices.

    Parameters
    ----
    sys : StateSpace
        Continuous-time model to reduce.
    order : int
        Target reduced order.
    alpha : float
        Stability shift applied before balancing.
    """
    # Shift poles to improve Gramian computation robustness.
    sys_s = alpha_shift(sys, alpha)

    # Balanced realization.
    sysb, g, T, Ti = balreal(sys_s)

    # Truncate balanced coordinates.
    A_r_s = sysb.A[:order, :order]
    B_r = sysb.B[:order, :]
    C_r = sysb.C[:, :order]
    D_r = sysb.D

    # Projection matrices from full to reduced spaces.
    W = T[:order, :]  # Left projection matrix.
    V = Ti[:, :order]  # Right projection matrix, shape (n, r).

    # Undo the alpha-shift in reduced coordinates.
    A_r = A_r_s + alpha * np.eye(order)

    sys_reduced = ss(A_r, B_r, C_r, D_r)
    info = {"W": W, "V": V, "method": "Balanced Truncation (alpha-shifted)"}

    return sys_reduced, info


def compute_modal_info(A):
    """
    Compute modal properties from a real Schur decomposition.

    Parameters
    ----
    A : ndarray
        System state matrix.

    Returns
    ----
    modes : list[dict]
        Per-mode frequency, damping, and oscillatory metadata.
    Z : ndarray
        Schur transformation matrix.
    """
    T_s, Z = schur(A, output="real")
    n = A.shape[0]
    modes = []

    i = 0
    while i < n:
        if i < n - 1 and abs(T_s[i + 1, i]) > 1e-10:
            blk = T_s[i : i + 2, i : i + 2]
            lam = np.linalg.eigvals(blk)[0]
            lam_conj = np.conj(lam)

            omega_n = np.abs(lam)
            zeta = -np.real(lam) / omega_n if omega_n > 1e-14 else 1.0

            modes.append(
                {
                    "eigenvalue": lam,
                    "index": i,
                    "freq_hz": omega_n / (2 * np.pi),
                    "freq_rad": omega_n,
                    "damping": zeta,
                    "is_oscillatory": True,
                }
            )
            modes.append(
                {
                    "eigenvalue": lam_conj,
                    "index": i + 1,
                    "freq_hz": omega_n / (2 * np.pi),
                    "freq_rad": omega_n,
                    "damping": zeta,
                    "is_oscillatory": True,
                }
            )
            i += 2
        else:
            lam = T_s[i, i]
            omega_n = np.abs(lam)
            zeta = 1.0 if lam <= 0 else -1.0
            modes.append(
                {
                    "eigenvalue": lam,
                    "index": i,
                    "freq_hz": omega_n / (2 * np.pi),
                    "freq_rad": omega_n,
                    "damping": zeta,
                    "is_oscillatory": False,
                }
            )
            i += 1

    return modes, Z


def print_modal_table(modal_info, title="Modal information table"):
    """
    Print modal information in a formatted text table.

    Parameters
    ----
    modal_info : list[dict]
        Output from compute_modal_info.
    title : str
        Table title.
    """
    print(f"\n{'=' * 58}")
    print(f"  {title}")
    print(f"{'=' * 58}")
    header = f"{'Idx':>4s}  {'Freq(Hz)':>10s}  {'Freq(rad/s)':>12s}  {'Damping':>8s}  {'Type':>6s}"
    print(header)
    print("-" * 58)
    for k, m in enumerate(modal_info):
        row = f"{m['index']:4d}  {m['freq_hz']:10.3f}  {m['freq_rad']:12.3f}  {m['damping']:8.5f}  "
        row += f"{'Osc':>6s}" if m["is_oscillatory"] else f"{'Real':>6s}"
        print(row)
    print(f"{'=' * 58}\n")


def modal_truncation_by_frequency(sys, freq_range_hz, alpha=0.0):
    """
    Keep modes within a target natural-frequency interval.

    Parameters
    ----
    sys : StateSpace
        Full-order model.
    freq_range_hz : tuple
        Kept interval as (f_low, f_high) in Hz.
    alpha : float
        Optional alpha-shift for preprocessing.
    """
    A, B, C = np.array(sys.A), np.array(sys.B), np.array(sys.C)
    f_low, f_high = freq_range_hz

    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    def freq_filter(lmbda):
        omega_n = np.abs(lmbda)
        freq_hz = omega_n / (2 * np.pi) if omega_n > 1e-14 else 0.0
        return (f_low <= freq_hz) and (freq_hz <= f_high)

    T_s, Z, sdim = schur(A, sort=freq_filter)

    Ar = T_s[:sdim, :sdim]
    Br = (Z.T @ B)[:sdim, :]
    Cr = (C @ Z)[:, :sdim]

    if alpha > 0:
        Ar = Ar + alpha * np.eye(Ar.shape[0])
    Dr = np.zeros((Cr.shape[0], Br.shape[1]))
    V = Z[:, :sdim]
    W = Z[:, :sdim].T

    info = {"kept_order": sdim, "method": "Schur (Frequency)", "W": W, "V": V}
    return ss(Ar, Br, Cr, Dr), info


def modal_truncation_by_damping(sys, order, alpha=0.0):
    """
    Keep modes with the lowest damping ratios up to target order.

    Parameters
    ----
    sys : StateSpace
        Full-order model.
    order : int
        Requested order bound.
    alpha : float
        Optional alpha-shift for preprocessing.
    """
    A, B, C = np.array(sys.A), np.array(sys.B), np.array(sys.C)

    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    modes, _ = compute_modal_info(A)
    dampings = [m["damping"] for m in modes]

    sorted_dampings = np.sort(dampings)
    safe_order = min(order, len(sorted_dampings))
    threshold = sorted_dampings[safe_order - 1]

    def damp_filter(lmbda):
        omega_n = np.abs(lmbda)
        zeta = -np.real(lmbda) / omega_n if omega_n > 1e-14 else 1.0
        return zeta <= threshold + 1e-9

    T_s, Z, sdim = schur(A, sort=damp_filter)

    Ar = T_s[:sdim, :sdim]
    Br = (Z.T @ B)[:sdim, :]
    Cr = (C @ Z)[:, :sdim]

    if alpha > 0:
        Ar = Ar + alpha * np.eye(Ar.shape[0])
    Dr = np.zeros((Cr.shape[0], Br.shape[1]))

    V = Z[:, :sdim]
    W = Z[:, :sdim].T

    info = {"kept_order": sdim, "method": "Schur (Damping)", "W": W, "V": V}
    return ss(Ar, Br, Cr, Dr), info


def modal_truncation_by_index(sys, keep_indices, alpha=0.0):
    """
    Keep user-selected modal indices from Schur/modal analysis.

    Parameters
    ----
    sys : StateSpace
        Full-order model.
    keep_indices : list[int]
        Modal indices to preserve.
    alpha : float
        Optional alpha-shift for preprocessing.
    """
    A, B, C = np.array(sys.A), np.array(sys.B), np.array(sys.C)

    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    modes, _ = compute_modal_info(A)
    kept_eigvals = [m["eigenvalue"] for m in modes if m["index"] in keep_indices]

    def index_filter(lmbda):
        for k_eig in kept_eigvals:
            if np.abs(lmbda - k_eig) < 1e-8:
                return True
        return False

    T_s, Z, sdim = schur(A, sort=index_filter)

    Ar = T_s[:sdim, :sdim]
    Br = (Z.T @ B)[:sdim, :]
    Cr = (C @ Z)[:, :sdim]

    if alpha > 0:
        Ar = Ar + alpha * np.eye(Ar.shape[0])
    Dr = np.zeros((Cr.shape[0], Br.shape[1]))
    V = Z[:, :sdim]
    W = Z[:, :sdim].T

    info = {"kept_order": sdim, "method": "Schur (Index)", "W": W, "V": V}
    return ss(Ar, Br, Cr, Dr), info


def modal_truncation_by_dominance(sys, order, alpha=0.0):
    """
    Keep most dominant modes based on approximate modal gain metrics.

    Parameters
    ----
    sys : StateSpace
        Full-order model.
    order : int
        Requested kept order.
    alpha : float
        Optional alpha-shift for preprocessing.
    """
    A, B, C = np.array(sys.A), np.array(sys.B), np.array(sys.C)

    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    # Left/right eigenvectors for dominance scoring.
    eigvals, vl, vr = la.eig(A, left=True, right=True)

    # Modal gain proxy.
    gains = np.zeros(len(eigvals))
    for i in range(len(eigvals)):
        v_i = vr[:, i]
        # Left eigenvector (conjugate for complex modes).
        l_vec = vl[:, i].conj()

        # Bi-orthogonality normalization factor.
        norm_fact = np.dot(l_vec, v_i)
        if np.abs(norm_fact) < 1e-14:
            gains[i] = 0.0
            continue

        c_i = C @ v_i
        b_i = l_vec @ B
        # Dominance score combines controllability/observability norms.
        gains[i] = np.linalg.norm(c_i) * np.linalg.norm(b_i) / np.abs(norm_fact)

    # Sort modes by descending dominance score.
    sorted_idx = np.argsort(gains)[::-1]
    kept_eigvals = []
    visited = set()
    kept_count = 0

    for idx in sorted_idx:
        if kept_count >= order:
            break
        if idx in visited:
            continue

        lam = eigvals[idx]
        kept_eigvals.append(lam)
        visited.add(idx)
        kept_count += 1

        # Keep complex-conjugate pairs together.
        if np.abs(np.imag(lam)) > 1e-10:
            conj_idx = np.argmin(np.abs(eigvals - np.conj(lam)))
            if conj_idx not in visited:
                kept_eigvals.append(eigvals[conj_idx])
                visited.add(conj_idx)
                kept_count += 1

    # Schur sort with tolerance around selected eigenvalues.
    def dominance_filter(lmbda):
        for k_eig in kept_eigvals:
            # Relative + absolute tolerance for robust matching.
            if np.abs(lmbda - k_eig) <= 1e-4 * np.abs(k_eig) + 1e-5:
                return True
        return False

    # First attempt using strict matching tolerance.
    T_s, Z, sdim = schur(A, sort=dominance_filter)

    # Fallback tolerance if strict matching keeps no modes.
    if sdim == 0 and order > 0:
        print(
            "  [warning] strict eigenvalue matching failed, switching to loose tolerance..."
        )

        def dominance_filter_loose(lmbda):
            for k_eig in kept_eigvals:
                if np.abs(lmbda - k_eig) <= 1e-2 * np.abs(k_eig) + 1e-2:
                    return True
            return False

        T_s, Z, sdim = schur(A, sort=dominance_filter_loose)

    Ar = T_s[:sdim, :sdim]
    Br = (Z.T @ B)[:sdim, :]
    Cr = (C @ Z)[:, :sdim]

    if alpha > 0:
        Ar += alpha * np.eye(Ar.shape[0])
    Dr = np.zeros((Cr.shape[0], Br.shape[1]))

    V = Z[:, :sdim]
    W = Z[:, :sdim].T
    info = {"kept_order": sdim, "method": "Schur (Dominance)", "W": W, "V": V}
    return ss(Ar, Br, Cr, Dr), info


def test_lqg(eso=True, dt=1e-3, freq=50, alpha=1e-3, beta=2e-3):
    from ALB.rotor import rotor0

    rotor = rotor0(dt, freq, alpha=alpha, beta=beta)

    # Example two-bearing setup.
    valve1 = moog_servovalve(dt=0.001)
    valve2 = moog_servovalve(dt=0.001)

    # Example bearing parameters.
    K1 = np.array([[1e6, 0], [0, 1e6]])
    C1 = np.array([[1e3, 0], [0, 1e3]])
    dxv1 = np.array([0.5, 0.5])

    K2 = np.array([[1.2e6, 0], [0, 1.2e6]])
    C2 = np.array([[1.1e3, 0], [0, 1.1e3]])
    dxv2 = np.array([0.4, 0.4])
    c = ALBLQGController(rotor, dt=dt, freq=freq, eso_enable=eso)

    c.add_bearing(valve1, K1, C1, dxv1, act_node=12, sensor_node=12)
    c.add_bearing(valve2, K2, C2, dxv2, act_node=24, sensor_node=24)
    c.add_unbalance_node(18)
    return c


def balreal(sys):
    """
    Compute balanced realization using controllability/observability Gramians.

    Returns
        sysb: balanced state-space system.
        g: Hankel singular values.
        T: left transformation.
        Ti: right transformation.
    """
    # Gramians.
    Wc = cl.gram(sys, "c")
    Wo = cl.gram(sys, "o")

    # Cholesky-like factors from SVD.
    Uc, Sc, _ = la.svd(Wc)
    Lc = Uc @ np.diag(np.sqrt(Sc))

    Uo, So, _ = la.svd(Wo)
    Lo = Uo @ np.diag(np.sqrt(So))

    # SVD of cross Gramian factor product.
    U, g, Vh = la.svd(Lo.T @ Lc)
    V = Vh.T

    # Balancing transforms.
    Sigma_inv_half = np.diag(g**-0.5)
    T = Sigma_inv_half @ U.T @ Lo.T
    Ti = Lc @ V @ Sigma_inv_half

    # Transform to balanced coordinates.
    A_b = T @ sys.A @ Ti
    B_b = T @ sys.B
    C_b = sys.C @ Ti
    D_b = sys.D
    sysb = cl.ss(A_b, B_b, C_b, D_b)

    return sysb, g, T, Ti
