"""Discrete LQG and disturbance-observer controller utilities."""

import numpy as np
from scipy.linalg import block_diag, pinv
from control.matlab import ss, lqr, lqe, balred, c2d
import control as ctrl
import matplotlib.pyplot as plt

from ALB.dynamics.rotor import location_mapping_matrix

# Encoding-repaired comment.
from model_reduction import (
    balanced_truncation,
    modal_truncation_by_damping,
    modal_truncation_by_frequency,
    modal_truncation_by_dominance,
    modal_truncation_by_index,
    compute_modal_info,
    to_real_modal_form,
    print_modal_table,
)


# Encoding-repaired comment.
class BearingConfig:
    """Bearing config helper."""

    __slots__ = ('valve', 'K', 'C', 'dxv', 'act_node', 'sensor_node')

    def __init__(self, valve, K, C, dxv, act_node, sensor_node):
        self.valve = valve
        self.K = np.array(K).reshape(2, 2)
        self.C = np.array(C).reshape(2, 2)
        self.dxv = np.array(dxv).reshape(2)
        self.act_node = act_node
        self.sensor_node = sensor_node


# Encoding-repaired comment.
# Encoding-repaired comment.
class ALBLQGController:
    """A l b l q g controller helper."""

    # Encoding-repaired comment.

    def __init__(self, rotor, dt, freq=50.0, eso_enable=True):
        # Encoding-repaired comment.
        self.rotor = rotor
        self.dt = dt
        self.freq = freq
        self.omega = 2 * np.pi * freq
        self.eso_enable = eso_enable

        # translated comment
        self.bearings: list[BearingConfig] = []
        self.unbalance_nodes: list[int] = []

        # Encoding-repaired comment.
        self.A_nom = None
        self.B_nom = None
        self.C_nom = None
        self.B_d = None
        self.ctrl_sys_full_c = None
        self.active_ctrl_sys_d = None

        # Encoding-repaired comment.
        self.is_built = False

    # Encoding-repaired comment.

    def add_bearing(self, valve, K, C, dxv, act_node, sensor_node):
        """Add bearing helper."""
        self.bearings.append(
            BearingConfig(valve, K, C, dxv, act_node, sensor_node)
        )
        return self

    def add_unbalance_node(self, node):
        """Add unbalance node helper."""
        self.unbalance_nodes.append(node)
        return self

    def set_weights(self, Q, R, Qn, Rn):
        """Set weights helper."""
        self.Q, self.R = Q, R
        self.Qn, self.Rn = Qn, Rn
        return self

    # Encoding-repaired comment.

    def _effective_unbalance_nodes(self):
        """Effective unbalance nodes helper."""
        nodes = list(self.unbalance_nodes)
        if self.eso_enable and not nodes:
            for b in self.bearings:
                if b.act_node not in nodes:
                    nodes.append(b.act_node)
        return nodes

    def get_dimensions(self, rotor_order=None, verbose=True):
        """Get dimensions helper."""
        lti_r = self.rotor._rotor._lti(self.freq)
        n_rotor = rotor_order if rotor_order is not None else lti_r.A.shape[0]

        n_valve = 0
        for b in self.bearings:
            Av_s = b.valve.main_model.A
            n_valve += Av_s.shape[0] * 2      # Encoding-repaired comment.

        n_inputs = len(self.bearings) * 2      # Encoding-repaired comment.
        n_outputs = len(self.bearings) * 2     # Encoding-repaired comment.
        n_nom_states = n_rotor + n_valve

        eff_nodes = self._effective_unbalance_nodes()
        # Encoding-repaired comment.
        n_dist = len(eff_nodes) * 4 if self.eso_enable else 0
        n_aug_states = n_nom_states + n_dist

        dims = {
            'n_rotor': n_rotor,
            'n_valve': n_valve,
            'n_inputs': n_inputs,
            'n_outputs': n_outputs,
            'n_nom_states': n_nom_states,
            'n_aug_states': n_aug_states,
            'n_dist': n_dist,
        }

        if verbose:
            print("Controller status.")
            print(f"Controller status.")
            print(f"Controller status.")
            print(f"Controller status.")
            print(f"Controller status.")
            print(f"Controller status.")
            print(f"Controller status.")
            print(f"Controller status.")
            print(f"Controller status.")
            print(f"Controller status.")
            print("Controller status.")

        return dims

    # Encoding-repaired comment.

    def build(self, rotor_reduce_func=None, rotor_reduce_kwargs=None,
              ctrl_reduce_func=None, ctrl_reduce_kwargs=None):
        """Build helper."""
        rotor_reduce_kwargs = rotor_reduce_kwargs or {}
        ctrl_reduce_kwargs = ctrl_reduce_kwargs or {}

        print(f"Controller status.")
        print(f"Controller status.")
        print(f"Controller status.")

        # Encoding-repaired comment.
        if self.eso_enable and not self.unbalance_nodes:
            print("Controller status.")
            for b in self.bearings:
                if b.act_node not in self.unbalance_nodes:
                    self.unbalance_nodes.append(b.act_node)

        # Encoding-repaired comment.
        sys_rotor_full = self._assemble_open_loop()

        # Encoding-repaired comment.
        if rotor_reduce_func is not None:
            result = rotor_reduce_func(sys_rotor_full, **rotor_reduce_kwargs)
            # Encoding-repaired comment.
            if isinstance(result, tuple):
                sys_rotor_use, self.rotor_reduce_info = result
            else:
                sys_rotor_use, self.rotor_reduce_info = result, None
            print(f"Controller status.")
        else:
            sys_rotor_use = sys_rotor_full
            self.rotor_reduce_info = None

        # Encoding-repaired comment.
        self._couple_bearings(sys_rotor_use)

        # Encoding-repaired comment.
        self._design_controller()

        # Encoding-repaired comment.
        self.apply_reduction_and_discretize(
            reduce_func=ctrl_reduce_func,
            reduce_kwargs=ctrl_reduce_kwargs
        )

        self.is_built = True
        print("Controller status.")
        return self

    # Encoding-repaired comment.

    def _assemble_open_loop(self):
        """Assemble open loop helper."""
        self.ndof = self.rotor._rotor.ndof
        lti_r = self.rotor._rotor._lti(self.freq)
        self._Ar_full, self._Br_full = lti_r.A, lti_r.B

        Ar, Br = self._Ar_full, self._Br_full
        B_all_list = []
        C_disp_act_list, C_vel_act_list, C_sen_list = [], [], []

        for b in self.bearings:
            act_loc = [[b.act_node, 'x'], [b.act_node, 'y']]
            sen_loc = [[b.sensor_node, 'x'], [b.sensor_node, 'y']]

            T_act = location_mapping_matrix(self.ndof, act_loc)
            B_all_list.append(Br @ T_act)

            H_sen_disp = location_mapping_matrix(self.ndof * 2, sen_loc).T
            H_act_disp = location_mapping_matrix(self.ndof * 2, act_loc).T
            H_act_vel = np.roll(H_act_disp, self.ndof, axis=1)

            C_disp_act_list.append(H_act_disp)
            C_vel_act_list.append(H_act_vel)
            C_sen_list.append(H_sen_disp)

        for node in self.unbalance_nodes:
            loc = [[node, 'x'], [node, 'y']]
            T_d = location_mapping_matrix(self.ndof, loc)
            B_all_list.append(Br @ T_d)

        B_all = np.hstack(B_all_list) if B_all_list else np.zeros((Ar.shape[0], 0))
        C_all = (np.vstack(C_disp_act_list + C_vel_act_list + C_sen_list)
                 if self.bearings else np.zeros((0, Ar.shape[1])))

        D_all = np.zeros((C_all.shape[0], B_all.shape[1]))
        return ss(Ar, B_all, C_all, D_all)

    # Encoding-repaired comment.

    def _couple_bearings(self, sys_rotor):
        """Couple bearings helper."""
        Arr = np.array(sys_rotor.A)
        Brr = np.array(sys_rotor.B)
        Crr = np.array(sys_rotor.C)

        Nb = len(self.bearings)
        Ar_closed = Arr.copy()

        A_rv_list, Av_list, Bv_list, Cv_list = [], [], [], []
        H_sensor_list = []

        for i, b in enumerate(self.bearings):
            # Encoding-repaired comment.
            B_act_i  = Brr[:, 2*i : 2*i+2]
            C_disp_i = Crr[2*i : 2*i+2, :]
            C_vel_i  = Crr[2*Nb + 2*i : 2*Nb + 2*i+2, :]
            C_sen_i  = Crr[4*Nb + 2*i : 4*Nb + 2*i+2, :]

            # Encoding-repaired comment.
            Ar_closed -= (B_act_i @ b.K @ C_disp_i + B_act_i @ b.C @ C_vel_i)

            # Encoding-repaired comment.
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

        self.A_nom = np.block([
            [Ar_closed,             A_rv_global],
            [np.zeros((nv, nr)),    Av_global  ]
        ])
        self.B_nom = np.block([
            [np.zeros((nr, Bv_global.shape[1]))],
            [Bv_global                         ]
        ])
        n_sensor_rows = sum(h.shape[0] for h in H_sensor_list)
        self.C_nom = np.block([
            [np.vstack(H_sensor_list), np.zeros((n_sensor_rows, nv))]
        ])

        # Encoding-repaired comment.
        if self.unbalance_nodes:
            B_d_rotor = Brr[:, 2*Nb : 2*Nb + 2*len(self.unbalance_nodes)]
            self.B_d = np.block([
                [B_d_rotor],
                [np.zeros((nv, B_d_rotor.shape[1]))]
            ])
        else:
            self.B_d = np.zeros((self.A_nom.shape[0], 0))

    # Encoding-repaired comment.

    def _design_controller(self):
        """Design controller helper."""
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
        """Design eso branch helper."""
        print("Controller status.")
        n_dist_channels = self.B_d.shape[1]

        # Encoding-repaired comment.
        Ad_block = np.array([[0, self.omega], [-self.omega, 0]])
        A_dist = block_diag(*[Ad_block for _ in range(n_dist_channels)])

        Cd_block = np.array([[1, 0]])
        C_dist = block_diag(*[Cd_block for _ in range(n_dist_channels)])

        # translated comment
        n_nom = self.A_nom.shape[0]
        n_d = A_dist.shape[0]

        A_aug = np.block([
            [self.A_nom,                self.B_d @ C_dist],
            [np.zeros((n_d, n_nom)),    A_dist           ]
        ])
        B_aug = np.block([
            [self.B_nom],
            [np.zeros((n_d, self.B_nom.shape[1]))]
        ])
        C_aug = np.block([
            [self.C_nom, np.zeros((self.C_nom.shape[0], n_d))]
        ])

        A_aug_design = A_aug - alpha_shift * np.eye(A_aug.shape[0])
        G_aug = np.eye(A_aug.shape[0])
        L_kf, _, _ = lqe(A_aug_design, G_aug, C_aug, self.Qn, self.Rn)

        # Encoding-repaired comment.
        self.K_dob = pinv(self.B_nom) @ (self.B_d @ C_dist)
        K_aug = np.hstack([self.K_lqr, self.K_dob])

        Ak = A_aug - B_aug @ K_aug - L_kf @ C_aug
        Bk = L_kf
        Ck = -K_aug
        Dk = np.zeros((Ck.shape[0], Bk.shape[1]))   # (n_output n_input)

        return Ak, Bk, Ck, Dk

    def _design_standard_branch(self, A_design):
        """Design standard branch helper."""
        print("Controller status.")
        G = np.eye(self.A_nom.shape[0])
        L_kf, _, _ = lqe(A_design, G, self.C_nom, self.Qn, self.Rn)

        Ak = self.A_nom - self.B_nom @ self.K_lqr - L_kf @ self.C_nom
        Bk = L_kf
        Ck = -self.K_lqr
        Dk = np.zeros((self.B_nom.shape[1], self.C_nom.shape[0]))

        return Ak, Bk, Ck, Dk

    # Encoding-repaired comment.

    def apply_reduction_and_discretize(self, reduce_func=None,
                                        reduce_kwargs=None, plot_bode=False):
        """Apply reduction and discretize helper."""
        reduce_kwargs = reduce_kwargs or {}

        if reduce_func is not None:
            result = reduce_func(self.ctrl_sys_full_c, **reduce_kwargs)
            if isinstance(result, tuple):
                sys_c, self.ctrl_reduce_info = result
            else:
                sys_c, self.ctrl_reduce_info = result, None
            print(f"Controller status."
                  f"  ({reduce_func.__name__})")

            if plot_bode:
                self._plot_bode_comparison(
                    self.ctrl_sys_full_c, sys_c,
                    title_suffix=f"({reduce_func.__name__})"
                )
        else:
            sys_c = self.ctrl_sys_full_c
            self.ctrl_reduce_info = None
            print("Controller status.")

        # Encoding-repaired comment.
        self.active_ctrl_sys_d = c2d(sys_c, self.dt, method='tustin')
        self._init_runtime_state()

    def _plot_bode_comparison(self, sys_full, sys_red, title_suffix=""):
        """Plot bode comparison helper."""
        n_red = sys_red.A.shape[0]
        plt.figure(figsize=(10, 7))
        ctrl.bode_plot(
            [sys_full, sys_red],
            dB=True, Hz=True,
            label=['Full', f'Reduced (n={n_red})'],
        )
        plt.legend()
        plt.suptitle(f'Controller Bode Comparison {title_suffix}')
        plt.tight_layout()
        plt.show()

    # Encoding-repaired comment.

    def _init_runtime_state(self):
        """Init runtime state helper."""
        n = self.active_ctrl_sys_d.A.shape[0]
        self.t_prev = -1.0
        self.x_hat = np.zeros((n, 1))
        self.x_next = np.zeros((n, 1))
        self.y_current = np.zeros((self.active_ctrl_sys_d.B.shape[1], 1))
        self.u_current = np.zeros((self.active_ctrl_sys_d.C.shape[0], 1))

    def init(self):
        """Init helper."""
        self._init_runtime_state()

    def input(self, t, y_disp):
        """Input helper."""
        self.y_current = np.array(y_disp).reshape(-1, 1)
        if t > self.t_prev:
            self.x_hat = self.x_next
            self.t_prev = t

    def output(self):
        """Output helper."""
        Ad = self.active_ctrl_sys_d.A
        Bd = self.active_ctrl_sys_d.B
        Cd = self.active_ctrl_sys_d.C
        Dd = self.active_ctrl_sys_d.D

        self.u_current = Cd @ self.x_hat + Dd @ self.y_current
        self.x_next = Ad @ self.x_hat + Bd @ self.y_current

        return self.u_current.flatten()

    # Encoding-repaired comment.

    def print_open_loop_modes(self):
        """Print open loop modes helper."""
        if self.A_nom is None:
            raise RuntimeError("Build the controller before this operation.")
        modes, _ = compute_modal_info(self.A_nom)
        print_modal_table(
            [{'freq_hz': m['freq_hz'], 'freq_rad': m['freq_rad'],
              'damping': m['damping'], 'is_oscillatory': m['is_oscillatory']}
             for m in modes],
            title="Modal information"
        )

    def summary(self):
        """Summary helper."""
        if not self.is_built:
            print("Controller status.")
            return
        n_full = self.ctrl_sys_full_c.A.shape[0]
        n_disc = self.active_ctrl_sys_d.A.shape[0]
        print(f"Controller status.")
        print(f"Controller status.")
        print(f"Controller status.")
        print(f"Controller status.")
        print(f"Controller status.")
        print(f"Controller status.")
        print(f"Controller status.")
        print(f"Controller status.")
        print(f"Controller status.")

    def plot_rotor_reduction(self, reduce_func, reduce_kwargs=None, channel=(0, 0)):
        """Plot rotor reduction helper."""
        reduce_kwargs = reduce_kwargs or {}

        print(f"Controller status.")
        sys_full = self._assemble_open_loop()
        n_full = sys_full.A.shape[0]

        print(f"Controller status.")
        result = reduce_func(sys_full, **reduce_kwargs)
        if isinstance(result, tuple):
            sys_reduced, info = result
        else:
            sys_reduced, info = result, None

        n_red = sys_reduced.A.shape[0]
        out_idx, in_idx = channel

        # Encoding-repaired comment.
        if out_idx >= sys_full.C.shape[0] or in_idx >= sys_full.B.shape[1]:
            raise ValueError(f"Controller status.")

        print(f"Controller status.")

        # Encoding-repaired comment.
        sys_full_siso = sys_full[out_idx, in_idx]
        sys_reduced_siso = sys_reduced[out_idx, in_idx]

        plt.figure(figsize=(10, 7))
        ctrl.bode_plot(
            [sys_full_siso, sys_reduced_siso],
            dB=True, Hz=True,
            label=[f'Full Rotor (n={n_full})', f'Reduced Rotor (n={n_red})']
        )
        plt.legend()
        plt.suptitle(
            f'Rotor Open-Loop Bode Comparison\nMethod: {reduce_func.__name__} | Channel: Out {out_idx} <- In {in_idx}')
        plt.tight_layout()
        plt.show()


