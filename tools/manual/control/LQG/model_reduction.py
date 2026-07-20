"""
model_reduction.py
==================
鐙珛鐨勬ā鍨嬮檷闃跺伐鍏峰嚱鏁伴泦锛屽彲涓庝换鎰?python-control 鐘舵€佺┖闂村璞＄粍鍚堜娇鐢ㄣ€?
鏀寔鐨勯檷闃剁瓥鐣ワ細
    平衡截断 (Balanced Truncation)。
    2. 鎸夐樆灏兼瘮鎺掑簭鐨勬ā鎬佹埅鏂?                    鈥?modal_truncation_by_damping()
    3. 鎸夐鐜囩獥鍙ｇ殑妯℃€佹埅鏂?                      鈥?modal_truncation_by_frequency()
    4. 鎸夋ā鎬佸彲鎺?鍙 Grammian 鐨勬ā鎬佹埅鏂?        鈥?modal_truncation_by_dominance()
    5. 鎵嬪姩鎸囧畾淇濈暀妯℃€佺储寮?                      鈥?modal_truncation_by_index()

杈呭姪宸ュ叿锛?    - compute_modal_info()       鐗瑰緛鍊煎垎瑙?+ 鐗╃悊鍙傛暟鎻愬彇
    - to_real_modal_form()       澶嶆ā鎬?鈫?瀹炲潡瀵硅妯℃€佸潗鏍?    - alpha_shift / unshift      涓虹函铏氳酱/鍘熺偣鏋佺偣鎻愪緵鏁板€肩ǔ瀹氭€?
璁捐鍘熷垯锛?    * 鎵€鏈夊嚱鏁板潎涓虹函鍑芥暟锛屾棤鍓綔鐢紝涓嶄緷璧栫被瀹炰緥
    * 杈撳叆/杈撳嚭鍧囦负 python-control 鐨?StateSpace 瀵硅薄 (鎴?numpy 矩阵)
    * 通过组合而非继承来集成至 ALBLQGController
"""

import numpy as np
from scipy.linalg import block_diag, schur, ordqz
from control.matlab import ss, balred


# ?# ュ
# ?
def alpha_shift(sys, alpha):
    """瀵圭郴缁熺煩闃?A 鏂藉姞琛板噺骞崇Щ  A 鈫?A - 伪路I锛屼娇铏氳酱鏋佺偣鍙樹负绋冲畾"""
    A_shifted = np.array(sys.A) - alpha * np.eye(sys.A.shape[0])
    return ss(A_shifted, sys.B, sys.C, sys.D)


def alpha_unshift(sys, alpha):
    """鍙嶅悜骞崇Щ鎭㈠鍘熺墿鐞嗘瀬鐐? A 鈫?A + 伪路I"""
    A_restored = np.array(sys.A) + alpha * np.eye(sys.A.shape[0])
    return ss(A_restored, sys.B, sys.C, sys.D)


def compute_modal_info(A):
    """
    瀵圭郴缁熺煩闃?A 鍋氱壒寰佸€煎垎瑙ｏ紝鎻愬彇姣忎釜妯℃€佺殑鐗╃悊鍙傛暟銆?
    返回
    ----
    modes : list[dict]
        每个元素包含:
        - 'eigenvalue'  : 澶嶇壒寰佸€?位
        - 'index'       : 鍦ㄥ師濮嬬壒寰佸€兼暟缁勪腑鐨勪笅鏍?        - 'freq_hz'     : 鍥烘湁棰戠巼 (Hz)
        - 'freq_rad'    : 固有频率 (rad/s)
        - 'damping'     : 闃诲凹姣?味  (璐熷疄閮?妯?鈫?鈮?)
        - 'is_oscillatory' : 鏄惁涓烘尟鑽℃ā鎬侊紙澶嶅叡杞锛?    eigvecs : ndarray
        鐗瑰緛鍚戦噺鐭╅樀 (鍒楀悜閲?
    """
    eigvals, eigvecs = np.linalg.eig(A)

    modes = []
    visited = set()
    for i, lam in enumerate(eigvals):
        if i in visited:
            continue

        omega_n = np.abs(lam)
        freq_hz = omega_n / (2 * np.pi) if omega_n > 1e-14 else 0.0
        zeta = -np.real(lam) / omega_n if omega_n > 1e-14 else 1.0

        is_osc = np.abs(np.imag(lam)) > 1e-10

        mode_info = {
            'eigenvalue': lam,
            'index': i,
            'freq_hz': freq_hz,
            'freq_rad': omega_n,
            'damping': zeta,
            'is_oscillatory': is_osc,
        }

        if is_osc:
            # 
            conj_idx = None
            for j in range(i + 1, len(eigvals)):
                if j not in visited and np.abs(eigvals[j] - np.conj(lam)) < 1e-10 * max(1, omega_n):
                    conj_idx = j
                    break
            mode_info['conjugate_index'] = conj_idx
            if conj_idx is not None:
                visited.add(conj_idx)

        modes.append(mode_info)
        visited.add(i)

    return modes, eigvecs


