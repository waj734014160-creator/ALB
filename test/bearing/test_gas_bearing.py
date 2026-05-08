import unittest
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ALB.config import GasConfig
from ALB.gas import GasBearing


class TestGasBearing(unittest.TestCase):
    @staticmethod
    def _save_pressure_cloud(bearing: GasBearing, save_path: Path):
        args = bearing.main_model.args
        nx, nz = args["size"]
        p = np.asarray(bearing.main_model.latest_result, dtype=float).reshape(
            nx + 1, nz + 1
        )
        theta = np.linspace(args["x_lim"][0], args["x_lim"][1], nx + 1)
        z = np.linspace(args["z_lim"][0], args["z_lim"][1], nz + 1)
        theta_grid, z_grid = np.meshgrid(theta, z, indexing="ij")

        fig, ax = plt.subplots(figsize=(7, 4.5))
        contour = ax.contourf(theta_grid, z_grid, p, levels=30, cmap="jet")
        fig.colorbar(contour, ax=ax, label="p (nondimensional)")
        ax.set_xlabel("theta [rad]")
        ax.set_ylabel("z (nondimensional)")
        ax.set_title("Gas Bearing Pressure Cloud")
        print(f"Saving gas bearing pressure cloud to {save_path}")
        fig.savefig(save_path, dpi=180, bbox_inches="tight")
        plt.close(fig)

    def test_gas_bearing_solver_produces_physical_pressure(self):
        cfg = GasConfig(
            e=0.25,
            angle=30.0,
            nx=20,
            nz=12,
            max_iter=20,
            error_set=1e-8,
            damp=0.7,
            coe=True,
            reynold=True,
        )
        bearing = GasBearing(cfg)
        bearing.solve()

        p = np.asarray(bearing.main_model.latest_result, dtype=float)
        self.assertTrue(np.all(np.isfinite(p)))
        self.assertGreaterEqual(float(np.min(p)), 0.0)
        self.assertGreater(float(np.max(p) - np.min(p)), 1e-6)

        force = bearing.calc_capacity(nodim=True)
        self.assertEqual(force.shape, (2,))
        self.assertTrue(np.all(np.isfinite(force)))

        # 获取本脚本地址
        root_dir = Path(__file__).parent
        artifact_dir = root_dir / "_gas_bearing"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        save_path = artifact_dir / "latest_gas_pressure_cloud.png"
        self._save_pressure_cloud(bearing, save_path)
        self.assertTrue(save_path.exists())
        self.assertGreater(save_path.stat().st_size, 0)

    def test_gas_pressure_floor_is_zero_not_boundary_pressure(self):
        cfg = GasConfig(p_set=1.0)
        bearing = GasBearing(cfg)

        clipped = bearing.main_model._apply_pressure_floor(
            np.array([-0.2, 0.2, 1.1]),
            bearing.main_model.args["pressure_floor"],
        )

        np.testing.assert_allclose(clipped, np.array([0.0, 0.2, 1.1]))

    def test_placeholder_interfaces_are_explicit(self):
        with self.assertRaises(NotImplementedError):
            GasBearing(GasConfig(thermal_enabled=True))

    def test_textured_foil_bearing_matches_paper_trend(self):
        smooth_cfg = GasConfig.paper_2023_foil_bearing(
            textured=False,
            nx=40,
            nz=12,
            max_iter=20,
            foil_relaxation=0.6,
            foil_tol=1e-5,
        )
        textured_cfg = GasConfig.paper_2023_foil_bearing(
            textured=True,
            texture_type=1,
            texture_circ_fraction=0.33,
            texture_axial_fraction=1.0,
            nx=40,
            nz=12,
            max_iter=20,
            foil_relaxation=0.6,
            foil_tol=1e-5,
        )

        smooth_bearing = GasBearing(smooth_cfg)
        textured_bearing = GasBearing(textured_cfg)
        smooth_bearing.solve()
        textured_bearing.solve()

        smooth_force = smooth_bearing.calc_capacity(nodim=True)
        textured_force = textured_bearing.calc_capacity(nodim=True)
        smooth_load = float(np.linalg.norm(smooth_force))
        textured_load = float(np.linalg.norm(textured_force))
        relative_gain = (textured_load - smooth_load) / smooth_load * 100.0

        self.assertGreater(smooth_load, 0.0)
        self.assertGreater(textured_load, 0.0)
        self.assertGreater(relative_gain, 0.0)
        self.assertGreaterEqual(relative_gain, 2.0)

        root_dir = Path(__file__).parent
        artifact_dir = root_dir / "_gas_bearing"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        save_path = artifact_dir / "paper_textured_foil_pressure_cloud.png"
        self._save_pressure_cloud(textured_bearing, save_path)
        self.assertTrue(save_path.exists())
        self.assertGreater(save_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