from scipy.linalg import schur
from control.matlab import ss, balred
import numpy as np


# Encoding-repaired comment.
def compute_modal_info(A):
    """Compute modal info helper."""
    T_s, Z = schur(A, output='real')
    n = A.shape[0]
    modes = []

    i = 0
    while i < n:
        # Encoding-repaired comment.
        if i < n - 1 and abs(T_s[i + 1, i]) > 1e-10:
            blk = T_s[i:i + 2, i:i + 2]
            lam = np.linalg.eigvals(blk)[0]
            lam_conj = np.conj(lam)

            omega_n = np.abs(lam)
            zeta = -np.real(lam) / omega_n if omega_n > 1e-14 else 1.0

            modes.append(
                {'eigenvalue': lam, 'index': i, 'freq_hz': omega_n / (2 * np.pi), 'freq_rad': omega_n, 'damping': zeta,
                 'is_oscillatory': True})
            modes.append({'eigenvalue': lam_conj, 'index': i + 1, 'freq_hz': omega_n / (2 * np.pi), 'freq_rad': omega_n,
                          'damping': zeta, 'is_oscillatory': True})
            i += 2
        else:
            # Encoding-repaired comment.
            lam = T_s[i, i]
            omega_n = np.abs(lam)
            zeta = 1.0 if lam <= 0 else -1.0
            modes.append(
                {'eigenvalue': lam, 'index': i, 'freq_hz': omega_n / (2 * np.pi), 'freq_rad': omega_n, 'damping': zeta,
                 'is_oscillatory': False})
            i += 1

    return modes, Z


