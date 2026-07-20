"""
alb_lqg_controller.py
======================
鍩轰簬 杞瓙-浼烘湇闃€-澶氳酱鎵?鑰﹀悎妯″瀷鐨?绂绘暎 LQG + DOB 鎺у埗鍣紙閲嶆瀯鐗堬級銆?
閲嶆瀯瑕佺偣锛?    1. 闄嶉樁绛栫暐瑙ｈ€︼細杞瓙闄嶉樁 / 鎺у埗鍣ㄩ檷闃?鍧囨帴鍙楀閮ㄥ彲鎻掓嫈鍑芥暟
    2. 鐙珛鍑芥暟妯″潡锛歮odel_reduction.py 涓殑绾嚱鏁板彲鐙珛娴嬭瘯涓庡鐢?    3. 娴佹按绾挎瀯寤猴細build 鈫?assemble_open_loop 鈫?_couple_bearings 鈫?_design_controller
    4. 宸蹭慨澶嶅師鐗堜笁澶勭己闄凤紙n_dist 缁村害銆丏k 杞疆銆乬et_dimensions 鑷姩鎺ㄦ柇锛?"""

import numpy as np
from scipy.linalg import block_diag, pinv
from control.matlab import ss, lqr, lqe, balred, c2d
import control as ctrl
import matplotlib.pyplot as plt

from ALB.dynamics.rotor import location_mapping_matrix

# € € € ā  ラ ? € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € €
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


# ?# ?# ?
class BearingConfig:
    """鍗曚釜杞存壙-浼烘湇闃€-浼犳劅鍣ㄩ摼璺殑鍙傛暟瀹瑰櫒"""

    __slots__ = ('valve', 'K', 'C', 'dxv', 'act_node', 'sensor_node')

    def __init__(self, valve, K, C, dxv, act_node, sensor_node):
        self.valve = valve
        self.K = np.array(K).reshape(2, 2)
        self.C = np.array(C).reshape(2, 2)
        self.dxv = np.array(dxv).reshape(2)
        self.act_node = act_node
        self.sensor_node = sensor_node


