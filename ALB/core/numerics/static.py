# coding: utf-8
import numpy as np
from numba import njit
from numpy import cos, sin


@njit(nogil=True)
def calc_ke(h: np.ndarray, lr: float, lz: float, lx: float) -> np.ndarray:
    """
    Compute the element stiffness matrix for a 4-node lubrication element.
    """
    h0 = h[0]
    h1 = h[1]
    h2 = h[2]
    h3 = h[3]
    h0_3 = h0**3
    h1_3 = h1**3
    h2_3 = h2**3
    h3_3 = h3**3
    lx_2 = lx**2
    lz_2 = lz**2
    lr_2 = lr**2
    ke = np.array(
        [
            [
                (
                    (h0_3 * lx_2) / 8
                    + (h1_3 * lx_2) / 24
                    + (h2_3 * lx_2) / 8
                    + (h3_3 * lx_2) / 24
                )
                / (lx * lz)
                + (
                    lz
                    * (
                        (h0_3 * lr_2) / 8
                        + (h1_3 * lr_2) / 8
                        + (h2_3 * lr_2) / 24
                        + (h3_3 * lr_2) / 24
                    )
                )
                / lx,
                0,
                0,
                0,
            ],
            [
                (
                    (h0_3 * lx_2) / 24
                    + (h1_3 * lx_2) / 24
                    + (h2_3 * lx_2) / 24
                    + (h3_3 * lx_2) / 24
                )
                / (lx * lz)
                - (
                    lz
                    * (
                        (h0_3 * lr_2) / 8
                        + (h1_3 * lr_2) / 8
                        + (h2_3 * lr_2) / 24
                        + (h3_3 * lr_2) / 24
                    )
                )
                / lx,
                (
                    (h0_3 * lx_2) / 24
                    + (h1_3 * lx_2) / 8
                    + (h2_3 * lx_2) / 24
                    + (h3_3 * lx_2) / 8
                )
                / (lx * lz)
                + (
                    lz
                    * (
                        (h0_3 * lr_2) / 8
                        + (h1_3 * lr_2) / 8
                        + (h2_3 * lr_2) / 24
                        + (h3_3 * lr_2) / 24
                    )
                )
                / lx,
                0,
                0,
            ],
            [
                (
                    lz
                    * (
                        (h0_3 * lr_2) / 24
                        + (h1_3 * lr_2) / 24
                        + (h2_3 * lr_2) / 24
                        + (h3_3 * lr_2) / 24
                    )
                )
                / lx
                - (
                    (h0_3 * lx_2) / 8
                    + (h1_3 * lx_2) / 24
                    + (h2_3 * lx_2) / 8
                    + (h3_3 * lx_2) / 24
                )
                / (lx * lz),
                -((lx_2 + lr_2 * lz_2) * (h0_3 + h1_3 + h2_3 + h3_3)) / (24 * lx * lz),
                (
                    (h0_3 * lx_2) / 8
                    + (h1_3 * lx_2) / 24
                    + (h2_3 * lx_2) / 8
                    + (h3_3 * lx_2) / 24
                )
                / (lx * lz)
                + (
                    lz
                    * (
                        (h0_3 * lr_2) / 24
                        + (h1_3 * lr_2) / 24
                        + (h2_3 * lr_2) / 8
                        + (h3_3 * lr_2) / 8
                    )
                )
                / lx,
                0,
            ],
            [
                -((lx_2 + lr_2 * lz_2) * (h0_3 + h1_3 + h2_3 + h3_3)) / (24 * lx * lz),
                (
                    lz
                    * (
                        (h0_3 * lr_2) / 24
                        + (h1_3 * lr_2) / 24
                        + (h2_3 * lr_2) / 24
                        + (h3_3 * lr_2) / 24
                    )
                )
                / lx
                - (
                    (h0_3 * lx_2) / 24
                    + (h1_3 * lx_2) / 8
                    + (h2_3 * lx_2) / 24
                    + (h3_3 * lx_2) / 8
                )
                / (lx * lz),
                (
                    (h0_3 * lx_2) / 24
                    + (h1_3 * lx_2) / 24
                    + (h2_3 * lx_2) / 24
                    + (h3_3 * lx_2) / 24
                )
                / (lx * lz)
                - (
                    lz
                    * (
                        (h0_3 * lr_2) / 24
                        + (h1_3 * lr_2) / 24
                        + (h2_3 * lr_2) / 8
                        + (h3_3 * lr_2) / 8
                    )
                )
                / lx,
                (
                    (h0_3 * lx_2) / 24
                    + (h1_3 * lx_2) / 8
                    + (h2_3 * lx_2) / 24
                    + (h3_3 * lx_2) / 8
                )
                / (lx * lz)
                + (
                    lz
                    * (
                        (h0_3 * lr_2) / 24
                        + (h1_3 * lr_2) / 24
                        + (h2_3 * lr_2) / 8
                        + (h3_3 * lr_2) / 8
                    )
                )
                / lx,
            ],
        ]
    )
    eon = ke.shape[0]
    for i in range(eon):
        for j in range(eon - 1 - i):
            ke[i, j + i + 1] = ke[j + i + 1, i]
    return ke


