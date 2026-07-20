# coding: utf-8
import numba
import numpy as np


@numba.jit(nopython=True, nogil=True)
def gauss_seidel_iteration_film(k: np.ndarray, f: np.ndarray, x0: np.ndarray, p0: np.ndarray, error_set=1e-10, n=10,
                                damp=1, reynold=False):
    """
    Gauss-Seidel iteration, not suitable for general equation solving; modified for Newton iteration format and Reynolds boundary conditions
    :param reynold: Whether to use Reynolds boundary conditions
    :param damp: Damping factor
    :param n: Maximum number of iterations
    :param error_set: Error tolerance
    :param k: Coefficient matrix
    :param f: Right-hand side term
    :param x0: Initial values
    :param p0: Pressure values before iteration
    """
    error = 1.0
    _ = 0
    xk0 = x0.copy()
    xk1 = x0.copy()
    for _ in numba.prange(n):
        for j in numba.prange(len(xk0)):
            k0 = np.ascontiguousarray(k[j, :j])
            k1 = np.ascontiguousarray(k[j, j + 1:])
            xk1[j] = 1 / k[j, j] * (f[j] - k0.dot(xk1[:j]) - k1.dot(xk0[j + 1:]))
            xk1[j] = xk0[j] + damp * (xk1[j] - xk0[j])
        if reynold:
            xk1 = np.maximum(xk1, -p0)
        temp = np.linalg.norm(xk0, ord=2)
        if temp == 0:
            error = 1.0
        else:
            error = np.linalg.norm(xk1 - xk0, ord=2) / temp
        if error < error_set:
            break
        xk0 = xk1.copy()
    return xk1, _, error


@numba.jit(nopython=True, nogil=True)
def gauss_seidel_iteration_matrix(k: np.ndarray, f: np.ndarray, x0: np.ndarray, p0: np.ndarray, error_set=1e-10, n=10,
                                  damp=1, reynold=False):
    """
    Gauss-Seidel iteration, matrix form; modified for Newton iteration format and Reynolds boundary conditions
    :param reynold: Whether to use Reynolds boundary conditions
    :param damp: Damping factor
    :param n: Maximum number of iterations
    :param error_set: Error tolerance
    :param k: Coefficient matrix
    :param f: Right-hand side term
    :param x0: Initial values
    :param p0: Pressure values before iteration
    """
    error = 1.0
    _ = 0
    xk0 = x0.copy()
    xk1 = x0.copy()
    DL = np.tril(k)
    U = np.triu(k, 1)
    inv_DL = np.linalg.inv(DL)
    B = inv_DL.dot(U)
    C = inv_DL.dot(f)
    for _ in numba.prange(n):
        xk1 = - B.dot(xk1) + C
        xk1 = xk0 + damp * (xk1 - xk0)
        if reynold:
            xk1 = np.maximum(xk1, -p0)
        temp = np.linalg.norm(xk0, ord=2)
        if temp == 0:
            error = 1.0
        else:
            error = np.linalg.norm(xk1 - xk0, ord=2) / temp
        if error < error_set:
            break
        xk0 = xk1.copy()
    return xk1, _, error