# ?# ALBLQGController
# ?
class ALBLQGController:
    """
    绂绘暎 LQG + DOB 鎺у埗鍣紝鏀寔鍙彃鎷旈檷闃剁瓥鐣ャ€?
    构建流程
    --------
    1. 閰嶇疆闃舵:  add_bearing() / add_unbalance_node() / set_weights()
    2. 缂栬瘧闃舵:  build()  鈫? assemble_open_loop()
                            鈫? _couple_bearings()
                            鈫? _design_controller()
    3. 杩愯闃舵:  input() / output()  绂绘暎閫掓帹

    降阶策略
    --------
    閫氳繃 `rotor_reduce_func` 鍜?`ctrl_reduce_func` 鍙傛暟娉ㄥ叆浠绘剰闄嶉樁鍑芥暟锛?    绛惧悕绾﹀畾锛?        reduce_func(sys: StateSpace, **kwargs) -> StateSpace  鎴?        reduce_func(sys: StateSpace, **kwargs) -> (StateSpace, info)
    """

    # € € €  ? € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € €

    def __init__(self, rotor, dt, freq=50.0, eso_enable=True):
        # ╃
        self.rotor = rotor
        self.dt = dt
        self.freq = freq
        self.omega = 2 * np.pi * freq
        self.eso_enable = eso_enable

        # translated comment
        self.bearings: list[BearingConfig] = []
        self.unbalance_nodes: list[int] = []

        #  х uild ～
        self.A_nom = None
        self.B_nom = None
        self.C_nom = None
        self.B_d = None
        self.ctrl_sys_full_c = None
        self.active_ctrl_sys_d = None

        # € ?
        self.is_built = False

    # € € € ュ ( ) € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € €

    def add_bearing(self, valve, K, C, dxv, act_node, sensor_node):
        """娣诲姞涓€缁?杞存壙-浼烘湇闃€-浼犳劅鍣?閾捐矾"""
        self.bearings.append(
            BearingConfig(valve, K, C, dxv, act_node, sensor_node)
        )
        return self

    def add_unbalance_node(self, node):
        """添加不平衡力作用节点"""
        self.unbalance_nodes.append(node)
        return self

    def set_weights(self, Q, R, Qn, Rn):
        """璁剧疆 LQR / Kalman 婊ゆ尝鍣ㄦ潈閲嶇煩闃?"""
        self.Q, self.R = Q, R
        self.Qn, self.Rn = Qn, Rn
        return self

    # € € € ヨ € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € €

    def _effective_unbalance_nodes(self):
        """
        预测实际的不平衡节点列表(与 build 中自动推断逻辑一致)。
        当 eso_enable=True 且用户未手动指定时,自动将所有轴承作用节点
        作为等效干扰输入节点。此方法不修改 self.unbalance_nodes。
        """
        nodes = list(self.unbalance_nodes)
        if self.eso_enable and not nodes:
            for b in self.bearings:
                if b.act_node not in nodes:
                    nodes.append(b.act_node)
        return nodes

    def get_dimensions(self, rotor_order=None, verbose=True):
        """
        鑾峰彇褰撳墠閰嶇疆涓嬬殑绯荤粺鍚勫瓙绌洪棿缁村害銆?
        鐢ㄦ埛搴旀嵁姝ゆ瀯寤?Q, R, Qn, Rn 鏉冮噸鐭╅樀銆?        """
        lti_r = self.rotor._rotor._lti(self.freq)
        n_rotor = rotor_order if rotor_order is not None else lti_r.A.shape[0]

        n_valve = 0
        for b in self.bearings:
            Av_s = b.valve.main_model.A
            n_valve += Av_s.shape[0] * 2      # x/y ら€

        n_inputs = len(self.bearings) * 2      # € у
        n_outputs = len(self.bearings) * 2     # ㄤ ?
        n_nom_states = n_rotor + n_valve

        eff_nodes = self._effective_unbalance_nodes()
        # ?2 (x,y) 2  ㄧ ?= 4
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
            print("鈹€鈹€鈹€ 绯荤粺缁村害鍒嗘瀽 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")
            print(f"  杞瓙鐘舵€佹暟锛堥檷闃跺悗锛? : {n_rotor}")
            print(f"  浼烘湇闃€鎬荤姸鎬佹暟        : {n_valve}")
            print(f"  鍚嶄箟鐘舵€?n_nom        : {n_nom_states}")
            print(f"  鎵╁紶鐘舵€?n_dist       : {n_dist}")
            print(f"  澧炲箍鐘舵€?n_aug        : {n_aug_states}")
            print(f"  LQR  Q : [{n_nom_states} × {n_nom_states}]")
            print(f"  LQR  R : [{n_inputs} × {n_inputs}]")
            print(f"  KF   Qn: [{n_aug_states} × {n_aug_states}]")
            print(f"  KF   Rn: [{n_outputs} × {n_outputs}]")
            print("鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")

        return dims

    # € € € ? € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € €

    def build(self, rotor_reduce_func=None, rotor_reduce_kwargs=None,
              ctrl_reduce_func=None, ctrl_reduce_kwargs=None):
        """
        缂栬瘧闃舵锛氱粍瑁呭紑鐜ā鍨?鈫?杞存壙闂幆鑰﹀悎 鈫?LQG 璁捐 鈫?绂绘暎鍖栥€?
        参数
        ----
        rotor_reduce_func : callable 鎴?None
            杞瓙闄嶉樁鍑芥暟锛岀鍚?f(sys, **kw) -> sys_reduced 鎴?(sys_reduced, info)銆?            浼犲叆 None 鍒欎繚鎸佸叏闃躲€?            鍐呯疆鍙€夛細balanced_truncation, modal_truncation_by_damping,
                      modal_truncation_by_frequency, modal_truncation_by_dominance,
                      modal_truncation_by_index
        rotor_reduce_kwargs : dict
            浼犵粰 rotor_reduce_func 鐨勯澶栧叧閿瓧鍙傛暟銆?        ctrl_reduce_func : callable 鎴?None
            鎺у埗鍣ㄩ檷闃跺嚱鏁帮紙璁捐瀹屾垚鍚庡鎺у埗寰嬬郴缁熷仛浜屾闄嶉樁锛夛紝绛惧悕鍚屼笂銆?        ctrl_reduce_kwargs : dict
            浼犵粰 ctrl_reduce_func 鐨勯澶栧叧閿瓧鍙傛暟銆?
        示例
        ----
        >>> #   ?20 ? >>> ctrl.build(rotor_reduce_func=balanced_truncation,
        ...            rotor_reduce_kwargs={'order': 20})

        >>> # ā  16 ℃€? >>> ctrl.build(rotor_reduce_func=modal_truncation_by_damping,
        ...            rotor_reduce_kwargs={'order': 16})

        >>> #  ｆ  ?10~200 Hz ℃€? >>> ctrl.build(rotor_reduce_func=modal_truncation_by_frequency,
        ...            rotor_reduce_kwargs={'freq_range_hz': (10, 200)})
        """
        rotor_reduce_kwargs = rotor_reduce_kwargs or {}
        ctrl_reduce_kwargs = ctrl_reduce_kwargs or {}

        print(f"══ 构建耦合系统 ══")
        print(f"  杞瓙闄嶉樁绛栫暐: {rotor_reduce_func.__name__ if rotor_reduce_func else '全阶'}")
        print(f"  鎺у埗鍣ㄩ檷闃剁瓥鐣? {ctrl_reduce_func.__name__ if ctrl_reduce_func else '全阶'}")

        # Step 0:  ㄦ ¤ ?
        if self.eso_enable and not self.unbalance_nodes:
            print("  [鑷姩鎺ㄦ柇] 灏嗚酱鎵夸綔鐢ㄨ妭鐐硅涓哄共鎵拌緭鍏ヨ妭鐐?")
            for b in self.bearings:
                if b.act_node not in self.unbalance_nodes:
                    self.unbalance_nodes.append(b.act_node)

        # Step 1:  €  € ″
        sys_rotor_full = self._assemble_open_loop()

        # Step 2: 
        if rotor_reduce_func is not None:
            result = rotor_reduce_func(sys_rotor_full, **rotor_reduce_kwargs)
            #  (sys, info) ?sys
            if isinstance(result, tuple):
                sys_rotor_use, self.rotor_reduce_info = result
            else:
                sys_rotor_use, self.rotor_reduce_info = result, None
            print(f"  杞瓙闄嶉樁瀹屾垚: {sys_rotor_full.A.shape[0]} 鈫?{sys_rotor_use.A.shape[0]} 闃?")
        else:
            sys_rotor_use = sys_rotor_full
            self.rotor_reduce_info = None

        # Step 3:  ﹀
        self._couple_bearings(sys_rotor_use)

        # Step 4:  LQG + DOB
        self._design_controller()

        # Step 5: у ㄩ ?+ ?
        self.apply_reduction_and_discretize(
            reduce_func=ctrl_reduce_func,
            reduce_kwargs=ctrl_reduce_kwargs
        )

        self.is_built = True
        print("══ 构建完成 ══\n")
        return self

    # € € € Step 1:  €  € ″ € € € € € € € € € € € € € € € € € € € € € € € €

    def _assemble_open_loop(self):
        """
        鏋勫缓鍏ㄩ樁杞瓙鐨勭粺涓€杈撳叆 (B_all) 鍜岃緭鍑?(C_all) 鐭╅樀锛?        杩斿洖 StateSpace 瀵硅薄渚涘悗缁檷闃躲€?        """
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

    # € € € Step 3:  ﹀ € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € €

    def _couple_bearings(self, sys_rotor):
        """鍦紙鍙兘宸查檷闃剁殑锛夎浆瀛愮姸鎬佺┖闂翠腑闂幆鑰﹀悎杞存壙涓庝己鏈嶉榾"""
        Arr = np.array(sys_rotor.A)
        Brr = np.array(sys_rotor.B)
        Crr = np.array(sys_rotor.C)

        Nb = len(self.bearings)
        Ar_closed = Arr.copy()

        A_rv_list, Av_list, Bv_list, Cv_list = [], [], [], []
        H_sensor_list = []

        for i, b in enumerate(self.bearings):
            # € B/C ╅   i 
            B_act_i  = Brr[:, 2*i : 2*i+2]
            C_disp_i = Crr[2*i : 2*i+2, :]
            C_vel_i  = Crr[2*Nb + 2*i : 2*Nb + 2*i+2, :]
            C_sen_i  = Crr[4*Nb + 2*i : 4*Nb + 2*i+2, :]

            # /  
            Ar_closed -= (B_act_i @ b.K @ C_disp_i + B_act_i @ b.C @ C_vel_i)

            # € € ┖ ?(x/y ? ?block_diag)
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

        # ╅
        if self.unbalance_nodes:
            B_d_rotor = Brr[:, 2*Nb : 2*Nb + 2*len(self.unbalance_nodes)]
            self.B_d = np.block([
                [B_d_rotor],
                [np.zeros((nv, B_d_rotor.shape[1]))]
            ])
        else:
            self.B_d = np.zeros((self.A_nom.shape[0], 0))

    # € € € Step 4: LQG + DOB  € € € € € € € € € € € € € € € € € € € € € € € € € € € € €

    def _design_controller(self):
        """璁捐鎵╁紶瑙傛祴鍣ㄥ拰 LQR 鍙嶉"""
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
        """姝ｅ鸡璋愭尝鎵╁紶瑙傛祴鍣?(Harmonic ESO) 鍒嗘敮"""
        print("  [ESO] 鍚敤姝ｅ鸡骞叉壈鎵╁紶瑙傛祴鍣?")
        n_dist_channels = self.B_d.shape[1]

        # ā ㈡ ″ [[0, ],[- ,0]]
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

        # 
        self.K_dob = pinv(self.B_nom) @ (self.B_d @ C_dist)
        K_aug = np.hstack([self.K_lqr, self.K_dob])

        Ak = A_aug - B_aug @ K_aug - L_kf @ C_aug
        Bk = L_kf
        Ck = -K_aug
        Dk = np.zeros((Ck.shape[0], Bk.shape[1]))   # (n_output n_input)

        return Ak, Bk, Ck, Dk

    def _design_standard_branch(self, A_design):
        """鏍囧噯鍏ㄩ樁 LQG 瑙傛祴鍣ㄥ垎鏀?"""
        print("  [LQG] 浣跨敤鏍囧噯鍏ㄩ樁瑙傛祴鍣?")
        G = np.eye(self.A_nom.shape[0])
        L_kf, _, _ = lqe(A_design, G, self.C_nom, self.Qn, self.Rn)

        Ak = self.A_nom - self.B_nom @ self.K_lqr - L_kf @ self.C_nom
        Bk = L_kf
        Ck = -self.K_lqr
        Dk = np.zeros((self.B_nom.shape[1], self.C_nom.shape[0]))

        return Ak, Bk, Ck, Dk

    # € € € Step 5: у ㄩ ?+ ? € € € € € € € € € € € € € € € € € € € € € € € €

    def apply_reduction_and_discretize(self, reduce_func=None,
                                        reduce_kwargs=None, plot_bode=False):
        """
        瀵规帶鍒跺緥绯荤粺鎵ц锛堝彲閫夌殑锛夐檷闃讹紝鐒跺悗 Tustin 绂绘暎鍖栥€?
        参数
        ----
        reduce_func : callable 鎴?None
            闄嶉樁鍑芥暟锛岀鍚嶅悓 rotor_reduce_func銆?        reduce_kwargs : dict
        plot_bode : bool
            鏄惁缁樺埗闄嶉樁鍓嶅悗 Bode 瀵规瘮鍥俱€?        """
        reduce_kwargs = reduce_kwargs or {}

        if reduce_func is not None:
            result = reduce_func(self.ctrl_sys_full_c, **reduce_kwargs)
            if isinstance(result, tuple):
                sys_c, self.ctrl_reduce_info = result
            else:
                sys_c, self.ctrl_reduce_info = result, None
            print(f"  鎺у埗鍣ㄩ檷闃? {self.ctrl_sys_full_c.A.shape[0]} 鈫?{sys_c.A.shape[0]} 闃?"
                  f"  ({reduce_func.__name__})")

            if plot_bode:
                self._plot_bode_comparison(
                    self.ctrl_sys_full_c, sys_c,
                    title_suffix=f"({reduce_func.__name__})"
                )
        else:
            sys_c = self.ctrl_sys_full_c
            self.ctrl_reduce_info = None
            print("  鎺у埗鍣ㄤ繚鎸佸叏闃?")

        # Tustin у ㈢ ｅ
        self.active_ctrl_sys_d = c2d(sys_c, self.dt, method='tustin')
        self._init_runtime_state()

    def _plot_bode_comparison(self, sys_full, sys_red, title_suffix=""):
        """缁樺埗鍏ㄩ樁/闄嶉樁鎺у埗鍣?Bode 瀵规瘮鍥?"""
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

    # € € €  ? € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € €

    def _init_runtime_state(self):
        """鍒濆鍖栫鏁ｄ豢鐪熺姸鎬佸悜閲?"""
        n = self.active_ctrl_sys_d.A.shape[0]
        self.t_prev = -1.0
        self.x_hat = np.zeros((n, 1))
        self.x_next = np.zeros((n, 1))
        self.y_current = np.zeros((self.active_ctrl_sys_d.B.shape[1], 1))
        self.u_current = np.zeros((self.active_ctrl_sys_d.C.shape[0], 1))

    def init(self):
        """鍏紑鎺ュ彛锛氶噸缃帶鍒跺櫒浠跨湡鐘舵€?"""
        self._init_runtime_state()

    def input(self, t, y_disp):
        """鎺ユ敹澶氶€氶亾浼犳劅鍣ㄤ綅绉伙紝闅忕墿鐞嗘椂闂存帹杩涚鏁ｇ姸鎬?"""
        self.y_current = np.array(y_disp).reshape(-1, 1)
        if t > self.t_prev:
            self.x_hat = self.x_next
            self.t_prev = t

    def output(self):
        """计算并返回伺服阀控制指令"""
        Ad = self.active_ctrl_sys_d.A
        Bd = self.active_ctrl_sys_d.B
        Cd = self.active_ctrl_sys_d.C
        Dd = self.active_ctrl_sys_d.D

        self.u_current = Cd @ self.x_hat + Dd @ self.y_current
        self.x_next = Ad @ self.x_hat + Bd @ self.y_current

        return self.u_current.flatten()

    # € € € ュ € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € € €

    def print_open_loop_modes(self):
        """鎵撳嵃鍚嶄箟闂幆绯荤粺 A_nom 鐨勬ā鎬佷俊鎭?"""
        if self.A_nom is None:
            raise RuntimeError("璇峰厛璋冪敤 build()銆?")
        modes, _ = compute_modal_info(self.A_nom)
        print_modal_table(
            [{'freq_hz': m['freq_hz'], 'freq_rad': m['freq_rad'],
              'damping': m['damping'], 'is_oscillatory': m['is_oscillatory']}
             for m in modes],
            title="鍚嶄箟闂幆绯荤粺 (A_nom) 妯℃€?"
        )

    def summary(self):
        """鎵撳嵃鎺у埗鍣ㄦ憳瑕佷俊鎭?"""
        if not self.is_built:
            print("鎺у埗鍣ㄥ皻鏈瀯寤猴紝璇峰厛璋冪敤 build()銆?")
            return
        n_full = self.ctrl_sys_full_c.A.shape[0]
        n_disc = self.active_ctrl_sys_d.A.shape[0]
        print(f"\n鈹屸攢鈹€鈹€ ALBLQGController 鎽樿 鈹€鈹€鈹€鈹?")
        print(f"鈹?杞存壙鏁?      : {len(self.bearings):<14d}鈹?")
        print(f"鈹?ESO          : {'鍚敤' if self.eso_enable else '绂佺敤':<14s}鈹?")
        print(f"鈹?鍚嶄箟绯荤粺闃舵暟 : {self.A_nom.shape[0]:<14d}鈹?")
        print(f"鈹?鎺у埗鍣ㄥ叏闃?  : {n_full:<14d}鈹?")
        print(f"鈹?鎺у埗鍣ㄧ鏁ｉ樁 : {n_disc:<14d}鈹?")
        print(f"鈹?閲囨牱鍛ㄦ湡     : {self.dt:<14g}鈹?")
        print(f"鈹?宸ヤ綔棰戠巼     : {self.freq:<12g}Hz鈹?")
        print(f"鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹榎n")

    def plot_rotor_reduction(self, reduce_func, reduce_kwargs=None, channel=(0, 0)):
        """
        缁樺埗杞瓙寮€鐜ā鍨嬮檷闃跺墠鍚庣殑 Bode 鍥惧姣旓紝鐢ㄤ簬楠岃瘉闄嶉樁淇濈湡搴︺€?
        参数
        ----
        reduce_func : callable
            杞瓙闄嶉樁鍑芥暟锛堝 balanced_truncation 鎴?robust_modal_truncation_by_frequency锛?        reduce_kwargs : dict, optional
            闄嶉樁鍑芥暟鐨勫弬鏁板瓧鍏?        channel : tuple (out_idx, in_idx), optional
            瑕佺粯鍒剁殑 MIMO 閫氶亾绱㈠紩銆傞粯璁?(0, 0) 琛ㄧず绗?0 涓紶鎰熷櫒杈撳嚭瀵瑰簲绗?0 涓帶鍒惰緭鍏ョ殑棰戝搷銆?        """
        reduce_kwargs = reduce_kwargs or {}

        print(f"  [楠岃瘉] 姝ｅ湪缁勮鍏ㄩ樁寮€鐜浆瀛愭ā鍨?..")
        sys_full = self._assemble_open_loop()
        n_full = sys_full.A.shape[0]

        print(f"  [楠岃瘉] 姝ｅ湪搴旂敤 {reduce_func.__name__} 杩涜闄嶉樁...")
        result = reduce_func(sys_full, **reduce_kwargs)
        if isinstance(result, tuple):
            sys_reduced, info = result
        else:
            sys_reduced, info = result, None

        n_red = sys_reduced.A.shape[0]
        out_idx, in_idx = channel

        # € ラ€ ㈠ 
        if out_idx >= sys_full.C.shape[0] or in_idx >= sys_full.B.shape[1]:
            raise ValueError(f"閫氶亾瓒婄晫锛佸綋鍓嶇郴缁熷叡鏈?{sys_full.B.shape[1]} 涓緭鍏? {sys_full.C.shape[0]} 涓緭鍑恒€?")

        print(f"  [验证] 绘制通道: 输出 {out_idx} <- 输入 {in_idx}")

        # SISO 
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