def to_real_modal_form(A, B, C):
    """
    灏嗙姸鎬佺┖闂?(A, B, C) 鍙樻崲鍒板疄鍧楀瑙掓ā鎬佸潗鏍囥€?
    鎸崱妯℃€?鈫?2脳2 鍧? [[蟽, 蠅], [-蠅, 蟽]]
    闈炴尟鑽℃ā鎬?鈫?1脳1 鍧?[位_real]

    返回
    ----
    Am, Bm, Cm : ndarray
        妯℃€佸潗鏍囦笅鐨勭郴缁熺煩闃?    T : ndarray
        变换矩阵 (x_physical = T @ x_modal)
    block_sizes : list[int]
        姣忎釜妯℃€佸潡鐨勫昂瀵?(2 鎴?1)锛岀敤浜庡悗缁寜鍧楁埅鏂?    modal_info : list[dict]
        涓?block_sizes 涓€涓€瀵瑰簲鐨勬ā鎬佺墿鐞嗕俊鎭?    """
    n = A.shape[0]
    eigvals, eigvecs = np.linalg.eig(A)

    #   €
    order = np.argsort(np.abs(np.imag(eigvals)))
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    # € ╅
    T_cols = []
    block_sizes = []
    modal_info = []
    i = 0
    while i < n:
        lam = eigvals[i]
        if np.abs(np.imag(lam)) > 1e-10:
            #  ℃€ ㄥ ゅ
            v = eigvecs[:, i]
            T_cols.append(np.real(v))
            T_cols.append(np.imag(v))
            omega_n = np.abs(lam)
            modal_info.append({
                'eigenvalue': lam,
                'freq_hz': omega_n / (2 * np.pi),
                'freq_rad': omega_n,
                'damping': -np.real(lam) / omega_n if omega_n > 1e-14 else 1.0,
                'is_oscillatory': True,
            })
            block_sizes.append(2)
            i += 2  # ? else:
            T_cols.append(np.real(eigvecs[:, i]))
            real_lam = np.real(lam)
            modal_info.append({
                'eigenvalue': lam,
                'freq_hz': np.abs(real_lam) / (2 * np.pi),
                'freq_rad': np.abs(real_lam),
                'damping': 1.0 if real_lam <= 0 else -1.0,
                'is_oscillatory': False,
            })
            block_sizes.append(1)
            i += 1

    T = np.column_stack(T_cols)
    T_inv = np.linalg.inv(T)

    Am = T_inv @ A @ T
    Bm = T_inv @ B
    Cm = C @ T

    # €  
    offset = 0
    for bs in block_sizes:
        blk = Am[offset:offset + bs, offset:offset + bs]
        Am[offset:offset + bs, :] = 0.0
        Am[:, offset:offset + bs] = 0.0
        Am[offset:offset + bs, offset:offset + bs] = blk
        offset += bs

    return Am, Bm, Cm, T, block_sizes, modal_info


def _truncate_modal(Am, Bm, Cm, block_sizes, modal_info, keep_mask):
    """
    鍐呴儴宸ュ叿锛氭牴鎹竷灏旀帺鐮佹埅鏂ā鎬佸潡銆?
    参数
    ----
    keep_mask : list[bool]
        涓?block_sizes 绛夐暱锛孴rue 琛ㄧず淇濈暀璇ユā鎬?
    返回
    ----
    Ar, Br, Cr : ndarray  (闄嶉樁鍚庣殑妯℃€佸潗鏍囩煩闃?
    kept_info  : list[dict]
    """
    keep_indices = []
    offset = 0
    kept_info = []
    for k, bs in enumerate(block_sizes):
        if keep_mask[k]:
            keep_indices.extend(range(offset, offset + bs))
            kept_info.append(modal_info[k])
        offset += bs

    idx = np.array(keep_indices)
    Ar = Am[np.ix_(idx, idx)]
    Br = Bm[idx, :]
    Cr = Cm[:, idx]
    return Ar, Br, Cr, kept_info


