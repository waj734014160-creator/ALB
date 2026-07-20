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
