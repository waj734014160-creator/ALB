import unittest

import numpy as np

from ALB.bearing import HydrostaticBearing
from ALB.config import HydConfig


class TestCoeBoundaryFullPad(unittest.TestCase):
    def test_single_pad_full_coverage_coe_boundary_connected(self):
        """Single pad with 360-degree coverage should satisfy periodic continuity."""
        cfg = HydConfig(
            nx=60,
            nz=40,
            e=0.3,
            angle=-45.0,
            freq=50,
            lx=360,
            ps=3e6,
            reynold=True,
            coe=True,
            max_iter=400,
            error_set=1e-8,
            iter_method="newton",
            damp=0.6,
        )
        bearing = HydrostaticBearing(cfg)
        bearing.init()

        # Apply a right-down eccentric displacement and solve pressure.
        uxy = np.array([0.2 * cfg.c, -0.2 * cfg.c])
        uxyt = np.array([0.0, 0.0])
        bearing.input(uxy=uxy, uxyt=uxyt)
        bearing.output(calc=True, nodim=True)

        model = bearing.main_model
        x_lim = model.args["x_lim"]

        right_ids = model.node_manager.search(0, x_lim[0], number=True)
        left_ids = model.node_manager.search(0, x_lim[1], number=True)

        self.assertGreater(len(right_ids), 0)
        self.assertEqual(len(right_ids), len(left_ids))

        right_data = sorted(
            [(model.nodes[i].coords[1], model.nodes[i].p) for i in right_ids],
            key=lambda item: item[0],
        )
        left_data = sorted(
            [(model.nodes[i].coords[1], model.nodes[i].p) for i in left_ids],
            key=lambda item: item[0],
        )

        p_right = np.array([p for _, p in right_data], dtype=float)
        p_left = np.array([p for _, p in left_data], dtype=float)
        z_right = np.array([z for z, _ in right_data], dtype=float)
        z_left = np.array([z for z, _ in left_data], dtype=float)

        # Same axial coordinates should be paired at the periodic seam.
        self.assertTrue(np.allclose(z_right, z_left, atol=1e-12))

        seam_diff = np.abs(p_right - p_left)
        max_seam_diff = float(np.max(seam_diff))
        mean_seam_diff = float(np.mean(seam_diff))

        self.assertTrue(np.isfinite(max_seam_diff))
        self.assertTrue(np.isfinite(mean_seam_diff))
        self.assertLess(
            bearing.final_iter,
            cfg.max_iter,
            msg=f"Pressure solver did not converge: final_iter={bearing.final_iter}",
        )

        # Continuity criterion: seam pressure mismatch should remain tiny.
        self.assertLess(
            max_seam_diff,
            1e-6,
            msg=f"Periodic seam mismatch too large: max_abs_diff={max_seam_diff:.3e}",
        )

        p_all = np.array([node.p for node in model.nodes.values()], dtype=float)
        self.assertTrue(np.all(np.isfinite(p_all)))
        self.assertGreater(float(np.max(p_all)), 0.0)


if __name__ == "__main__":
    unittest.main()
