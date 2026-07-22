"""Construction-time validation tests for standard port DTOs."""

import numpy as np
import pytest

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ControlInput,
    ControlOutput,
    RotorLoadInput,
    RotorState,
    StepContext,
    UnitSystem,
    ValveInput,
    ValveOutput,
)


@pytest.mark.parametrize(
    "dto",
    [
        BearingInput([0.0, 1.0], [2.0, 3.0], 0.0, "dimensional"),
        BearingOutput([4.0, 5.0], 0.0, UnitSystem.DIMENSIONAL),
        ControlInput([0.1, -0.1], 0.0, "nondimensional"),
        ControlOutput([0.2, -0.2], 0.0, "nondimensional"),
        ValveInput([0.2, -0.2], 0.0, "nondimensional"),
        ValveOutput([0.3, -0.3], 0.0, "nondimensional"),
    ],
)
def test_two_axis_dtos_normalize_to_read_only_arrays(dto):
    array = next(
        getattr(dto, name)
        for name in ("displacement", "velocity", "force", "error", "command", "spool")
        if hasattr(dto, name)
    )
    assert array.shape == (2,)
    assert not array.flags.writeable


def test_rotor_ports_validate_node_axis_shape_and_links():
    load = RotorLoadInput(
        force=[[1.0, 2.0], [3.0, 4.0]],
        previous_force=[[0.0, 0.0], [1.0, 1.0]],
        node_links=(2, 4),
        time=0.1,
        unit_system="dimensional",
    )
    state = RotorState(
        displacement=[[1.0, 2.0], [3.0, 4.0]],
        velocity=[[0.0, 0.0], [1.0, 1.0]],
        time=0.1,
        unit_system="dimensional",
    )
    assert load.force.shape == state.displacement.shape == (2, 2)


@pytest.mark.parametrize("spool", [[1.01, 0.0], [0.0, -1.01]])
def test_valve_output_rejects_out_of_range_normalized_spool(spool):
    with pytest.raises(ValueError, match=r"\[-1, 1\]"):
        ValveOutput(spool, 0.0, "nondimensional")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: BearingInput([0.0], [0.0, 0.0], 0.0, "dimensional"),
        lambda: BearingOutput([0.0, np.nan], 0.0, "dimensional"),
        lambda: ControlInput([0.0, 0.0], -1.0, "nondimensional"),
        lambda: ValveInput([0.0, 0.0], 0.0, "unspecified"),
        lambda: RotorLoadInput([[0.0, 0.0]], [[0.0, 0.0]], (), 0.0, "dimensional"),
    ],
)
def test_invalid_port_values_fail_at_construction(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_step_context_allows_only_explicit_supported_units():
    context = StepContext(0, 0.0, 0.01, "dimensional")
    assert context.unit_system is UnitSystem.DIMENSIONAL
    with pytest.raises(ValueError, match="unit_system"):
        StepContext(0, 0.0, 0.01, "unspecified")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ControlInput([1.0 + 1.0j, 0.0], 0.0, "nondimensional"),
        lambda: ValveInput([0.0, 1.0j], 0.0, "nondimensional"),
        lambda: RotorLoadInput(
            [[1.0 + 1.0j, 0.0]], [[0.0, 0.0]], (0,), 0.0, "dimensional"
        ),
    ],
)
def test_port_dtos_reject_complex_values_before_float_conversion(factory):
    with pytest.raises(ValueError, match="complex"):
        factory()


@pytest.mark.parametrize("time", [True, np.bool_(False)])
def test_port_dtos_reject_boolean_timestamps(time):
    with pytest.raises(TypeError, match="real scalar"):
        ControlInput([0.0, 0.0], time, "nondimensional")
