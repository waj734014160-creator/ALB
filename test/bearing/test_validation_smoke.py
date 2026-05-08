# -- coding: utf-8 --

import importlib
import math
import pathlib
import sys
import unittest

import numpy as np

_CURRENT_DIR = pathlib.Path(__file__).resolve().parent
if str(_CURRENT_DIR) not in sys.path:
    sys.path.append(str(_CURRENT_DIR))

_ref = importlib.import_module("validation_reference_data")
_runner = importlib.import_module("validation_runner")
ANGLE_VALUES = _ref.ANGLE_VALUES
E_VALUES = _ref.E_VALUES
run_validation_case = _runner.run_validation_case


class TestValidationSmoke(unittest.TestCase):
    def test_representative_cases_return_finite_metrics(self):
        # Lowest and highest eccentricity points from validation_e_angle baseline.
        sample_indexes = [0, len(E_VALUES) - 1]
        for idx in sample_indexes:
            with self.subTest(idx=idx, e=E_VALUES[idx], angle=ANGLE_VALUES[idx]):
                result = run_validation_case(E_VALUES[idx], ANGLE_VALUES[idx])
                self.assertGreater(result["load"], 0.0)
                self.assertTrue(np.all(np.isfinite(result["force"])))
                self.assertTrue(np.all(np.isfinite(result["k_matrix"])))
                self.assertTrue(np.all(np.isfinite(result["c_matrix"])))
                self.assertTrue(math.isfinite(result["friction"]))
                self.assertTrue(math.isfinite(result["S"]))


if __name__ == "__main__":
    unittest.main()
