import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np


def _load_split_imports():
    for parent in Path(__file__).resolve().parents:
        helper_path = parent / "_split_imports.py"
        if helper_path.exists():
            spec = importlib.util.spec_from_file_location(
                "_split_imports_for_thermal_kc_compare",
                helper_path,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise ImportError("Could not locate test/_split_imports.py")


split_imports = _load_split_imports()
compare = split_imports.import_validation_run_module(
    "thermal_kc_compare",
    dependencies=("thermal_force_time_term_compare",),
)


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
    def test_validation_dependency_ignores_param_scan_run_first_on_sys_path(self):
        workspace_root = split_imports.find_split_workspace_root(Path(__file__))
        param_scan_root = str(workspace_root / "PARAM_SCAN")
        original_path = list(sys.path)
        try:
            sys.path.insert(0, param_scan_root)
            imported = split_imports.import_validation_run_module(
                "thermal_kc_compare",
                dependencies=("thermal_force_time_term_compare",),
            )
        finally:
            sys.path[:] = original_path

        validation_run = (workspace_root / "VALIDATION" / "run").resolve()
        self.assertTrue(
            Path(imported.__file__).resolve().is_relative_to(validation_run)
        )
        self.assertTrue(
            Path(imported.force_compare.__file__).resolve().is_relative_to(
                validation_run
            )
        )

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
