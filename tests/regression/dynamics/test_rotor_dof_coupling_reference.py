"""Exact regression gate for real ROSS 4/6-DOF coupling behavior."""

from tests._support.dynamics.coupling_v4 import (
    assert_corrected_coupling_reference_exact,
)


def test_real_ross_coupling_and_lqg_mapping_match_v4_exactly():
    """Protect state, loads, interpolation, histories, extraction, and mapping."""
    assert_corrected_coupling_reference_exact()
