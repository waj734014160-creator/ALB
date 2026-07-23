"""Unit tests for explicit bearing unit conversion."""

from __future__ import annotations

import numpy as np
import pytest

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    DirectSpoolBearingInput,
    StepContext,
    UnitSystem,
    ValveOutput,
)
from ALB.physics.bearing import BearingScaleSet, BearingUnitAdapter


def _scales() -> BearingScaleSet:
    return BearingScaleSet(
        rotor_unit=UnitSystem.DIMENSIONAL,
        bearing_unit=UnitSystem.NONDIMENSIONAL,
        Sx=8.0e-5,
        St=0.01,
        Sv=0.008,
        Sf=8400.0,
        Sp=7.0e6,
        scale_id="test-scales",
        pressure_scale_source="test pressure",
        velocity_definition_id="test.velocity.v1",
        residual_definition_id="test.residual.v1",
        provenance="unit test",
    )


def test_scale_set_rejects_inconsistent_velocity_and_missing_provenance():
    values = _scales()
    with pytest.raises(ValueError, match="Sv must equal"):
        BearingScaleSet(
            rotor_unit=values.rotor_unit,
            bearing_unit=values.bearing_unit,
            Sx=values.Sx,
            St=values.St,
            Sv=values.Sv * 2.0,
            Sf=values.Sf,
            Sp=values.Sp,
            scale_id=values.scale_id,
            pressure_scale_source=values.pressure_scale_source,
            velocity_definition_id=values.velocity_definition_id,
            residual_definition_id=values.residual_definition_id,
            provenance=values.provenance,
        )
    with pytest.raises(ValueError, match="provenance"):
        BearingScaleSet(
            rotor_unit=values.rotor_unit,
            bearing_unit=values.bearing_unit,
            Sx=values.Sx,
            St=values.St,
            Sv=values.Sv,
            Sf=values.Sf,
            Sp=values.Sp,
            scale_id=values.scale_id,
            pressure_scale_source=values.pressure_scale_source,
            velocity_definition_id=values.velocity_definition_id,
            residual_definition_id=values.residual_definition_id,
            provenance="",
        )


def test_adapter_converts_each_port_quantity_and_context_independently():
    adapter = BearingUnitAdapter(_scales())
    context = StepContext(4, 0.02, 0.005, "dimensional")
    bearing_context = adapter.rotor_context_to_bearing(context)
    bearing_input = adapter.rotor_input_to_bearing(
        BearingInput(
            [8.0e-6, -1.6e-5],
            [2.4e-4, -3.2e-4],
            0.02,
            "dimensional",
        )
    )

    assert bearing_context == StepContext(4, 2.0, 0.5, "nondimensional")
    np.testing.assert_array_equal(
        bearing_input.displacement,
        np.asarray([8.0e-6, -1.6e-5]) / 8.0e-5,
    )
    np.testing.assert_array_equal(
        bearing_input.velocity,
        np.asarray([2.4e-4, -3.2e-4]) / 0.008,
    )
    assert bearing_input.time == 2.0

    rotor_output = adapter.bearing_output_to_rotor(
        BearingOutput([1.5, -2.0], 2.0, "nondimensional")
    )
    np.testing.assert_array_equal(rotor_output.force, [12600.0, -16800.0])
    assert rotor_output.time == 0.02
    np.testing.assert_array_equal(
        adapter.pressure(
            [0.25, 1.0],
            source=UnitSystem.NONDIMENSIONAL,
            target=UnitSystem.DIMENSIONAL,
        ),
        [1.75e6, 7.0e6],
    )


def test_direct_spool_conversion_preserves_normalized_command_identity():
    adapter = BearingUnitAdapter(_scales())
    spool = ValveOutput([0.2, -0.3], 0.02, "nondimensional")
    converted = adapter.rotor_direct_spool_to_bearing(
        DirectSpoolBearingInput(
            BearingInput(
                [8.0e-6, -1.6e-5],
                [2.4e-4, -3.2e-4],
                0.02,
                "dimensional",
            ),
            spool,
        )
    )

    np.testing.assert_array_equal(converted.spool.spool, spool.spool)
    assert converted.spool.time == converted.bearing.time == 2.0
    np.testing.assert_array_equal(
        converted.bearing.displacement,
        np.asarray([8.0e-6, -1.6e-5]) / 8.0e-5,
    )


def test_scale_descriptor_uses_primitive_direction_metadata():
    scales = _scales()
    descriptor = scales.descriptor(
        applied_transform="bearing_to_rotor",
        global_context=StepContext(3, 0.02, 0.005, "dimensional"),
        bearing_local_context=StepContext(
            3,
            2.0,
            0.5,
            "nondimensional",
        ),
    )

    assert descriptor["scale_definition"] == "dimensional_per_nondimensional"
    assert descriptor["applied_transform"] == "bearing_to_rotor"
    assert descriptor["source_unit"] == "nondimensional"
    assert descriptor["target_unit"] == "dimensional"
    assert descriptor["global_context"]["step_index"] == 3
    assert descriptor["bearing_local_context"]["time"] == 2.0