def print_modal_table(modal_info, title="Modal information"):
    """Print modal table helper."""
    print(f"\n{'=' * 58}")
    print(f"  {title}")
    print(f"{'=' * 58}")
    header = f"Controller status."
    print(header)
    print('-' * 58)
    for k, m in enumerate(modal_info):
        row = f"{m['index']:4d}  {m['freq_hz']:10.3f}  {m['freq_rad']:12.3f}  {m['damping']:8.5f}  "
        row += f"Controller status." if m['is_oscillatory'] else f"Controller status."
        print(row)
    print(f"{'=' * 58}\n")


# Encoding-repaired comment.
# Encoding-repaired comment.
def robust_modal_truncation_by_frequency(sys, freq_range_hz, alpha=0.0):
    """Robust modal truncation by frequency helper."""
    A, B, C = np.array(sys.A), np.array(sys.B), np.array(sys.C)
    f_low, f_high = freq_range_hz

    if alpha > 0: A = A - alpha * np.eye(A.shape[0])

    def freq_filter(lmbda):
        omega_n = np.abs(lmbda)
        freq_hz = omega_n / (2 * np.pi) if omega_n > 1e-14 else 0.0
        return (f_low <= freq_hz) and (freq_hz <= f_high)

    T_s, Z, sdim = schur(A, sort=freq_filter)

    Ar = T_s[:sdim, :sdim]
    Br = (Z.T @ B)[:sdim, :]
    Cr = (C @ Z)[:, :sdim]

    if alpha > 0: Ar = Ar + alpha * np.eye(Ar.shape[0])
    Dr = np.zeros((Cr.shape[0], Br.shape[1]))

    return ss(Ar, Br, Cr, Dr), {'kept_order': sdim, 'method': 'Robust Schur (Frequency)'}


