import numpy as np
import scipy.sparse as sp


# Set continuous/periodic boundary conditions
# nodes1 and nodes2 need to be passed in with corresponding node numbers, and they need to correspond one-to-one
# Returns the Lagrangian multiplier matrix and its non-homogeneous term
def set_continuity_boundary(nodes1, nodes2, all_freedoms, node_freedom=1):
    """
    Set continuity boundary conditions.
    :param nodes1: Node numbers of the mesh to set boundary conditions for, input as an iterable array.
    :param nodes2: Node numbers of the mesh to set boundary conditions for, input as an iterable array.
    :param all_freedoms: Total degrees of freedom of the system of equations.
    :param node_freedom: Nodal degrees of freedom, default is 1.
    :return: kp3, fp3
    """
    if len(nodes1) == len(nodes2):
        q_nodes = all_freedoms  # Number of columns in the supplementary matrix
        len_nodes = len(nodes1)  # Number of nodes
        r_nodes = (
            len(nodes1) * node_freedom
        )  # Number of rows in the supplementary matrix
        kp3 = np.zeros((r_nodes, q_nodes), dtype=np.float32)
        fp3 = np.zeros(r_nodes)
        for i in range(len_nodes):
            for j in range(node_freedom):
                pt = i * node_freedom + j
                kp3[pt, nodes1[pt]] = (
                    1  # In the appended matrix, set the left boundary to 1
                )
                kp3[
                    pt, nodes2[pt]
                ] = -1  # In the appended matrix, set the right boundary to -1
        return kp3, fp3
    else:
        print(
            "Error! The number of nodes on both sides of the continuous boundary must be the same."
        )
        return False


# Set fixed pressure boundary conditions
# nodes are passed in as node numbers
# Returns the Lagrangian multiplier matrix and its non-homogeneous term
def set_value_boundary(freedoms, nodes, p_set=0.5, **kwargs):
    """
    Set fixed value boundary conditions.
    :param freedoms: Total degrees of freedom of the system of equations.
    :param nodes: Node numbers of the mesh to set boundary conditions for, input as an iterable array.
    :param p_set: The value to set, input as int or float.
    :param kwargs: Optional arguments can be 'dims' and 'el_fd'. 'dims' is an iterable array for setting the nodal degrees of freedom, e.g., dims=[0,1] sets the x and y of the node to the set value. Default is [0]. 'el_fd' is the nodal degrees of freedom, default is 1.
    :return: Returns the supplementary multiplier matrix.
    """
    for key in kwargs.keys():
        assert key in ["dims", "node_freedom"], "unknown keys"
    if "dims" in kwargs.keys():
        dims = kwargs["dims"]
    else:
        dims = [0]
    if "el_fd" in kwargs.keys():
        el_fd = kwargs["el_fd"]
    else:
        el_fd = 1
    q_nodes = freedoms  # Number of columns in the supplementary matrix
    len_nodes = len(nodes)  # Number of nodes
    l_nodes = len(nodes) * len(dims)  # Number of rows in the supplementary matrix
    kp1 = np.zeros((l_nodes, q_nodes), dtype=np.float32)
    fp1 = np.zeros(l_nodes)
    for i in range(len_nodes):
        nd_id = nodes[i]
        for j, dim in enumerate(dims):
            l_pt = i * len(dims) + j
            r_pt = nd_id * el_fd + dim
            kp1[l_pt, r_pt] = 1  # In the appended matrix, set the left boundary to 1
            fp1[l_pt] = p_set
    return kp1, fp1


def check_boundary(f_bd, s_bd):
    """
    Check for duplicate boundary nodes and remove nodes in s_bd that intersect with f_bd.
    :param f_bd: Boundary nodes that are not to be modified, must be a list object.
    :param s_bd: Boundary nodes to be modified, must be a list object. The overlapping part with f_bd will be removed.
    :return:
    """
    if isinstance(f_bd, list) and isinstance(s_bd, list):
        for i, nd_id in enumerate(s_bd):
            if nd_id in f_bd:
                s_bd.pop(i)
        return True
    else:
        assert "check_boundary inputs must be iterable"
        return False


def couple_boundary_matrix(matrix: np.ndarray, right: np.ndarray, kps: list, fps: list):
    """
    Couples the boundary condition matrices with the main system matrix and right-hand side vector.
    :param matrix: The main stiffness matrix.
    :param right: The main right-hand side vector.
    :param kps: A list of boundary condition stiffness matrices.
    :param fps: A list of boundary condition right-hand side vectors.
    :return: The coupled matrix and right-hand side vector.
    """
    if matrix.shape[1] != right.size:
        raise Exception("matrix.shape(1) must be same as right.size")
    if len(kps) == 1:
        kp = kps[0]
        fp = fps[0]
    else:
        kp = sp.vstack(kps)  # Combine boundary condition stiffness matrices
        fp = np.hstack(fps)  # Combine non-homogeneous terms of the appended matrix
    if kp.shape[0] != fp.size or kp.shape[1] != matrix.shape[1]:
        raise Exception("ke.shape(1) must be same as fp.size")
    matrix = sp.vstack(
        (matrix, kp)
    )  # Append Lagrangian multiplier stiffness matrix - bottom
    zeros_mat = sp.coo_matrix(
        (len(fp), len(fp))
    )  # Supplementary zero matrix for stiffness
    kp_t = sp.vstack((kp.T, zeros_mat))
    matrix = sp.hstack(
        (matrix, kp_t)
    )  # Append Lagrangian multiplier stiffness matrix - right
    right = np.hstack(
        (right, fp)
    )  # Append non-homogeneous terms of the appended matrix
    return matrix, right
