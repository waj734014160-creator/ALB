import time
import unittest

import matplotlib.pyplot as plt
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve
from skfem import Basis, BilinearForm, ElementTriP1, LinearForm, MeshTri, asm, enforce
from skfem.helpers import grad

PSI2 = 1.0
LAMBDA = 1.0
EPSILON = 0.5
NUM_HOLES = 10
SUPPLY_PRESSURE = 5.0
ORIFICE_COEFF = 2.0


@BilinearForm
def reynolds_lhs(u, v, w):
    h3 = w.h**3
    return h3 * (w.psi2 * grad(u)[0] * grad(v)[0] + grad(u)[1] * grad(v)[1])


@LinearForm
def reynolds_rhs(v, w):
    dh_dx = grad(w.h)[0]
    return -w.Lambda * dh_dx * v


def solve_skfem_case(*, make_plot=False):
    start_time = time.time()

    x_grid = np.linspace(0.0, 2.0 * np.pi, 80)
    z_grid = np.linspace(-1.0, 1.0, 40)
    mesh = MeshTri.init_tensor(x_grid, z_grid)
    basis = Basis(mesh, ElementTriP1())

    h_nodal = 1.0 + EPSILON * np.cos(mesh.p[0])
    h_qp = basis.interpolate(h_nodal)
    stiffness = asm(reynolds_lhs, basis, h=h_qp, psi2=PSI2)
    rhs = asm(reynolds_rhs, basis, h=h_qp, Lambda=LAMBDA)
    stiffness_bc, rhs_bc = enforce(stiffness, rhs, D=mesh.boundary_nodes())

    x_holes = np.full(NUM_HOLES, np.pi)
    z_holes = np.linspace(-0.8, 0.8, NUM_HOLES)
    hole_nodes = []
    for x_hole, z_hole in zip(x_holes, z_holes):
        dist = (mesh.p[0] - x_hole) ** 2 + (mesh.p[1] - z_hole) ** 2
        hole_nodes.append(np.argmin(dist))
    hole_nodes = np.array(hole_nodes)

    num_nodes = stiffness_bc.shape[0]
    pressure = np.zeros(num_nodes)
    tol = 1e-6
    max_iter = 30
    eps_fb = 1e-12
    identity = sp.eye(num_nodes, format="csr")

    iterations = 0
    converged = False
    for i in range(max_iter):
        force = stiffness_bc @ pressure - rhs_bc
        flow = np.zeros(num_nodes)
        dflow_dp = np.zeros(num_nodes)

        for idx in hole_nodes:
            delta_p = SUPPLY_PRESSURE - pressure[idx]
            abs_delta_p = max(abs(delta_p), 1e-6)
            flow[idx] = ORIFICE_COEFF * np.sign(delta_p) * np.sqrt(abs_delta_p)
            dflow_dp[idx] = -0.5 * ORIFICE_COEFF / np.sqrt(abs_delta_p)

        force -= flow
        norm_val = np.sqrt(pressure**2 + force**2 + eps_fb)
        phi = pressure + force - norm_val
        error = float(np.linalg.norm(phi))
        iterations = i + 1
        if error < tol:
            converged = True
            break

        dp_mat = sp.diags(pressure / norm_val, format="csr")
        df_mat = sp.diags(force / norm_val, format="csr")
        jac_base = stiffness_bc - sp.diags(dflow_dp, format="csr")
        jacobian = (identity - dp_mat) + (identity - df_mat) @ jac_base
        delta = spsolve(jacobian, -phi)
        pressure = pressure + delta

    elapsed = time.time() - start_time

    if make_plot:
        fig = plt.figure(figsize=(12, 7))
        ax = fig.add_subplot(111, projection="3d")
        surface = ax.plot_trisurf(
            mesh.p[0], mesh.p[1], pressure, cmap="jet", edgecolor="none"
        )
        p_holes = pressure[hole_nodes]
        ax.scatter(
            x_holes,
            z_holes,
            p_holes,
            color="red",
            s=50,
            label="Orifices",
            zorder=5,
        )
        ax.set_xlabel("X (Circumferential)")
        ax.set_ylabel("Z (Axial)")
        ax.set_zlabel("Pressure")
        ax.set_title("Hybrid Bearing Pressure (Hydrodynamic + Hydrostatic Orifices)")
        ax.legend()
        fig.colorbar(surface, shrink=0.5, aspect=10)
        plt.close(fig)

    return {
        "converged": converged,
        "iterations": iterations,
        "elapsed": elapsed,
        "pressure": pressure,
        "hole_nodes": hole_nodes,
    }


class TestSkfem(unittest.TestCase):
    def test_skfem_solver_returns_finite_pressure(self):
        result = solve_skfem_case(make_plot=False)

        self.assertTrue(result["converged"])
        self.assertLessEqual(result["iterations"], 30)
        self.assertTrue(np.all(np.isfinite(result["pressure"])))
        self.assertTrue(np.all(result["pressure"] >= -1e-8))
        hole_pressures = result["pressure"][result["hole_nodes"]]
        self.assertGreater(float(np.max(hole_pressures)), 0.0)


if __name__ == "__main__":
    unittest.main()
