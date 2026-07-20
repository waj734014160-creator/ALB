# -- coding: utf-8 --

import math
import unittest

import numpy as np

from tests._support.bearing import validation_reference_data as _ref
from tests._support.bearing import validation_runner as _runner
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
