# -- coding: utf-8 --
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ALB.alb import ALB, alb2, alb2_fuzzy
from ALB.bearing import MultiPad, four_pads_bearing
from ALB.config import ALBConfig, FPBConfig
from ALB.servovalve import moog_servovalve
from ALB.thermal import (
    ThermalHydroBearing,
    build_thermal_config,
    wrap_pad_collection_with_thermal,
)
from ALB.tool import read_json5_with_share


PAPER_CONFIG_REQUIRED_FILES = (
    "alb12.json5",
    "albfuzzy12.json5",
    "hb34.json5",
    "rotor.json5",
    "share.json5",
)


def _load_split_imports():
    for parent in Path(__file__).resolve().parents:
        helper_path = parent / "_split_imports.py"
        if helper_path.exists():
            spec = importlib.util.spec_from_file_location(
                "_split_imports_for_config_task",
                helper_path,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise ImportError("Could not locate test/_split_imports.py")


split_imports = _load_split_imports()


class TestPaperTaskConfigBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo_root = Path(__file__).resolve().parents[2]
        cls.config_dir = split_imports.select_paper_config_dir(
            repo_root,
            PAPER_CONFIG_REQUIRED_FILES,
        )

    def _read_config(self, name):
        return read_json5_with_share(str(self.config_dir / name))

    def _assert_allclose(self, actual, expected):
        np.testing.assert_allclose(
            np.asarray(actual, dtype=float),
            np.asarray(expected, dtype=float),
            rtol=1e-9,
            atol=1e-12,
        )

    def _assert_pad_matches_config(self, data, pad, x0):
        for key in ["freq", "miu", "c", "r", "l", "ps", "rho", "lx", "lz"]:
            self.assertAlmostEqual(pad.input_args[key], data[key])
        for key in ["nx", "nz", "bias", "node_link"]:
            self.assertEqual(pad.input_args[key], data[key])
        self.assertAlmostEqual(pad.input_args["e"], data["e"])
        self.assertAlmostEqual(pad.input_args["angle"], data["angle"])
        self.assertAlmostEqual(pad.input_args["x0"], x0)
        self.assertAlmostEqual(pad.thickness._thickness_args["e"], data["e"])
        self.assertAlmostEqual(
            pad.thickness._thickness_args["angle"], np.deg2rad(data["angle"])
        )

    def test_empty_local_config_dir_does_not_shadow_param_scan(self):
        with tempfile.TemporaryDirectory() as workspace:
            workspace_root = Path(workspace)
            repo_root = workspace_root / "ALB_MAIN"
            local_config_dir = repo_root / "task" / "PAPER" / "config"
            sibling_config_dir = (
                workspace_root / "PARAM_SCAN" / "task" / "PAPER" / "config"
            )
            local_config_dir.mkdir(parents=True)
            sibling_config_dir.mkdir(parents=True)
            for file_name in PAPER_CONFIG_REQUIRED_FILES:
                (sibling_config_dir / file_name).write_text("{}", encoding="utf-8")

            selected = split_imports.select_paper_config_dir(
                repo_root,
                PAPER_CONFIG_REQUIRED_FILES,
            )

        self.assertEqual(selected, sibling_config_dir)

    def test_paper_alb12_builds_pid_alb_instance(self):
        data = self._read_config("alb12.json5")

        self.assertIn("thermal_enabled", data)
        self.assertIn("thermal", data)
        self.assertIn("delay", data)
        self.assertIn("tw", data)
        self.assertIn("zeta", data)
        self.assertIn("tp3", data)

        config = ALBConfig.from_dict(data)
        alb = alb2(config)

        self.assertIsInstance(alb, ALB)
        self.assertEqual(alb.node_link, 12)
        self.assertEqual(config.servo, "moog")
        self.assertEqual(config.thermal_enabled, data["thermal_enabled"])
        self.assertEqual(config.thermal_config.t_in, data["thermal"]["t_in"])
        self.assertAlmostEqual(config.servo_config.delay, data["delay"])
        self.assertAlmostEqual(config.servo_config.tw, data["tw"])
        self.assertAlmostEqual(config.servo_config.zeta, data["zeta"])
        self.assertAlmostEqual(config.servo_config.tp3, data["tp3"])
        self.assertAlmostEqual(config.pad_config.bias, data["bias"])
        self.assertAlmostEqual(config.pad_config.c, data["c"])
        self.assertAlmostEqual(config.tank_config.h_tank, data["h_tank"])
        self._assert_allclose(config.gxy, data["gxy"])
        self._assert_allclose(config.gxyt, data["gxyt"])
        self.assertEqual(len(alb.pads), 4)
        self.assertEqual(len(alb.servovalves), 2)
        self._assert_allclose(alb.gxy, data["gxy"])
        self._assert_allclose(alb.gxyt, data["gxyt"])
        self.assertAlmostEqual(alb.servovalves[0].main_model._dt, data["dt"])
        self._assert_allclose(alb.controller.kp, data["kp"])
        self._assert_allclose(alb.controller.ki, data["ki"])
        self._assert_allclose(alb.controller.kd, data["kd"])
        self._assert_allclose(
            alb.controller.config.sensor_angles, data["sensor_angles"]
        )

        expected_x0s = list(config.pad_config.x0s)
        actual_x0s = [pad.input_args["x0"] for pad in alb.pads]
        self._assert_allclose(actual_x0s, expected_x0s)
        for pad, x0 in zip(alb.pads, expected_x0s):
            self._assert_pad_matches_config(data, pad, x0)
            self._assert_allclose(
                pad.thickness._thickness_args["xrange"], data["xrange"]
            )
            self._assert_allclose(
                pad.thickness._thickness_args["zrange"], data["zrange"]
            )
            self.assertAlmostEqual(
                pad.thickness._thickness_args["h_tank"], data["h_tank"]
            )

    def test_paper_albfuzzy12_builds_fuzzy_alb_instance(self):
        data = self._read_config("albfuzzy12.json5")

        self.assertIn("thermal_enabled", data)
        self.assertIn("thermal", data)
        self.assertIn("error_range", data)
        self.assertIn("rule_path", data)

        config = ALBConfig.from_dict(data, controller="FuzzyPID")
        alb = alb2_fuzzy(config)

        self.assertIsInstance(alb, ALB)
        self.assertEqual(alb.node_link, 12)
        self.assertEqual(config.servo, "moog")
        self.assertEqual(len(alb.pads), 4)
        self.assertEqual(len(alb.servovalves), 2)
        self.assertAlmostEqual(alb.servovalves[0].main_model._dt, data["dt"])
        self.assertEqual(
            list(config.controller_config.error_range), data["error_range"]
        )
        self.assertEqual(
            list(config.controller_config.delta_error_range), data["delta_error_range"]
        )
        self.assertEqual(list(config.controller_config.kp_range), data["kp_range"])
        self.assertEqual(list(config.controller_config.ki_range), data["ki_range"])
        self.assertEqual(list(config.controller_config.kd_range), data["kd_range"])
        self.assertEqual(config.controller_config.rule_path, data["rule_path"])
        self._assert_allclose(alb.gxy, data["gxy"])
        self._assert_allclose(alb.gxyt, data["gxyt"])
        self._assert_allclose(
            alb.controller.config.sensor_angles, data["sensor_angles"]
        )
        self.assertEqual(list(alb.controller.config.error_range), data["error_range"])
        self.assertEqual(
            list(alb.controller.config.delta_error_range), data["delta_error_range"]
        )
        self.assertEqual(alb.controller.config.rule_path, data["rule_path"])

        expected_x0s = list(config.pad_config.x0s)
        actual_x0s = [pad.input_args["x0"] for pad in alb.pads]
        self._assert_allclose(actual_x0s, expected_x0s)
        for pad, x0 in zip(alb.pads, expected_x0s):
            self._assert_pad_matches_config(data, pad, x0)
            self._assert_allclose(
                pad.thickness._thickness_args["xrange"], data["xrange"]
            )
            self._assert_allclose(
                pad.thickness._thickness_args["zrange"], data["zrange"]
            )
            self.assertAlmostEqual(
                pad.thickness._thickness_args["h_tank"], data["h_tank"]
            )

    def test_paper_hb34_builds_four_pad_bearing_instance(self):
        data = self._read_config("hb34.json5")

        self.assertIn("thermal_enabled", data)
        self.assertIn("thermal", data)
        self.assertEqual(data["angle"], 0)

        config = FPBConfig.from_dict(data)
        bearing = four_pads_bearing(config)

        self.assertIsInstance(bearing, MultiPad)
        self.assertEqual(bearing.node_link, 34)
        self.assertEqual(len(bearing.bearings), 4)
        self.assertAlmostEqual(config.bias, data["bias"])
        self.assertAlmostEqual(config.c, data["c"])
        self.assertAlmostEqual(config.ps, data["ps"])
        self.assertEqual(config.thermal_enabled, data["thermal_enabled"])
        self.assertEqual(config.thermal_config.t_in, data["thermal"]["t_in"])

        expected_x0s = list(config.x0s)
        actual_x0s = [pad.input_args["x0"] for pad in bearing.bearings]
        self._assert_allclose(actual_x0s, expected_x0s)
        for pad, x0 in zip(bearing.bearings, expected_x0s):
            self._assert_pad_matches_config(data, pad, x0)

    def test_alb_builder_wraps_pads_with_transient_thermal_when_enabled(self):
        data = self._read_config("alb12.json5")
        data["thermal_enabled"] = True
        data["thermal"] = dict(data["thermal"])
        data["thermal"]["transient_enabled"] = True

        config = ALBConfig.from_dict(data)
        alb = alb2(config)

        self.assertTrue(all(isinstance(pad, ThermalHydroBearing) for pad in alb.pads))
        self.assertTrue(all(pad.config.transient_enabled for pad in alb.pads))
        self.assertAlmostEqual(alb.pads[0].config.dt, data["dt"])
        self.assertAlmostEqual(alb.pads[0].config.t_in, data["thermal"]["t_in"])

    def test_hb_thermal_helper_wraps_four_pad_bearing(self):
        data = self._read_config("hb34.json5")
        data["thermal_enabled"] = True
        data["thermal"] = dict(data["thermal"])
        data["thermal"]["transient_enabled"] = None

        config = FPBConfig.from_dict(data)
        bearing = four_pads_bearing(config)
        thermal_config = config.thermal_config
        thermal_args = vars(thermal_config).copy()
        thermal_args["dt"] = 1e-4
        if not thermal_args.get("transient_enabled"):
            thermal_args["transient_enabled"] = True
        from ALB.config import ThermalConfig as _TC

        thermal_config = _TC.from_dict(thermal_args)
        wrapped = MultiPad(
            *wrap_pad_collection_with_thermal(list(bearing.bearings), thermal_config)
        )

        self.assertTrue(
            all(isinstance(pad, ThermalHydroBearing) for pad in wrapped.bearings)
        )
        self.assertTrue(all(pad.config.transient_enabled for pad in wrapped.bearings))
        self.assertAlmostEqual(wrapped.bearings[0].config.dt, 1e-4)

    def test_paper_rotor_config_loads_shared_values(self):
        data = self._read_config("rotor.json5")

        self.assertEqual(data["freq"], 50)
        self.assertEqual(data["dt"], 4e-05)
        self.assertIn("alpha", data)
        self.assertIn("beta", data)
        self.assertIn("rotor_path", data)

    def test_moog_delay_model_uses_configured_dynamic_coefficients(self):
        dt = 1e-4
        delay = 1e-3

        sv_a = moog_servovalve(dt, delay=delay, tw=1e-8, zeta=0.01, tp3=1e-3)
        sv_b = moog_servovalve(dt, delay=delay, tw=4e-8, zeta=0.2, tp3=4e-3)

        self.assertFalse(np.allclose(sv_a.main_model.A, sv_b.main_model.A))
        self.assertAlmostEqual(sv_a.main_model._dt, dt)
        self.assertAlmostEqual(sv_b.main_model._dt, dt)


if __name__ == "__main__":
    unittest.main()
