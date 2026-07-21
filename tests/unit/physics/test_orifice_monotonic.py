"""Unit tests for the unified monotonic CSOrifice pressure-flow solve."""

from __future__ import annotations

import numpy as np
import pytest

from ALB.config import NodimOrificeConfig
from ALB.physics.hydraulics.orifice import (
    NodimCSOrifice,
    _assembly_flow_jacobian,
    define_equations,
    solve_q,
)


CASES = [
    (1.7, np.array([0.8, 1.2, 2.0]), 0.3, np.array([0.2, 0.35, 0.5]), 0.6, 1.0),
    (
        1.7,
        np.array([0.8, 1.2, 2.0]),
        0.3,
        np.array([-1.8e-9, -2.6e-9, -1.78e-9]),
        0.4,
        0.0,
    ),
    (1.7, np.array([0.8, 1.2, 2.0]), 0.3, np.array([0.7, 0.8, 0.9]), 0.6, 0.0),
    (1.7, np.array([0.8, 1.2, 2.0]), 0.3, np.zeros(3), 0.6, 0.0),
]


@pytest.mark.parametrize("cq0,cq1_h2,cq2,pn,xv,ps", CASES)
def test_monotonic_solve_satisfies_full_orifice_equations(
    cq0, cq1_h2, cq2, pn, xv, ps
):
    answer = solve_q(cq0, cq1_h2, cq2, pn, xv, ps, 0.0)
    residual = define_equations(cq0, cq1_h2, cq2, pn, xv, ps, 0.0)(answer)

    assert np.all(np.isfinite(answer))
    assert np.linalg.norm(residual, ord=np.inf) <= 1e-10
    assert min(ps, float(np.min(pn))) <= answer[1]
    assert answer[1] <= max(ps, float(np.max(pn)))


@pytest.mark.parametrize("case", CASES[:3])
def test_assembly_flow_jacobian_matches_negative_finite_difference(case):
    cq0, cq1_h2, cq2, pn, xv, ps = case
    answer = solve_q(cq0, cq1_h2, cq2, pn, xv, ps, 0.0)
    actual = _assembly_flow_jacobian(
        cq0, cq1_h2, cq2, pn, xv, ps, float(answer[1])
    )
    step = 3e-10 if np.max(np.abs(pn)) < 1e-6 else 1e-6
    columns = []
    for index in range(len(pn)):
        delta = np.zeros_like(pn)
        delta[index] = step
        plus = solve_q(cq0, cq1_h2, cq2, pn + delta, xv, ps, 0.0)[2:]
        minus = solve_q(cq0, cq1_h2, cq2, pn - delta, xv, ps, 0.0)[2:]
        columns.append(-(plus - minus) / (2.0 * step))
    expected = np.column_stack(columns)

    np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-9)


def test_zero_leakage_contract_rejects_nonzero_values():
    with pytest.raises(ValueError, match="q_leak must be 0.0"):
        solve_q(1.0, np.ones(3), 0.3, np.zeros(3), 0.5, 1.0, 1e-12)
    with pytest.raises(ValueError, match="q_leak must be 0.0"):
        NodimOrificeConfig(q_leak=1e-12)
    with pytest.raises(ValueError, match="q_leak must be 0.0"):
        NodimCSOrifice(
            position=np.array([[0.5, 0.5]]),
            cq0=1.0,
            cq1=1.0,
            cq2=0.3,
            q_leak=1e-12,
        )


def test_degenerate_node_resistance_is_rejected():
    with pytest.raises(ValueError, match="cannot both vanish"):
        solve_q(1.0, 0.0, 0.0, np.array([0.2]), 0.5, 1.0, 0.0)


@pytest.mark.parametrize("invalid", [1.01, -1.01, np.nan, [0.1, 0.2]])
def test_nodim_orifice_rejects_invalid_spool_without_reusing_old_state(invalid):
    orifice = NodimCSOrifice(
        position=np.array([[0.5, 0.5]]),
        cq0=1.0,
        cq1=1.0,
        cq2=0.3,
    )
    orifice.input(0.4)

    with pytest.raises(ValueError, match="xv"):
        orifice.input(invalid)

    assert orifice.xv == pytest.approx(0.4)
