"""Numerical acceptance of the packaged analytic thermal harmonic tool."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

import ALB
from ALB.physics.thermal._harmonic_base import PadComplementaritySystem
from ALB.physics.thermal._harmonic_equations import AnalyticPadSystem
from ALB.physics.thermal.solver import _build_film_grid
from ALB.systems.alb.linearization import _temperature_branch_diagnostics, solve_frequency

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "refs/thermal_harmonic_projection_v1"


@pytest.fixture(scope="module")
def reference():
    metadata = json.loads(REFERENCE.with_suffix(".json").read_text(encoding="utf-8"))
    data = REFERENCE.with_suffix(".npz").read_bytes()
    assert hashlib.sha256(data).hexdigest() == metadata["npz_sha256"]
    with np.load(REFERENCE.with_suffix(".npz")) as archive:
        yield metadata["case"], dict(archive)


@pytest.fixture(scope="module")
def frequency_results(reference):
    case, _ = reference
    bearing = ALB.build_bearing(ALB.BearingConfig(case["spec"]))
    owner = bearing._runtime
    results = {}
    for frequency in case["frequencies_hz"]:
        results[frequency] = bearing.analysis.harmonic_linearize(
            case["operating_point"], frequency, spool=case["spool"],
        )
    assert bearing._runtime is owner
    with pytest.raises(RuntimeError, match="no bearing result"):
        _ = bearing.latest_result
    return results


@pytest.mark.parametrize("frequency", [25.0, 50.0, 100.0])
def test_thermal_coefficients_match_independent_source_reference(reference, frequency_results, frequency):
    _, expected = reference
    result = frequency_results[frequency]
    assert result.convergence.converged
    assert result.convergence.residual < 1.0e-8
    for key, name in (("K", "stiffness"), ("C", "damping"), ("G", "spool_transfer")):
        # Aggregate scaling before/after summation differs only by roundoff.
        np.testing.assert_allclose(result.values[name], expected[f"{key}_{frequency:g}"], rtol=2e-12, atol=1e-10)
    for pad in range(4):
        np.testing.assert_array_equal(result.values["pad_pressurized"][pad], expected[f"pad_{pad}_active"])
        np.testing.assert_array_equal(result.values["pad_base_state"][pad], expected[f"pad_{pad}_state"])
        np.testing.assert_array_equal(result.values["pad_force_transfer_nondim"][pad], expected[f"pad_{pad}_transfer_{frequency:g}"])
    assert np.iscomplexobj(result.values["spool_transfer"])
    assert not result.values["spool_transfer"].flags.writeable


def test_thermal_frequency_dependence_and_complex_artifact_roundtrip(frequency_results, tmp_path):
    low, high = frequency_results[25.0], frequency_results[100.0]
    for name in ("stiffness", "damping", "spool_transfer"):
        assert not np.allclose(low.values[name], high.values[name], rtol=1e-6)
    result = frequency_results[50.0]
    manifest = result.write(tmp_path / "harmonic")
    record = next(record for record in manifest.artifacts if record.path.endswith("spool_transfer.npy") and "pad_" not in record.path)
    np.testing.assert_array_equal(np.load(tmp_path / "harmonic" / record.path), result.values["spool_transfer"])
    assert all(audit["weakly_active_nodes"] == 0 for audit in result.metadata["pad_diagnostics"].values())


@pytest.fixture(scope="module", params=["nearest_node", "element_shape"])
def equations(reference, request):
    case, _ = reference
    spec = copy.deepcopy(case["spec"])
    spec["film"].update(circumferential_elements=19, axial_elements=15)
    spec["restrictors"]["flow_projection"] = request.param
    bearing = ALB.build_bearing(ALB.BearingConfig(spec))
    base = bearing.calculate(displacement=case["operating_point"], velocity=(0., 0.), time=0., spool=case["spool"])
    assert base.convergence.converged
    pad = bearing._runtime._pads[1]
    film = pad.bearing.main_model
    scales = pad.thermal_model.build_mesh(film, _build_film_grid(film))["scales"]
    initial = {"temperature_nondim": scales.temperature_to_nondim(pad.result_snapshot().values["temperature"], scales.t_supply)}
    inputs = np.r_[np.asarray(case["operating_point"])/scales.c, [0., 0.], case["spool"]]
    return AnalyticPadSystem(pad, initial, inputs, 1)


def test_analytic_state_and_input_columns_against_independent_perturbations(equations):
    system = equations
    z = system.z.copy()
    base_input = system.base_input.copy()
    _, jacobian, context = system.assemble(z)
    direction = np.random.default_rng(7231).normal(size=z.size)
    step = 1.0e-7
    try:
        plus = system.assemble(z + step * direction)[0]
        minus = system.assemble(z - step * direction)[0]
        np.testing.assert_allclose(jacobian @ direction, (plus-minus)/(2*step), rtol=2e-5, atol=2e-8)
        for column in range(6):
            system.base_input = base_input.copy()
            system.base_input[column] += step
            plus = system.assemble(z)[0]
            system.base_input[column] -= 2 * step
            minus = system.assemble(z)[0]
            system.base_input = base_input.copy()
            system.assemble(z)
            analytic = system.analytic_input_column(column, context)
            np.testing.assert_allclose(analytic, (plus-minus)/(2*step), rtol=2e-5, atol=2e-8)
    finally:
        system.base_input = base_input
        system.assemble(z)


def test_cooling_projection_matches_production_thermal_source(equations):
    system = equations
    flow = system.z[2*system.n+2:] * system.cold_source_active
    calculated = system.thermal_projection.T @ sp.diags(flow) @ system.thermal_projection
    source_data = system.wrapper._collect_orifice_info()
    expected, rhs = system.thermal_model._apply_nondim_orifice_sources(
        sp.csr_matrix((system.n, system.n)), np.zeros(system.n), system.mesh, 0., source_data,
    )
    np.testing.assert_allclose(calculated.toarray(), expected.toarray(), rtol=1e-14, atol=1e-16)
    np.testing.assert_array_equal(rhs, 0.)


def test_thermal_storage_disabled_has_real_spool_and_frequency_independent_kc(equations):
    strict = PadComplementaritySystem(equations)
    audit = strict.refine_base()
    assert audit["converged"] and audit["weakly_active_nodes"] == 0
    low, _ = solve_frequency(strict, 2*np.pi*25, thermal_inertia=False)
    high, _ = solve_frequency(strict, 2*np.pi*100, thermal_inertia=False)
    np.testing.assert_array_equal(low, high)
    np.testing.assert_array_equal(low.imag, 0.)
    assert np.all(np.isfinite(low))


def test_temperature_limits_are_checked_after_strict_base_refinement(equations):
    strict = PadComplementaritySystem(equations)
    audit = strict.refine_base()
    assert audit["converged"]
    assert _temperature_branch_diagnostics(strict)["temperature_rise_max_k"] > 0.0
    original = strict.base_state.copy()
    for temperature_rise in (-6.0, equations.wrapper.config.max_delta_t + 1.0):
        strict.base_state[strict.n] = temperature_rise / equations.scales.delta_t
        with pytest.raises(RuntimeError, match="temperature clipping bound"):
            _temperature_branch_diagnostics(strict)
        strict.base_state[:] = original


@pytest.mark.parametrize("change, match", [
    ({"thermal": {"coupling": "half"}}, "full nodal"),
    ({"film": {"ambient_pressure": 10.}}, "zero-pressure"),
    ({"film": {"mesh_type": "quadrilateral", "element_order": 1}, "thermal": {"transient_enabled": False}}, "tensor grid"),
])
def test_rejects_unsupported_thermal_contract_before_calculation(reference, change, match):
    case, _ = reference
    spec = copy.deepcopy(case["spec"])
    for section, values in change.items():
        spec[section].update(values)
    bearing = ALB.build_bearing(ALB.BearingConfig(spec))
    with pytest.raises(ALB.CalculationError, match=match):
        bearing.analysis.harmonic_linearize(case["operating_point"], 50., spool=case["spool"])


def test_base_failure_preserves_evidence_and_does_not_publish(reference, monkeypatch):
    case, _ = reference
    spec = copy.deepcopy(case["spec"])
    spec["film"].update(circumferential_elements=9, axial_elements=7)
    original = PadComplementaritySystem.refine_base
    def fail(self, **kwargs):
        audit = original(self, maximum_iterations=1)
        audit["converged"] = False
        return audit
    monkeypatch.setattr(PadComplementaritySystem, "refine_base", fail)
    bearing = ALB.build_bearing(ALB.BearingConfig(spec))
    with pytest.raises(ALB.CalculationError, match="strict thermal base") as caught:
        bearing.analysis.harmonic_linearize(case["operating_point"], 50., spool=case["spool"])
    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert "failed_pad_state" in snapshot.values
    assert snapshot.metadata["failed_pad"] == 0
    with pytest.raises(RuntimeError, match="no bearing result"):
        _ = bearing.latest_result


def test_element_shape_public_tool_preserves_existing_bearing_result(reference):
    case, _ = reference
    spec = copy.deepcopy(case["spec"])
    spec["restrictors"]["flow_projection"] = "element_shape"
    bearing = ALB.build_bearing(ALB.BearingConfig(spec))
    previous = bearing.calculate(displacement=case["operating_point"], time=0., spool=case["spool"])
    result = bearing.analysis.harmonic_linearize(case["operating_point"], 50., spool=case["spool"])
    assert bearing.latest_result is previous
    assert result.convergence.converged
    assert result.metadata["flow_projection"] == "element_shape"
    assert np.all(np.isfinite(result.values["spool_transfer"]))


def test_thermal_production_failure_has_stable_api_error(reference, monkeypatch):
    case, _ = reference
    bearing = ALB.build_bearing(ALB.BearingConfig(case["spec"]))
    def fail(*args, **kwargs):
        raise RuntimeError("injected pressure failure")
    monkeypatch.setattr(ALB.BearingAnalysis, "_run_runtime", fail)
    with pytest.raises(ALB.CalculationError, match="production base failed") as caught:
        bearing.analysis.harmonic_linearize(case["operating_point"], 50., spool=case["spool"])
    assert caught.value.failure_snapshot is not None


def test_zero_spool_is_rejected_before_solving(reference, monkeypatch):
    case, _ = reference
    bearing = ALB.build_bearing(ALB.BearingConfig(case["spec"]))
    def unexpected(*args, **kwargs):
        raise AssertionError("a switching-point request must not start a base solve")
    monkeypatch.setattr(ALB.BearingAnalysis, "_run_runtime", unexpected)
    with pytest.raises(ALB.CalculationError, match="nonzero base spool"):
        bearing.analysis.harmonic_linearize(case["operating_point"], 50., spool=(0., .2))