# ?# ュ ?Schur В ā ?# ?
def compute_modal_info(A):
    """
    [瀹夊叏鍗囩骇鐗圿 鍩轰簬鏈夊簭瀹?Schur 鍒嗚В鎻愬彇妯℃€佺墿鐞嗗弬鏁般€?    褰诲簳閬垮厤鐗瑰緛鍚戦噺鐭╅樀楂樺害鐥呮€佸鑷寸殑姹傞€嗗穿婧冦€?    """
    T_s, Z = schur(A, output='real')
    n = A.shape[0]
    modes = []

    i = 0
    while i < n:
        # € ユ ︿ 2x2  ℃€ (  0)
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
            # 1x1 ℃€
            lam = T_s[i, i]
            omega_n = np.abs(lam)
            zeta = 1.0 if lam <= 0 else -1.0
            modes.append(
                {'eigenvalue': lam, 'index': i, 'freq_hz': omega_n / (2 * np.pi), 'freq_rad': omega_n, 'damping': zeta,
                 'is_oscillatory': False})
            i += 1

    return modes, Z


def print_modal_table(modal_info, title="妯℃€佷俊鎭〃"):
    """缇庤鎵撳嵃妯℃€佷俊鎭〃鏍?(閫傞厤 Schur 杈撳嚭)"""
    print(f"\n{'=' * 58}")
    print(f"  {title}")
    print(f"{'=' * 58}")
    header = f"{'搴忓彿':>4s}  {'棰戠巼(Hz)':>10s}  {'棰戠巼(rad/s)':>12s}  {'闃诲凹姣?':>8s}  {'绫诲瀷':>6s}"
    print(header)
    print('-' * 58)
    for k, m in enumerate(modal_info):
        row = f"{m['index']:4d}  {m['freq_hz']:10.3f}  {m['freq_rad']:12.3f}  {m['damping']:8.5f}  "
        row += f"{'鎸崱':>6s}" if m['is_oscillatory'] else f"{'瀹炴暟':>6s}"
        print(row)
    print(f"{'=' * 58}\n")


