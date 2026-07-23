"""Exact regression replay for behavior outside the approved review fixes."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ALB.config import HydConfig, PIDConfig
from ALB.contracts import BearingInput, UnitSystem
from ALB.control import PID
from ALB.physics.bearing import HydrostaticBearing, MultiPad


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "refs" / "review_fix_unaffected_reference_v1.json"


class _ReferenceLeafPad:
    unit_system = UnitSystem.DIMENSIONAL
    node_link = 0

    def __init__(self, force, friction):
        self.args = {"c": 1.0}
        self.force = np.asarray(force, dtype=float)
        self.friction = float(friction)
        self.init_calls = 0
        self.input_calls = 0
        self.output_calls = 0

    def init(self):
        self.init_calls += 1

    def input(self, *, uxy, uxyt, t, nodim):
        del uxy, uxyt, t, nodim
        self.input_calls += 1

    def output(self, *, nodim):
        del nodim
        self.output_calls += 1
        return {
            "force": self.force.copy(),
            "friction": self.friction,
        }

    def calc_is_finished(self):
        return True


def _load_reference():
    payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert payload["schema"] == "alb.review-fix-unaffected-reference.v1"
    return payload


def test_unsaturated_pid_behavior_matches_reference_exactly() -> None:
    payload = _load_reference()
    inputs = payload["inputs"]["pid"]
    expected = payload["outputs"]["pid"]
    controller = PID(
        PIDConfig(
            dt=inputs["dt"],
            kp=inputs["kp"],
            ki=inputs["ki"],
            kd=inputs["kd"],
            freq=inputs["freq"],
            sensor_angles=inputs["sensor_angles"],
        )
    )

    for sample, target in zip(inputs["samples"], expected):
        time, error = sample
        controller.input(time, error)
        output = controller.evaluate()
        assert controller.t == target["time"]
        np.testing.assert_array_equal(controller.error, target["error"])
        np.testing.assert_array_equal(
            controller.delta_error,
            target["delta_error"],
        )
        np.testing.assert_array_equal(controller.kp_calc, target["kp_calc"])
        np.testing.assert_array_equal(controller.ki_calc, target["ki_calc"])
        np.testing.assert_array_equal(controller.kd_calc, target["kd_calc"])
        np.testing.assert_array_equal(output, target["output"])


def test_multipad_numeric_aggregation_matches_reference_exactly() -> None:
    payload = _load_reference()
    inputs = payload["inputs"]["multi_pad"]
    expected = payload["outputs"]["multi_pad"]
    pads = [
        _ReferenceLeafPad(force, friction)
        for force, friction in zip(inputs["forces"], inputs["frictions"])
    ]
    runtime = MultiPad(*pads)
    output = runtime.step(
        BearingInput(
            displacement=inputs["displacement"],
            velocity=inputs["velocity"],
            time=inputs["time"],
            unit_system=UnitSystem.DIMENSIONAL,
        )
    )

    np.testing.assert_array_equal(output.force, expected["force"])
    assert runtime.result_snapshot().values["friction"] == expected["friction"]
    assert [pad.init_calls for pad in pads] == expected["pad_init_calls"]
    assert [pad.input_calls for pad in pads] == expected["pad_input_calls"]
    assert [pad.output_calls for pad in pads] == expected["pad_output_calls"]


def test_hydrostatic_internal_velocity_matches_reference_exactly() -> None:
    payload = _load_reference()
    inputs = payload["inputs"]["hydrostatic"]
    expected = payload["outputs"]["hydrostatic"]
    bearing = HydrostaticBearing(HydConfig(**inputs))

    assert bearing.input_args["dxt"] == expected["dxt"]
    assert bearing.input_args["dyt"] == expected["dyt"]
    assert bearing.input_args["vf"] == expected["vf"]
