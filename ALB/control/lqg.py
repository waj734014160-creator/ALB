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

from .reduction_core import alpha_shift, compute_modal_info, print_modal_table

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
    for both plant and controller stages. ``freq`` is the shaft rotational
    frequency in Hz; ROSS rotor state-space models are evaluated at the
    corresponding angular speed in rad/s. Returned actuator commands are
    limited to ``output_min`` and ``output_max``; both bounds default to
    ``-1`` and ``1`` and may be scalar or per-channel values.
    """

    # Public API.

    def __init__(
        self,
        rotor,
        dt=None,
        freq=50.0,
        eso_enable=True,
        output_min=-1.0,
        output_max=1.0,
        *,
        config=None,
    ):
        """Initialize the LQG controller and its runtime output protection.

        Parameters
        ----------
        rotor : object
            ALB rotor wrapper exposing ``_rotor`` and the operating ``_speed``.
        dt : float, optional
            Sampling time in seconds. Required unless ``config`` is supplied.
        freq : float, optional
            Shaft rotational frequency in Hz.
        eso_enable : bool, optional
            Enable the disturbance-state observer branch.
        output_min, output_max : float or array-like, optional
            Actuator command bounds. Scalars apply to every output channel.
        config : LQGConfig or dict, optional
            Core LQG configuration. When supplied, it replaces the direct
            runtime arguments and ``dt`` must be omitted.
        """
        super().__init__()
        if config is not None:
            if dt is not None:
                raise ValueError("dt and config cannot be supplied together")
            config = LQGConfig.from_dict(config)
        else:
            if dt is None:
                raise TypeError("dt is required when config is not supplied")
            config = LQGConfig(
                dt=dt,
                freq=freq,
                eso_enable=eso_enable,
                output_min=output_min,
                output_max=output_max,
            )

        # Core simulation settings.
        self.rotor = rotor
        self.config = config
        self.dt = float(config.dt)
        self.freq = float(config.freq)
        self.omega = 2.0 * np.pi * self.freq
        self.eso_enable = config.eso_enable
        self.output_min = config.output_min
        self.output_max = config.output_max

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
        self._lifecycle = RuntimeLifecycle(type(self).__name__)

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

    def _rotor_lti(self):
        """Return the ROSS rotor LTI model at the configured shaft speed.

        ALB exposes ``freq`` in Hz, whereas ROSS interprets a plain numeric
        rotor ``speed`` as rad/s. The wrapped rotor and the controller design
        must use the same physical operating speed.
        """
        rotor_speed = getattr(self.rotor, "_speed", None)
        if rotor_speed is not None and not np.isclose(
            float(rotor_speed), self.omega, rtol=1e-9, atol=1e-12
        ):
            raise ValueError(
                "RossRotor speed does not match the LQG operating frequency: "
                f"rotor speed={float(rotor_speed):.12g} rad/s, "
                f"controller freq={self.freq:.12g} Hz "
                f"({self.omega:.12g} rad/s)."
            )
        return self.rotor._rotor._lti(self.omega)

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
        lti_r = self._rotor_lti()
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
        from ALB.dynamics.rotor import RotorDofLayout, location_mapping_matrix

        self.ndof = self.rotor._rotor.ndof
        try:
            layout = self.rotor.dof_layout
        except (AttributeError, ValueError):
            layout = None
        if layout is None:
            raw_rotor = self.rotor._rotor
            if hasattr(raw_rotor, "number_dof"):
                layout = RotorDofLayout.from_ross(raw_rotor)
            else:
                # Minimal legacy test plants expose only a single four-DOF
                # planar node and are not complete ROSS rotor objects.
                layout = RotorDofLayout.from_dof_per_node(4)
        lti_r = self._rotor_lti()
        self._Ar_full, self._Br_full = lti_r.A, lti_r.B

        Ar, Br = self._Ar_full, self._Br_full
        B_all_list = []
        C_disp_act_list, C_vel_act_list, C_sen_list = [], [], []

        for b in self.bearings:
            act_loc = [[b.act_node, "x"], [b.act_node, "y"]]
            sen_loc = [[b.sensor_node, "x"], [b.sensor_node, "y"]]

            T_act = location_mapping_matrix(self.ndof, act_loc, layout=layout)
            B_all_list.append(Br @ T_act)

            H_sen_disp = location_mapping_matrix(
                self.ndof * 2, sen_loc, layout=layout
            ).T
            H_act_disp = location_mapping_matrix(
                self.ndof * 2, act_loc, layout=layout
            ).T
            H_act_vel = np.roll(H_act_disp, self.ndof, axis=1)

            C_disp_act_list.append(H_act_disp)
            C_vel_act_list.append(H_act_vel)
            C_sen_list.append(H_sen_disp)

        for node in self.unbalance_nodes:
            loc = [[node, "x"], [node, "y"]]
            T_d = location_mapping_matrix(self.ndof, loc, layout=layout)
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
        self.u_raw_current = self.u_current.copy()
        self._pending_time = 0.0
        self._pending_measurement = self.y_current.copy()
        self._last_input_time = None
        self._last_output = None
        # Logged per control step for analysis/debug.
        self._history = {"t": [], "y": [], "u_raw": [], "u": [], "x_hat": []}
        self._lifecycle.reset()

    def _output_bound(self, bound, output_count, name):
        """Return one scalar or one value per actuator as a column vector."""
        values = np.asarray(bound, dtype=float).reshape(-1)
        if values.size == 1:
            values = np.full(output_count, values.item())
        elif values.size != output_count:
            raise ValueError(
                f"{name} must be scalar or contain {output_count} values; "
                f"received {values.size}."
            )
        return values.reshape(-1, 1)

    def _limit_output(self, output):
        """Apply configured scalar or per-channel command bounds."""
        output_count = output.shape[0]
        lower = self._output_bound(self.output_min, output_count, "output_min")
        upper = self._output_bound(self.output_max, output_count, "output_max")
        if np.any(lower >= upper):
            raise ValueError(
                "output_min must be less than output_max for every channel"
            )
        return np.clip(output, lower, upper)

    def init(self):
        """Reset runtime state for a new simulation run."""
        self._init_runtime_state()

    def input(self, t, y_disp):
        """Validate and latch one measurement without advancing the observer."""

        self._lifecycle.require_input_slot()
        if self.active_ctrl_sys_d is None:
            raise RuntimeError("LQG controller must be built before input()")
        time = finite_real_scalar(t, "controller time")
        input_count = int(self.active_ctrl_sys_d.B.shape[1])
        measurement = finite_real_vector(
            y_disp, "controller measurement", input_count
        ).reshape(-1, 1)
        if self._last_input_time is not None and time <= self._last_input_time:
            raise ValueError("controller time must increase strictly between inputs")
        self._pending_time = time
        self._pending_measurement = measurement
        self._last_output = None
        self._lifecycle.latch()

    def evaluate(self):
        """Compute one command and propagate the observer exactly once."""

        with self._lifecycle.evaluation():
            Ad = self.active_ctrl_sys_d.A
            Bd = self.active_ctrl_sys_d.B
            Cd = self.active_ctrl_sys_d.C
            Dd = self.active_ctrl_sys_d.D

            self.y_current = self._pending_measurement.copy()
            self.x_hat = self.x_next.copy()
            self.t_prev = self._pending_time
            self._last_input_time = self._pending_time

            # Static output equation followed by actuator command protection.
            self.u_raw_current = Cd @ self.x_hat + Dd @ self.y_current
            self.u_current = self._limit_output(self.u_raw_current)

            # Save history after time has started advancing.
            if self.t_prev >= 0:  # Skip initial pre-step state.
                self._history["t"].append(self.t_prev)
                self._history["y"].append(self.y_current.flatten())
                self._history["u_raw"].append(self.u_raw_current.flatten())
                self._history["u"].append(self.u_current.flatten())
                self._history["x_hat"].append(self.x_hat.flatten())

            # State update equation.
            self.x_next = Ad @ self.x_hat + Bd @ self.y_current
            self._last_output = self.u_current.flatten().copy()
        return self.output()

    def output(self):
        """Read the completed command without advancing observer state."""

        self._lifecycle.require_output()
        assert self._last_output is not None
        return self._last_output.copy()

    def step(self, t, y_disp):
        """Compose input, evaluation, and read-only output for one local step."""

        self.input(t, y_disp)
        self.evaluate()
        return self.output()

    @property
    def lifecycle_state(self):
        """Return the current strict runtime state."""

        return self._lifecycle.state

    def get_history(self, to_dataframe=True):
        """
        Return runtime history as either raw arrays or a DataFrame.

        Parameters
        ----
        to_dataframe : bool
            If True, return a flattened pandas DataFrame.
        """
        widths = {
            "y": self.y_current.shape[0],
            "u_raw": self.u_raw_current.shape[0],
            "u": self.u_current.shape[0],
            "x_hat": self.x_hat.shape[0],
        }
        res = {"t": np.asarray(self._history["t"], dtype=float)}
        for name, width in widths.items():
            values = self._history[name]
            res[name] = (
                np.asarray(values, dtype=float).reshape(-1, width)
                if values
                else np.empty((0, width), dtype=float)
            )

        if to_dataframe:
            import pandas as pd

            # Flatten vector channels into scalar DataFrame columns.
            df = pd.DataFrame({"t": res["t"]})
            for i in range(res["y"].shape[1]):
                df[f"y_{i}"] = res["y"][:, i]
            for i in range(res["u_raw"].shape[1]):
                df[f"u_raw_{i}"] = res["u_raw"][:, i]
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
        print(f"Output lower limit    : {np.asarray(self.output_min).tolist()}")
        print(f"Output upper limit    : {np.asarray(self.output_max).tolist()}")
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

__all__ = ["ALBLQGController", "BearingContent"]
