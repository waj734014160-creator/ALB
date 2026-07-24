import os
import unittest
from functools import wraps

from abc import ABC, abstractmethod
import numpy as np
import pandas as pd
import scipy.sparse as sp
from numba import njit

from ALB.core.component import BaseCSystem, BaseSimpleModel, BaseSystem
from ALB.core.time import TimeIter, TimeIterDt


# def opensinglelist(func):
#     """
#     """
#
#     @wraps(func)
#     def review(*args, **kwargs):
#         return_value = func(*args, **kwargs)
#         if len(return_value) == 1:
#             return_value = return_value[0]
#         elif len(return_value) == 0:
#             return_value = None
#         return return_value
#
#     return review
#
#
# def intcheck(func):
#     """
#     """
#
#     @wraps(func)
#     def review(cls, val):
#         if isinstance(val, (int, np.int_)):
#             return_value = func(cls, val)
#             return return_value
#         else:
#             raise Exception("val must be int")
#
#     return review
#
#
def resize(right=False):
    """
    data->(n),if matrix ,position->(n/2,2)
    if right, position->(n)
    """

    def decorate(func):
        @wraps(func)
        def wrapper(cls, datas, positions, *args, **kwargs):
            datas = np.array(datas)
            positions = np.array(positions)
            datas = datas.reshape(datas.size)
            if right:
                positions = positions.reshape(positions.size)
            else:
                positions = positions.reshape(positions.size // 2, 2)
            return func(cls, datas, positions, *args, **kwargs)

        return wrapper

    return decorate


# class resize:
#     def __init__(self, right=False):
#         self.right = right
#
#     def __call__(self, func):
#         @wraps(func)
#         def wrapper(cls, datas, positions, *args, **kwargs):
#             datas = np.array(datas)
#             positions = np.array(positions)
#             datas = datas.reshape(datas.size)
#             if self.right:
#                 positions = positions.reshape(positions.size)
#             else:
#                 positions = positions.reshape(positions.size // 2, 2)
#             return func(cls, datas, positions, *args, **kwargs)
#         return wrapper

class BaseNode:
    """
    Base class for a node in a finite element model.
    """

    def __init__(self, coords, freedom: int = 1):
        """
        :param coords: node coordinates
        """
        self._number = None  # node number
        self.coords = coords  # node coordinates
        self.freedom = freedom

    @property
    def number(self):
        return self._number

    @number.setter
    def number(self, val):
        if isinstance(val, (int, np.int_)):
            self._number = val
        else:
            raise Exception('error node number set')

    @property
    def coords(self):
        return self._coords

    @coords.setter
    def coords(self, val):
        if isinstance(val, (np.ndarray, list)):
            self._coords = np.array(val)
            self._dim = len(val)
        else:
            raise Exception('error node coords setting')
            pass

    @property
    def dim(self):
        """
        Abstract method to be implemented by subclasses.
        """
        return self._dim

    @dim.setter
    def dim(self, value):
        self._dim = value

    def is_this(self, dims, coords, **kwargs) -> bool:
        """
        Check if the node coordinates match the search criteria.
        :param dims: dimensions to query
        :param coords: corresponding coordinate values to query
        :return: True if it meets the requirements
        eg:
        node.coords = [1,2]
        node.is_this([0,1],[1,2]) = True
        node.is_this([0],[1]) = True

        Options:
        err:float, tolerance, default=1e-10
        """
        err = kwargs.get('err', 1e-10)

        return is_this_func(self.coords, dims, coords, err)


@njit(nogil=True, cache=True)
def is_this_func(self_coords, dims, coords, err) -> bool:
    """
    A Numba JIT-compiled function to check if a node's coordinates match given criteria.
    :param self_coords: The coordinates of the node.
    :param dims: The dimensions to check.
    :param coords: The coordinates to match.
    :param err: The tolerance for matching.
    :return: True if the coordinates match, False otherwise.
    """
    dims = np.array(dims)
    dims = dims.reshape(dims.size)
    coords = np.array(coords)
    coords = coords.reshape(coords.size)
    for num, dim in enumerate(dims):
        if abs(coords[num] - self_coords[dim]) > err:
            return False
    else:
        return True


class NodeManager:
    def __init__(self, nodes=None, freedom: int = 1):
        """
        Manages a collection of nodes.
        :param nodes: An iterable of nodes to initialize the manager with.
        :param freedom: The number of degrees of freedom per node.
        """
        self._nodes = {}
        self._count = 0
        self._freedom = freedom
        if nodes is not None:
            self.nodes = nodes

    def __getitem__(self, item):
        return self.nodes[item]

    def __call__(self, *args, **kwargs):
        return self._nodes.values()

    @property
    def nodes(self) -> dict:
        return self._nodes

    @nodes.setter
    def nodes(self, nodes):
        """
        Set the nodes in the manager.
        :param nodes: An iterable of nodes, not a dict.
        """
        self.adds(nodes)

    @property
    def freedoms(self) -> int:
        """
        Total degrees of freedom of all nodes.
        :return:int
        """
        return self._calc_freedoms()

    def add(self, node: BaseNode):
        """
        Add a single node.
        """
        assert issubclass(type(node), BaseNode), 'Please add a node object.'
        if node.number is None:
            node.number = self._count
            self._count += 1
        self.nodes[node.number] = node

    def adds(self, *nodes):
        """
        Add multiple nodes.
        """
        for nd in nodes:
            if isinstance(nd, (list, tuple, np.ndarray)):
                for n in nd:
                    self.add(n)
            else:
                self.add(nd)

    @property
    def non(self) -> int:
        """
        Returns the number of nodes.
        """
        return len(self.nodes)

    def search(self, dims, coords, **kwargs):
        """
        Search for nodes.
        option:number
        if number is true, return the number list of nodes
        :param dims: search dimensions
        :param coords: corresponding coordinates
        :return: A list of nodes or node numbers.
        """
        if 'number' in kwargs.keys():
            number = kwargs['number']
        else:
            number = False
        if number is True:
            nodes = [node.number for node in self() if node.is_this(dims, coords)]
            if len(nodes) == 1:
                nodes = nodes[0]
            return nodes
        nodes = [node for node in self() if node.is_this(dims, coords)]
        if len(nodes) == 1:
            nodes = nodes[0]
        return nodes

    def mindistance_search(self, coords: np.ndarray):
        """
        Search for the nearest node and return it.
        """
        length = np.array([((coords - nd.coords) ** 2).sum() for nd in self.nodes.values()])
        node_number = length.argmin()
        node = self.nodes[node_number]
        return node

    def delete(self, node_number):
        """
        Deletes a node and re-indexes the remaining nodes.
        This function has not been fully tested and may affect element assembly or other parts.
        It is reserved for future extension.
        """
        return_node = self.nodes.pop(node_number)
        self._nodes = {num: node for num, node in enumerate(self())}
        for num, node in self.nodes.items():
            node.number = num
        return return_node

    def _calc_freedoms(self) -> int:
        """
        Calculate the total degrees of freedom.
        """
        return self.non * self[0].freedom


class BaseElem:
    matrixs_name = []
    rights_name = []

    def __init__(self, nodes=None, args=None):
        """
        :param nodes:list,np.ndarray,tuple,len(nodes)>=2
        """
        self._nodes = None
        self._number = None  # Element number
        self._args = args  # Element parameters
        self._mapping = None
        self._matrixs = {}
        self._rights = {}
        if nodes is not None:
            self.nodes = nodes  # Nodes within the element

    def __len__(self):
        """
        Return the number of nodes in the element.
        """
        return self._nodes_number

    # Call nodes within the element
    @property
    def nodes(self) -> dict:
        """
        Return the nodes within the element.
        """
        return self._nodes

    @nodes.setter
    def nodes(self, nodes):
        """
        When inputting nodes, create initialization for the number of nodes, element stiffness matrix, and right-hand side.
        Also, obtain the set of node numbers on the element from the nodes.
        """
        if isinstance(nodes, (list, tuple, np.ndarray)):
            self._nodes = {key: value for key, value in enumerate(nodes)}
            self._nodes_number = len(nodes)
        else:
            raise Exception("Please input iterable object of the node substance")

    @property
    def nodes_number(self) -> int:
        return self._nodes_number
    @property
    def number(self) -> int:
        return self._number
    @number.setter
    def number(self, val):
        if isinstance(val, int):
            self._number = val
        else:
            raise Exception('error elem number set')
            pass

    @property
    def args(self):
        """
        :return: Element parameters, used for element matrix calculation.
        """
        return self._args

    @args.setter
    def args(self, args):
        self._args = args

    @property
    def mapping(self) -> np.ndarray:
        """
        Return the set of node numbers on the element.
        """
        return np.array([node.number for node in self.nodes.values()])

    @property
    def matrixs(self) -> dict:
        """
        Calculate matrices and return them by name.
        :return:['matrix_name':matrix]
        """
        return self._matrixs

    @property
    def rights(self) -> dict:
        """
        Calculate the right-hand side and return it.
        :return: np.ndarray
        """
        return self._rights

    def calc_matrixs(self):
        """
        Perform stiffness matrix calculation for the element.
        """
        pass

    def calc_rights(self):
        """
        Perform right-hand side calculation for the element.
        """
        pass

    def intergral(self):
        """
        Perform integral calculation on the results of the element.
        """
        pass

    def mean_coords(self):
        """
        Return the average coordinates of all nodes, which can be considered the center of the element.
        """
        mean_coords = np.array([node.coords for node in self.nodes.values()]).mean(axis=0)
        return mean_coords

    # Interpolation
    def interpolation(self, coords):
        """
        Interpolation calculation.
        """
        pass


class ElemManager:
    def __init__(self, elems=None, args=None):
        """
        Initialization method for ElemManager.
        """
        self._right = None  # Right-hand items
        self._matrixs = None  # Matrices
        self._elems = {}  # Element dictionary
        self._count = 0  # Counter for assigning element numbers
        self._elems_args = args  # Element set parameters, assigned to all elements
        if elems is not None:
            self.elems = elems
            self.set_args(args)

    def __getitem__(self, item):
        return self._elems[item]

    def __call__(self, *args, **kwargs):
        return self._elems.values()

    @property
    def elems(self) -> dict:
        return self._elems

    @property
    def elems_args(self):
        return self._elems_args

    @elems_args.setter
    def elems_args(self, val):
        """
        When the element set parameters are set, all are set.
        """
        self._elems_args = val
        self.set_args(val)

    @elems.setter
    def elems(self, *elems):
        self.adds(*elems)

    def _add(self, elem):
        """
        Add a single element and set its parameters to self.elems_args.
        """
        assert issubclass(type(elem), BaseElem), 'Please add an element.'
        if elem.number is None:
            elem.number = self._count
            self._count += 1
        elem.args = self.elems_args
        self.elems[elem.number] = elem

    def adds(self, *elems):
        """
        Add multiple elements and set their parameters to self.elems_args.
        """
        for elem in elems:
            if isinstance(elem, (list, tuple, np.ndarray)):
                for el in elem:
                    self._add(el)
            else:
                self._add(elem)

    @property
    def noe(self) -> int:
        """
        Return the number of elements.
        """
        return len(self.elems)

    def delete(self, number):
        """
        Delete an element by its key.
        """
        return self.elems.pop(number)

    def set_args(self, args, *numbers):
        """
        Set the calculation parameters for all elements by default.
        """
        if not numbers:
            for elem in self.elems.values():
                elem.args = args
        else:
            for number in numbers:
                if isinstance(number, (list, tuple, np.ndarray)):
                    for num in number:
                        self.elems[num].args = args
                else:
                    self.elems[number].args = args

    def assemble_matrixs_rights(self, freedoms: int, calc: bool = True) -> tuple:
        """
        Calculate the stiffness matrices and right-hand sides of all elements and assemble them into total matrices and right-hand sides.
        :param freedoms: Total degrees of freedom.
        :param calc: If True (default), re-calculate all stiffness matrices. If False, return the last calculated result (or None if none exists).
        :return: matrix, right
        """
        return self.assemble_matrixs(freedoms, calc), self.assemble_rights(freedoms, calc)

    def assemble_matrixs(self, freedoms: int, calc: bool = True, csc: bool = True) -> dict:
        """
        Calculate the stiffness matrices of all elements and assemble them into a total stiffness matrix.
        :param freedoms: Total degrees of freedom.
        :param calc: If True (default), re-calculate all stiffness matrices. If False, return the last calculated result (or None if none exists).
        :param csc: If True (default), return a sparse matrix, otherwise return a np.ndarray.
        :return: Total stiffness matrix, {matrix_name:matrix}, a copy of the total matrix to decouple from subsequent data calculations.
        """
        if calc:
            matrixs = self._assemble_matrix(freedoms)
            self._matrixs = {}
            for name, matrix in matrixs.items():
                self._matrixs[name] = matrix
        else:
            matrixs = self._matrixs.copy()
        if csc:
            matrixs = {name: sp.csc_matrix(matrix) for name, matrix in matrixs.items()}
        else:
            matrixs = {name: matrix.toarray() for name, matrix in matrixs.items()}
        return matrixs

    def assemble_rights(self, freedoms: int, calc: bool = True) -> dict:
        """
        Calculate the right-hand sides of all elements and assemble them into a total right-hand side.
        :param freedoms: Total degrees of freedom.
        :param calc: If True (default), re-calculate all stiffness matrices. If False, return the last calculated result (or None if none exists).
        :return: A copy of the total right-hand side to decouple from subsequent data calculations.
        """
        if calc:
            rights = self._assemble_right(freedoms)
            self._right = {}
            for name, right in rights.items():
                self._right[name] = right
        return self._right.copy()

    def _assemble_matrix(self, freedoms) -> dict:
        """
        Used to assemble matrices.
        """
        matrix_names = self.elems[0].matrixs_name
        for elem in self():
            elem.calc_matrixs()
        elems_matrixs = {name: np.array([elem.matrixs[name] for elem in self()]) for name in matrix_names}
        mappings = np.array([elem.mapping for elem in self()])
        return {name: _assemble_matrixs(elm, mappings, freedoms) for name, elm in elems_matrixs.items()}

    def _assemble_right(self, freedoms) -> dict:
        """
        Used to assemble right-hand sides.
        """
        right_names = self.elems[0].rights_name
        for elem in self():
            elem.calc_rights()
        elems_rights = {name: np.array([elem.rights[name] for elem in self()]) for name in right_names}
        mappings = np.array([elem.mapping for elem in self()])
        return {name: _assemble_rights(elm, mappings, freedoms) for name, elm in elems_rights.items()}

    def search(self, dims, coords):
        """
        Search for elements within a given range.
        """
        dims = np.array(dims)
        dims = dims.reshape((-1, 1))
        coords = np.array(coords)
        coords = coords.reshape((-1, 2))
        if coords.size != 2 * dims.size:
            raise Exception('coords must be 2*dims.size')
        elems = self.elems.values()
        for dim in dims:
            elems = [elem for elem in elems if coords[dim, 0] <= elem.mean_coords()[dim] <= coords[dim, 1]]
        return elems

@njit(nogil=True)
def _assemble(elem_matrixs, elem_rights, mappings, freedoms):
    """
    :param elem_matrixs: All element matrices of the model, index corresponds to matrix number.
    :param elem_rights: All element right-hand sides of the model, index corresponds to matrix number.
    :param mappings: All element mappings of the model, index corresponds to matrix number.
    :param freedoms: Total degrees of freedom.
    :return: Assembled matrix and right-hand side.
    """
    matrix = _assemble_matrixs(elem_matrixs, mappings, freedoms)
    right = _assemble_rights(elem_rights, mappings, freedoms)
    return matrix, right


# @njit(nogil=True)
# def _assemble_matrix(elem_matrix, mapping: np.ndarray, matrix: np.ndarray):
#     """
#     """
#     el_non = elem_matrix.shape[0]
#     for n in range(el_non):
#         tol_n = mapping[n]
#         for m in range(el_non):
#             tol_m = mapping[m]
#             matrix[tol_n, tol_m] += elem_matrix[n, m]
#     return matrix


@njit(nogil=True)
def _assemble_right(elem_right: np.ndarray, mapping: np.ndarray, right: np.ndarray):
    """
    Assemble the right-hand side, accelerated with njit.
    :param elem_right: Element right-hand side.
    :param mapping: Element mapping.
    :param right: Total right-hand side.
    """
    el_non = elem_right.size
    for n in range(el_non):
        tol_n = mapping[n]
        right[tol_n] += elem_right[n]
    return right


# @njit(nogil=True)
# def _assemble_matrixs(elem_matrixs: np.ndarray, mappings: np.ndarray, freedoms: int):
#     """
# :param freedoms:
#     """
#     init_matrix = np.zeros((freedoms, freedoms))
#     el_non = elem_matrixs[0].shape[0]
#     for num, elm in enumerate(elem_matrixs):
#         mapping = mappings[num]
#         for n in range(el_non):
#             tol_n = mapping[n]
#             for m in numba.prange(el_non):
#                 tol_m = mapping[m]
#                 init_matrix[tol_n, tol_m] += elm[n, m]
#     return init_matrix

def _assemble_matrixs(elem_matrixs: np.ndarray, mappings: np.ndarray, freedoms: int):
    """
    Assemble matrices, accelerated with njit.
    :param elem_matrixs: All element matrices of the model, index corresponds to matrix number.
    :param mappings: All element mappings of the model, index corresponds to matrix number.
    :param freedoms: Total degrees of freedom.
    """
    non = elem_matrixs.shape[-1]
    elem_matrixs = elem_matrixs.reshape((-1, elem_matrixs.shape[-1] ** 2))
    datas, rows, cols = _assemble_matrixs_coord(elem_matrixs, mappings, non)
    matrixs = sp.coo_matrix((datas, (rows, cols)), shape=(freedoms, freedoms))
    matrixs = matrixs.tocsc()
    return matrixs


@njit(nogil=True)
def _assemble_matrixs_coord(elem_matrixs: np.ndarray, mappings: np.ndarray, non):
    """
    Assemble matrices, accelerated with njit.
    :param elem_matrixs: All element matrices of the model, index corresponds to matrix number.
    :param mappings: All element mappings of the model, index corresponds to matrix number.

    """
    el_non = elem_matrixs[0].shape[0]
    all_nums = el_non * len(elem_matrixs)
    datas = np.zeros(all_nums)
    cols = np.zeros(all_nums)
    rows = np.zeros(all_nums)
    for num in range(elem_matrixs.shape[0]):
        elm = elem_matrixs[num]
        mapping = mappings[num]
        row = np.repeat(mapping, non)
        col = np.zeros(el_non)
        for i in range(non):
            col[i * non:(i + 1) * non] = mapping
        datas[num * el_non:(num + 1) * el_non] = elm
        cols[num * el_non:(num + 1) * el_non] = col
        rows[num * el_non:(num + 1) * el_non] = row
    return datas, rows, cols


@njit(nogil=True)
def _assemble_rights(elem_rights: np.ndarray, mappings: np.ndarray, freedoms: int):
    """
    Assemble right-hand sides, accelerated with njit.
    :param elem_rights: All element right-hand sides of the model, index corresponds to matrix number.
    :param mappings: All element mappings of the model, index corresponds to matrix number.
    :param freedoms: Total degrees of freedom.
    """
    init_right = np.zeros(freedoms)
    el_non = elem_rights[0].size
    for num, elr in enumerate(elem_rights):
        mapping = mappings[num]
        for n in range(el_non):
            tol_n = mapping[n]
            init_right[tol_n] += elr[n]
    return init_right


class BaseMesh:
    """
    Base class for a mesh.
    """
    method = {}

    def __init__(self):
        self._mapping = None
        self._ps = None

    @property
    def mapping(self):
        """
        Mesh mapping.
        """
        return self._mapping

    @property
    def ps(self):
        """
        Mesh nodes.
        """
        return self._ps

    def build(self, name, nodeclass, elemclass):
        """
        Build the mesh.
        """
        pass


class MatrixProcess:
    """
    Manages a single matrix, with functionality to add, delete, and reset elements for multiple matrices.
    This class provides a way to handle matrix operations and associated right-hand side terms.
    It uses properties to manage access to the matrices and rights attributes.
    """

    def __init__(self, matrixs: dict = None, rights: np.ndarray = None):
        """

        Initialize a new MatrixProcss instance.
        :param matrixs: Left-hand side matrices. Default is None.
        :param rights: Right-hand side terms. Default is None.
        """
        self.p = None  # Placeholder attribute, currently not used
        self.matrixs = matrixs  # Initialize matrices property
        self.rights = rights  # Initialize rights property

    @property
    def matrixs(self) -> dict:
        """Getter method for the matrixs property. Returns the stored matrices dictionary."""
        return self._matrix  # Return the internal _matrix attribute

    @matrixs.setter
    def matrixs(self, val):
        """Setter method for the matrixs property. Updates the internal _matrix attribute."""
        self._matrix = val  # Assign the provided value to the internal _matrix attribute

    @property
    def rights(self):
        """Getter method for the rights property. Returns the stored rights array."""
        return self._right  # Return the internal _right attribute

    @rights.setter
    def rights(self, val):
        """
        Setter method for the rights property.
        This method is called when the rights property is assigned a new value.
        It updates the internal _right attribute with the provided value.

        Parameters:
            val: The new value to be assigned to the rights property.
        """
        self._right = val  # Assign the provided value to the internal _right attribute

    @staticmethod
    def _add_to(datas: np.ndarray, positions: np.ndarray, array: np.ndarray):
        """
        Add data to a matrix.
        """
        if len(positions.shape) == 2:
            array[positions[:, 0], positions[:, 1]] += datas
        else:
            array[positions] += datas

    @resize()
    def add_to_matrix(self, data, position, matrix_name):
        """
        Add data to a matrix at the specified positions. The elements in the position matrix must be unique.
        """
        self._add_to(data, position, self.matrixs[matrix_name])

    @resize(right=True)
    def add_to_right(self, data, position, right_name):
        """
        Add data to the right-hand side at the specified positions. The elements in the position matrix must be unique.
        """
        self._add_to(data, position, self.rights[right_name])

    @staticmethod
    def _set_to(datas: np.ndarray, positions: np.ndarray, array: np.ndarray):
        """
        Set elements in a matrix to the given data.
        """
        if len(positions.shape) == 2:
            array[positions[:, 0], positions[:, 1]] = datas
        else:
            array[positions] = datas

    @resize()
    def set_to_matrix(self, data, position, matrix_name: str):
        """
        Set matrix elements to the given data at the specified positions. The elements in the position matrix must be unique.
        """
        self._set_to(data, position, self.matrixs[matrix_name])

    @resize(right=True)
    def set_to_right(self, data, position, right_name: str):
        """
        Set right-hand side elements to the given data at the specified coordinates. The elements in the position matrix must be unique.
        """
        self._set_to(data, position, self.rights[right_name])

    def reset_all(self):
        """
        Reset all matrices and right-hand sides.
        """
        for name, matrix in self.matrixs.items():
            self.matrixs[name] = np.zeros_like(matrix)
        for name, right in self.rights.items():
            self.rights[name] = np.zeros_like(right)


class BaseBoundary:
    """
    Base class for boundary conditions.
    """

    def set(self, *args, **kwargs):
        pass


class BaseMainModel:
    def __init__(self, mesh: BaseMesh, boundary,
                 node_manager=None, elem_manager=None, matrix_process=None):
        """
        Initialize the model.
        :param mesh: BaseMesh or its subclass.
        :param boundary: BaseBoundary.
        :param node_manager: NodeManager.
        :param elem_manager: ElemManager.
        :param matrix_process: MatrixProcess.
        """
        self._results = []
        self.node_manager = node_manager
        if node_manager is None:
            self.node_manager = NodeManager()
        self.elem_manager = elem_manager
        if elem_manager is None:
            self.elem_manager = ElemManager()
        self.matrix_process = matrix_process
        if matrix_process is None:
            self.matrix_process = MatrixProcess()
        self.boundary = boundary
        self.args = {}
        self.mesh = mesh

    @property
    def matrixs(self) -> dict:
        return self.matrix_process.matrixs

    @matrixs.setter
    def matrixs(self, value: dict):
        self.matrix_process.matrixs = value

    @property
    def rights(self) -> np.ndarray:
        return self.matrix_process.rights

    @rights.setter
    def rights(self, value: np.ndarray):
        self.matrix_process.rights = value

    @property
    def nodes(self):
        return self.node_manager.nodes

    @property
    def elems(self):
        return self.elem_manager.elems

    @property
    def results(self) -> list:
        """
        Return all stored calculation results.
        """
        return self._results

    @property
    def latest_result(self):
        """
        The last stored calculation result.
        """
        return self._results[-1]

    def calc_error(self):
        """
        Calculate the iterative residual of the model.
        """
        if len(self.results) <= 1:
            return 1
        delta_result = np.array(self.results[-1]) - np.array(self.results[-2])
        error = (delta_result ** 2).sum() / len(delta_result)
        return error

    def calc_is_finished(self):
        pass

    def calc_matrixs_rights(self, calc=True, csc=True):
        """
        Update the matrices for matrix_process. If calc=True, re-calculate and assemble element matrices.
        If calc=False, re-import the last calculated matrices.
        """
        freedoms = self.node_manager.freedoms
        self.matrixs = self.elem_manager.assemble_matrixs(freedoms, calc, csc)
        self.rights = self.elem_manager.assemble_rights(freedoms, calc)
        return self.matrixs, self.rights

    def solve(self, *args, **kwargs):
        """
        Directly solve the system's stiffness matrix and right-hand side.
        """
        pass

    def set_boundary(self, *args, **kwargs):
        """
        Set boundary conditions.
        """
        self.boundary.set(self, *args, **kwargs)

    def update_to_nodes(self, *args, **kwargs):
        """
        Update calculation results to the nodes.
        """
        pass

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        Save calculation results.
        """
        pass


class BaseSimpleModels(BaseSimpleModel, ABC):
    """
    A collection of simple models, mainly used to generate a set of simple models with similar parameters.
    The input of the simple model set is used to calculate the output of the simple model set.
    """

    def __init__(self, models_args, model_class, builder, *args, **kwargs):
        """
        :param builder: Used to generate simple models.

        :param model_class: Specifies the class of the model to be generated.

        :param models_args: Parameters for setting up the simple models.
        """
        super().__init__(*args, **kwargs)
        self._builder = builder
        self._simple_models = []
        self._model_class = model_class
        self._models_args = models_args

    def calc_is_finished(self, *args, **kwargs):
        """
        Abstract method to be implemented by subclasses.
        """
        pass
class BaseOutput:
    """
    Abstract method to be implemented by subclasses.
    """

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        pass


class BasePostProcess:
    """
    Abstract method to be implemented by subclasses.
    """

    def __init__(self):
        self.postprocess_result = {}


class BaseResults(dict):

    def __init__(self, model, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model

    def get_results(self, name):
        """
        Abstract method to be implemented by subclasses.
        """
        return self[name]

    def add_results(self, name, value, t=None):
        """
        Abstract method to be implemented by subclasses.
        """
        if name not in self:
            self[name] = []
        if t is None:
            self[name].append(value)
        else:
            self[name].append((t, value))

    @property
    def val_names(self):
        """
        Abstract method to be implemented by subclasses.
        """
        return self.keys()


class TestResult(unittest.TestCase):
    def setUp(self):
        self.model = None
        self.results = BaseResults(self.model)

    def test_add_res(self):
        self.results.add_results('a', 1)
        self.results.add_results('b', 2, 0)
        print(self.results.get_results('a'))
        print(self.results.get_results('b'))
        print(self.results.val_names)
        self.results.clear()
        print(self.results)


if __name__ == '__main__':
    unittest.main()





