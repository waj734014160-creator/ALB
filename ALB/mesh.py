import unittest

import numpy as np
from numba import njit

from ALB.base import BaseElem, BaseMesh, BaseNode


def take_args(func, keys=None, z_lim=False):
    """
    Standardize the input of mesh generation functions
    """
    if keys is None:
        keys = ["x_lim", "y_lim", "size"]

    def addon(args):
        if z_lim:
            keys.append("z_lim")
        args = [np.array(args[key]) for key in keys]
        return func(*args)

    return addon


@njit
def create_serend_2d(
    x_lim: np.ndarray, y_lim: np.ndarray, size: np.ndarray
) -> (np.ndarray, np.ndarray):
    """
    :param x_lim: x-coordinate upper and lower limits
    :param y_lim: y-coordinate upper and lower limits
    :param size: Number of mesh grids
    :return: p for node coordinates, elems for mapping between elements and nodes
    """
    nx = size[0]
    ny = size[1]
    x0 = np.linspace(x_lim[0], x_lim[1], nx + 1)
    x1 = np.linspace(x_lim[0], x_lim[1], 2 * nx + 1)
    y0 = np.linspace(y_lim[0], y_lim[1], ny + 1)
    y1 = np.linspace(y_lim[0], y_lim[1], 2 * ny + 1)
    p0 = np.array([(i, j) for i in x0 for j in y0])
    p1 = np.array(
        [(x1[2 * i + 1], y1[2 * j]) for i in range(nx) for j in range(ny + 1)]
    )  # x ?
    p2 = np.array(
        [(x1[2 * i], y1[2 * j + 1]) for i in range(nx + 1) for j in range(ny)]
    )  # y ?
    num1 = p0.shape[0]
    num2 = p0.shape[0] + p1.shape[0]
    p = np.vstack((p0, p1, p2))
    elems = np.array(
        [
            (
                (ny + 1) * i + j,
                (ny + 1) * (i + 1) + j,
                (ny + 1) * (i + 1) + j + 1,
                (ny + 1) * i + j + 1,
                num1 + (ny + 1) * i + j,
                num2 + ny * (i + 1) + j,
                num1 + (ny + 1) * i + j + 1,
                num2 + ny * i + j,
            )
            for i in range(nx)
            for j in range(ny)
        ]
    )
    return p, elems


@njit
def create_rect(x_lim, y_lim, size):
    """
    :param x_lim: x-coordinate upper and lower limits
    :param y_lim: y-coordinate upper and lower limits
    :param size: Number of mesh grids
    :return: p for node coordinates, elems for mapping between elements and nodes
    """
    nx = size[0]
    ny = size[1]
    x0 = np.linspace(x_lim[0], x_lim[1], nx + 1)
    y0 = np.linspace(y_lim[0], y_lim[1], ny + 1)
    p = np.array([(i, j) for i in x0 for j in y0])
    elems = np.array(
        [
            (
                (ny + 1) * i + j,
                (ny + 1) * (i + 1) + j,
                (ny + 1) * i + j + 1,
                (ny + 1) * (i + 1) + j + 1,
            )
            for i in range(nx)
            for j in range(ny)
        ]
    )
    return p, elems


@njit
def create_rect_by_mesh(xs, ys):
    x0 = xs
    y0 = ys
    nx = len(x0) - 1
    ny = len(y0) - 1
    p = np.array([(i, j) for i in x0 for j in y0])
    elems = np.array(
        [
            (
                (ny + 1) * i + j,
                (ny + 1) * (i + 1) + j,
                (ny + 1) * i + j + 1,
                (ny + 1) * (i + 1) + j + 1,
            )
            for i in range(nx)
            for j in range(ny)
        ]
    )
    return p, elems


