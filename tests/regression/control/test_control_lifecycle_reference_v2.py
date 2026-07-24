"""Regression tests for read-only internal control outputs."""

from pathlib import Path

import control as cl
import numpy as np
import pytest

from ALB.config import FuzzyPIDConfig, PIDConfig
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.state_space import BaseLti


ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "refs" / "control_lifecycle_reference_v2.npz"


def _assert_controller_lifecycle(controller, prefix, reference):
    with pytest.raises(RuntimeError, match="unavailable"):
        controller.output()

    controller.input(0.0, [0.2, -0.3])
    with pytest.raises(RuntimeError, match="unavailable"):
        controller.output()
    computed = controller.evaluate()
    first = controller.output()
    second = controller.output()

    np.testing.assert_array_equal(computed, reference[f"{prefix}.first_output"])
    np.testing.assert_array_equal(
        np.stack([first, second]),
        reference[f"{prefix}.corrected_repeated_outputs"],
    )
    np.testing.assert_array_equal(
        controller.ki_intergral,
        reference[f"{prefix}.corrected_integral"],
    )
    np.testing.assert_array_equal(
        [len(controller.results)],
        reference[f"{prefix}.corrected_result_rows"],
    )
    with pytest.raises(RuntimeError, match="new controller input"):
        controller.evaluate()


def test_pid_and_fuzzy_outputs_are_read_only_after_one_evaluation():
    with np.load(REFERENCE) as reference:
        pid = PID(
            PIDConfig(
                dt=0.1,
                kp=1.0,
                ki=0.5,
                kd=0.1,
                freq=5.0,
                sensor_angles=[0.0, 90.0],
            )
        )
        fuzzy = FuzzyPID(
            FuzzyPIDConfig(
                dt=0.1,
                freq=5.0,
                rule_path=None,
                sensor_angles=[0.0, 90.0],
            )
        )
        _assert_controller_lifecycle(pid, "pid", reference)
        _assert_controller_lifecycle(fuzzy, "fuzzy", reference)


def test_lti_output_is_read_only_after_one_evaluation():
    system = cl.ss([[-2.0]], [[1.0]], [[3.0]], [[0.0]])
    model = BaseLti(system, 0.05, x0=np.asarray([0.4], dtype=float))

    with pytest.raises(RuntimeError, match="unavailable"):
        model.output()
    model.input(0.0, [0.25])
    with pytest.raises(RuntimeError, match="unavailable"):
        model.output()
    computed = model.evaluate()
    first = model.output()
    second = model.output()

    with np.load(REFERENCE) as reference:
        np.testing.assert_array_equal(computed, reference["lti.first_output"])
        np.testing.assert_array_equal(
            np.stack([first, second]),
            reference["lti.corrected_repeated_outputs"],
        )
        np.testing.assert_array_equal(
            model.xk0,
            reference["lti.corrected_state"],
        )
        np.testing.assert_array_equal(
            [len(model.xout), len(model.yout)],
            reference["lti.corrected_history_lengths"],
        )
    with pytest.raises(RuntimeError, match="new LTI input"):
        model.evaluate()