@njit
def calc_fe(h: np.ndarray, lz: float, lambda_value: float) -> np.ndarray:
    """
    Compute the element force vector induced by surface velocity.
    """
    h0 = h[0]
    h1 = h[1]
    h2 = h[2]
    h3 = h[3]
    fe = np.array(
        [
            -(lz * lambda_value * (2 * h0 + 2 * h1 + h2 + h3)) / 12,
            (lz * lambda_value * (2 * h0 + 2 * h1 + h2 + h3)) / 12,
            -(lz * lambda_value * (h0 + h1 + 2 * h2 + 2 * h3)) / 12,
            (lz * lambda_value * (h0 + h1 + 2 * h2 + 2 * h3)) / 12,
        ]
    )
    return fe


@njit
def calc_fe_vf(x0, lx, lz, lambda_value, vf, xct, yct) -> np.ndarray:
    """
    Compute the element force vector with feedforward velocity terms.
    """
    fe = np.array(
        [
            -(
                lz
                * vf
                * lambda_value
                * (
                    yct * cos(lx + x0)
                    - xct * sin(lx + x0)
                    - yct * cos(x0)
                    + xct * sin(x0)
                    + lx * xct * cos(x0)
                    + lx * yct * sin(x0)
                )
            )
            / lx,
            (
                lz
                * vf
                * lambda_value
                * (
                    yct * cos(lx + x0)
                    - xct * sin(lx + x0)
                    - yct * cos(x0)
                    + xct * sin(x0)
                    + lx * xct * cos(lx + x0)
                    + lx * yct * sin(lx + x0)
                )
            )
            / lx,
            -(
                lz
                * vf
                * lambda_value
                * (
                    yct * cos(lx + x0)
                    - xct * sin(lx + x0)
                    - yct * cos(x0)
                    + xct * sin(x0)
                    + lx * xct * cos(x0)
                    + lx * yct * sin(x0)
                )
            )
            / lx,
            (
                lz
                * vf
                * lambda_value
                * (
                    yct * cos(lx + x0)
                    - xct * sin(lx + x0)
                    - yct * cos(x0)
                    + xct * sin(x0)
                    + lx * xct * cos(lx + x0)
                    + lx * yct * sin(lx + x0)
                )
            )
            / lx,
        ]
    )
    return fe


intpoint = np.array(
    [
        -0.932469514203152,
        -0.661209386466265,
        -0.238619186083,
        0.238619186083,
        0.661209386466265,
        0.932469514203152,
    ]
)
weight = np.array(
    [
        0.171324492379170,
        0.360761573048139,
        0.467913934572691,
        0.467913934572691,
        0.360761573048139,
        0.171324492379170,
    ]
)



