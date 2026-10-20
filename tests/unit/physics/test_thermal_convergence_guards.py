"""Reject small-step and clipped-temperature false convergence."""

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import eye

from ALB import BearingConfig, build_bearing
from ALB.physics.thermal.solver import _thermal_linear_diagnostics


def _bearing(**thermal):
    reference = Path(__file__).resolve().parents[3] / "refs/mesh_independence_legacy_reference_v1.json"
    spec = json.loads(reference.read_text(encoding="utf-8"))["derived_spec"]
    spec["thermal"].update(thermal)
    return build_bearing(BearingConfig(spec))


def _calculate(bearing):
    return bearing.calculate(displacement=(-24e-6, -36e-6), velocity=(0.0, 0.0),
                             spool=(0.2, 0.2), time=0.0)


@pytest.mark.parametrize("update", ["linear", "log"])
def test_tiny_relaxation_cannot_claim_success_with_large_coupled_defect(update):
    bearing = _bearing(relax=1e-8, max_iter=2, tol=1e-6, miu_update=update)
    result = _calculate(bearing)
    assert not result.convergence.converged
    for pad in bearing._runtime._pads:
        diagnostic = pad.result_snapshot().metadata["thermal_diagnostics"]
        assert diagnostic["residual_history"][0]["step_residual"] < pad.config.tol
        assert diagnostic["fixed_point_residual"] > 100 * pad.config.tol
        assert pad.convergence_status.iterations == 2
        assert not pad.convergence_status.converged
        assert pad.convergence_status.residual >= diagnostic["fixed_point_residual"]


def test_clipping_is_not_an_energy_solution_even_with_exact_linear_solve():
    raw = np.array([0.0, 2.0])
    diagnostic = _thermal_linear_diagnostics(eye(2), raw, raw, np.array([0.0, 1.0]),
                                             scale=80.0, offset=20.0)
    assert diagnostic["linear_residual"] == 0.0
    assert diagnostic["energy_residual"] == 0.5
    assert diagnostic["temperature_clip_count"] == 1
    assert diagnostic["raw_temperature_max"] == 180.0


def test_temperature_limited_fixed_point_is_reported_as_failure():
    # With beta=0 the viscosity is already a fixed point.  An artificially low
    # temperature guard still cannot turn the clipped field into an energy solve.
    bearing = _bearing(beta=0.0, max_delta_t=1e-5, tol=1e-6, max_iter=5)
    result = _calculate(bearing)
    assert not result.convergence.converged
    diagnostics = [p.result_snapshot().metadata["thermal_diagnostics"]
                   for p in bearing._runtime._pads]
    clipped = [d for d in diagnostics if d["temperature_clip_count"] > 0]
    assert clipped
    for diagnostic in clipped:
        assert diagnostic["fixed_point_converged"]
        assert not diagnostic["energy_converged"]
        assert diagnostic["failure_reason"] == "temperature_clipping_energy_residual"


def test_unrelaxed_defect_drives_adaptation_and_final_fields_are_consistent():
    bearing = _bearing(max_iter=240, tol=1e-6,
                       adaptive_damp={"enabled": True, "min_value": 0.05})
    result = _calculate(bearing)
    assert result.convergence.converged
    for pad in bearing._runtime._pads:
        diagnostic = pad.result_snapshot().metadata["thermal_diagnostics"]
        assert diagnostic["fixed_point_residual"] < pad.config.tol
        assert diagnostic["energy_residual"] < pad.config.tol
        for control, record in zip(pad._last_thermal["relax_history"], diagnostic["residual_history"]):
            assert control["error"] == record["fixed_point_residual"]
