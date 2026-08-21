"""Regression guards for parameterized element-shape supply-flow coupling."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from ALB.api import BearingConfig
from tools.reference.generate_mesh_independence_legacy_reference_v1 import _run_case


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_JSON = ROOT / "refs" / "supply_flow_element_shape_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs" / "supply_flow_element_shape_reference_v1.npz"
SUPPLY_ON = (0.2, 0.2)


@pytest.mark.parametrize("case_id", ["tri_p1", "tri_p2", "quad_q1", "quad_q2"])
def test_element_shape_matches_frozen_preparameterization_fields(case_id) -> None:
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    spec = deepcopy(metadata["case_specs"][case_id])
    spec["restrictors"]["flow_projection"] = "element_shape"
    arrays, status = _run_case(BearingConfig(spec), SUPPLY_ON)

    assert status["converged"]
    assert all(status["thermal_converged_by_pad"])
    assert np.min(arrays["film.pressure_fields"]) >= -1.0e-8
    assert all(np.all(np.isfinite(value)) for value in arrays.values())
    with np.load(REFERENCE_NPZ) as expected:
        for name, actual in arrays.items():
            np.testing.assert_array_equal(actual, expected[f"{case_id}.{name}"])


def test_element_shape_supply_off_remains_finite_and_converged() -> None:
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    spec = deepcopy(metadata["case_specs"]["quad_q1"])
    spec["restrictors"]["flow_projection"] = "element_shape"
    arrays, status = _run_case(BearingConfig(spec), (0.0, 0.0))

    assert status["converged"]
    assert all(status["thermal_converged_by_pad"])
    assert np.min(arrays["film.pressure_fields"]) >= -1.0e-8
    assert np.all(np.isfinite(arrays["thermal.temperature_fields"]))
    np.testing.assert_array_equal(arrays["orifice.flow_fields"], 0.0)