def print_modal_table(modal_info, block_sizes=None, title="妯℃€佷俊鎭〃"):
    """缇庤鎵撳嵃妯℃€佷俊鎭〃鏍?"""
    print(f"\n{'=' * 64}")
    print(f"  {title}")
    print(f"{'=' * 64}")
    header = f"{'搴忓彿':>4s}  {'棰戠巼(Hz)':>10s}  {'棰戠巼(rad/s)':>12s}  {'闃诲凹姣?':>8s}  {'绫诲瀷':>6s}"
    if block_sizes is not None:
        header += f"  {'阶数':>4s}"
    print(header)
    print('-' * 64)
    for k, m in enumerate(modal_info):
        row = f"{k:4d}  {m['freq_hz']:10.3f}  {m['freq_rad']:12.3f}  {m['damping']:8.5f}  "
        row += f"{'鎸崱':>6s}" if m['is_oscillatory'] else f"{'瀹炴暟':>6s}"
        if block_sizes is not None:
            row += f"  {block_sizes[k]:4d}"
        print(row)
    print(f"{'=' * 64}\n")


# ?# € ?# ?#
# ﹀ educe_func(sys, **kwargs) -> sys_reduced
# ython-control StateSpace
# ython-control StateSpace ( ?
#
# ょ  ALBLQGController ?
def balanced_truncation(sys, order, alpha=1e-2):
    """
    平衡截断 (Balanced Truncation)。
    通过 alpha-shift 使系统稳定，执行 balred，再反向恢复极点。
    参数
    ----
    sys   : StateSpace  原系统
    alpha : float        衰减平移量 (默认 1e-2)
    """
    sys_s = alpha_shift(sys, alpha)
    sys_r = balred(sys_s, order)
    sys_r = alpha_unshift(sys_r, alpha)
    return sys_r


def modal_truncation_by_damping(sys, order, alpha=0.0):
    """
    鎸夐樆灏兼瘮鎺掑簭鐨勬ā鎬佹埅鏂細淇濈暀闃诲凹姣旀渶灏忥紙鏈€闅捐“鍑忥級鐨勬ā鎬併€?
    瀵逛簬鎸姩鎺у埗闂锛屼綆闃诲凹妯℃€佷富瀵肩郴缁熷搷搴旓紝鍥犳搴斾紭鍏堜繚鐣欍€?
    参数
    ----
    sys   : StateSpace  原系统
    alpha : float        鍙€夌殑 alpha-shift
    """
    A = np.array(sys.A)
    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    Am, Bm, Cm, T, block_sizes, modal_info = to_real_modal_form(
        A, np.array(sys.B), np.array(sys.C)
    )

    # ? ? € ?
    sorted_idx = sorted(range(len(modal_info)),
                        key=lambda k: modal_info[k]['damping'])

    keep_mask = [False] * len(block_sizes)
    total_kept = 0
    for k in sorted_idx:
        if total_kept + block_sizes[k] <= order:
            keep_mask[k] = True
            total_kept += block_sizes[k]

    Ar, Br, Cr, kept_info = _truncate_modal(Am, Bm, Cm, block_sizes, modal_info, keep_mask)

    if alpha > 0:
        Ar = Ar + alpha * np.eye(Ar.shape[0])

    Dr = np.zeros((Cr.shape[0], Br.shape[1]))
    return ss(Ar, Br, Cr, Dr), kept_info


