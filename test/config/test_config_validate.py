# -- coding: utf-8 --
import unittest

from ALB.config import ALBConfig, HydConfig, ThermalConfig


class TestHydConfigValidation(unittest.TestCase):
    def test_hyd_config_valid(self):
        cfg = HydConfig(e=0.5, ps=1e6, c=80e-6, freq=50, nx=59, nz=39)
        self.assertAlmostEqual(cfg.e, 0.5)

    def test_hyd_config_invalid_e(self):
        with self.assertRaises(ValueError):
            HydConfig(e=1.2)

    def test_hyd_config_invalid_iter_method(self):
        with self.assertRaises(ValueError):
            HydConfig(iter_method="bad_method")

    def test_hyd_config_invalid_reynold(self):
        with self.assertRaises(ValueError):
            HydConfig(reynold="invalid_mode")


class TestALBConfigValidation(unittest.TestCase):
    def test_alb_config_from_dict_valid(self):
        cfg = ALBConfig.from_dict({"alb": "ALB", "servo": "moog", "freq": 50})
        self.assertEqual(cfg.alb, "ALB")

    def test_alb_config_invalid_controller(self):
        with self.assertRaises(ValueError):
            ALBConfig.from_dict({}, controller="MPC")

    def test_alb_config_invalid_alb(self):
        with self.assertRaises(ValueError):
            ALBConfig.from_dict({"alb": "BAD"})

    def test_alb_config_invalid_servo(self):
        with self.assertRaises(ValueError):
            ALBConfig.from_dict({"servo": "BAD"})


class TestThermalConfigValidation(unittest.TestCase):
    def test_coupling_is_normalized_and_strict(self):
        self.assertEqual(ThermalConfig(coupling="FULL").coupling, "full")
        with self.assertRaisesRegex(ValueError, "coupling"):
            ThermalConfig(coupling="typo")

    def test_transient_requires_direct_iteration(self):
        for method in ("newton", "direct_then_newton"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, "require iter_method='direct'"):
                    ThermalConfig(transient_enabled=True, iter_method=method)

    def test_deprecated_flow_rate_factor_is_a_strict_no_op(self):
        self.assertEqual(ThermalConfig().flow_rate_factor, 1.0)
        with self.assertRaisesRegex(ValueError, "deprecated"):
            ThermalConfig(flow_rate_factor=1.01)

    def test_physical_thermal_reference_values_are_positive(self):
        with self.assertRaisesRegex(ValueError, "k_lub"):
            ThermalConfig(k_lub=-0.1)
        with self.assertRaisesRegex(ValueError, "cp_lub"):
            ThermalConfig(cp_lub=0.0)
        with self.assertRaisesRegex(ValueError, "miu0"):
            ThermalConfig(miu0=0.0)


if __name__ == "__main__":
    unittest.main()
