# -- coding: utf-8 --
import unittest

import numpy as np

from ALB.config import (
    ALBConfig,
    FuzzyPIDConfig,
    HydConfig,
    NodimALBConfig,
    PIDConfig,
    ThermalConfig,
)


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
    def test_array_defaults_are_independent_factories(self):
        for config_type in (ALBConfig, NodimALBConfig):
            with self.subTest(config_type=config_type.__name__):
                first = config_type()
                second = config_type()
                first.gxy[0, 0] = 9.0
                first.gxyt[0, 0] = 8.0
                np.testing.assert_array_equal(second.gxy, np.eye(2))
                np.testing.assert_array_equal(second.gxyt, np.zeros((2, 2)))

    def test_uncontrolled_and_external_spool_require_no_controller(self):
        for config_class in (ALBConfig, NodimALBConfig):
            for mode in ("uncontrolled", "external_spool"):
                with self.subTest(
                    config_class=config_class.__name__,
                    mode=mode,
                ):
                    config = config_class(
                        control_mode=mode,
                        controller_config=None,
                    )
                    self.assertIsNone(config.controller_config)

    def test_controlled_modes_require_typed_controller(self):
        for config_class in (ALBConfig, NodimALBConfig):
            with self.subTest(config_class=config_class.__name__):
                pid = config_class(
                    control_mode="pid",
                    controller_config=PIDConfig(kp=0.75),
                )
                fuzzy = config_class(
                    control_mode="fuzzy_pid",
                    controller_config=FuzzyPIDConfig(rule_path=None),
                )
                self.assertEqual(pid.controller_config.kp, 0.75)
                self.assertIsInstance(
                    fuzzy.controller_config,
                    FuzzyPIDConfig,
                )
                with self.assertRaisesRegex(ValueError, "requires"):
                    config_class(
                        control_mode="pid",
                        controller_config=None,
                    )

    def test_removed_assembly_fields_are_not_constructor_parameters(self):
        with self.assertRaises(ValueError):
            ALBConfig(control_mode="removed")
        with self.assertRaises(TypeError):
            ALBConfig(alb="ALB")
        with self.assertRaises(TypeError):
            ALBConfig(servo="static")
        with self.assertRaises(TypeError):
            ALBConfig(switch=False)

    def test_invalid_valve_model_is_rejected(self):
        with self.assertRaises(ValueError):
            ALBConfig(valve_model="bad")


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

    def test_removed_thermal_fields_are_rejected(self):
        with self.assertRaises(TypeError):
            ThermalConfig(flow_rate_factor=1.0)
        with self.assertRaises(TypeError):
            ThermalConfig(pressure_backend="skfem")

    def test_physical_thermal_reference_values_are_positive(self):
        with self.assertRaisesRegex(ValueError, "k_lub"):
            ThermalConfig(k_lub=-0.1)
        with self.assertRaisesRegex(ValueError, "cp_lub"):
            ThermalConfig(cp_lub=0.0)
        with self.assertRaisesRegex(ValueError, "miu0"):
            ThermalConfig(miu0=0.0)


if __name__ == "__main__":
    unittest.main()
