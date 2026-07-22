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

def alpha_shift(sys, alpha):
    """Shift system A-matrix by -alpha*I for numerically safer reduction."""
    A_shifted = np.array(sys.A) - alpha * np.eye(sys.A.shape[0])
    return ss(A_shifted, sys.B, sys.C, sys.D)

def alpha_unshift(sys, alpha):
    """Restore a previously alpha-shifted system by adding alpha*I back."""
    A_restored = np.array(sys.A) + alpha * np.eye(sys.A.shape[0])
    return ss(A_restored, sys.B, sys.C, sys.D)

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

__all__ = ['alpha_shift', 'alpha_unshift', 'balanced_truncation', 'compute_modal_info', 'print_modal_table', 'modal_truncation_by_frequency', 'modal_truncation_by_damping', 'modal_truncation_by_index', 'modal_truncation_by_dominance', 'balreal']