# ?#  (Robust Truncation)
# ?
def robust_modal_truncation_by_frequency(sys, freq_range_hz, alpha=0.0):
    """鎸夐鐜囩獥鍙ｇ殑妯℃€佹埅鏂?(Schur 鐗堟湰)"""
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
    """鎸夐樆灏兼瘮鎺掑簭鐨勬ā鎬佹埅鏂?(Schur 鐗堟湰)"""
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
    """鎵嬪姩鎸囧畾淇濈暀妯℃€佺储寮曟埅鏂?(Schur 鐗堟湰)"""
    A, B, C = np.array(sys.A), np.array(sys.B), np.array(sys.C)

    if alpha > 0: A = A - alpha * np.eye(A.shape[0])

    modes, _ = compute_modal_info(A)
    # ㄦ €? kept_eigvals = [m['eigenvalue'] for m in modes if m['index'] in keep_indices]

    def index_filter(lmbda):
        #  € € 
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
    """
    鎸夋ā鎬佸彲鎺?鍙搴︿富瀵兼€ф埅鏂殑缁堟瀬椴佹鐗堟湰銆?    銆愭牳蹇冩暟瀛﹀師鐞嗐€戯細骞宠　鎴柇 (Balanced Truncation) 鍦ㄦ暟瀛︿笂姝ｆ槸妯℃€佷富瀵煎害鐨勬渶绮剧‘銆佹渶椴佹鐨勫疄鐜板舰寮忥紒
    鍥犳锛屾湰鏂规硶鐩存帴璋冪敤鍩轰簬鍙帶/鍙鏍兼媺濮嗙煩闃电殑 balanced_truncation銆?    """
    sys_r = balanced_truncation(sys, order, alpha=alpha)
    return sys_r, {'kept_order': sys_r.A.shape[0], 'method': 'Robust Dominance (Balanced Truncation)'}
