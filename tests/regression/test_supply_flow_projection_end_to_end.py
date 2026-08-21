"""End-to-end active-bearing checks for supply-flow projection modes."""

from __future__ import annotations

import numpy as np
import pytest

from ALB.api import BearingConfig, build_bearing
from ALB.physics.hydraulics.orifice import FilmPointAttachment


def _nondimensional_thermal_spec() -> dict:
    return {
        "family": "active_lubricated",
        "unit_system": "nondimensional",
        "time_step": 1.0e-3,
        "node": 1,
        "film": {
            "bearing_number": 1.0,
            "reference_bearing_number": 1.0,
            "length_ratio": 1.5,
            "arc_angle_deg": 80.0,
            "axial_length_ratio": 2.0,
            "circumferential_elements": 10,
            "axial_elements": 5,
            "eccentricity": 0.0,
            "attitude_angle_deg": 0.0,
            "reynolds_boundary": True,
            "continuous_boundary": False,
            "ambient_pressure": 0.0,
            "solver_tolerance": 1.0e-7,
            "max_iterations": 100,
            "relaxation": 0.8,
            "scale_viscosity": 0.0195,
            "scale_clearance": 1.2e-4,
            "scale_radius": 0.04,
            "scale_length": 0.06,
            "scale_pressure": 7.0e6,
            "scale_density": 872.0,
            "scale_speed_rpm": 3000.0,
        },
        "restrictors": {
            "positions": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            "base_flow_coefficient": 1.0,
            "spool_flow_coefficient": 1.0,
            "pressure_flow_coefficient": 0.0,
            "supply_pressure": 1.0,
            "tank_pressure": 0.0,
            "flow_projection": "element_shape",
        },
        "tank": {
            "x_range": [0.49, 0.51],
            "z_range": [0.2, 0.8],
            "depth_ratio": 2.0,
        },
        "valve": {"model": "static"},
        "control": {"mode": "external_spool"},
        "transforms": {},
        "thermal": {
            "t_in": 20.0,
            "t_ref": 20.0,
            "miu0": 0.0195,
            "beta": 0.03,
            "k_lub": 0.0,
            "cp_lub": 2000.0,
            "max_delta_t": 80.0,
            "heat_partition": 0.9,
            "relax": 0.5,
            "iter_method": "direct",
            "tol": 1.0e-4,
            "max_iter": 60,
            "miu_min": 1.0e-4,
            "miu_max": 1.0,
            "coupling": "full",
            "supg": True,
            "transient_enabled": False,
        },
    }


def _linearization_spec() -> dict:
    return {
        "family": "active_lubricated",
        "unit_system": "dimensional",
        "time_step": 6.667e-4,
        "node": 0,
        "film": {
            "circumferential_elements": 7,
            "axial_elements": 5,
            "max_iterations": 300,
            "solver_tolerance": 1.0e-9,
            "continuous_boundary": False,
            "solver": "newton",
        },
        "restrictors": {
            "positions": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            "flow_projection": "element_shape",
        },
        "tank": {},
        "valve": {"model": "static"},
        "control": {"mode": "external_spool"},
        "transforms": {},
        "thermal": None,
    }


@pytest.mark.parametrize("spool", [(0.0, 0.0), (0.0, 0.2)])
def test_nondimensional_element_shape_thermal_supply_cases(spool) -> None:
    bearing = build_bearing(BearingConfig(_nondimensional_thermal_spec()))
    result = bearing.calculate(
        displacement=(-0.2, -0.3),
        velocity=(0.0, 0.0),
        time=0.0,
        spool=spool,
    )

    assert result.convergence.converged
    assert np.all(np.isfinite(result.force))
    flow_magnitudes = []
    for pad in bearing._runtime._pads:
        snapshot = pad.result_snapshot()
        pressure = np.asarray(pad.bearing.main_model.output(), dtype=float)
        temperature = np.asarray(snapshot.values["temperature"], dtype=float)
        orifice = pad.bearing.simple_models[0]
        assert snapshot.metadata["converged"]
        assert np.min(pressure) >= -2.0e-8
        assert np.all(np.isfinite(temperature))
        assert all(isinstance(node, FilmPointAttachment) for node in orifice.node)
        assert orifice.flow_info()["structure"]["flow_projection"] == "element_shape"
        flow_magnitudes.append(float(np.max(np.abs(orifice.qn))))
        if spool == (0.0, 0.0):
            np.testing.assert_array_equal(orifice.qn, 0.0)
    if spool != (0.0, 0.0):
        assert max(flow_magnitudes) > 0.0


def test_element_shape_spool_linearization_matches_centered_finite_difference() -> None:
    config = BearingConfig(_linearization_spec())
    displacement = (0.0, 0.0)
    spool = np.array([0.2, 0.2], dtype=float)
    analytic = build_bearing(config).analysis.harmonic_linearize(
        displacement,
        5.0,
        spool=spool,
    ).values["spool_jacobian"]
    step = 1.0e-5
    columns = []
    for index in range(2):
        plus = spool.copy()
        minus = spool.copy()
        plus[index] += step
        minus[index] -= step
        force_plus = build_bearing(config).calculate(
            displacement=displacement,
            velocity=(0.0, 0.0),
            time=0.0,
            spool=plus,
        ).force
        force_minus = build_bearing(config).calculate(
            displacement=displacement,
            velocity=(0.0, 0.0),
            time=0.0,
            spool=minus,
        ).force
        columns.append((force_plus - force_minus) / (2.0 * step))
    finite_difference = np.column_stack(columns)

    np.testing.assert_allclose(
        analytic,
        finite_difference,
        rtol=5.0e-4,
        atol=1.0e-4,
    )
