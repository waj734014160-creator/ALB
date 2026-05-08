import unittest
from unittest.mock import patch

import numpy as np

from run import thermal_kc_compare as compare


def small_pad_config():
    return compare.FPBConfig(
        nx=12,
        nz=6,
        e=0.0,
        angle=0.0,
        lx=80,
        ps=3e6,
        freq=50,
        max_iter=40,
        error_set=1e-9,
        iter_method="skfem_newton",
        damp=0.6,
        coe=False,
    )


class TestThermalKcCompare(unittest.TestCase):
    def test_requested_orbit_matches_user_spec_and_is_valid(self):
        orbit_spec = compare.validate_requested_orbit(compare.create_pad_config().c)

        np.testing.assert_allclose(orbit_spec["center_um"], np.array([20.0, -40.0]))
        self.assertEqual(orbit_spec["radius_um"], 10.0)
        self.assertEqual(compare.VALVE_OPENING, 0.0)
        self.assertTrue(orbit_spec["requested_valid"])

    def test_case_bearing_uses_fixed_zero_opening_without_control(self):
        with patch.object(compare, "create_pad_config", small_pad_config):
            bearing, dt = compare.create_case_bearing("thermal_steady")

        self.assertEqual(len(bearing.bearings), 4)
        self.assertAlmostEqual(
            dt, 1.0 / (compare.ORBIT_FREQ_HZ * compare.PTS_PER_CYCLE)
        )

        for pad in bearing.bearings:
            inner_pad = getattr(pad, "bearing", pad)
            simple_models = list(getattr(inner_pad, "simple_models", []))
            self.assertGreater(len(simple_models), 0)
            for model in simple_models:
                if hasattr(model, "xv"):
                    self.assertEqual(model.xv, 0.0)

    def test_short_kc_identification_returns_finite_coefficients_for_three_cases(self):
        with (
            patch.object(compare, "PTS_PER_CYCLE", 6),
            patch.object(compare, "N_CYCLES", 2),
            patch.object(compare, "create_pad_config", small_pad_config),
        ):
            orbit_spec = compare.validate_requested_orbit(compare.create_pad_config().c)
            for case_key in compare.CASE_ORDER:
                result = compare.identify_case_coefficients(case_key, orbit_spec)
                self.assertTrue(np.isfinite(result["stiffness"]).all(), msg=case_key)
                self.assertTrue(np.isfinite(result["damping"]).all(), msg=case_key)
                self.assertEqual(result["stiffness"].shape, (2, 2))
                self.assertEqual(result["damping"].shape, (2, 2))


if __name__ == "__main__":
    unittest.main()
