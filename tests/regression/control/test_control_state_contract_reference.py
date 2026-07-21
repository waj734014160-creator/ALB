"""Regression tests for corrected control-state lifecycle contracts."""

from __future__ import annotations

import json
from pathlib import Path
import warnings

import control as cl
import numpy as np
import pytest

from ALB.config import FuzzyPIDConfig, PIDConfig
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.state_space import BaseLti


ROOT = Path(__file__).resolve().parents[3]
REF_JSON = ROOT / "refs/control_state_contract_reference_v1.json"
REF_NPZ = ROOT / "refs/control_state_contract_reference_v1.npz"


def _run_pid() -> dict[str, np.ndarray]:
    controller = PID(
        PIDConfig(
            dt=0.1,
            kp=1.0,
            ki=0.5,
            kd=0.1,
            freq=5.0,
            sensor_angles=[0.0, 90.0],
        )
    )
    times = np.asarray([0.0, 0.1], dtype=float)
    errors = np.asarray([[0.2, -0.3], [0.1, -0.2]], dtype=float)
    outputs = []
    terms = {name: [] for name in ("kp_calc", "ki_calc", "kd_calc")}
    for time, error in zip(times, errors):
        controller.input(float(time), error)
        outputs.append(controller.output())
        for name in terms:
            terms[name].append(np.asarray(getattr(controller, name), dtype=float))
    return {
        "pid.times": times,
        "pid.errors": errors,
        "pid.outputs": np.asarray(outputs, dtype=float),
        **{
            f"pid.{name}": np.asarray(values, dtype=float)
            for name, values in terms.items()
        },
    }


def _run_fuzzy(controller: FuzzyPID) -> dict[str, np.ndarray]:
    times = np.asarray([0.0, 0.1], dtype=float)
    errors = np.asarray([[0.2, -0.3], [0.1, -0.2]], dtype=float)
    outputs = []
    gains = []
    for time, error in zip(times, errors):
        controller.input(float(time), error)
        outputs.append(controller.output())
        gains.append(np.stack([controller.kp, controller.ki, controller.kd]))
    return {
        "fuzzy.times": times,
        "fuzzy.errors": errors,
        "fuzzy.outputs": np.asarray(outputs, dtype=float),
        "fuzzy.gains": np.asarray(gains, dtype=float),
    }


def test_pid_fresh_trajectory_and_reset_match_reference_exactly():
    with np.load(REF_NPZ, allow_pickle=False) as reference:
        actual = _run_pid()
        for name, value in actual.items():
            np.testing.assert_array_equal(value, reference[name], err_msg=name)

        controller = PID(
            PIDConfig(
                dt=0.1,
                kp=1.0,
                ki=0.5,
                kd=0.1,
                freq=5.0,
                sensor_angles=[0.0, 90.0],
            )
        )
        controller.input(0.0, [0.8, -0.6])
        controller.output()
        controller.init()
        controller.input(0.0, reference["pid.errors"][0])
        np.testing.assert_array_equal(controller.output(), reference["pid.outputs"][0])
        assert len(controller.results) == 1


def test_fuzzy_fixed_ki_has_no_warning_and_reset_matches_reference_exactly():
    config = FuzzyPIDConfig(
        dt=0.1,
        freq=5.0,
        rule_path=None,
        sensor_angles=[0.0, 90.0],
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        controller = FuzzyPID(config)
        actual = _run_fuzzy(controller)
    assert not [item for item in caught if issubclass(item.category, RuntimeWarning)]

    with np.load(REF_NPZ, allow_pickle=False) as reference:
        for name, value in actual.items():
            np.testing.assert_array_equal(value, reference[name], err_msg=name)
        controller.init()
        reset = _run_fuzzy(controller)
        for name, value in reset.items():
            np.testing.assert_array_equal(value, reference[name], err_msg=name)


def test_fuzzy_all_fixed_gains_bypass_zero_width_memberships():
    config = FuzzyPIDConfig(
        dt=0.1,
        freq=5.0,
        rule_path=None,
        sensor_angles=[0.0, 90.0],
        kp_range=[0.2, 0.2, 0.01],
        ki_range=[0.0, 0.0, 0.01],
        kd_range=[0.1, 0.1, 0.01],
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        controller = FuzzyPID(config)
        controller.input(0.0, [0.2, -0.3])
        output = controller.output()
    assert controller.pid_sim is None
    assert not [item for item in caught if issubclass(item.category, RuntimeWarning)]
    np.testing.assert_array_equal(controller.kp, [0.2, 0.2])
    np.testing.assert_array_equal(controller.ki, [0.0, 0.0])
    np.testing.assert_array_equal(controller.kd, [0.1, 0.1])
    assert np.all(np.isfinite(output))


def test_siso_lti_history_is_exact_and_output_is_current_vector():
    with np.load(REF_NPZ, allow_pickle=False) as reference:
        system = cl.ss([[-2.0]], [[1.0]], [[3.0]], [[0.0]])
        model = BaseLti(system, 0.05, x0=np.asarray([0.4], dtype=float))
        returned = []
        for time, value in zip(
            reference["lti_siso.times"], reference["lti_siso.inputs"]
        ):
            model.input(float(time), value)
            returned.append(model.output())
        np.testing.assert_array_equal(
            np.asarray(model.xout).reshape(-1, 1), reference["lti_siso.states"]
        )
        np.testing.assert_array_equal(
            np.asarray(model.yout).reshape(-1, 1), reference["lti_siso.outputs"]
        )
        np.testing.assert_array_equal(
            np.asarray(returned).reshape(-1, 1), reference["lti_siso.outputs"]
        )


def test_mimo_lti_accepts_all_inputs_and_includes_feedthrough():
    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    assert "current Cx+Du vector" in metadata["mimo_contract"]
    with np.load(REF_NPZ, allow_pickle=False) as reference:
        system = cl.ss(
            reference["lti_mimo.A"],
            reference["lti_mimo.B"],
            reference["lti_mimo.C"],
            reference["lti_mimo.D"],
        )
        model = BaseLti(system, 0.1, x0=reference["lti_mimo.x0"])
        outputs = []
        for time, value in zip([0.0, 0.1], reference["lti_mimo.inputs"]):
            model.input(time, value)
            outputs.append(model.output())
        np.testing.assert_array_equal(
            np.asarray(model.xout), reference["lti_mimo.expected_states"]
        )
        np.testing.assert_array_equal(
            np.asarray(outputs), reference["lti_mimo.expected_outputs"]
        )

        with pytest.raises(ValueError, match="dimension"):
            model.input(0.2, [1.0])
        with pytest.raises(ValueError, match="sampling time"):
            model.input(0.15, [1.0, 2.0])
        with pytest.raises(ValueError, match="finite"):
            model.input(float("nan"), [1.0, 2.0])
