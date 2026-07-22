# -- coding: utf-8 --
import unittest
from dataclasses import fields

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

    def test_alb_config_from_dict_valid(self):
        cfg = ALBConfig.from_dict({"alb": "ALB", "servo": "moog", "freq": 50})
        self.assertEqual(cfg.alb, "ALB")

    def test_alb_config_invalid_controller(self):
        with self.assertRaises(ValueError):
            ALBConfig.from_dict({}, controller="MPC")

    def test_no_controller_config_is_explicit_and_round_trippable(self):
        for config_class in (ALBConfig, NodimALBConfig):
            with self.subTest(config_class=config_class.__name__):
                explicit = config_class.from_dict({"controller": "none"})
                self.assertIsNone(explicit.controller_config)

                serialized = config_class(controller_config=None).to_dict()
                self.assertEqual(serialized["controller"], "none")
                restored = config_class.from_dict(serialized)
                self.assertIsNone(restored.controller_config)

                default = config_class.from_dict({})
                self.assertIsNotNone(default.controller_config)

    def test_controller_type_and_nondefault_values_round_trip_exactly(self):
        controller_cases = (
            (
                "PID",
                PIDConfig(
                    dt=0.002,
                    kp=0.45,
                    ki=0.15,
                    kd=0.08,
                    uf=0.3,
                    freq=37.0,
                    sensor_angles=np.asarray([25.0, 115.0]),
                ),
            ),
            (
                "FuzzyPID",
                FuzzyPIDConfig(
                    dt=0.003,
                    freq=41.0,
                    error_range=[-0.8, 0.9, 0.05],
                    delta_error_range=[-0.4, 0.7, 0.02],
                    kp_range=[0.1, 0.9, 0.04],
                    ki_range=[0.0, 0.2, 0.01],
                    kd_range=[0.05, 0.6, 0.025],
                    rule_path="rules/custom.csv",
                    sensor_angles=[30.0, 120.0],
                ),
            ),
        )
        for config_class in (ALBConfig, NodimALBConfig):
            for tag, source_controller in controller_cases:
                with self.subTest(config_class=config_class.__name__, tag=tag):
                    source = config_class(controller_config=source_controller)
                    serialized = source.to_dict()
                    self.assertEqual(serialized["controller"], tag)

                    restored = config_class.from_dict(serialized)
                    self.assertIsInstance(
                        restored.controller_config, type(source_controller)
                    )
                    for config_field in fields(source_controller):
                        expected = getattr(source_controller, config_field.name)
                        actual = getattr(restored.controller_config, config_field.name)
                        if isinstance(expected, np.ndarray):
                            np.testing.assert_array_equal(actual, expected)
                        else:
                            self.assertEqual(actual, expected)

    def test_controller_tag_and_nested_payload_type_must_agree(self):
        for config_class in (ALBConfig, NodimALBConfig):
            conflicts = (
                {
                    "controller": "PID",
                    "controller_config": FuzzyPIDConfig(),
                },
                {
                    "controller": "FuzzyPID",
                    "controller_config": PIDConfig(),
                },
                {
                    "controller": "none",
                    "controller_config": PIDConfig(),
                },
                {"controller": "PID", "controller_config": None},
            )
            for payload in conflicts:
                with self.subTest(
                    config_class=config_class.__name__,
                    controller=payload["controller"],
                ):
                    with self.assertRaisesRegex(ValueError, "conflicts|requires"):
                        config_class.from_dict(payload)

    def test_nested_controller_payload_rejects_unknown_fields(self):
        for config_class in (ALBConfig, NodimALBConfig):
            with self.subTest(config_class=config_class.__name__):
                with self.assertRaisesRegex(ValueError, "Unknown PID"):
                    config_class.from_dict(
                        {
                            "controller": "PID",
                            "controller_config": {
                                "kp": 0.5,
                                "fuzzy_only_field": 12.0,
                            },
                        }
                    )

    def test_legacy_flat_controller_payload_remains_permissive(self):
        for config_class in (ALBConfig, NodimALBConfig):
            with self.subTest(config_class=config_class.__name__):
                restored = config_class.from_dict(
                    {
                        "controller": "PID",
                        "kp": 0.75,
                        "legacy_unrelated_field": "ignored",
                    }
                )
                self.assertIsInstance(restored.controller_config, PIDConfig)
                self.assertEqual(restored.controller_config.kp, 0.75)

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
