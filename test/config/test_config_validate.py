# -- coding: utf-8 --
import unittest

from ALB.config import ALBConfig, HydConfig


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


if __name__ == "__main__":
    unittest.main()