@njit
def create_tri(x_lim, y_lim, size):
    """
    :param x_lim: x-coordinate upper and lower limits
    :param y_lim: y-coordinate upper and lower limits
    :param size: Number of mesh grids
    :return: p for node coordinates, elems for mapping between elements and nodes
    """
    nx = size[0]
    ny = size[1]
    x0 = np.linspace(x_lim[0], x_lim[1], nx + 1)
    y0 = np.linspace(y_lim[0], y_lim[1], ny + 1)
    p = np.array([(i, j) for i in x0 for j in y0])
    elems = np.array(
        [
            (
                (ny + 1) * i + j,
                (ny + 1) * (i + 1) + j,
                (ny + 1) * (i + 1) + j + 1,
                (ny + 1) * i + j,
                (ny + 1) * i + j + 1,
                (ny + 1) * (i + 1) + j + 1,
            )
            for i in range(nx)
            for j in range(ny)
        ]
    )
    elems = elems.reshape((nx * ny * 2, 3))
    return p, elems


class Mesh(BaseMesh):
    """
    Mesh builder utilities for rectangular, triangular, and serendipity grids.
    """

    def build_rect(self, nodeclass, elemclass, x_lim, y_lim, size, **elemargs):
        """
        :param nodeclass: Node class
        :param elemclass: Element class
        :param x_lim: x-coordinate upper and lower limits
        :param y_lim: y-coordinate upper and lower limits
        :param size: Number of mesh grids
        """
        x_lim = np.array(x_lim)
        y_lim = np.array(y_lim)
        size = np.array(size)
        ps, elems = create_rect(x_lim, y_lim, size)
        return self.create_mesh(ps, elems, nodeclass, elemclass, **elemargs)

    def build_rect_by_mesh(self, nodeclass, elemclass, xs, ys, **elemargs):
        """
        :param nodeclass: Node class
        :param elemclass: Element class
        :param xs: x-coordinates
        :param ys: y-coordinates
        """
        xs = np.array(xs)
        ys = np.array(ys)
        ps, elems = create_rect_by_mesh(xs, ys)
        return self.create_mesh(ps, elems, nodeclass, **elemclass, **elemargs)

    def build_tri(self, nodeclass, elemclass, x_lim, y_lim, size, **elemargs):
        """
        :param nodeclass: Node class
        :param elemclass: Element class
        :param x_lim: x-coordinate upper and lower limits
        :param y_lim: y-coordinate upper and lower limits
        :param size: Number of mesh grids
        """
        ps, elems = create_tri(x_lim, y_lim, size)
        return self.create_mesh(ps, elems, nodeclass, elemclass, **elemargs)

    def build_serend_2d(self, nodeclass, elemclass, x_lim, y_lim, size, **elemargs):
        """
        :param nodeclass: Node class
        :param elemclass: Element class
        :param x_lim: x-coordinate upper and lower limits
        :param y_lim: y-coordinate upper and lower limits
        :param size: Number of mesh grids
        """
        ps, elems = create_serend_2d(x_lim, y_lim, size)
        return self.create_mesh(ps, elems, nodeclass, elemclass, **elemargs)

    def create_mesh(self, ps, elems, nodeclass, elemclass, **elemargs):
        """
        :param ps: Node coordinates
        :param elems: Mapping between elements and nodes
        :param nodeclass: Node class
        :param elemclass: Element class
        """
        self._ps = ps
        self._mapping = elems
        nodes = np.array([nodeclass(p) for p in ps])
        elems = np.array([elemclass(nodes[el], **elemargs) for el in elems])
        return nodes, elems


class MeshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.kargs = {
            "x_lim": np.array([0, 1]),
            "y_lim": np.array([0, 1]),
            "size": np.array([20, 20]),
        }
        self.mesh = Mesh(self.kargs)

    def test_build_mesh(self):
        print(self.mesh.build("rect", BaseNode, BaseElem))

    def test_tri(self):
        print(self.mesh.build("tri", BaseNode, BaseElem))

    def test_serend(self):
        print(self.mesh.build("serend_2d", BaseNode, BaseElem))


def pair_wise(L, end=False):
    """
    Generate a pairwise iterator
    """
    pool = tuple(L)
    n = len(pool)
    assert n >= 2, "Length of iterable must greater than 2"
    if end is True:
        indices = list(range(n))
        for i in indices:
            if i < n - 1:
                yield pool[i], pool[i + 1]
            else:
                yield pool[i], pool[0]

    if end is False:
        indices = list(range(n - 1))
        for i in indices:
            yield pool[i], pool[i + 1]


if __name__ == "__main__":
    unittest.main()


