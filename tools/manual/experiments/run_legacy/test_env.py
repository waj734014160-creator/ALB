# Encoding-repaired comment.
import math

import numpy as np

from ALB.physics.film import FilmBoundary, RectFilmElem, RectFilmNode
from ALB.core.fem import ElemManager, MatrixProcess, Mesh, NodeManager

mesh = Mesh()
x_lim = np.array([0, 2 * np.pi])
y_lim = np.array([-1, 1])

e = 0.5  # eccentricity ratio
angel = 0  # attitude angle
w = 1000  # rotational speed
x0 = 0  # initial angular coordinate
lx = 360  # circumferential span in degrees
lz = 2  # axial span
nx = 100  # circumferential node count
nz = 100  # axial node count
size = np.array([nx, nz])
miu = 0.0195  # dynamic viscosity
c = 80E-6  # c,
rho = 872  # rho,
r = 0.04  # journal radius
l = 0.08  # bearing length
ps = 1E6  # supply pressure
reynold = True  # enable Reynolds boundary condition
coe = True  # enable coupled equation
p_set = 0  # pressure boundary setting
error_set = 1E-10  # solver tolerance
max_iter = 30  # maximum iterations
damp = 0.8
lambda_value = 3 / 2 * miu * (w * 2 * math.pi / 60) * l ** 2 / ps / c ** 2
lr = l / 2 / r
nodes, elems = mesh.build_rect(RectFilmNode, RectFilmElem, x_lim, y_lim, size, lambda_value=lambda_value, lr=lr)
elems = ElemManager(elems)
nodes = NodeManager(nodes)
matrix_process = MatrixProcess()
boundary = FilmBoundary()
