import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse.linalg import spsolve


def _load_split_imports():
    for parent in Path(__file__).resolve().parents:
        helper_path = parent / "_split_imports.py"
        if helper_path.exists():
            spec = importlib.util.spec_from_file_location(
                "_split_imports_for_thermal_force_time_term_compare",
                helper_path,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise ImportError("Could not locate test/_split_imports.py")


compare = _load_split_imports().import_validation_run_module(
    "thermal_force_time_term_compare"
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


def sparse_max_abs(matrix):
    if matrix.nnz == 0:
        return 0.0
    return float(np.max(np.abs(matrix.data)))


class TestThermalForceTimeTermCompare(unittest.TestCase):
    def test_three_case_configs_match_refactor_intent(self):
        bare_hydro_cfg = compare.CASE_CONFIGS["bare_hydro"]
        thermal_steady_cfg = compare.CASE_CONFIGS["thermal_steady"]
        thermal_transient_cfg = compare.CASE_CONFIGS["thermal_transient"]

        self.assertEqual(
            compare.CASE_ORDER, ["bare_hydro", "thermal_steady", "thermal_transient"]
        )
        self.assertEqual(compare.BASELINE_CASE, "bare_hydro")
        self.assertEqual(bare_hydro_cfg["label"], "no thermal coupling")
        self.assertFalse(bare_hydro_cfg["thermal_enabled"])
        self.assertIsNone(bare_hydro_cfg["thermal_data"])
        self.assertTrue(thermal_steady_cfg["thermal_enabled"])
        self.assertTrue(thermal_transient_cfg["thermal_enabled"])
        self.assertEqual(
            thermal_steady_cfg["label"], "thermal coupling without time term"
        )
        self.assertEqual(
            thermal_transient_cfg["label"], "thermal coupling with time term"
        )
        self.assertFalse(thermal_steady_cfg["thermal_data"]["transient_enabled"])
        self.assertTrue(thermal_transient_cfg["thermal_data"]["transient_enabled"])
        self.assertFalse(thermal_steady_cfg["thermal_data"]["args_nodim"])
        self.assertFalse(thermal_transient_cfg["thermal_data"]["args_nodim"])
        self.assertEqual(
            thermal_steady_cfg["thermal_data"]["heat_partition"],
            compare.THERMAL_HEAT_PARTITION,
        )
        self.assertEqual(
            thermal_transient_cfg["thermal_data"]["heat_partition"],
            compare.THERMAL_HEAT_PARTITION,
        )

    def test_extract_last_cycle_excludes_repeated_endpoint(self):
        with patch.object(compare, "PTS_PER_CYCLE", 4):
            data = {
                "time": np.arange(9, dtype=float),
                "force": np.arange(18, dtype=float).reshape(9, 2),
                "uxy": np.arange(18, dtype=float).reshape(9, 2),
            }
            last_cycle = compare.extract_last_cycle(data)

        np.testing.assert_array_equal(
            last_cycle["time"], np.array([4.0, 5.0, 6.0, 7.0])
        )
        np.testing.assert_array_equal(last_cycle["force"], data["force"][4:8])

    def test_three_cases_run_on_short_orbit(self):
        pts_per_cycle = 2
        with (
            patch.object(compare, "PTS_PER_CYCLE", pts_per_cycle),
            patch.object(compare, "N_CYCLES", 1),
            patch.object(compare, "create_pad_config", small_pad_config),
        ):
            orbit_spec = compare.resolve_orbit(compare.create_pad_config().c)
            results = {
                case_key: compare.extract_last_cycle(
                    compare.simulate_force_trace(case_key, orbit_spec)
                )
                for case_key in compare.CASE_ORDER
            }

        for case_key, result in results.items():
            self.assertEqual(result["force"].shape, (pts_per_cycle, 2))
            self.assertEqual(result["uxy"].shape, (pts_per_cycle, 2))
            self.assertTrue(np.isfinite(result["force"]).all(), msg=case_key)

    def test_viscosity_skfem_degenerates_to_skfem_when_miu_ratio_is_one(self):
        with patch.object(compare, "create_pad_config", small_pad_config):
            bare_alb, _, _ = compare.create_case_system("bare_hydro")
            thermal_alb, _, _ = compare.create_case_system("thermal_steady")

        uxy = np.array([10e-6, -20e-6], dtype=float)
        uxyt = np.array([0.0, 0.0], dtype=float)
        bare_pad = bare_alb.pads[0]
        thermal_pad = thermal_alb.pads[0]
        bare_pad.input(t=0.0, uxy=uxy, uxyt=uxyt, nodim=False)
        thermal_pad.input(t=0.0, uxy=uxy, uxyt=uxyt, nodim=False)

        bare_model = compare.get_pad_main_model(bare_pad)
        thermal_model = compare.get_pad_main_model(thermal_pad)

        self.assertEqual(bare_model.node_manager.non, thermal_model.node_manager.non)
        self.assertEqual(bare_model.elem_manager.noe, thermal_model.elem_manager.noe)
        self.assertEqual(bare_model.boundary.args, thermal_model.boundary.args)
        np.testing.assert_allclose(
            [node.coords for node in bare_model.nodes.values()],
            [node.coords for node in thermal_model.nodes.values()],
            rtol=0.0,
            atol=0.0,
        )
        np.testing.assert_allclose(
            [node.h for node in bare_model.nodes.values()],
            [node.h for node in thermal_model.nodes.values()],
            rtol=0.0,
            atol=0.0,
        )

        for node in thermal_model.nodes.values():
            self.assertEqual(node.miu_ratio, 1.0)

        self.assertAlmostEqual(bare_model.args["lambda"], thermal_model.args["lambda"])
        self.assertAlmostEqual(thermal_model.args["lambda0"], thermal_model.args["lambda"])

        bare_model.calc_matrixs_rights(calc=True, csc=True)
        thermal_model.calc_matrixs_rights(calc=True, csc=True)
        bare_matrix = bare_model.matrixs["ke"].copy()
        thermal_matrix = thermal_model.matrixs["ke"].copy()
        bare_rhs = bare_model.rights["fe"].copy()
        thermal_rhs = thermal_model.rights["fe"].copy()

        self.assertLess(sparse_max_abs(bare_matrix - thermal_matrix), 1e-11)
        np.testing.assert_allclose(bare_rhs, thermal_rhs, rtol=1e-12, atol=1e-12)

        bare_model.set_boundary(bare_model)
        thermal_model.set_boundary(thermal_model)
        bare_bc_matrix = bare_model.matrixs["ke"].copy()
        thermal_bc_matrix = thermal_model.matrixs["ke"].copy()
        bare_bc_rhs = bare_model.rights["fe"].copy()
        thermal_bc_rhs = thermal_model.rights["fe"].copy()

        self.assertLess(sparse_max_abs(bare_bc_matrix - thermal_bc_matrix), 1e-11)
        np.testing.assert_allclose(bare_bc_rhs, thermal_bc_rhs, rtol=1e-12, atol=1e-12)

        bare_pressure = spsolve(bare_bc_matrix, bare_bc_rhs)
        thermal_pressure = spsolve(thermal_bc_matrix, thermal_bc_rhs)
        np.testing.assert_allclose(
            bare_pressure, thermal_pressure, rtol=1e-11, atol=1e-11
        )


if __name__ == "__main__":
    unittest.main()
