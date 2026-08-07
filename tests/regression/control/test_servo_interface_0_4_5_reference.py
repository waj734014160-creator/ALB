"""Exact regression for the 0.4.5 servovalve interface replacement."""

from __future__ import annotations

from pathlib import Path

import control
import numpy as np
import pytest

from ALB.control.valve import (
    second_order_servovalve,
    transfer_function_servovalve,
)
from tools.reference.generate_servo_interface_0_4_5_reference import (
    DT,
    _capture_case,
)


REFERENCE = Path("refs/servo_interface_0_4_5_reference_v1.npz")


def _equivalent_valves() -> dict[str, object]:
    """Build new-interface valves equivalent to every frozen legacy case."""

    tw = 1.0 / (2.0 * np.pi * 120.0)
    pade_numerator, pade_denominator = control.pade(0.001, n=1)
    third_order_numerator = np.polymul([1.0], pade_numerator)
    third_order_denominator = np.polymul(
        np.polymul([tw**2, 2.0 * 0.65 * tw, 1.0], [0.003, 1.0]),
        pade_denominator,
    )
    return {
        "second_order_166hz": second_order_servovalve(
            DT, 166.0, 0.7, 0.0
        ),
        "second_order_80hz_delayed": second_order_servovalve(
            DT, 80.0, 0.6, 0.002
        ),
        "legacy_third_order": transfer_function_servovalve(
            DT,
            third_order_numerator,
            third_order_denominator,
        ),
        "legacy_static": transfer_function_servovalve(DT, [1.0], [1.0]),
    }


@pytest.mark.parametrize("case_name", tuple(_equivalent_valves()))
def test_new_servo_interfaces_match_pre_0_4_5_reference_exactly(
    case_name: str,
) -> None:
    """Require exact matrices and outputs for every equivalent valve model."""

    reference = np.load(REFERENCE)
    valve = _equivalent_valves()[case_name]
    _, actual = _capture_case(case_name, valve)

    for array_name, values in actual.items():
        np.testing.assert_array_equal(values, reference[array_name])