def modal_truncation_by_frequency(sys, freq_range_hz, alpha=0.0):
    """
    鎸夐鐜囩獥鍙ｇ殑妯℃€佹埅鏂細浠呬繚鐣欏浐鏈夐鐜囪惤鍦?[f_low, f_high] 鑼冨洿鍐呯殑妯℃€併€?
    閫傜敤浜庡彧鍏冲績鐗瑰畾杞€熻寖鍥村搷搴旂殑鍦烘櫙銆?
    参数
    ----
    sys           : StateSpace
    freq_range_hz : tuple (f_low, f_high)  单位 Hz
    alpha         : float
    """
    f_low, f_high = freq_range_hz
    A = np.array(sys.A)
    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    Am, Bm, Cm, T, block_sizes, modal_info = to_real_modal_form(
        A, np.array(sys.B), np.array(sys.C)
    )

    keep_mask = []
    for m in modal_info:
        keep_mask.append(f_low <= m['freq_hz'] <= f_high)

    Ar, Br, Cr, kept_info = _truncate_modal(Am, Bm, Cm, block_sizes, modal_info, keep_mask)

    if alpha > 0:
        Ar = Ar + alpha * np.eye(Ar.shape[0])

    Dr = np.zeros((Cr.shape[0], Br.shape[1]))
    return ss(Ar, Br, Cr, Dr), kept_info


def modal_truncation_by_dominance(sys, order, alpha=0.0):
    """
    鎸夋ā鎬佸彲鎺?鍙搴︽帓搴忕殑妯℃€佹埅鏂€?
    瀵规瘡涓ā鎬佸潡璁＄畻鍏跺湪杈撳叆-杈撳嚭閫氶亾涓殑 H2 鑼冩暟璐＄尞锛堟ā鎬佸鐩婏級锛?    淇濈暀璐＄尞鏈€澶х殑妯℃€侊紝淇濊瘉闄嶉樁鍚庡杈撳叆-杈撳嚭琛屼负鐨勪繚鐪熷害鏈€浼樸€?
    参数
    ----
    sys   : StateSpace
    order : int   鐩爣鐘舵€佹暟
    alpha : float
    """
    A = np.array(sys.A)
    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    Am, Bm, Cm, T, block_sizes, modal_info = to_real_modal_form(
        A, np.array(sys.B), np.array(sys.C)
    )

    # ＄ ℃€ ? -
    gains = []
    offset = 0
    for bs in block_sizes:
        Bi = Bm[offset:offset + bs, :]
        Ci = Cm[:, offset:offset + bs]
        # ?Frobenius  ā
        gain = np.linalg.norm(Ci, 'fro') * np.linalg.norm(Bi, 'fro')
        gains.append(gain)
        offset += bs

    sorted_idx = sorted(range(len(gains)), key=lambda k: -gains[k])

    keep_mask = [False] * len(block_sizes)
    total_kept = 0
    for k in sorted_idx:
        if total_kept + block_sizes[k] <= order:
            keep_mask[k] = True
            total_kept += block_sizes[k]

    Ar, Br, Cr, kept_info = _truncate_modal(Am, Bm, Cm, block_sizes, modal_info, keep_mask)

    if alpha > 0:
        Ar = Ar + alpha * np.eye(Ar.shape[0])

    Dr = np.zeros((Cr.shape[0], Br.shape[1]))
    return ss(Ar, Br, Cr, Dr), kept_info


def modal_truncation_by_index(sys, keep_indices, alpha=0.0):
    """
    鎵嬪姩鎸囧畾淇濈暀妯℃€佺储寮曡繘琛屾埅鏂€?
    閰嶅悎 compute_modal_info() 鎴?print_modal_table() 浣跨敤锛?    鐢ㄦ埛鏍规嵁妯℃€佽〃鎵嬪姩閫夊彇鎰熷叴瓒ｇ殑妯℃€併€?
    参数
    ----
    sys          : StateSpace
    keep_indices : list[int]  瑕佷繚鐣欑殑妯℃€佸簭鍙凤紙瀵瑰簲 modal_info 鍒楄〃涓嬫爣锛?    alpha        : float
    """
    A = np.array(sys.A)
    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    Am, Bm, Cm, T, block_sizes, modal_info = to_real_modal_form(
        A, np.array(sys.B), np.array(sys.C)
    )

    keep_mask = [i in keep_indices for i in range(len(block_sizes))]

    Ar, Br, Cr, kept_info = _truncate_modal(Am, Bm, Cm, block_sizes, modal_info, keep_mask)

    if alpha > 0:
        Ar = Ar + alpha * np.eye(Ar.shape[0])

    Dr = np.zeros((Cr.shape[0], Br.shape[1]))
    return ss(Ar, Br, Cr, Dr), kept_info