def robust_modal_truncation_by_damping(sys, order, alpha=0.0):
    """Robust modal truncation by damping helper."""
    A, B, C = np.array(sys.A), np.array(sys.B), np.array(sys.C)

    if alpha > 0: A = A - alpha * np.eye(A.shape[0])

    modes, _ = compute_modal_info(A)
    dampings = [m['damping'] for m in modes]

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

    if alpha > 0: Ar = Ar + alpha * np.eye(Ar.shape[0])
    Dr = np.zeros((Cr.shape[0], Br.shape[1]))

    return ss(Ar, Br, Cr, Dr), {'kept_order': sdim, 'method': 'Robust Schur (Damping)'}


def robust_modal_truncation_by_index(sys, keep_indices, alpha=0.0):
    """Robust modal truncation by index helper."""
    A, B, C = np.array(sys.A), np.array(sys.B), np.array(sys.C)

    if alpha > 0: A = A - alpha * np.eye(A.shape[0])

    modes, _ = compute_modal_info(A)
    # Encoding-repaired comment.

    def index_filter(lmbda):
        # Encoding-repaired comment.
        for k_eig in kept_eigvals:
            if np.abs(lmbda - k_eig) < 1e-8:
                return True
        return False

    T_s, Z, sdim = schur(A, sort=index_filter)

    Ar = T_s[:sdim, :sdim]
    Br = (Z.T @ B)[:sdim, :]
    Cr = (C @ Z)[:, :sdim]

    if alpha > 0: Ar = Ar + alpha * np.eye(Ar.shape[0])
    Dr = np.zeros((Cr.shape[0], Br.shape[1]))

    return ss(Ar, Br, Cr, Dr), {'kept_order': sdim, 'method': 'Robust Schur (Index)'}


def robust_modal_truncation_by_dominance(sys, order, alpha=1e-2):
    """Robust modal truncation by dominance helper."""
    sys_r = balanced_truncation(sys, order, alpha=alpha)
    return sys_r, {'kept_order': sys_r.A.shape[0], 'method': 'Robust Dominance (Balanced Truncation)'}
