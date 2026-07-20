# -- coding: utf-8 --

import unittest

from tests._support.bearing import validation_reference_data as _ref
from tests._support.bearing import validation_runner as _runner
ANGLE_VALUES = _ref.ANGLE_VALUES
CXY_REF = _ref.CXY_REF
CYX_REF = _ref.CYX_REF
E_VALUES = _ref.E_VALUES
KXX_REF = _ref.KXX_REF
P_REF = _ref.P_REF
is_case_correct = _runner.is_case_correct
run_validation_case = _runner.run_validation_case


class TestValidationPrecision(unittest.TestCase):
    def test_hydrostatic_bearing_matches_reference_on_sampled_cases(self):
        # Sampled cases to keep runtime acceptable while preserving reference check.
        sampled_indexes = [0, 8, 15]
        for idx in sampled_indexes:
            with self.subTest(idx=idx, e=E_VALUES[idx], angle=ANGLE_VALUES[idx]):
                result = run_validation_case(E_VALUES[idx], ANGLE_VALUES[idx])
                reference = {
                    "kxx": KXX_REF[idx],
                    "cxy": CXY_REF[idx],
                    "cyx": CYX_REF[idx],
                    "p": P_REF[idx],
                }
                ok, detail = is_case_correct(result, reference)
                self.assertTrue(
                    ok,
                    msg=(
                        f"Model mismatch at idx={idx}, e={E_VALUES[idx]}, angle={ANGLE_VALUES[idx]}: "
                        f"checks={detail}, result={{'kxx':{result['kxx']:.4f}, 'cxy':{result['cxy']:.4f}, "
                        f"'cyx':{result['cyx']:.4f}, 'p':{result['friction']:.4f}}}, "
                        f"reference={reference}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
