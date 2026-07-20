# coding: utf-8
import numpy as np
from numba import njit


@njit
def calc_ke_dx(x0, lr, lx, lz, h):
    h_2 = h ** 2
    cosx0 = np.cos(x0)
    sinx0 = np.sin(x0)
    coslx = np.cos(x0 + lx)
    sinlx = np.sin(x0 + lx)
    h0_2 = h_2[0]
    h1_2 = h_2[1]
    h2_2 = h_2[2]
    h3_2 = h_2[3]
    ke_dx = np.array([[((6 * cosx0 * h0_2 + 6 * cosx0 * h2_2) * lx ** 3 + (
            18 * h0_2 * sinx0 - 6 * h1_2 * sinx0 + 18 * h2_2 * sinx0 - 6 * h3_2 * sinx0) * lx ** 2 + (
                                24 * cosx0 * h1_2 - 36 * cosx0 * h0_2 - 36 * cosx0 * h2_2 + 24 * cosx0 * h3_2 + 12 * coslx * h1_2 + 12 * coslx * h3_2 + 3 * cosx0 * h0_2 * lr ** 2 * lz ** 2 + cosx0 * h2_2 * lr ** 2 * lz ** 2 - 3 * coslx * h1_2 * lr ** 2 * lz ** 2 - coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                36 * h1_2 * sinx0 - 36 * h0_2 * sinx0 - 36 * h2_2 * sinx0 + 36 * h3_2 * sinx0 + 36 * h0_2 * sinlx - 36 * h1_2 * sinlx + 36 * h2_2 * sinlx - 36 * h3_2 * sinlx + 3 * h0_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h1_2 * lr ** 2 * lz ** 2 * sinx0 + h2_2 * lr ** 2 * lz ** 2 * sinx0 - h3_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h0_2 * lr ** 2 * lz ** 2 * sinlx + 3 * h1_2 * lr ** 2 * lz ** 2 * sinlx - h2_2 * lr ** 2 * lz ** 2 * sinlx + h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                               (4 * lz) * lx ** 3), 0.0, 0.0, 0.0, ], [((
                                                                                - 6 * h0_2 * sinx0 - 6 * h2_2 * sinx0 - 6 * h1_2 * sinlx - 6 * h3_2 * sinlx) * lx ** 2 + (
                                                                                24 * cosx0 * h0_2 - 12 * cosx0 * h1_2 + 24 * cosx0 * h2_2 - 12 * cosx0 * h3_2 + 12 * coslx * h0_2 - 24 * coslx * h1_2 + 12 * coslx * h2_2 - 24 * coslx * h3_2 - 3 * cosx0 * h0_2 * lr ** 2 * lz ** 2 - cosx0 * h2_2 * lr ** 2 * lz ** 2 + 3 * coslx * h1_2 * lr ** 2 * lz ** 2 + coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                                                                36 * h0_2 * sinx0 - 36 * h1_2 * sinx0 + 36 * h2_2 * sinx0 - 36 * h3_2 * sinx0 - 36 * h0_2 * sinlx + 36 * h1_2 * sinlx - 36 * h2_2 * sinlx + 36 * h3_2 * sinlx - 3 * h0_2 * lr ** 2 * lz ** 2 * sinx0 + 3 * h1_2 * lr ** 2 * lz ** 2 * sinx0 - h2_2 * lr ** 2 * lz ** 2 * sinx0 + h3_2 * lr ** 2 * lz ** 2 * sinx0 + 3 * h0_2 * lr ** 2 * lz ** 2 * sinlx - 3 * h1_2 * lr ** 2 * lz ** 2 * sinlx + h2_2 * lr ** 2 * lz ** 2 * sinlx - h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                                                                               (4 * lz) * lx ** 3), (
                                                                               (
                                                                                       - 6 * coslx * h1_2 - 6 * coslx * h3_2) * lx ** 3 + (
                                                                                       18 * h1_2 * sinlx - 6 * h0_2 * sinlx - 6 * h2_2 * sinlx + 18 * h3_2 * sinlx) * lx ** 2 + (
                                                                                       36 * coslx * h1_2 - 12 * cosx0 * h2_2 - 24 * coslx * h0_2 - 12 * cosx0 * h0_2 - 24 * coslx * h2_2 + 36 * coslx * h3_2 + 3 * cosx0 * h0_2 * lr ** 2 * lz ** 2 + cosx0 * h2_2 * lr ** 2 * lz ** 2 - 3 * coslx * h1_2 * lr ** 2 * lz ** 2 - coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                                                                       36 * h1_2 * sinx0 - 36 * h0_2 * sinx0 - 36 * h2_2 * sinx0 + 36 * h3_2 * sinx0 + 36 * h0_2 * sinlx - 36 * h1_2 * sinlx + 36 * h2_2 * sinlx - 36 * h3_2 * sinlx + 3 * h0_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h1_2 * lr ** 2 * lz ** 2 * sinx0 + h2_2 * lr ** 2 * lz ** 2 * sinx0 - h3_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h0_2 * lr ** 2 * lz ** 2 * sinlx + 3 * h1_2 * lr ** 2 * lz ** 2 * sinlx - h2_2 * lr ** 2 * lz ** 2 * sinlx + h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                                                                               (4 * lz) * lx ** 3), 0.0, 0.0, ], [((
                                                                                                                           - 6 * cosx0 * h0_2 - 6 * cosx0 * h2_2) * lx ** 3 + (
                                                                                                                           6 * h1_2 * sinx0 - 18 * h0_2 * sinx0 - 18 * h2_2 * sinx0 + 6 * h3_2 * sinx0) * lx ** 2 + (
                                                                                                                           36 * cosx0 * h0_2 - 24 * cosx0 * h1_2 + 36 * cosx0 * h2_2 - 24 * cosx0 * h3_2 - 12 * coslx * h1_2 - 12 * coslx * h3_2 + cosx0 * h0_2 * lr ** 2 * lz ** 2 + cosx0 * h2_2 * lr ** 2 * lz ** 2 - coslx * h1_2 * lr ** 2 * lz ** 2 - coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                                                                                                           36 * h0_2 * sinx0 - 36 * h1_2 * sinx0 + 36 * h2_2 * sinx0 - 36 * h3_2 * sinx0 - 36 * h0_2 * sinlx + 36 * h1_2 * sinlx - 36 * h2_2 * sinlx + 36 * h3_2 * sinlx + h0_2 * lr ** 2 * lz ** 2 * sinx0 - h1_2 * lr ** 2 * lz ** 2 * sinx0 + h2_2 * lr ** 2 * lz ** 2 * sinx0 - h3_2 * lr ** 2 * lz ** 2 * sinx0 - h0_2 * lr ** 2 * lz ** 2 * sinlx + h1_2 * lr ** 2 * lz ** 2 * sinlx - h2_2 * lr ** 2 * lz ** 2 * sinlx + h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                                                                                                                          (
                                                                                                                                  4 * lz) * lx ** 3),
                                                                                                                  ((
                                                                                                                           6 * h0_2 * sinx0 + 6 * h2_2 * sinx0 + 6 * h1_2 * sinlx + 6 * h3_2 * sinlx) * lx ** 2 + (
                                                                                                                           12 * cosx0 * h1_2 - 24 * cosx0 * h0_2 - 24 * cosx0 * h2_2 + 12 * cosx0 * h3_2 - 12 * coslx * h0_2 + 24 * coslx * h1_2 - 12 * coslx * h2_2 + 24 * coslx * h3_2 - cosx0 * h0_2 * lr ** 2 * lz ** 2 - cosx0 * h2_2 * lr ** 2 * lz ** 2 + coslx * h1_2 * lr ** 2 * lz ** 2 + coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                                                                                                           36 * h1_2 * sinx0 - 36 * h0_2 * sinx0 - 36 * h2_2 * sinx0 + 36 * h3_2 * sinx0 + 36 * h0_2 * sinlx - 36 * h1_2 * sinlx + 36 * h2_2 * sinlx - 36 * h3_2 * sinlx - h0_2 * lr ** 2 * lz ** 2 * sinx0 + h1_2 * lr ** 2 * lz ** 2 * sinx0 - h2_2 * lr ** 2 * lz ** 2 * sinx0 + h3_2 * lr ** 2 * lz ** 2 * sinx0 + h0_2 * lr ** 2 * lz ** 2 * sinlx - h1_2 * lr ** 2 * lz ** 2 * sinlx + h2_2 * lr ** 2 * lz ** 2 * sinlx - h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                                                                                                                          (
                                                                                                                                  4 * lz) * lx ** 3),
                                                                                                                  ((
                                                                                                                           6 * cosx0 * h0_2 + 6 * cosx0 * h2_2) * lx ** 3 + (
                                                                                                                           18 * h0_2 * sinx0 - 6 * h1_2 * sinx0 + 18 * h2_2 * sinx0 - 6 * h3_2 * sinx0) * lx ** 2 + (
                                                                                                                           24 * cosx0 * h1_2 - 36 * cosx0 * h0_2 - 36 * cosx0 * h2_2 + 24 * cosx0 * h3_2 + 12 * coslx * h1_2 + 12 * coslx * h3_2 + cosx0 * h0_2 * lr ** 2 * lz ** 2 + 3 * cosx0 * h2_2 * lr ** 2 * lz ** 2 - coslx * h1_2 * lr ** 2 * lz ** 2 - 3 * coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                                                                                                           36 * h1_2 * sinx0 - 36 * h0_2 * sinx0 - 36 * h2_2 * sinx0 + 36 * h3_2 * sinx0 + 36 * h0_2 * sinlx - 36 * h1_2 * sinlx + 36 * h2_2 * sinlx - 36 * h3_2 * sinlx + h0_2 * lr ** 2 * lz ** 2 * sinx0 - h1_2 * lr ** 2 * lz ** 2 * sinx0 + 3 * h2_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h3_2 * lr ** 2 * lz ** 2 * sinx0 - h0_2 * lr ** 2 * lz ** 2 * sinlx + h1_2 * lr ** 2 * lz ** 2 * sinlx - 3 * h2_2 * lr ** 2 * lz ** 2 * sinlx + 3 * h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                                                                                                                          (
                                                                                                                                  4 * lz) * lx ** 3),
                                                                                                                  0.0, ],
                      [((
                                6 * h0_2 * sinx0 + 6 * h2_2 * sinx0 + 6 * h1_2 * sinlx + 6 * h3_2 * sinlx) * lx ** 2 + (
                                12 * cosx0 * h1_2 - 24 * cosx0 * h0_2 - 24 * cosx0 * h2_2 + 12 * cosx0 * h3_2 - 12 * coslx * h0_2 + 24 * coslx * h1_2 - 12 * coslx * h2_2 + 24 * coslx * h3_2 - cosx0 * h0_2 * lr ** 2 * lz ** 2 - cosx0 * h2_2 * lr ** 2 * lz ** 2 + coslx * h1_2 * lr ** 2 * lz ** 2 + coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                36 * h1_2 * sinx0 - 36 * h0_2 * sinx0 - 36 * h2_2 * sinx0 + 36 * h3_2 * sinx0 + 36 * h0_2 * sinlx - 36 * h1_2 * sinlx + 36 * h2_2 * sinlx - 36 * h3_2 * sinlx - h0_2 * lr ** 2 * lz ** 2 * sinx0 + h1_2 * lr ** 2 * lz ** 2 * sinx0 - h2_2 * lr ** 2 * lz ** 2 * sinx0 + h3_2 * lr ** 2 * lz ** 2 * sinx0 + h0_2 * lr ** 2 * lz ** 2 * sinlx - h1_2 * lr ** 2 * lz ** 2 * sinlx + h2_2 * lr ** 2 * lz ** 2 * sinlx - h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                               (
                                       4 * lz) * lx ** 3),
                       ((
                                6 * coslx * h1_2 + 6 * coslx * h3_2) * lx ** 3 + (
                                6 * h0_2 * sinlx - 18 * h1_2 * sinlx + 6 * h2_2 * sinlx - 18 * h3_2 * sinlx) * lx ** 2 + (
                                12 * cosx0 * h0_2 + 12 * cosx0 * h2_2 + 24 * coslx * h0_2 - 36 * coslx * h1_2 + 24 * coslx * h2_2 - 36 * coslx * h3_2 + cosx0 * h0_2 * lr ** 2 * lz ** 2 + cosx0 * h2_2 * lr ** 2 * lz ** 2 - coslx * h1_2 * lr ** 2 * lz ** 2 - coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                36 * h0_2 * sinx0 - 36 * h1_2 * sinx0 + 36 * h2_2 * sinx0 - 36 * h3_2 * sinx0 - 36 * h0_2 * sinlx + 36 * h1_2 * sinlx - 36 * h2_2 * sinlx + 36 * h3_2 * sinlx + h0_2 * lr ** 2 * lz ** 2 * sinx0 - h1_2 * lr ** 2 * lz ** 2 * sinx0 + h2_2 * lr ** 2 * lz ** 2 * sinx0 - h3_2 * lr ** 2 * lz ** 2 * sinx0 - h0_2 * lr ** 2 * lz ** 2 * sinlx + h1_2 * lr ** 2 * lz ** 2 * sinlx - h2_2 * lr ** 2 * lz ** 2 * sinlx + h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                               (
                                       4 * lz) * lx ** 3),
                       ((
                                - 6 * h0_2 * sinx0 - 6 * h2_2 * sinx0 - 6 * h1_2 * sinlx - 6 * h3_2 * sinlx) * lx ** 2 + (
                                24 * cosx0 * h0_2 - 12 * cosx0 * h1_2 + 24 * cosx0 * h2_2 - 12 * cosx0 * h3_2 + 12 * coslx * h0_2 - 24 * coslx * h1_2 + 12 * coslx * h2_2 - 24 * coslx * h3_2 - cosx0 * h0_2 * lr ** 2 * lz ** 2 - 3 * cosx0 * h2_2 * lr ** 2 * lz ** 2 + coslx * h1_2 * lr ** 2 * lz ** 2 + 3 * coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                36 * h0_2 * sinx0 - 36 * h1_2 * sinx0 + 36 * h2_2 * sinx0 - 36 * h3_2 * sinx0 - 36 * h0_2 * sinlx + 36 * h1_2 * sinlx - 36 * h2_2 * sinlx + 36 * h3_2 * sinlx - h0_2 * lr ** 2 * lz ** 2 * sinx0 + h1_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h2_2 * lr ** 2 * lz ** 2 * sinx0 + 3 * h3_2 * lr ** 2 * lz ** 2 * sinx0 + h0_2 * lr ** 2 * lz ** 2 * sinlx - h1_2 * lr ** 2 * lz ** 2 * sinlx + 3 * h2_2 * lr ** 2 * lz ** 2 * sinlx - 3 * h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                               (
                                       4 * lz) * lx ** 3),
                       ((
                                - 6 * coslx * h1_2 - 6 * coslx * h3_2) * lx ** 3 + (
                                18 * h1_2 * sinlx - 6 * h0_2 * sinlx - 6 * h2_2 * sinlx + 18 * h3_2 * sinlx) * lx ** 2 + (
                                36 * coslx * h1_2 - 12 * cosx0 * h2_2 - 24 * coslx * h0_2 - 12 * cosx0 * h0_2 - 24 * coslx * h2_2 + 36 * coslx * h3_2 + cosx0 * h0_2 * lr ** 2 * lz ** 2 + 3 * cosx0 * h2_2 * lr ** 2 * lz ** 2 - coslx * h1_2 * lr ** 2 * lz ** 2 - 3 * coslx * h3_2 * lr ** 2 * lz ** 2) * lx + (
                                36 * h1_2 * sinx0 - 36 * h0_2 * sinx0 - 36 * h2_2 * sinx0 + 36 * h3_2 * sinx0 + 36 * h0_2 * sinlx - 36 * h1_2 * sinlx + 36 * h2_2 * sinlx - 36 * h3_2 * sinlx + h0_2 * lr ** 2 * lz ** 2 * sinx0 - h1_2 * lr ** 2 * lz ** 2 * sinx0 + 3 * h2_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h3_2 * lr ** 2 * lz ** 2 * sinx0 - h0_2 * lr ** 2 * lz ** 2 * sinlx + h1_2 * lr ** 2 * lz ** 2 * sinlx - 3 * h2_2 * lr ** 2 * lz ** 2 * sinlx + 3 * h3_2 * lr ** 2 * lz ** 2 * sinlx)) / (
                               (
                                       4 * lz) * lx ** 3), ], ])
    for i in range(ke_dx.shape[0]):
        for j in range(ke_dx.shape[1] - i - 1):
            ke_dx[i, j + i + 1] = ke_dx[j + i + 1, i]

    return ke_dx


@njit
def calc_fe_dx(x0, lx, lz, lambda_value):
    coslx = np.cos(lx + x0)
    cosx0 = np.cos(x0)
    fe_dx = np.array(
                [
            (lz * lambda_value * (coslx - cosx0)) / (2 * lx),
                        -(lz * lambda_value * (coslx - cosx0)) / (2 * lx),
            (lz * lambda_value * (coslx - cosx0)) / (2 * lx),
                        -(lz * lambda_value * (coslx - cosx0)) / (2 * lx),
                ]
        )
    return fe_dx


@njit
def calc_ke_dy(x0, lr, lx, lz, h):
    h_2 = h ** 2
    cosx0 = np.cos(x0)
    sinx0 = np.sin(x0)
    coslx = np.cos(x0 + lx)
    sinlx = np.sin(x0 + lx)
    h0_2 = h_2[0]
    h1_2 = h_2[1]
    h2_2 = h_2[2]
    h3_2 = h_2[3]
    ke_dy = np.array([[((6 * h0_2 * sinx0 + 6 * h2_2 * sinx0) * lx ** 3 + (
            6 * cosx0 * h1_2 - 18 * cosx0 * h0_2 - 18 * cosx0 * h2_2 + 6 * cosx0 * h3_2) * lx ** 2 + (
                                24 * h1_2 * sinx0 - 36 * h0_2 * sinx0 - 36 * h2_2 * sinx0 + 24 * h3_2 * sinx0 + 12 * h1_2 * sinlx + 12 * h3_2 * sinlx + 3 * h0_2 * lr ** 2 * lz ** 2 * sinx0 + h2_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h1_2 * lr ** 2 * lz ** 2 * sinlx - h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                36 * cosx0 * h0_2 - 36 * cosx0 * h1_2 + 36 * cosx0 * h2_2 - 36 * cosx0 * h3_2 - 36 * coslx * h0_2 + 36 * coslx * h1_2 - 36 * coslx * h2_2 + 36 * coslx * h3_2 - 3 * cosx0 * h0_2 * lr ** 2 * lz ** 2 + 3 * cosx0 * h1_2 * lr ** 2 * lz ** 2 - cosx0 * h2_2 * lr ** 2 * lz ** 2 + cosx0 * h3_2 * lr ** 2 * lz ** 2 + 3 * coslx * h0_2 * lr ** 2 * lz ** 2 - 3 * coslx * h1_2 * lr ** 2 * lz ** 2 + coslx * h2_2 * lr ** 2 * lz ** 2 - coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                               (4 * lz) * lx ** 3), 0, 0, 0, ], [((
                                                                          6 * cosx0 * h0_2 + 6 * cosx0 * h2_2 + 6 * coslx * h1_2 + 6 * coslx * h3_2) * lx ** 2 + (
                                                                          24 * h0_2 * sinx0 - 12 * h1_2 * sinx0 + 24 * h2_2 * sinx0 - 12 * h3_2 * sinx0 + 12 * h0_2 * sinlx - 24 * h1_2 * sinlx + 12 * h2_2 * sinlx - 24 * h3_2 * sinlx - 3 * h0_2 * lr ** 2 * lz ** 2 * sinx0 - h2_2 * lr ** 2 * lz ** 2 * sinx0 + 3 * h1_2 * lr ** 2 * lz ** 2 * sinlx + h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                                                          36 * cosx0 * h1_2 - 36 * cosx0 * h0_2 - 36 * cosx0 * h2_2 + 36 * cosx0 * h3_2 + 36 * coslx * h0_2 - 36 * coslx * h1_2 + 36 * coslx * h2_2 - 36 * coslx * h3_2 + 3 * cosx0 * h0_2 * lr ** 2 * lz ** 2 - 3 * cosx0 * h1_2 * lr ** 2 * lz ** 2 + cosx0 * h2_2 * lr ** 2 * lz ** 2 - cosx0 * h3_2 * lr ** 2 * lz ** 2 - 3 * coslx * h0_2 * lr ** 2 * lz ** 2 + 3 * coslx * h1_2 * lr ** 2 * lz ** 2 - coslx * h2_2 * lr ** 2 * lz ** 2 + coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                                                                         (4 * lz) * lx ** 3), ((
                                                                                                       - 6 * h1_2 * sinlx - 6 * h3_2 * sinlx) * lx ** 3 + (
                                                                                                       6 * coslx * h0_2 - 18 * coslx * h1_2 + 6 * coslx * h2_2 - 18 * coslx * h3_2) * lx ** 2 + (
                                                                                                       36 * h1_2 * sinlx - 12 * h2_2 * sinx0 - 24 * h0_2 * sinlx - 12 * h0_2 * sinx0 - 24 * h2_2 * sinlx + 36 * h3_2 * sinlx + 3 * h0_2 * lr ** 2 * lz ** 2 * sinx0 + h2_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h1_2 * lr ** 2 * lz ** 2 * sinlx - h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                                                                                       36 * cosx0 * h0_2 - 36 * cosx0 * h1_2 + 36 * cosx0 * h2_2 - 36 * cosx0 * h3_2 - 36 * coslx * h0_2 + 36 * coslx * h1_2 - 36 * coslx * h2_2 + 36 * coslx * h3_2 - 3 * cosx0 * h0_2 * lr ** 2 * lz ** 2 + 3 * cosx0 * h1_2 * lr ** 2 * lz ** 2 - cosx0 * h2_2 * lr ** 2 * lz ** 2 + cosx0 * h3_2 * lr ** 2 * lz ** 2 + 3 * coslx * h0_2 * lr ** 2 * lz ** 2 - 3 * coslx * h1_2 * lr ** 2 * lz ** 2 + coslx * h2_2 * lr ** 2 * lz ** 2 - coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                                                                         (4 * lz) * lx ** 3), 0, 0, ], [((
                                                                                                                 - 6 * h0_2 * sinx0 - 6 * h2_2 * sinx0) * lx ** 3 + (
                                                                                                                 18 * cosx0 * h0_2 - 6 * cosx0 * h1_2 + 18 * cosx0 * h2_2 - 6 * cosx0 * h3_2) * lx ** 2 + (
                                                                                                                 36 * h0_2 * sinx0 - 24 * h1_2 * sinx0 + 36 * h2_2 * sinx0 - 24 * h3_2 * sinx0 - 12 * h1_2 * sinlx - 12 * h3_2 * sinlx + h0_2 * lr ** 2 * lz ** 2 * sinx0 + h2_2 * lr ** 2 * lz ** 2 * sinx0 - h1_2 * lr ** 2 * lz ** 2 * sinlx - h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                                                                                                 36 * cosx0 * h1_2 - 36 * cosx0 * h0_2 - 36 * cosx0 * h2_2 + 36 * cosx0 * h3_2 + 36 * coslx * h0_2 - 36 * coslx * h1_2 + 36 * coslx * h2_2 - 36 * coslx * h3_2 - cosx0 * h0_2 * lr ** 2 * lz ** 2 + cosx0 * h1_2 * lr ** 2 * lz ** 2 - cosx0 * h2_2 * lr ** 2 * lz ** 2 + cosx0 * h3_2 * lr ** 2 * lz ** 2 + coslx * h0_2 * lr ** 2 * lz ** 2 - coslx * h1_2 * lr ** 2 * lz ** 2 + coslx * h2_2 * lr ** 2 * lz ** 2 - coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                                                                                                                (
                                                                                                                        4 * lz) * lx ** 3),
                                                                                                        ((
                                                                                                                 - 6 * cosx0 * h0_2 - 6 * cosx0 * h2_2 - 6 * coslx * h1_2 - 6 * coslx * h3_2) * lx ** 2 + (
                                                                                                                 12 * h1_2 * sinx0 - 24 * h0_2 * sinx0 - 24 * h2_2 * sinx0 + 12 * h3_2 * sinx0 - 12 * h0_2 * sinlx + 24 * h1_2 * sinlx - 12 * h2_2 * sinlx + 24 * h3_2 * sinlx - h0_2 * lr ** 2 * lz ** 2 * sinx0 - h2_2 * lr ** 2 * lz ** 2 * sinx0 + h1_2 * lr ** 2 * lz ** 2 * sinlx + h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                                                                                                 36 * cosx0 * h0_2 - 36 * cosx0 * h1_2 + 36 * cosx0 * h2_2 - 36 * cosx0 * h3_2 - 36 * coslx * h0_2 + 36 * coslx * h1_2 - 36 * coslx * h2_2 + 36 * coslx * h3_2 + cosx0 * h0_2 * lr ** 2 * lz ** 2 - cosx0 * h1_2 * lr ** 2 * lz ** 2 + cosx0 * h2_2 * lr ** 2 * lz ** 2 - cosx0 * h3_2 * lr ** 2 * lz ** 2 - coslx * h0_2 * lr ** 2 * lz ** 2 + coslx * h1_2 * lr ** 2 * lz ** 2 - coslx * h2_2 * lr ** 2 * lz ** 2 + coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                                                                                                                (
                                                                                                                        4 * lz) * lx ** 3),
                                                                                                        ((
                                                                                                                 6 * h0_2 * sinx0 + 6 * h2_2 * sinx0) * lx ** 3 + (
                                                                                                                 6 * cosx0 * h1_2 - 18 * cosx0 * h0_2 - 18 * cosx0 * h2_2 + 6 * cosx0 * h3_2) * lx ** 2 + (
                                                                                                                 24 * h1_2 * sinx0 - 36 * h0_2 * sinx0 - 36 * h2_2 * sinx0 + 24 * h3_2 * sinx0 + 12 * h1_2 * sinlx + 12 * h3_2 * sinlx + h0_2 * lr ** 2 * lz ** 2 * sinx0 + 3 * h2_2 * lr ** 2 * lz ** 2 * sinx0 - h1_2 * lr ** 2 * lz ** 2 * sinlx - 3 * h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                                                                                                 36 * cosx0 * h0_2 - 36 * cosx0 * h1_2 + 36 * cosx0 * h2_2 - 36 * cosx0 * h3_2 - 36 * coslx * h0_2 + 36 * coslx * h1_2 - 36 * coslx * h2_2 + 36 * coslx * h3_2 - cosx0 * h0_2 * lr ** 2 * lz ** 2 + cosx0 * h1_2 * lr ** 2 * lz ** 2 - 3 * cosx0 * h2_2 * lr ** 2 * lz ** 2 + 3 * cosx0 * h3_2 * lr ** 2 * lz ** 2 + coslx * h0_2 * lr ** 2 * lz ** 2 - coslx * h1_2 * lr ** 2 * lz ** 2 + 3 * coslx * h2_2 * lr ** 2 * lz ** 2 - 3 * coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                                                                                                                (
                                                                                                                        4 * lz) * lx ** 3),
                                                                                                        0.0, ],
                      [((- 6 * cosx0 * h0_2 - 6 * cosx0 * h2_2 - 6 * coslx * h1_2 - 6 * coslx * h3_2) * lx ** 2 + (
                              12 * h1_2 * sinx0 - 24 * h0_2 * sinx0 - 24 * h2_2 * sinx0 + 12 * h3_2 * sinx0 - 12 * h0_2 * sinlx + 24 * h1_2 * sinlx - 12 * h2_2 * sinlx + 24 * h3_2 * sinlx - h0_2 * lr ** 2 * lz ** 2 * sinx0 - h2_2 * lr ** 2 * lz ** 2 * sinx0 + h1_2 * lr ** 2 * lz ** 2 * sinlx + h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                36 * cosx0 * h0_2 - 36 * cosx0 * h1_2 + 36 * cosx0 * h2_2 - 36 * cosx0 * h3_2 - 36 * coslx * h0_2 + 36 * coslx * h1_2 - 36 * coslx * h2_2 + 36 * coslx * h3_2 + cosx0 * h0_2 * lr ** 2 * lz ** 2 - cosx0 * h1_2 * lr ** 2 * lz ** 2 + cosx0 * h2_2 * lr ** 2 * lz ** 2 - cosx0 * h3_2 * lr ** 2 * lz ** 2 - coslx * h0_2 * lr ** 2 * lz ** 2 + coslx * h1_2 * lr ** 2 * lz ** 2 - coslx * h2_2 * lr ** 2 * lz ** 2 + coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                               (4 * lz) * lx ** 3), ((6 * h1_2 * sinlx + 6 * h3_2 * sinlx) * lx ** 3 + (
                              18 * coslx * h1_2 - 6 * coslx * h0_2 - 6 * coslx * h2_2 + 18 * coslx * h3_2) * lx ** 2 + (
                                                             12 * h0_2 * sinx0 + 12 * h2_2 * sinx0 + 24 * h0_2 * sinlx - 36 * h1_2 * sinlx + 24 * h2_2 * sinlx - 36 * h3_2 * sinlx + h0_2 * lr ** 2 * lz ** 2 * sinx0 + h2_2 * lr ** 2 * lz ** 2 * sinx0 - h1_2 * lr ** 2 * lz ** 2 * sinlx - h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                                             36 * cosx0 * h1_2 - 36 * cosx0 * h0_2 - 36 * cosx0 * h2_2 + 36 * cosx0 * h3_2 + 36 * coslx * h0_2 - 36 * coslx * h1_2 + 36 * coslx * h2_2 - 36 * coslx * h3_2 - cosx0 * h0_2 * lr ** 2 * lz ** 2 + cosx0 * h1_2 * lr ** 2 * lz ** 2 - cosx0 * h2_2 * lr ** 2 * lz ** 2 + cosx0 * h3_2 * lr ** 2 * lz ** 2 + coslx * h0_2 * lr ** 2 * lz ** 2 - coslx * h1_2 * lr ** 2 * lz ** 2 + coslx * h2_2 * lr ** 2 * lz ** 2 - coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                               (4 * lz) * lx ** 3), ((
                                                             6 * cosx0 * h0_2 + 6 * cosx0 * h2_2 + 6 * coslx * h1_2 + 6 * coslx * h3_2) * lx ** 2 + (
                                                             24 * h0_2 * sinx0 - 12 * h1_2 * sinx0 + 24 * h2_2 * sinx0 - 12 * h3_2 * sinx0 + 12 * h0_2 * sinlx - 24 * h1_2 * sinlx + 12 * h2_2 * sinlx - 24 * h3_2 * sinlx - h0_2 * lr ** 2 * lz ** 2 * sinx0 - 3 * h2_2 * lr ** 2 * lz ** 2 * sinx0 + h1_2 * lr ** 2 * lz ** 2 * sinlx + 3 * h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                                             36 * cosx0 * h1_2 - 36 * cosx0 * h0_2 - 36 * cosx0 * h2_2 + 36 * cosx0 * h3_2 + 36 * coslx * h0_2 - 36 * coslx * h1_2 + 36 * coslx * h2_2 - 36 * coslx * h3_2 + cosx0 * h0_2 * lr ** 2 * lz ** 2 - cosx0 * h1_2 * lr ** 2 * lz ** 2 + 3 * cosx0 * h2_2 * lr ** 2 * lz ** 2 - 3 * cosx0 * h3_2 * lr ** 2 * lz ** 2 - coslx * h0_2 * lr ** 2 * lz ** 2 + coslx * h1_2 * lr ** 2 * lz ** 2 - 3 * coslx * h2_2 * lr ** 2 * lz ** 2 + 3 * coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                               (4 * lz) * lx ** 3), ((- 6 * h1_2 * sinlx - 6 * h3_2 * sinlx) * lx ** 3 + (
                              6 * coslx * h0_2 - 18 * coslx * h1_2 + 6 * coslx * h2_2 - 18 * coslx * h3_2) * lx ** 2 + (
                                                             36 * h1_2 * sinlx - 12 * h2_2 * sinx0 - 24 * h0_2 * sinlx - 12 * h0_2 * sinx0 - 24 * h2_2 * sinlx + 36 * h3_2 * sinlx + h0_2 * lr ** 2 * lz ** 2 * sinx0 + 3 * h2_2 * lr ** 2 * lz ** 2 * sinx0 - h1_2 * lr ** 2 * lz ** 2 * sinlx - 3 * h3_2 * lr ** 2 * lz ** 2 * sinlx) * lx + (
                                                             36 * cosx0 * h0_2 - 36 * cosx0 * h1_2 + 36 * cosx0 * h2_2 - 36 * cosx0 * h3_2 - 36 * coslx * h0_2 + 36 * coslx * h1_2 - 36 * coslx * h2_2 + 36 * coslx * h3_2 - cosx0 * h0_2 * lr ** 2 * lz ** 2 + cosx0 * h1_2 * lr ** 2 * lz ** 2 - 3 * cosx0 * h2_2 * lr ** 2 * lz ** 2 + 3 * cosx0 * h3_2 * lr ** 2 * lz ** 2 + coslx * h0_2 * lr ** 2 * lz ** 2 - coslx * h1_2 * lr ** 2 * lz ** 2 + 3 * coslx * h2_2 * lr ** 2 * lz ** 2 - 3 * coslx * h3_2 * lr ** 2 * lz ** 2)) / (
                               (4 * lz) * lx ** 3), ], ])
    for i in range(ke_dy.shape[0]):
        for j in range(ke_dy.shape[1] - i - 1):
            ke_dy[i, j + i + 1] = ke_dy[j + i + 1, i]
    return ke_dy


@njit
def calc_fe_dy(x0, lx, lz, lambda_value):
    sinx0 = np.sin(x0)
    sinlx = np.sin(x0 + lx)
    fe_dy = np.array([(lz * lambda_value * (sinlx - sinx0)) / (2 * lx), -(lz * lambda_value * (sinlx - sinx0)) / (2 * lx),
                                                                          (lz * lambda_value * (sinlx - sinx0)) / (2 * lx), -(lz * lambda_value * (sinlx - sinx0)) / (2 * lx), ])
    return fe_dy


@njit
def calc_fe_dxt(x0, lx, lz, vf, lambda_value):
    fe_dxt = 2 * vf * lambda_value * np.array([(lz * (np.sin(lx + x0) - np.sin(x0))) / (2 * lx) - (lz * np.cos(x0)) / 2,
                                     (lz * np.cos(lx + x0)) / 2 - (lz * (np.sin(lx + x0) - np.sin(x0))) / (2 * lx),
                                     (lz * (np.sin(lx + x0) - np.sin(x0))) / (2 * lx) - (lz * np.cos(x0)) / 2,
                                     (lz * np.cos(lx + x0)) / 2 - (lz * (np.sin(lx + x0) - np.sin(x0))) / (2 * lx), ])
    return fe_dxt


# @njit
# def calc_fe_dxt(x0, lx, lz, vf, lambda_value):
#     fe_dxt = -2 * vf * lambda_value * np.array(
#         [-(lz * (np.sin(lx + x0) - np.sin(x0))) / (2 * lx), (lz * (np.sin(lx + x0) - np.sin(x0))) / (2 * lx),
#          -(lz * (np.sin(lx + x0) - np.sin(x0))) / (2 * lx), (lz * (np.sin(lx + x0) - np.sin(x0))) / (2 * lx), ])
#     return fe_dxt


@njit
def calc_fe_dyt(x0, lx, lz, vf, lambda_value):
    fe_dyt = 2 * vf * lambda_value * np.array([- (lz * np.sin(x0)) / 2 - (lz * (np.cos(lx + x0) - np.cos(x0))) / (2 * lx),
                                     (lz * np.sin(lx + x0)) / 2 + (lz * (np.cos(lx + x0) - np.cos(x0))) / (2 * lx),
                                     - (lz * np.sin(x0)) / 2 - (lz * (np.cos(lx + x0) - np.cos(x0))) / (2 * lx),
                                     (lz * np.sin(lx + x0)) / 2 + (lz * (np.cos(lx + x0) - np.cos(x0))) / (2 * lx), ])
    return fe_dyt


@njit
def calc_ke2_dx2(x0, lr, lx, lz, h):
    cos2x0 = np.cos(2 * x0)
    sin2x0 = np.sin(2 * x0)
    cos2lx = np.cos(2 * (x0 + lx))
    sin2lx = np.sin(2 * (x0 + lx))
    h0 = h[0]
    h1 = h[1]
    h2 = h[2]
    h3 = h[3]
    ke2_dx2 = np.array(
        [[((6 * h0 + 2 * h1 + 6 * h2 + 2 * h3) * lx ** 4 + (12 * h0 * sin2x0 + 12 * h2 * sin2x0) * lx ** 3 + (
                6 * cos2x0 * h1 - 18 * cos2x0 * h0 - 18 * cos2x0 * h2 + 6 * cos2x0 * h3 + 6 * h0 * lr ** 2 * lz ** 2 + 6 * h1 * lr ** 2 * lz ** 2 + 2 * h2 * lr ** 2 * lz ** 2 + 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                   12 * h1 * sin2x0 - 18 * h0 * sin2x0 - 18 * h2 * sin2x0 + 12 * h3 * sin2x0 + 6 * h1 * sin2lx + 6 * h3 * sin2lx + 6 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 6 * h1 * lr ** 2 * lz ** 2 * sin2lx - 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                   9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 - 3 * cos2x0 * h0 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h1 * lr ** 2 * lz ** 2 - cos2x0 * h2 * lr ** 2 * lz ** 2 + cos2x0 * h3 * lr ** 2 * lz ** 2 + 3 * cos2lx * h0 * lr ** 2 * lz ** 2 - 3 * cos2lx * h1 * lr ** 2 * lz ** 2 + cos2lx * h2 * lr ** 2 * lz ** 2 - cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ((2 * h0 + 2 * h1 + 2 * h2 + 2 * h3) * lx ** 4 + (
                6 * cos2x0 * h0 + 6 * cos2x0 * h2 + 6 * cos2lx * h1 + 6 * cos2lx * h3 - 6 * h0 * lr ** 2 * lz ** 2 - 6 * h1 * lr ** 2 * lz ** 2 - 2 * h2 * lr ** 2 * lz ** 2 - 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                 12 * h0 * sin2x0 - 6 * h1 * sin2x0 + 12 * h2 * sin2x0 - 6 * h3 * sin2x0 + 6 * h0 * sin2lx - 12 * h1 * sin2lx + 6 * h2 * sin2lx - 12 * h3 * sin2lx - 6 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 6 * h1 * lr ** 2 * lz ** 2 * sin2lx + 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                 9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 + 3 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h1 * lr ** 2 * lz ** 2 + cos2x0 * h2 * lr ** 2 * lz ** 2 - cos2x0 * h3 * lr ** 2 * lz ** 2 - 3 * cos2lx * h0 * lr ** 2 * lz ** 2 + 3 * cos2lx * h1 * lr ** 2 * lz ** 2 - cos2lx * h2 * lr ** 2 * lz ** 2 + cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ((- 6 * h0 - 2 * h1 - 6 * h2 - 2 * h3) * lx ** 4 + (
                - 12 * h0 * sin2x0 - 12 * h2 * sin2x0) * lx ** 3 + (
                                                 18 * cos2x0 * h0 - 6 * cos2x0 * h1 + 18 * cos2x0 * h2 - 6 * cos2x0 * h3 + 2 * h0 * lr ** 2 * lz ** 2 + 2 * h1 * lr ** 2 * lz ** 2 + 2 * h2 * lr ** 2 * lz ** 2 + 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                 18 * h0 * sin2x0 - 12 * h1 * sin2x0 + 18 * h2 * sin2x0 - 12 * h3 * sin2x0 - 6 * h1 * sin2lx - 6 * h3 * sin2lx + 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h1 * lr ** 2 * lz ** 2 * sin2lx - 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                 9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 - cos2x0 * h0 * lr ** 2 * lz ** 2 + cos2x0 * h1 * lr ** 2 * lz ** 2 - cos2x0 * h2 * lr ** 2 * lz ** 2 + cos2x0 * h3 * lr ** 2 * lz ** 2 + cos2lx * h0 * lr ** 2 * lz ** 2 - cos2lx * h1 * lr ** 2 * lz ** 2 + cos2lx * h2 * lr ** 2 * lz ** 2 - cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ((- 2 * h0 - 2 * h1 - 2 * h2 - 2 * h3) * lx ** 4 + (
                - 6 * cos2x0 * h0 - 6 * cos2x0 * h2 - 6 * cos2lx * h1 - 6 * cos2lx * h3 - 2 * h0 * lr ** 2 * lz ** 2 - 2 * h1 * lr ** 2 * lz ** 2 - 2 * h2 * lr ** 2 * lz ** 2 - 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                 6 * h1 * sin2x0 - 12 * h0 * sin2x0 - 12 * h2 * sin2x0 + 6 * h3 * sin2x0 - 6 * h0 * sin2lx + 12 * h1 * sin2lx - 6 * h2 * sin2lx + 12 * h3 * sin2lx - 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h1 * lr ** 2 * lz ** 2 * sin2lx + 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                 9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 + cos2x0 * h0 * lr ** 2 * lz ** 2 - cos2x0 * h1 * lr ** 2 * lz ** 2 + cos2x0 * h2 * lr ** 2 * lz ** 2 - cos2x0 * h3 * lr ** 2 * lz ** 2 - cos2lx * h0 * lr ** 2 * lz ** 2 + cos2lx * h1 * lr ** 2 * lz ** 2 - cos2lx * h2 * lr ** 2 * lz ** 2 + cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ], [0, (
                (2 * h0 + 6 * h1 + 2 * h2 + 6 * h3) * lx ** 4 + (- 12 * h1 * sin2lx - 12 * h3 * sin2lx) * lx ** 3 + (
                6 * cos2lx * h0 - 18 * cos2lx * h1 + 6 * cos2lx * h2 - 18 * cos2lx * h3 + 6 * h0 * lr ** 2 * lz ** 2 + 6 * h1 * lr ** 2 * lz ** 2 + 2 * h2 * lr ** 2 * lz ** 2 + 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                        18 * h1 * sin2lx - 6 * h2 * sin2x0 - 12 * h0 * sin2lx - 6 * h0 * sin2x0 - 12 * h2 * sin2lx + 18 * h3 * sin2lx + 6 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 6 * h1 * lr ** 2 * lz ** 2 * sin2lx - 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                        9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 - 3 * cos2x0 * h0 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h1 * lr ** 2 * lz ** 2 - cos2x0 * h2 * lr ** 2 * lz ** 2 + cos2x0 * h3 * lr ** 2 * lz ** 2 + 3 * cos2lx * h0 * lr ** 2 * lz ** 2 - 3 * cos2lx * h1 * lr ** 2 * lz ** 2 + cos2lx * h2 * lr ** 2 * lz ** 2 - cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                    (16 * lz) * lx ** 3), (
                                                    (- 2 * h0 - 2 * h1 - 2 * h2 - 2 * h3) * lx ** 4 + (
                                                    - 6 * cos2x0 * h0 - 6 * cos2x0 * h2 - 6 * cos2lx * h1 - 6 * cos2lx * h3 - 2 * h0 * lr ** 2 * lz ** 2 - 2 * h1 * lr ** 2 * lz ** 2 - 2 * h2 * lr ** 2 * lz ** 2 - 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                            6 * h1 * sin2x0 - 12 * h0 * sin2x0 - 12 * h2 * sin2x0 + 6 * h3 * sin2x0 - 6 * h0 * sin2lx + 12 * h1 * sin2lx - 6 * h2 * sin2lx + 12 * h3 * sin2lx - 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h1 * lr ** 2 * lz ** 2 * sin2lx + 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                            9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 + cos2x0 * h0 * lr ** 2 * lz ** 2 - cos2x0 * h1 * lr ** 2 * lz ** 2 + cos2x0 * h2 * lr ** 2 * lz ** 2 - cos2x0 * h3 * lr ** 2 * lz ** 2 - cos2lx * h0 * lr ** 2 * lz ** 2 + cos2lx * h1 * lr ** 2 * lz ** 2 - cos2lx * h2 * lr ** 2 * lz ** 2 + cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                    (16 * lz) * lx ** 3), (
                                                    (- 2 * h0 - 6 * h1 - 2 * h2 - 6 * h3) * lx ** 4 + (
                                                    12 * h1 * sin2lx + 12 * h3 * sin2lx) * lx ** 3 + (
                                                            18 * cos2lx * h1 - 6 * cos2lx * h0 - 6 * cos2lx * h2 + 18 * cos2lx * h3 + 2 * h0 * lr ** 2 * lz ** 2 + 2 * h1 * lr ** 2 * lz ** 2 + 2 * h2 * lr ** 2 * lz ** 2 + 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                            6 * h0 * sin2x0 + 6 * h2 * sin2x0 + 12 * h0 * sin2lx - 18 * h1 * sin2lx + 12 * h2 * sin2lx - 18 * h3 * sin2lx + 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h1 * lr ** 2 * lz ** 2 * sin2lx - 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                            9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 - cos2x0 * h0 * lr ** 2 * lz ** 2 + cos2x0 * h1 * lr ** 2 * lz ** 2 - cos2x0 * h2 * lr ** 2 * lz ** 2 + cos2x0 * h3 * lr ** 2 * lz ** 2 + cos2lx * h0 * lr ** 2 * lz ** 2 - cos2lx * h1 * lr ** 2 * lz ** 2 + cos2lx * h2 * lr ** 2 * lz ** 2 - cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                    (16 * lz) * lx ** 3), ], [0, 0, (
                (6 * h0 + 2 * h1 + 6 * h2 + 2 * h3) * lx ** 4 + (12 * h0 * sin2x0 + 12 * h2 * sin2x0) * lx ** 3 + (
                6 * cos2x0 * h1 - 18 * cos2x0 * h0 - 18 * cos2x0 * h2 + 6 * cos2x0 * h3 + 2 * h0 * lr ** 2 * lz ** 2 + 2 * h1 * lr ** 2 * lz ** 2 + 6 * h2 * lr ** 2 * lz ** 2 + 6 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                        12 * h1 * sin2x0 - 18 * h0 * sin2x0 - 18 * h2 * sin2x0 + 12 * h3 * sin2x0 + 6 * h1 * sin2lx + 6 * h3 * sin2lx + 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 6 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h1 * lr ** 2 * lz ** 2 * sin2lx - 6 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                        9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 - cos2x0 * h0 * lr ** 2 * lz ** 2 + cos2x0 * h1 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h3 * lr ** 2 * lz ** 2 + cos2lx * h0 * lr ** 2 * lz ** 2 - cos2lx * h1 * lr ** 2 * lz ** 2 + 3 * cos2lx * h2 * lr ** 2 * lz ** 2 - 3 * cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                                                      (16 * lz) * lx ** 3), ((
                                                                                                                     2 * h0 + 2 * h1 + 2 * h2 + 2 * h3) * lx ** 4 + (
                                                                                                                     6 * cos2x0 * h0 + 6 * cos2x0 * h2 + 6 * cos2lx * h1 + 6 * cos2lx * h3 - 2 * h0 * lr ** 2 * lz ** 2 - 2 * h1 * lr ** 2 * lz ** 2 - 6 * h2 * lr ** 2 * lz ** 2 - 6 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                                                                                     12 * h0 * sin2x0 - 6 * h1 * sin2x0 + 12 * h2 * sin2x0 - 6 * h3 * sin2x0 + 6 * h0 * sin2lx - 12 * h1 * sin2lx + 6 * h2 * sin2lx - 12 * h3 * sin2lx - 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 6 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h1 * lr ** 2 * lz ** 2 * sin2lx + 6 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                                                                                     9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 + cos2x0 * h0 * lr ** 2 * lz ** 2 - cos2x0 * h1 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h2 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h3 * lr ** 2 * lz ** 2 - cos2lx * h0 * lr ** 2 * lz ** 2 + cos2lx * h1 * lr ** 2 * lz ** 2 - 3 * cos2lx * h2 * lr ** 2 * lz ** 2 + 3 * cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                                                      (16 * lz) * lx ** 3), ],
         [0, 0, 0,
          ((2 * h0 + 6 * h1 + 2 * h2 + 6 * h3) * lx ** 4 + (- 12 * h1 * sin2lx - 12 * h3 * sin2lx) * lx ** 3 + (
                  6 * cos2lx * h0 - 18 * cos2lx * h1 + 6 * cos2lx * h2 - 18 * cos2lx * h3 + 2 * h0 * lr ** 2 * lz ** 2 + 2 * h1 * lr ** 2 * lz ** 2 + 6 * h2 * lr ** 2 * lz ** 2 + 6 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                   18 * h1 * sin2lx - 6 * h2 * sin2x0 - 12 * h0 * sin2lx - 6 * h0 * sin2x0 - 12 * h2 * sin2lx + 18 * h3 * sin2lx + 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 6 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h1 * lr ** 2 * lz ** 2 * sin2lx - 6 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                   9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 - cos2x0 * h0 * lr ** 2 * lz ** 2 + cos2x0 * h1 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h3 * lr ** 2 * lz ** 2 + cos2lx * h0 * lr ** 2 * lz ** 2 - cos2lx * h1 * lr ** 2 * lz ** 2 + 3 * cos2lx * h2 * lr ** 2 * lz ** 2 - 3 * cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ], ])
    for i in range(ke2_dx2.shape[0]):
        for j in range(ke2_dx2.shape[1] - i - 1):
            ke2_dx2[j + i + 1, i] = ke2_dx2[i, j + i + 1]

    return ke2_dx2


@njit
def calc_ke2_dy2(x0, lr, lx, lz, h):
    cos2x0 = np.cos(2 * x0)
    sin2x0 = np.sin(2 * x0)
    cos2lx = np.cos(2 * (x0 + lx))
    sin2lx = np.sin(2 * (x0 + lx))
    h0 = h[0]
    h1 = h[1]
    h2 = h[2]
    h3 = h[3]
    ke2_dy2 = np.array(
        [[((6 * h0 + 2 * h1 + 6 * h2 + 2 * h3) * lx ** 4 + (- 12 * h0 * sin2x0 - 12 * h2 * sin2x0) * lx ** 3 + (
                18 * cos2x0 * h0 - 6 * cos2x0 * h1 + 18 * cos2x0 * h2 - 6 * cos2x0 * h3 + 6 * h0 * lr ** 2 * lz ** 2 + 6 * h1 * lr ** 2 * lz ** 2 + 2 * h2 * lr ** 2 * lz ** 2 + 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                   18 * h0 * sin2x0 - 12 * h1 * sin2x0 + 18 * h2 * sin2x0 - 12 * h3 * sin2x0 - 6 * h1 * sin2lx - 6 * h3 * sin2lx - 6 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 6 * h1 * lr ** 2 * lz ** 2 * sin2lx + 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                   9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 + 3 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h1 * lr ** 2 * lz ** 2 + cos2x0 * h2 * lr ** 2 * lz ** 2 - cos2x0 * h3 * lr ** 2 * lz ** 2 - 3 * cos2lx * h0 * lr ** 2 * lz ** 2 + 3 * cos2lx * h1 * lr ** 2 * lz ** 2 - cos2lx * h2 * lr ** 2 * lz ** 2 + cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ((2 * h0 + 2 * h1 + 2 * h2 + 2 * h3) * lx ** 4 + (
                - 6 * cos2x0 * h0 - 6 * cos2x0 * h2 - 6 * cos2lx * h1 - 6 * cos2lx * h3 - 6 * h0 * lr ** 2 * lz ** 2 - 6 * h1 * lr ** 2 * lz ** 2 - 2 * h2 * lr ** 2 * lz ** 2 - 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                 6 * h1 * sin2x0 - 12 * h0 * sin2x0 - 12 * h2 * sin2x0 + 6 * h3 * sin2x0 - 6 * h0 * sin2lx + 12 * h1 * sin2lx - 6 * h2 * sin2lx + 12 * h3 * sin2lx + 6 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 6 * h1 * lr ** 2 * lz ** 2 * sin2lx - 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                 9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 - 3 * cos2x0 * h0 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h1 * lr ** 2 * lz ** 2 - cos2x0 * h2 * lr ** 2 * lz ** 2 + cos2x0 * h3 * lr ** 2 * lz ** 2 + 3 * cos2lx * h0 * lr ** 2 * lz ** 2 - 3 * cos2lx * h1 * lr ** 2 * lz ** 2 + cos2lx * h2 * lr ** 2 * lz ** 2 - cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ((- 6 * h0 - 2 * h1 - 6 * h2 - 2 * h3) * lx ** 4 + (
                12 * h0 * sin2x0 + 12 * h2 * sin2x0) * lx ** 3 + (
                                                 6 * cos2x0 * h1 - 18 * cos2x0 * h0 - 18 * cos2x0 * h2 + 6 * cos2x0 * h3 + 2 * h0 * lr ** 2 * lz ** 2 + 2 * h1 * lr ** 2 * lz ** 2 + 2 * h2 * lr ** 2 * lz ** 2 + 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                 12 * h1 * sin2x0 - 18 * h0 * sin2x0 - 18 * h2 * sin2x0 + 12 * h3 * sin2x0 + 6 * h1 * sin2lx + 6 * h3 * sin2lx - 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h1 * lr ** 2 * lz ** 2 * sin2lx + 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                 9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 + cos2x0 * h0 * lr ** 2 * lz ** 2 - cos2x0 * h1 * lr ** 2 * lz ** 2 + cos2x0 * h2 * lr ** 2 * lz ** 2 - cos2x0 * h3 * lr ** 2 * lz ** 2 - cos2lx * h0 * lr ** 2 * lz ** 2 + cos2lx * h1 * lr ** 2 * lz ** 2 - cos2lx * h2 * lr ** 2 * lz ** 2 + cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ((- 2 * h0 - 2 * h1 - 2 * h2 - 2 * h3) * lx ** 4 + (
                6 * cos2x0 * h0 + 6 * cos2x0 * h2 + 6 * cos2lx * h1 + 6 * cos2lx * h3 - 2 * h0 * lr ** 2 * lz ** 2 - 2 * h1 * lr ** 2 * lz ** 2 - 2 * h2 * lr ** 2 * lz ** 2 - 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                 12 * h0 * sin2x0 - 6 * h1 * sin2x0 + 12 * h2 * sin2x0 - 6 * h3 * sin2x0 + 6 * h0 * sin2lx - 12 * h1 * sin2lx + 6 * h2 * sin2lx - 12 * h3 * sin2lx + 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h1 * lr ** 2 * lz ** 2 * sin2lx - 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                 9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 - cos2x0 * h0 * lr ** 2 * lz ** 2 + cos2x0 * h1 * lr ** 2 * lz ** 2 - cos2x0 * h2 * lr ** 2 * lz ** 2 + cos2x0 * h3 * lr ** 2 * lz ** 2 + cos2lx * h0 * lr ** 2 * lz ** 2 - cos2lx * h1 * lr ** 2 * lz ** 2 + cos2lx * h2 * lr ** 2 * lz ** 2 - cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ], [0, (
                (2 * h0 + 6 * h1 + 2 * h2 + 6 * h3) * lx ** 4 + (12 * h1 * sin2lx + 12 * h3 * sin2lx) * lx ** 3 + (
                18 * cos2lx * h1 - 6 * cos2lx * h0 - 6 * cos2lx * h2 + 18 * cos2lx * h3 + 6 * h0 * lr ** 2 * lz ** 2 + 6 * h1 * lr ** 2 * lz ** 2 + 2 * h2 * lr ** 2 * lz ** 2 + 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                        6 * h0 * sin2x0 + 6 * h2 * sin2x0 + 12 * h0 * sin2lx - 18 * h1 * sin2lx + 12 * h2 * sin2lx - 18 * h3 * sin2lx - 6 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 6 * h1 * lr ** 2 * lz ** 2 * sin2lx + 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                        9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 + 3 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h1 * lr ** 2 * lz ** 2 + cos2x0 * h2 * lr ** 2 * lz ** 2 - cos2x0 * h3 * lr ** 2 * lz ** 2 - 3 * cos2lx * h0 * lr ** 2 * lz ** 2 + 3 * cos2lx * h1 * lr ** 2 * lz ** 2 - cos2lx * h2 * lr ** 2 * lz ** 2 + cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                    (16 * lz) * lx ** 3), (
                                                    (- 2 * h0 - 2 * h1 - 2 * h2 - 2 * h3) * lx ** 4 + (
                                                    6 * cos2x0 * h0 + 6 * cos2x0 * h2 + 6 * cos2lx * h1 + 6 * cos2lx * h3 - 2 * h0 * lr ** 2 * lz ** 2 - 2 * h1 * lr ** 2 * lz ** 2 - 2 * h2 * lr ** 2 * lz ** 2 - 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                            12 * h0 * sin2x0 - 6 * h1 * sin2x0 + 12 * h2 * sin2x0 - 6 * h3 * sin2x0 + 6 * h0 * sin2lx - 12 * h1 * sin2lx + 6 * h2 * sin2lx - 12 * h3 * sin2lx + 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h1 * lr ** 2 * lz ** 2 * sin2lx - 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                            9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 - cos2x0 * h0 * lr ** 2 * lz ** 2 + cos2x0 * h1 * lr ** 2 * lz ** 2 - cos2x0 * h2 * lr ** 2 * lz ** 2 + cos2x0 * h3 * lr ** 2 * lz ** 2 + cos2lx * h0 * lr ** 2 * lz ** 2 - cos2lx * h1 * lr ** 2 * lz ** 2 + cos2lx * h2 * lr ** 2 * lz ** 2 - cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                    (16 * lz) * lx ** 3), (
                                                    (- 2 * h0 - 6 * h1 - 2 * h2 - 6 * h3) * lx ** 4 + (
                                                    - 12 * h1 * sin2lx - 12 * h3 * sin2lx) * lx ** 3 + (
                                                            6 * cos2lx * h0 - 18 * cos2lx * h1 + 6 * cos2lx * h2 - 18 * cos2lx * h3 + 2 * h0 * lr ** 2 * lz ** 2 + 2 * h1 * lr ** 2 * lz ** 2 + 2 * h2 * lr ** 2 * lz ** 2 + 2 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                            18 * h1 * sin2lx - 6 * h2 * sin2x0 - 12 * h0 * sin2lx - 6 * h0 * sin2x0 - 12 * h2 * sin2lx + 18 * h3 * sin2lx - 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h1 * lr ** 2 * lz ** 2 * sin2lx + 2 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                            9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 + cos2x0 * h0 * lr ** 2 * lz ** 2 - cos2x0 * h1 * lr ** 2 * lz ** 2 + cos2x0 * h2 * lr ** 2 * lz ** 2 - cos2x0 * h3 * lr ** 2 * lz ** 2 - cos2lx * h0 * lr ** 2 * lz ** 2 + cos2lx * h1 * lr ** 2 * lz ** 2 - cos2lx * h2 * lr ** 2 * lz ** 2 + cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                    (16 * lz) * lx ** 3), ], [0, 0, (
                (6 * h0 + 2 * h1 + 6 * h2 + 2 * h3) * lx ** 4 + (
                - 12 * h0 * sin2x0 - 12 * h2 * sin2x0) * lx ** 3 + (
                        18 * cos2x0 * h0 - 6 * cos2x0 * h1 + 18 * cos2x0 * h2 - 6 * cos2x0 * h3 + 2 * h0 * lr ** 2 * lz ** 2 + 2 * h1 * lr ** 2 * lz ** 2 + 6 * h2 * lr ** 2 * lz ** 2 + 6 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                        18 * h0 * sin2x0 - 12 * h1 * sin2x0 + 18 * h2 * sin2x0 - 12 * h3 * sin2x0 - 6 * h1 * sin2lx - 6 * h3 * sin2lx - 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 6 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h1 * lr ** 2 * lz ** 2 * sin2lx + 6 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                        9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 + cos2x0 * h0 * lr ** 2 * lz ** 2 - cos2x0 * h1 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h2 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h3 * lr ** 2 * lz ** 2 - cos2lx * h0 * lr ** 2 * lz ** 2 + cos2lx * h1 * lr ** 2 * lz ** 2 - 3 * cos2lx * h2 * lr ** 2 * lz ** 2 + 3 * cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                                                      (16 * lz) * lx ** 3),
                                                                              ((
                                                                                       2 * h0 + 2 * h1 + 2 * h2 + 2 * h3) * lx ** 4 + (
                                                                                       - 6 * cos2x0 * h0 - 6 * cos2x0 * h2 - 6 * cos2lx * h1 - 6 * cos2lx * h3 - 2 * h0 * lr ** 2 * lz ** 2 - 2 * h1 * lr ** 2 * lz ** 2 - 6 * h2 * lr ** 2 * lz ** 2 - 6 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                                                                                       6 * h1 * sin2x0 - 12 * h0 * sin2x0 - 12 * h2 * sin2x0 + 6 * h3 * sin2x0 - 6 * h0 * sin2lx + 12 * h1 * sin2lx - 6 * h2 * sin2lx + 12 * h3 * sin2lx + 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 6 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 2 * h1 * lr ** 2 * lz ** 2 * sin2lx - 6 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                                                                                       9 * cos2x0 * h0 - 9 * cos2x0 * h1 + 9 * cos2x0 * h2 - 9 * cos2x0 * h3 - 9 * cos2lx * h0 + 9 * cos2lx * h1 - 9 * cos2lx * h2 + 9 * cos2lx * h3 - cos2x0 * h0 * lr ** 2 * lz ** 2 + cos2x0 * h1 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h3 * lr ** 2 * lz ** 2 + cos2lx * h0 * lr ** 2 * lz ** 2 - cos2lx * h1 * lr ** 2 * lz ** 2 + 3 * cos2lx * h2 * lr ** 2 * lz ** 2 - 3 * cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                                                                                      (
                                                                                              16 * lz) * lx ** 3), ],
         [0, 0, 0, ((2 * h0 + 6 * h1 + 2 * h2 + 6 * h3) * lx ** 4 + (12 * h1 * sin2lx + 12 * h3 * sin2lx) * lx ** 3 + (
                 18 * cos2lx * h1 - 6 * cos2lx * h0 - 6 * cos2lx * h2 + 18 * cos2lx * h3 + 2 * h0 * lr ** 2 * lz ** 2 + 2 * h1 * lr ** 2 * lz ** 2 + 6 * h2 * lr ** 2 * lz ** 2 + 6 * h3 * lr ** 2 * lz ** 2) * lx ** 2 + (
                            6 * h0 * sin2x0 + 6 * h2 * sin2x0 + 12 * h0 * sin2lx - 18 * h1 * sin2lx + 12 * h2 * sin2lx - 18 * h3 * sin2lx - 2 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 6 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 2 * h1 * lr ** 2 * lz ** 2 * sin2lx + 6 * h3 * lr ** 2 * lz ** 2 * sin2lx) * lx + (
                            9 * cos2x0 * h1 - 9 * cos2x0 * h0 - 9 * cos2x0 * h2 + 9 * cos2x0 * h3 + 9 * cos2lx * h0 - 9 * cos2lx * h1 + 9 * cos2lx * h2 - 9 * cos2lx * h3 + cos2x0 * h0 * lr ** 2 * lz ** 2 - cos2x0 * h1 * lr ** 2 * lz ** 2 + 3 * cos2x0 * h2 * lr ** 2 * lz ** 2 - 3 * cos2x0 * h3 * lr ** 2 * lz ** 2 - cos2lx * h0 * lr ** 2 * lz ** 2 + cos2lx * h1 * lr ** 2 * lz ** 2 - 3 * cos2lx * h2 * lr ** 2 * lz ** 2 + 3 * cos2lx * h3 * lr ** 2 * lz ** 2)) / (
                  (16 * lz) * lx ** 3), ], ])
    for i in range(ke2_dy2.shape[0]):
        for j in range(ke2_dy2.shape[1] - i - 1):
            ke2_dy2[j + i + 1, i] = ke2_dy2[i, j + i + 1]

    return ke2_dy2

@njit
def calc_ke2_dx_dy(x0, lr, lx, lz, h):
    cos2x0 = np.cos(2 * x0)
    sin2x0 = np.sin(2 * x0)
    cos2lx = np.cos(2 * (x0 + lx))
    sin2lx = np.sin(2 * (x0 + lx))
    h0 = h[0]
    h1 = h[1]
    h2 = h[2]
    h3 = h[3]
    ke2_dx_dy = np.array([[((- 12 * cos2x0 * h0 - 12 * cos2x0 * h2) * lx ** 3 + (
            6 * h1 * sin2x0 - 18 * h0 * sin2x0 - 18 * h2 * sin2x0 + 6 * h3 * sin2x0) * lx ** 2 + (
                                    18 * cos2x0 * h0 - 12 * cos2x0 * h1 + 18 * cos2x0 * h2 - 12 * cos2x0 * h3 - 6 * cos2lx * h1 - 6 * cos2lx * h3 - 6 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 2 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 6 * cos2lx * h1 * lr ** 2 * lz ** 2 + 2 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                    9 * h0 * sin2x0 - 9 * h1 * sin2x0 + 9 * h2 * sin2x0 - 9 * h3 * sin2x0 - 9 * h0 * sin2lx + 9 * h1 * sin2lx - 9 * h2 * sin2lx + 9 * h3 * sin2lx - 3 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 3 * h1 * lr ** 2 * lz ** 2 * sin2x0 - h2 * lr ** 2 * lz ** 2 * sin2x0 + h3 * lr ** 2 * lz ** 2 * sin2x0 + 3 * h0 * lr ** 2 * lz ** 2 * sin2lx - 3 * h1 * lr ** 2 * lz ** 2 * sin2lx + h2 * lr ** 2 * lz ** 2 * sin2lx - h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                   (16 * lz) * lx ** 3), ((
                                                                  6 * h0 * sin2x0 + 6 * h2 * sin2x0 + 6 * h1 * sin2lx + 6 * h3 * sin2lx) * lx ** 2 + (
                                                                  6 * cos2x0 * h1 - 12 * cos2x0 * h0 - 12 * cos2x0 * h2 + 6 * cos2x0 * h3 - 6 * cos2lx * h0 + 12 * cos2lx * h1 - 6 * cos2lx * h2 + 12 * cos2lx * h3 + 6 * cos2x0 * h0 * lr ** 2 * lz ** 2 + 2 * cos2x0 * h2 * lr ** 2 * lz ** 2 - 6 * cos2lx * h1 * lr ** 2 * lz ** 2 - 2 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                                                  9 * h1 * sin2x0 - 9 * h0 * sin2x0 - 9 * h2 * sin2x0 + 9 * h3 * sin2x0 + 9 * h0 * sin2lx - 9 * h1 * sin2lx + 9 * h2 * sin2lx - 9 * h3 * sin2lx + 3 * h0 * lr ** 2 * lz ** 2 * sin2x0 - 3 * h1 * lr ** 2 * lz ** 2 * sin2x0 + h2 * lr ** 2 * lz ** 2 * sin2x0 - h3 * lr ** 2 * lz ** 2 * sin2x0 - 3 * h0 * lr ** 2 * lz ** 2 * sin2lx + 3 * h1 * lr ** 2 * lz ** 2 * sin2lx - h2 * lr ** 2 * lz ** 2 * sin2lx + h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                   (16 * lz) * lx ** 3), ((12 * cos2x0 * h0 + 12 * cos2x0 * h2) * lx ** 3 + (
            18 * h0 * sin2x0 - 6 * h1 * sin2x0 + 18 * h2 * sin2x0 - 6 * h3 * sin2x0) * lx ** 2 + (
                                                                  12 * cos2x0 * h1 - 18 * cos2x0 * h0 - 18 * cos2x0 * h2 + 12 * cos2x0 * h3 + 6 * cos2lx * h1 + 6 * cos2lx * h3 - 2 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 2 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 2 * cos2lx * h1 * lr ** 2 * lz ** 2 + 2 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                                                  9 * h1 * sin2x0 - 9 * h0 * sin2x0 - 9 * h2 * sin2x0 + 9 * h3 * sin2x0 + 9 * h0 * sin2lx - 9 * h1 * sin2lx + 9 * h2 * sin2lx - 9 * h3 * sin2lx - h0 * lr ** 2 * lz ** 2 * sin2x0 + h1 * lr ** 2 * lz ** 2 * sin2x0 - h2 * lr ** 2 * lz ** 2 * sin2x0 + h3 * lr ** 2 * lz ** 2 * sin2x0 + h0 * lr ** 2 * lz ** 2 * sin2lx - h1 * lr ** 2 * lz ** 2 * sin2lx + h2 * lr ** 2 * lz ** 2 * sin2lx - h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                   (16 * lz) * lx ** 3), ((
                                                                  - 6 * h0 * sin2x0 - 6 * h2 * sin2x0 - 6 * h1 * sin2lx - 6 * h3 * sin2lx) * lx ** 2 + (
                                                                  12 * cos2x0 * h0 - 6 * cos2x0 * h1 + 12 * cos2x0 * h2 - 6 * cos2x0 * h3 + 6 * cos2lx * h0 - 12 * cos2lx * h1 + 6 * cos2lx * h2 - 12 * cos2lx * h3 + 2 * cos2x0 * h0 * lr ** 2 * lz ** 2 + 2 * cos2x0 * h2 * lr ** 2 * lz ** 2 - 2 * cos2lx * h1 * lr ** 2 * lz ** 2 - 2 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                                                  9 * h0 * sin2x0 - 9 * h1 * sin2x0 + 9 * h2 * sin2x0 - 9 * h3 * sin2x0 - 9 * h0 * sin2lx + 9 * h1 * sin2lx - 9 * h2 * sin2lx + 9 * h3 * sin2lx + h0 * lr ** 2 * lz ** 2 * sin2x0 - h1 * lr ** 2 * lz ** 2 * sin2x0 + h2 * lr ** 2 * lz ** 2 * sin2x0 - h3 * lr ** 2 * lz ** 2 * sin2x0 - h0 * lr ** 2 * lz ** 2 * sin2lx + h1 * lr ** 2 * lz ** 2 * sin2lx - h2 * lr ** 2 * lz ** 2 * sin2lx + h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                   (16 * lz) * lx ** 3), ], [0, ((12 * cos2lx * h1 + 12 * cos2lx * h3) * lx ** 3 + (
            6 * h0 * sin2lx - 18 * h1 * sin2lx + 6 * h2 * sin2lx - 18 * h3 * sin2lx) * lx ** 2 + (
                                                                         6 * cos2x0 * h0 + 6 * cos2x0 * h2 + 12 * cos2lx * h0 - 18 * cos2lx * h1 + 12 * cos2lx * h2 - 18 * cos2lx * h3 - 6 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 2 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 6 * cos2lx * h1 * lr ** 2 * lz ** 2 + 2 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                                                         9 * h0 * sin2x0 - 9 * h1 * sin2x0 + 9 * h2 * sin2x0 - 9 * h3 * sin2x0 - 9 * h0 * sin2lx + 9 * h1 * sin2lx - 9 * h2 * sin2lx + 9 * h3 * sin2lx - 3 * h0 * lr ** 2 * lz ** 2 * sin2x0 + 3 * h1 * lr ** 2 * lz ** 2 * sin2x0 - h2 * lr ** 2 * lz ** 2 * sin2x0 + h3 * lr ** 2 * lz ** 2 * sin2x0 + 3 * h0 * lr ** 2 * lz ** 2 * sin2lx - 3 * h1 * lr ** 2 * lz ** 2 * sin2lx + h2 * lr ** 2 * lz ** 2 * sin2lx - h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                                                     (16 * lz) * lx ** 3), ((
                                                                                                    - 6 * h0 * sin2x0 - 6 * h2 * sin2x0 - 6 * h1 * sin2lx - 6 * h3 * sin2lx) * lx ** 2 + (
                                                                                                    12 * cos2x0 * h0 - 6 * cos2x0 * h1 + 12 * cos2x0 * h2 - 6 * cos2x0 * h3 + 6 * cos2lx * h0 - 12 * cos2lx * h1 + 6 * cos2lx * h2 - 12 * cos2lx * h3 + 2 * cos2x0 * h0 * lr ** 2 * lz ** 2 + 2 * cos2x0 * h2 * lr ** 2 * lz ** 2 - 2 * cos2lx * h1 * lr ** 2 * lz ** 2 - 2 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                                                                                    9 * h0 * sin2x0 - 9 * h1 * sin2x0 + 9 * h2 * sin2x0 - 9 * h3 * sin2x0 - 9 * h0 * sin2lx + 9 * h1 * sin2lx - 9 * h2 * sin2lx + 9 * h3 * sin2lx + h0 * lr ** 2 * lz ** 2 * sin2x0 - h1 * lr ** 2 * lz ** 2 * sin2x0 + h2 * lr ** 2 * lz ** 2 * sin2x0 - h3 * lr ** 2 * lz ** 2 * sin2x0 - h0 * lr ** 2 * lz ** 2 * sin2lx + h1 * lr ** 2 * lz ** 2 * sin2lx - h2 * lr ** 2 * lz ** 2 * sin2lx + h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                                                     (16 * lz) * lx ** 3), ((
                                                                                                    - 12 * cos2lx * h1 - 12 * cos2lx * h3) * lx ** 3 + (
                                                                                                    18 * h1 * sin2lx - 6 * h0 * sin2lx - 6 * h2 * sin2lx + 18 * h3 * sin2lx) * lx ** 2 + (
                                                                                                    18 * cos2lx * h1 - 6 * cos2x0 * h2 - 12 * cos2lx * h0 - 6 * cos2x0 * h0 - 12 * cos2lx * h2 + 18 * cos2lx * h3 - 2 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 2 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 2 * cos2lx * h1 * lr ** 2 * lz ** 2 + 2 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                                                                                    9 * h1 * sin2x0 - 9 * h0 * sin2x0 - 9 * h2 * sin2x0 + 9 * h3 * sin2x0 + 9 * h0 * sin2lx - 9 * h1 * sin2lx + 9 * h2 * sin2lx - 9 * h3 * sin2lx - h0 * lr ** 2 * lz ** 2 * sin2x0 + h1 * lr ** 2 * lz ** 2 * sin2x0 - h2 * lr ** 2 * lz ** 2 * sin2x0 + h3 * lr ** 2 * lz ** 2 * sin2x0 + h0 * lr ** 2 * lz ** 2 * sin2lx - h1 * lr ** 2 * lz ** 2 * sin2lx + h2 * lr ** 2 * lz ** 2 * sin2lx - h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                                                     (16 * lz) * lx ** 3), ], [0, 0, (
            (- 12 * cos2x0 * h0 - 12 * cos2x0 * h2) * lx ** 3 + (
            6 * h1 * sin2x0 - 18 * h0 * sin2x0 - 18 * h2 * sin2x0 + 6 * h3 * sin2x0) * lx ** 2 + (
                    18 * cos2x0 * h0 - 12 * cos2x0 * h1 + 18 * cos2x0 * h2 - 12 * cos2x0 * h3 - 6 * cos2lx * h1 - 6 * cos2lx * h3 - 2 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 6 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 2 * cos2lx * h1 * lr ** 2 * lz ** 2 + 6 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                    9 * h0 * sin2x0 - 9 * h1 * sin2x0 + 9 * h2 * sin2x0 - 9 * h3 * sin2x0 - 9 * h0 * sin2lx + 9 * h1 * sin2lx - 9 * h2 * sin2lx + 9 * h3 * sin2lx - h0 * lr ** 2 * lz ** 2 * sin2x0 + h1 * lr ** 2 * lz ** 2 * sin2x0 - 3 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 3 * h3 * lr ** 2 * lz ** 2 * sin2x0 + h0 * lr ** 2 * lz ** 2 * sin2lx - h1 * lr ** 2 * lz ** 2 * sin2lx + 3 * h2 * lr ** 2 * lz ** 2 * sin2lx - 3 * h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                                                                                       (
                                                                                                               16 * lz) * lx ** 3),
                                                                                               ((
                                                                                                        6 * h0 * sin2x0 + 6 * h2 * sin2x0 + 6 * h1 * sin2lx + 6 * h3 * sin2lx) * lx ** 2 + (
                                                                                                        6 * cos2x0 * h1 - 12 * cos2x0 * h0 - 12 * cos2x0 * h2 + 6 * cos2x0 * h3 - 6 * cos2lx * h0 + 12 * cos2lx * h1 - 6 * cos2lx * h2 + 12 * cos2lx * h3 + 2 * cos2x0 * h0 * lr ** 2 * lz ** 2 + 6 * cos2x0 * h2 * lr ** 2 * lz ** 2 - 2 * cos2lx * h1 * lr ** 2 * lz ** 2 - 6 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                                                                                        9 * h1 * sin2x0 - 9 * h0 * sin2x0 - 9 * h2 * sin2x0 + 9 * h3 * sin2x0 + 9 * h0 * sin2lx - 9 * h1 * sin2lx + 9 * h2 * sin2lx - 9 * h3 * sin2lx + h0 * lr ** 2 * lz ** 2 * sin2x0 - h1 * lr ** 2 * lz ** 2 * sin2x0 + 3 * h2 * lr ** 2 * lz ** 2 * sin2x0 - 3 * h3 * lr ** 2 * lz ** 2 * sin2x0 - h0 * lr ** 2 * lz ** 2 * sin2lx + h1 * lr ** 2 * lz ** 2 * sin2lx - 3 * h2 * lr ** 2 * lz ** 2 * sin2lx + 3 * h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                                                                                       (
                                                                                                               16 * lz) * lx ** 3), ],
                          [0, 0, 0, ((12 * cos2lx * h1 + 12 * cos2lx * h3) * lx ** 3 + (
                                  6 * h0 * sin2lx - 18 * h1 * sin2lx + 6 * h2 * sin2lx - 18 * h3 * sin2lx) * lx ** 2 + (
                                             6 * cos2x0 * h0 + 6 * cos2x0 * h2 + 12 * cos2lx * h0 - 18 * cos2lx * h1 + 12 * cos2lx * h2 - 18 * cos2lx * h3 - 2 * cos2x0 * h0 * lr ** 2 * lz ** 2 - 6 * cos2x0 * h2 * lr ** 2 * lz ** 2 + 2 * cos2lx * h1 * lr ** 2 * lz ** 2 + 6 * cos2lx * h3 * lr ** 2 * lz ** 2) * lx + (
                                             9 * h0 * sin2x0 - 9 * h1 * sin2x0 + 9 * h2 * sin2x0 - 9 * h3 * sin2x0 - 9 * h0 * sin2lx + 9 * h1 * sin2lx - 9 * h2 * sin2lx + 9 * h3 * sin2lx - h0 * lr ** 2 * lz ** 2 * sin2x0 + h1 * lr ** 2 * lz ** 2 * sin2x0 - 3 * h2 * lr ** 2 * lz ** 2 * sin2x0 + 3 * h3 * lr ** 2 * lz ** 2 * sin2x0 + h0 * lr ** 2 * lz ** 2 * sin2lx - h1 * lr ** 2 * lz ** 2 * sin2lx + 3 * h2 * lr ** 2 * lz ** 2 * sin2lx - 3 * h3 * lr ** 2 * lz ** 2 * sin2lx)) / (
                                   (16 * lz) * lx ** 3), ], ])
    for i in range(ke2_dx_dy.shape[0]):
        for j in range(ke2_dx_dy.shape[1] - i - 1):
            ke2_dx_dy[j + i + 1, i] = ke2_dx_dy[i, j + i + 1]

    return ke2_dx_dy


# Test case
def test_calc_ke2_dx2():
    # Test parameters
    x0 = np.pi / 4  # 45 degrees
    lr = 1.0
    lx = 0.5
    lz = 0.3
    h = np.array([1.0, 2.0, 3.0, 4.0])

    # Calculate the matrix
    result = calc_ke2_dx2(x0, lr, lx, lz, h)
    # Print the result
    print("Resulting matrix:")
    print(result)
    # Verify symmetry
    is_symmetric = np.allclose(result, result.T)
    print("\nMatrix is symmetric:", is_symmetric)

    result = calc_ke2_dy2(x0, lr, lx, lz, h)
    # Print the result
    print("\nResulting matrix:")
    print(result)
    # Verify symmetry
    is_symmetric = np.allclose(result, result.T)
    print("\nMatrix is symmetric:", is_symmetric)

    result = calc_ke2_dx_dy(x0, lr, lx, lz, h)
    # Print the result
    print("\nResulting matrix:")
    print(result)
    # Verify symmetry
    is_symmetric = np.allclose(result, result.T)
    print("\nMatrix is symmetric:", is_symmetric)


# Run the test
if __name__ == "__main__":
    test_calc_ke2_dx2()
# @njit
# def calc_fe_dyt(x0, lx, lz, vf, lambda_value):
#     fe_dyt = 2 * vf * lambda_value * np.array(
#         [-(lz * (np.cos(lx + x0) - np.cos(x0))) / (2 * lx), (lz * (np.cos(lx + x0) - np.cos(x0))) / (2 * lx),
#          -(lz * (np.cos(lx + x0) - np.cos(x0))) / (2 * lx), (lz * (np.cos(lx + x0) - np.cos(x0))) / (2 * lx), ])
#     return fe_dyt



