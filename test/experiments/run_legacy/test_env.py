# ?coding: utf-8 ?
import math

import numpy as np

from ALB.film import RectFilmElem, RectFilmNode, FilmBoundary
from ALB.base import ElemManager, NodeManager, MatrixProcess
from ALB.mesh import Mesh

mesh = Mesh()
x_lim = np.array([0, 2 * np.pi])
y_lim = np.array([-1, 1])

e = 0.5  # e, ?
angel = 0  # angel, ?
w = 1000  # w, €?
x0 = 0  # x0, ﹀ ㄥ € ?
lx = 360  # LX, ?
lz = 2  # LZ, ?
nx = 100  # NX,x ?
nz = 100  # NZ,z ?
size = np.array([nx, nz])
miu = 0.0195  # miu, ㄥ
c = 80E-6  # c,
rho = 872  # rho,
r = 0.04  # r ?
l = 0.08  # l ?
ps = 1E6  # ?
reynold = True  #  
coe = True  # ′
p_set = 0  # ф 
error_set = 1E-10  # 
max_iter = 30  # € ц ｆ ?
damp = 0.8
lambda_value = 3 / 2 * miu * (w * 2 * math.pi / 60) * l ** 2 / ps / c ** 2
lr = l / 2 / r
nodes, elems = mesh.build_rect(RectFilmNode, RectFilmElem, x_lim, y_lim, size, lambda_value=lambda_value, lr=lr)
elems = ElemManager(elems)
nodes = NodeManager(nodes)
matrix_process = MatrixProcess()
boundary = FilmBoundary()
