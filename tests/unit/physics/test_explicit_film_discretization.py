"""Tests for synchronized explicit pressure/thermal film discretizations."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from ALB.api import BearingConfig, build_bearing
from ALB.api.errors import ConfigurationError
from ALB.physics.film.solver import FilmPostProcess, _explicit_mesh
from ALB.physics.hydraulics.orifice import FilmPointAttachment
from ALB.physics.thermal.solver import (
    SkfemThermalModelNondim,
    _apply_exact_point_coupling,
    _build_film_grid,
    _mesh_doflocs,
    _supg_characteristic_length,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs" / "mesh_independence_legacy_reference_v1.json"


def _base_config():
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    return BearingConfig(metadata["derived_spec"])


def _model(mesh_type: str, element_order: int):
    config = _base_config().with_overrides(
        {
            "film.mesh_type": mesh_type,
            "film.element_order": element_order,
            "restrictors.flow_projection": "element_shape",
        }
    )
    return build_bearing(config)._runtime._pads[0].bearing.main_model


def _thermal_mesh(model):
    from ALB.config import ThermalConfig

    thermal = SkfemThermalModelNondim(
        ThermalConfig(args_nodim=True, iter_method="direct")
    )
    return thermal.build_mesh(model, _build_film_grid(model))["mesh"]


@pytest.mark.parametrize(
    ("mesh_type", "element_order", "elements", "dofs"),
    [
        ("triangular", 1, 100, 66),
        ("triangular", 2, 100, 231),
        ("quadrilateral", 1, 50, 66),
        ("quadrilateral", 2, 50, 231),
    ],
)
def test_explicit_basis_counts_and_all_boundary_dofs(
    mesh_type, element_order, elements, dofs
):
    model = _model(mesh_type, element_order)
    assert model.mesh_skfem.nelements == elements
    assert model.basis.N == dofs
    coords = model.basis.doflocs
    expected = np.flatnonzero(
        np.isclose(coords[0], model.args["x_lim"][0])
        | np.isclose(coords[0], model.args["x_lim"][1])
        | np.isclose(coords[1], model.args["z_lim"][0])
        | np.isclose(coords[1], model.args["z_lim"][1])
    )
    actual = set()
    for axis, value in (
        (0, model.args["x_lim"][0]),
        (0, model.args["x_lim"][1]),
        (1, model.args["z_lim"][0]),
        (1, model.args["z_lim"][1]),
    ):
        actual.update(model.node_manager.search(axis, value, number=True))
    assert actual == set(expected.tolist())


@pytest.mark.parametrize("mesh_type", ["triangular", "quadrilateral"])
@pytest.mark.parametrize("element_order", [1, 2])
def test_exact_supply_attachment_reproduces_linear_pressure(
    mesh_type, element_order
):
    model = _model(mesh_type, element_order)
    x_lim = model.args["x_lim"]
    z_lim = model.args["z_lim"]
    point = np.array(
        [x_lim[0] + 0.37 * np.diff(x_lim)[0], z_lim[0] + 0.41 * np.diff(z_lim)[0]]
    )
    values = 1.0 + 2.0 * model.basis.doflocs[0] - 3.0 * model.basis.doflocs[1]
    model.add_result(values)
    model.update_to_nodes(values)
    attachment = FilmPointAttachment(model, point)
    assert np.sum(attachment.weights) == pytest.approx(1.0, abs=1.0e-13)
    assert attachment.p == pytest.approx(
        1.0 + 2.0 * point[0] - 3.0 * point[1], abs=1.0e-12
    )


def test_exact_thermal_point_source_is_conservative_for_q2():
    model = _model("quadrilateral", 2)
    basis = model.basis
    point = np.mean(basis.doflocs, axis=1)
    K, f = _apply_exact_point_coupling(
        csr_matrix((basis.N, basis.N)),
        np.zeros(basis.N),
        basis,
        point,
        2.5,
        20.0,
    )
    assert float(K.sum()) == pytest.approx(2.5, abs=1.0e-12)
    assert float(np.sum(f)) == pytest.approx(50.0, abs=1.0e-12)


@pytest.mark.parametrize("mesh_type", ["triangular", "quadrilateral"])
@pytest.mark.parametrize("element_order", [1, 2])
def test_pressure_and_temperature_share_dofs(mesh_type, element_order):
    model = _model(mesh_type, element_order)
    from ALB.config import ThermalConfig

    thermal = SkfemThermalModelNondim(
        ThermalConfig(args_nodim=True, iter_method="direct")
    )
    mesh_data = thermal.build_mesh(model, _build_film_grid(model))
    assert mesh_data["basis"].N == model.basis.N
    np.testing.assert_allclose(
        mesh_data["basis"].doflocs, model.basis.doflocs, rtol=0.0, atol=1.0e-14
    )


@pytest.mark.parametrize("mesh_type", ["triangular", "quadrilateral"])
@pytest.mark.parametrize("element_order", [1, 2])
def test_explicit_supg_length_uses_macro_grid_and_element_order(
    mesh_type, element_order
):
    model = _model(mesh_type, element_order)
    mesh = _thermal_mesh(model)
    doflocs = _mesh_doflocs(mesh)
    expected = np.sqrt(
        (np.ptp(doflocs[0]) / (model.args["nx"] * element_order)) ** 2
        + (np.ptp(doflocs[1]) / (model.args["nz"] * element_order)) ** 2
    )
    assert _supg_characteristic_length(mesh) == pytest.approx(
        expected, rel=0.0, abs=1.0e-15
    )


def test_q2_supg_length_is_invariant_across_translated_pads():
    config = _base_config().with_overrides(
        {
            "film.mesh_type": "quadrilateral",
            "film.element_order": 2,
            "film.circumferential_elements": 50,
            "film.axial_elements": 25,
        }
    )
    bearing = build_bearing(config)
    lengths = []
    for pad in bearing._runtime._pads:
        model = pad.bearing.main_model
        lengths.append(_supg_characteristic_length(_thermal_mesh(model)))
    expected = np.sqrt((np.deg2rad(80.0) / 100.0) ** 2 + (2.0 / 50.0) ** 2)
    np.testing.assert_allclose(lengths, expected, rtol=0.0, atol=1.0e-15)


def test_mirrored_triangle_mesh_changes_only_the_macro_diagonal():
    x_axis = np.linspace(0.0, 1.0, 4)
    z_axis = np.linspace(-1.0, 1.0, 3)
    default = _explicit_mesh("triangular", x_axis, z_axis, "default")
    mirrored = _explicit_mesh("triangular", x_axis, z_axis, "mirrored")
    np.testing.assert_array_equal(default.p, mirrored.p)
    assert default.nelements == mirrored.nelements
    assert not np.array_equal(default.t, mirrored.t)


@pytest.mark.parametrize("mesh_type", ["triangular", "quadrilateral"])
@pytest.mark.parametrize("element_order", [1, 2])
def test_eighth_order_force_integration_matches_constant_pressure(
    mesh_type, element_order
):
    model = _model(mesh_type, element_order)
    pressure = np.ones(model.basis.N)
    model.add_result(pressure)
    model.update_to_nodes(pressure)
    force = FilmPostProcess(model).calc_capacity_nodim()
    x0, x1 = model.args["x_lim"]
    z0, z1 = model.args["z_lim"]
    expected = np.array(
        [
            (z1 - z0) * (np.cos(x0) - np.cos(x1)),
            -(z1 - z0) * (np.sin(x1) - np.sin(x0)),
        ]
    )
    np.testing.assert_allclose(force, expected, rtol=1.0e-12, atol=1.0e-13)


def test_explicit_mesh_fields_are_paired_and_scope_is_restricted():
    base = _base_config()
    with pytest.raises(ConfigurationError, match="must be provided together"):
        base.with_overrides({"film.mesh_type": "triangular"})
    with pytest.raises(ConfigurationError, match="require spec.film.solver"):
        base.with_overrides(
            {
                "film.mesh_type": "triangular",
                "film.element_order": 1,
                "film.solver": "newton",
            }
        )
    liquid = base.to_dict()["spec"]
    liquid["family"] = "liquid_film"
    for section in ("tank", "valve", "control", "transforms"):
        liquid.pop(section, None)
    liquid["film"]["mesh_type"] = "triangular"
    liquid["film"]["element_order"] = 1
    with pytest.raises(ConfigurationError, match="require family"):
        BearingConfig(liquid)
    no_thermal = base.to_dict()["spec"]
    no_thermal["film"]["mesh_type"] = "triangular"
    no_thermal["film"]["element_order"] = 1
    no_thermal["thermal"] = None
    with pytest.raises(ConfigurationError, match="require steady thermal"):
        BearingConfig(no_thermal)


def test_q2_full_thermal_supply_solve_preserves_cavitation_and_shared_fields():
    config = _base_config().with_overrides(
        {
            "film.mesh_type": "quadrilateral",
            "film.element_order": 2,
            "restrictors.flow_projection": "element_shape",
        }
    )
    bearing = build_bearing(config)
    result = bearing.calculate(
        displacement=(-24.0e-6, -36.0e-6),
        velocity=(0.0, 0.0),
        time=0.0,
        spool=(0.2, 0.2),
    )
    pad_pressure = np.asarray(result.details.values["pad_pressure"], dtype=float)
    snapshots = [pad.result_snapshot() for pad in bearing._runtime._pads]
    pad_temperature = np.vstack(
        [np.asarray(item.values["temperature"], dtype=float) for item in snapshots]
    )

    assert result.convergence.converged
    assert np.min(pad_pressure) >= -1.0e-8
    assert pad_pressure.shape == pad_temperature.shape
    assert np.all(np.isfinite(pad_temperature))
    assert all(item.metadata["converged"] for item in snapshots)
