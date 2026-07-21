"""State-space model reduction utilities for the LQG controller."""

import numpy as np
from scipy.linalg import block_diag, schur, ordqz
from control.matlab import ss, balred


# Encoding-repaired comment.
# Encoding-repaired comment.
def alpha_shift(sys, alpha):
    """Alpha shift helper."""
    A_shifted = np.array(sys.A) - alpha * np.eye(sys.A.shape[0])
    return ss(A_shifted, sys.B, sys.C, sys.D)


def alpha_unshift(sys, alpha):
    """Alpha unshift helper."""
    A_restored = np.array(sys.A) + alpha * np.eye(sys.A.shape[0])
    return ss(A_restored, sys.B, sys.C, sys.D)


def compute_modal_info(A):
    """Compute modal info helper."""
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
            # Encoding-repaired comment.
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
    """To real modal form helper."""
    n = A.shape[0]
    eigvals, eigvecs = np.linalg.eig(A)

    # Encoding-repaired comment.
    order = np.argsort(np.abs(np.imag(eigvals)))
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    # Encoding-repaired comment.
    T_cols = []
    block_sizes = []
    modal_info = []
    i = 0
    while i < n:
        lam = eigvals[i]
        if np.abs(np.imag(lam)) > 1e-10:
            # Encoding-repaired comment.
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
            i += 2  # Encoding-repaired comment.
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

    # Encoding-repaired comment.
    offset = 0
    for bs in block_sizes:
        blk = Am[offset:offset + bs, offset:offset + bs]
        Am[offset:offset + bs, :] = 0.0
        Am[:, offset:offset + bs] = 0.0
        Am[offset:offset + bs, offset:offset + bs] = blk
        offset += bs

    return Am, Bm, Cm, T, block_sizes, modal_info


def _truncate_modal(Am, Bm, Cm, block_sizes, modal_info, keep_mask):
    """Truncate modal helper."""
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


def print_modal_table(modal_info, block_sizes=None, title="Modal information"):
    """Print modal table helper."""
    print(f"\n{'=' * 64}")
    print(f"  {title}")
    print(f"{'=' * 64}")
    header = f"Controller status."
    if block_sizes is not None:
        header += f"Controller status."
    print(header)
    print('-' * 64)
    for k, m in enumerate(modal_info):
        row = f"{k:4d}  {m['freq_hz']:10.3f}  {m['freq_rad']:12.3f}  {m['damping']:8.5f}  "
        row += f"Controller status." if m['is_oscillatory'] else f"Controller status."
        if block_sizes is not None:
            row += f"  {block_sizes[k]:4d}"
        print(row)
    print(f"{'=' * 64}\n")


# Encoding-repaired comment.
# Encoding-repaired comment.
# ython-control StateSpace
# Encoding-repaired comment.
#
# Encoding-repaired comment.
def balanced_truncation(sys, order, alpha=1e-2):
    """Balanced truncation helper."""
    sys_s = alpha_shift(sys, alpha)
    sys_r = balred(sys_s, order)
    sys_r = alpha_unshift(sys_r, alpha)
    return sys_r


def modal_truncation_by_damping(sys, order, alpha=0.0):
    """Modal truncation by damping helper."""
    A = np.array(sys.A)
    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    Am, Bm, Cm, T, block_sizes, modal_info = to_real_modal_form(
        A, np.array(sys.B), np.array(sys.C)
    )

    # Encoding-repaired comment.
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
    """Modal truncation by frequency helper."""
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
    """Modal truncation by dominance helper."""
    A = np.array(sys.A)
    if alpha > 0:
        A = A - alpha * np.eye(A.shape[0])

    Am, Bm, Cm, T, block_sizes, modal_info = to_real_modal_form(
        A, np.array(sys.B), np.array(sys.C)
    )

    # Encoding-repaired comment.
    gains = []
    offset = 0
    for bs in block_sizes:
        Bi = Bm[offset:offset + bs, :]
        Ci = Cm[:, offset:offset + bs]
        # Encoding-repaired comment.
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
    """Modal truncation by index helper."""
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
