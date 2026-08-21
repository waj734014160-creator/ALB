"""Finite-element and nearest-node supply-flow projection tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from ALB.api import BearingConfig, build_bearing
from ALB.config import ThermalConfig
from ALB.physics.hydraulics.orifice import (
    FilmPointAttachment,
    _attachment_matrix,
    _get_node,
    _map_normalized_position,
)
from ALB.physics.thermal.solver import (
    SkfemThermalModelNondim,
    _build_film_grid,
)


ROOT = Path(__file__).resolve().parents[3]
LEGACY_REFERENCE = ROOT / "refs" / "mesh_independence_legacy_reference_v1.json"


def _base_config() -> BearingConfig:
    metadata = json.loads(LEGACY_REFERENCE.read_text(encoding="utf-8"))
    return BearingConfig(deepcopy(metadata["derived_spec"]))


def _model(mesh_type: str | None = None, element_order: int | None = None):
    config = _base_config()
    if mesh_type is not None:
        config = config.with_overrides(
            {
                "film.mesh_type": mesh_type,
                "film.element_order": element_order,
            }
        )
    return build_bearing(config)._runtime._pads[0].bearing.main_model


@pytest.mark.parametrize(
    ("mesh_type", "element_order", "local_dofs"),
    [
        ("triangular", 1, 3),
        ("triangular", 2, 6),
        ("quadrilateral", 1, 4),
        ("quadrilateral", 2, 9),
    ],
)
def test_explicit_projection_uses_native_element_dofs(
    mesh_type, element_order, local_dofs
) -> None:
    model = _model(mesh_type, element_order)
    point = _map_normalized_position(model, (0.371, 0.417))
    attachment = FilmPointAttachment(model, point)

    assert len(attachment.indices) == local_dofs
    assert np.sum(attachment.weights) == pytest.approx(1.0, abs=1.0e-13)


def test_native_q1_projection_is_nonnegative_and_bilinear_exact() -> None:
    model = _model()
    point = _map_normalized_position(model, (0.371, 0.417))
    attachment = FilmPointAttachment(model, point)
    coords = np.asarray(
        [model.node_manager.nodes[index].coords for index in range(model.basis.N)],
        dtype=float,
    )
    values = 1.0 + 2.0 * coords[:, 0] - 3.0 * coords[:, 1]
    values += 0.75 * coords[:, 0] * coords[:, 1]
    model.add_result(values)
    model.update_to_nodes(values)
    expected = 1.0 + 2.0 * point[0] - 3.0 * point[1]
    expected += 0.75 * point[0] * point[1]

    assert len(attachment.indices) == 4
    assert np.min(attachment.weights) >= -1.0e-14
    assert np.sum(attachment.weights) == pytest.approx(1.0, abs=1.0e-13)
    assert attachment.p == pytest.approx(expected, abs=1.0e-12)


def test_projected_rhs_conserves_flow_and_jacobian_matches_finite_difference() -> None:
    model = _model("quadrilateral", 1)
    attachments = [
        _get_node(model, position, "element_shape")
        for position in ((0.37, 0.31), (0.43, 0.52), (0.58, 0.69))
    ]
    projection = _attachment_matrix(attachments, model.node_manager.freedoms)
    pressure = np.linspace(0.05, 0.85, model.node_manager.freedoms)
    flow_offset = np.array([0.7, 0.8, 0.9])
    flow_jacobian = np.array(
        [[-0.4, 0.1, 0.02], [0.05, -0.3, 0.04], [0.01, 0.03, -0.2]]
    )

    def projected_rhs(values):
        point_pressure = np.asarray(projection @ values).reshape(-1)
        flow = flow_offset + flow_jacobian @ point_pressure
        return np.asarray(projection.T @ flow).reshape(-1), flow

    rhs, flow = projected_rhs(pressure)
    analytic = (projection.T @ csr_matrix(flow_jacobian) @ projection).toarray()
    finite_difference = np.empty_like(analytic)
    step = 1.0e-7
    for column in range(pressure.size):
        plus = pressure.copy()
        minus = pressure.copy()
        plus[column] += step
        minus[column] -= step
        finite_difference[:, column] = (
            projected_rhs(plus)[0] - projected_rhs(minus)[0]
        ) / (2.0 * step)

    assert np.sum(rhs) == pytest.approx(np.sum(flow), abs=1.0e-13)
    np.testing.assert_allclose(
        analytic, finite_difference, rtol=5.0e-7, atol=5.0e-10
    )


def test_element_projection_moves_continuously_while_nearest_node_steps() -> None:
    model = _model("quadrilateral", 1)
    left = (0.35 - 1.0e-6, 0.5)
    right = (0.35 + 1.0e-6, 0.5)
    shape_nodes = [
        _get_node(model, position, "element_shape") for position in (left, right)
    ]
    shape_weights = _attachment_matrix(
        shape_nodes, model.node_manager.freedoms
    ).toarray()
    nearest_nodes = [
        _get_node(model, position, "nearest_node") for position in (left, right)
    ]

    assert np.linalg.norm(shape_weights[1] - shape_weights[0], ord=1) < 1.0e-3
    assert nearest_nodes[0].number != nearest_nodes[1].number


def test_projection_rejects_nonfinite_and_outside_points() -> None:
    model = _model("quadrilateral", 1)
    with pytest.raises(ValueError, match="finite"):
        FilmPointAttachment(model, (np.nan, 0.0))
    with pytest.raises(ValueError, match="outside"):
        FilmPointAttachment(model, (1.0e6, 1.0e6))


@pytest.mark.parametrize("projection", ["nearest_node", "element_shape"])
def test_thermal_source_follows_projection_and_conserves_enthalpy(projection) -> None:
    model = _model("quadrilateral", 2)
    thermal = SkfemThermalModelNondim(
        ThermalConfig(args_nodim=True, iter_method="direct")
    )
    mesh_data = thermal.build_mesh(model, _build_film_grid(model))
    basis = mesh_data["basis"]
    point = _map_normalized_position(model, (0.371, 0.417))
    K, f = SkfemThermalModelNondim._apply_nondim_orifice_sources(
        csr_matrix((basis.N, basis.N)),
        np.zeros(basis.N),
        mesh_data["mesh"],
        20.0,
        [(point[0], point[1], 2.5, projection)],
    )

    assert float(K.sum()) == pytest.approx(2.5, abs=1.0e-12)
    assert float(np.sum(f)) == pytest.approx(50.0, abs=1.0e-12)
    if projection == "nearest_node":
        assert np.count_nonzero(K.diagonal()) == 1
        assert np.count_nonzero(f) == 1
    else:
        assert np.count_nonzero(f) == 9
