import unittest
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ALB.config import GasConfig
from ALB.contracts import BearingInput
from ALB.physics.gas import GasFilmRuntime


class TestGasBearing(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _set_artifact_dir(self, tmp_path):
        self.artifact_dir = tmp_path

    @staticmethod
    def _save_pressure_cloud(runtime, config, save_path: Path):
        nx, nz = config.nx, config.nz
        p = np.asarray(
            runtime.result_snapshot().values["pressure"],
            dtype=float,
        ).reshape(
            nx + 1, nz + 1
        )
        theta = np.linspace(
            np.deg2rad(config.x0),
            np.deg2rad(config.x0 + config.lx),
            nx + 1,
        )
        z = np.linspace(0.0, config.lz, nz + 1)
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

    @staticmethod
    def _input(config: GasConfig) -> BearingInput:
        angle = np.deg2rad(config.angle)
        displacement = (
            config.e * config.c * np.sin(angle),
            -config.e * config.c * np.cos(angle),
        )
        return BearingInput(
            displacement,
            (config.dxt or 0.0, config.dyt or 0.0),
            0.0,
            "dimensional",
        )

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
        runtime = GasFilmRuntime(cfg)
        output = runtime.step(self._input(cfg))

        p = np.asarray(runtime.result_snapshot().values["pressure"], dtype=float)
        self.assertTrue(np.all(np.isfinite(p)))
        self.assertGreaterEqual(float(np.min(p)), 0.0)
        self.assertGreater(float(np.max(p) - np.min(p)), 1e-6)

        force = output.force
        self.assertEqual(force.shape, (2,))
        self.assertTrue(np.all(np.isfinite(force)))

        save_path = self.artifact_dir / "latest_gas_pressure_cloud.png"
        self._save_pressure_cloud(runtime, cfg, save_path)
        self.assertTrue(save_path.exists())
        self.assertGreater(save_path.stat().st_size, 0)

    def test_gas_pressure_floor_is_zero_not_boundary_pressure(self):
        cfg = GasConfig(p_set=1.0)
        runtime = GasFilmRuntime(cfg)

        clipped = runtime._solver.main_model._apply_pressure_floor(
            np.array([-0.2, 0.2, 1.1]),
            runtime._solver.main_model.args["pressure_floor"],
        )

        np.testing.assert_allclose(clipped, np.array([0.0, 0.2, 1.1]))

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

        smooth_bearing = GasFilmRuntime(smooth_cfg)
        textured_bearing = GasFilmRuntime(textured_cfg)
        smooth_output = smooth_bearing.step(self._input(smooth_cfg))
        textured_output = textured_bearing.step(self._input(textured_cfg))

        smooth_force = smooth_output.force
        textured_force = textured_output.force
        smooth_load = float(np.linalg.norm(smooth_force))
        textured_load = float(np.linalg.norm(textured_force))
        relative_gain = (textured_load - smooth_load) / smooth_load * 100.0

        self.assertGreater(smooth_load, 0.0)
        self.assertGreater(textured_load, 0.0)
        self.assertGreater(relative_gain, 0.0)
        self.assertGreaterEqual(relative_gain, 2.0)

        save_path = self.artifact_dir / "paper_textured_foil_pressure_cloud.png"
        self._save_pressure_cloud(textured_bearing, textured_cfg, save_path)
        self.assertTrue(save_path.exists())
        self.assertGreater(save_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
