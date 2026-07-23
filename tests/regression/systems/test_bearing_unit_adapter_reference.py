"""Exact adapter checks against the frozen pre-0.3 unit reference."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ALB.contracts import BearingInput, BearingOutput, StepContext, UnitSystem
from ALB.physics.bearing import BearingUnitAdapter
from ALB.systems.alb import bearing_scale_set_from_config
from tools.reference.generate_bearing_unit_boundary_reference_v1 import _config


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs" / "bearing_unit_boundary_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs" / "bearing_unit_boundary_reference_v1.npz"


def test_explicit_adapter_matches_frozen_unit_boundary_exactly():
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    contract = metadata["contracts"]
    scales = bearing_scale_set_from_config(
        _config(),
        scale_id=contract["scale_id"],
    )
    adapter = BearingUnitAdapter(scales)

    with np.load(REFERENCE_NPZ, allow_pickle=False) as frozen:
        local_input = adapter.rotor_input_to_bearing(
            BearingInput(
                frozen["input.displacement_dimensional"],
                frozen["input.velocity_dimensional"],
                frozen["context.time_dimensional"][-1],
                UnitSystem.DIMENSIONAL,
            )
        )
        local_context = adapter.rotor_context_to_bearing(
            StepContext(
                step_index=4,
                time=frozen["context.time_dimensional"][-1],
                dt=frozen["context.time_dimensional"][1],
                unit_system=UnitSystem.DIMENSIONAL,
            )
        )
        global_output = adapter.bearing_output_to_rotor(
            BearingOutput(
                frozen["force.total_nondimensional"],
                frozen["context.time_nondimensional"][-1],
                UnitSystem.NONDIMENSIONAL,
            )
        )
        dimensional_pressure = adapter.pressure(
            frozen["pressure.nondimensional"],
            source=UnitSystem.NONDIMENSIONAL,
            target=UnitSystem.DIMENSIONAL,
        )

        np.testing.assert_array_equal(
            local_input.displacement,
            frozen["input.displacement_dimensional"] / scales.Sx,
        )
        np.testing.assert_array_equal(
            local_input.velocity,
            frozen["input.velocity_dimensional"] / scales.Sv,
        )
        np.testing.assert_array_equal(
            global_output.force,
            frozen["force.total_nondimensional"] * scales.Sf,
        )
        np.testing.assert_array_equal(
            dimensional_pressure,
            frozen["pressure.dimensional"],
        )
        assert local_context.time == contract["bearing_local_context"]["time"]
        assert local_context.dt == contract["bearing_local_context"]["dt"]

    descriptor = scales.descriptor(
        applied_transform="rotor_to_bearing",
        global_context=StepContext(
            **contract["global_context"],
        ),
        bearing_local_context=StepContext(
            **contract["bearing_local_context"],
        ),
    )
    assert descriptor["schema"] == contract["schema"]
    assert descriptor["scale_id"] == contract["scale_id"]
    assert descriptor["scale_definition"] == contract["scale_definition"]
    assert descriptor["applied_transform"] == "rotor_to_bearing"
    assert descriptor["Sx"] == contract["Sx"]
    assert descriptor["St"] == contract["St"]
    assert descriptor["Sv"] == contract["Sv"]
    assert descriptor["Sf"] == contract["Sf"]
    assert descriptor["Sp"] == contract["Sp"]
