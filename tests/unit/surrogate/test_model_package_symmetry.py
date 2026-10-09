"""Unit contracts for ALBNN package inference-symmetry resolution."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import ALB

torch = pytest.importorskip("torch")
sklearn = pytest.importorskip("sklearn")
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from ALB.surrogate.inference import (
    ALBNN,
    ALBNN_BASE_INPUT_COLS,
    ALBNN_OUTPUT_COLS,
    ALBNNC4Canonical,
    Net,
    SelectiveMinMaxScaler,
)
from ALB.surrogate.package import (
    _declared_symmetry,
    _fitted_quadrant_i_only,
    create_model_package,
    load_albnn_package,
)


PARAMETERS = {
    "lambda_value": 0.33,
    "beta_nondim": 0.108,
    "lr": 0.75,
    "cq0": 1.35,
    "cq1": 0.208,
    "cq2": 0.0098,
}
M0031_DECLARATION = {
    "name": "c4_canonical_quadrant",
    "canonical_domain": "ex>=0, ey>=0",
    "rotated_input_pairs": [["ex", "ey"], ["vx", "vy"], ["sx", "sy"]],
    "restored_output_cols": ["fx", "fy"],
}


def _fit_frame(ex_min: float) -> pd.DataFrame:
    lo = [ex_min, ex_min, -0.4, -0.4, -0.6, -0.6, 0.006, 0.05, 0.5, 1.0, 0.1, 0.005]
    hi = [0.85, 0.85, 0.4, 0.4, 0.6, 0.6, 1.32, 0.15, 1.0, 1.5, 0.3, 0.015]
    return pd.DataFrame([lo, hi], columns=ALBNN_BASE_INPUT_COLS)


def _package(tmp_path, *, quadrant: bool = True, metadata=None, input_cols=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(7)
    net = Net([12, 8, 2])
    checkpoint = tmp_path / "checkpoint.pt"
    torch.save(
        {
            "architecture": [12, 8, 2],
            "activation": "gelu",
            "model_state_dict": net.state_dict(),
        },
        checkpoint,
    )
    frame = _fit_frame(1.0e-5 if quadrant else -0.85)
    if input_cols is not None:
        frame = frame.assign(sin_theta=[-1.0, 1.0])[input_cols]
    payload = {
        "input_cols": input_cols or ALBNN_BASE_INPUT_COLS,
        "output_cols": ALBNN_OUTPUT_COLS,
        "use_augment": False,
        "feature_set": "default",
        "target_output": "cartesian",
        **(metadata or {}),
    }
    return create_model_package(
        tmp_path / "model",
        checkpoint=checkpoint,
        input_scaler=SelectiveMinMaxScaler().fit(frame),
        output_scaler=SelectiveMinMaxScaler().fit(
            pd.DataFrame([[-3.0, -2.5], [3.5, 2.0]], columns=ALBNN_OUTPUT_COLS)
        ),
        metadata=payload,
    ).root


def _config(root, model_package, **runtime):
    return ALB.BearingConfig(
        {
            "family": "surrogate",
            "unit_system": "nondimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "model_package": {"path": "model", **model_package},
            "runtime": {"parameters": dict(PARAMETERS), **runtime},
        },
        resource_root=root,
    )


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({}, None),
        ({"inference_symmetry": "none"}, "none"),
        ({"inference_symmetry": "c4"}, "c4"),
        ({"inference_symmetry": "c4_canonical_quadrant"}, "c4"),
        ({"inference_symmetry": M0031_DECLARATION}, "c4"),
        ({"inference_symmetry": {"name": "none"}}, "none"),
    ],
)
def test_declared_symmetry_accepts_supported_markers(metadata, expected) -> None:
    assert _declared_symmetry(metadata) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "C4",
        "c2",
        True,
        {"name": "c4", "extra": 1},
        {"name": "none", "canonical_domain": "ex>=0, ey>=0"},
        {**M0031_DECLARATION, "canonical_domain": "ex<=0, ey>=0"},
        {**M0031_DECLARATION, "rotated_input_pairs": [["ex", "ey"]]},
        {"canonical_domain": "ex>=0, ey>=0"},
    ],
)
def test_declared_symmetry_rejects_malformed_markers(value) -> None:
    with pytest.raises(ValueError, match="inference_symmetry"):
        _declared_symmetry({"inference_symmetry": value})


def test_create_model_package_rejects_malformed_declaration(tmp_path) -> None:
    with pytest.raises(ValueError, match="inference_symmetry"):
        _package(tmp_path, metadata={"inference_symmetry": "c8"})
    assert not (tmp_path / "model").exists()


def test_fitted_domain_detection_uses_recorded_minima() -> None:
    assert _fitted_quadrant_i_only(SelectiveMinMaxScaler().fit(_fit_frame(0.0)))
    assert not _fitted_quadrant_i_only(SelectiveMinMaxScaler().fit(_fit_frame(-0.1)))
    assert _fitted_quadrant_i_only(MinMaxScaler().fit(_fit_frame(1.0e-5)))
    assert not _fitted_quadrant_i_only(MinMaxScaler().fit(_fit_frame(-0.85)))
    # Without per-column minima the domain is unknown, not quadrant-limited.
    assert not _fitted_quadrant_i_only(StandardScaler().fit(_fit_frame(1.0e-5)))
    passthrough = SelectiveMinMaxScaler(pass_through_columns=("ex", "ey"))
    assert not _fitted_quadrant_i_only(passthrough.fit(_fit_frame(1.0e-5)))


def test_loader_default_returns_bare_network_unchanged(tmp_path) -> None:
    root = _package(tmp_path)
    model = load_albnn_package(root, runtime_parameters=PARAMETERS)
    assert type(model) is ALBNN
    wrapped = load_albnn_package(root, runtime_parameters=PARAMETERS, symmetry="c4")
    assert isinstance(wrapped, ALBNNC4Canonical)
    with pytest.raises(ValueError, match="fitted only on ex >= 0"):
        load_albnn_package(root, symmetry="package")
    with pytest.raises(ValueError, match="symmetry must be one of"):
        load_albnn_package(root, symmetry="auto")


def test_package_mode_follows_declaration_and_full_plane_default(tmp_path) -> None:
    declared = _package(
        tmp_path / "declared", metadata={"inference_symmetry": M0031_DECLARATION}
    )
    assert isinstance(
        load_albnn_package(declared, symmetry="package"), ALBNNC4Canonical
    )
    # Explicit modes override the declaration, mirroring use_augment.
    assert type(load_albnn_package(declared, symmetry="none")) is ALBNN
    full = _package(tmp_path / "full", quadrant=False)
    assert type(load_albnn_package(full, symmetry="package")) is ALBNN


def test_c4_rejects_rotation_dependent_input_columns(tmp_path) -> None:
    columns = [*ALBNN_BASE_INPUT_COLS, "sin_theta"]
    root = _package(tmp_path, input_cols=columns)
    with pytest.raises(ValueError, match="sin_theta"):
        load_albnn_package(root, symmetry="c4")
    assert type(load_albnn_package(root, symmetry="none")) is ALBNN


@pytest.mark.parametrize("value", ["C4", "auto", "package", 4, True])
def test_config_rejects_unknown_symmetry(tmp_path, value) -> None:
    with pytest.raises(ALB.ConfigurationError, match="symmetry"):
        _config(tmp_path, {"symmetry": value})


def test_declared_package_builds_c4_without_config_field(tmp_path) -> None:
    root = _package(tmp_path, metadata={"inference_symmetry": "c4"})
    bearing = ALB.build_bearing(_config(root.parent, {}, spool=(0.2, -0.1)))
    reference = ALBNNC4Canonical(
        load_albnn_package(root, runtime_parameters=PARAMETERS)
    )
    reference.input((-0.3, -0.2), (0.05, 0.02), (0.2, -0.1))
    result = bearing.calculate(
        displacement=(-0.3, -0.2), velocity=(0.05, 0.02), time=0.0
    )
    np.testing.assert_array_equal(result.force, reference.output().reshape(-1))


def test_fixed_spool_is_rotated_with_c4(tmp_path) -> None:
    root = _package(tmp_path)
    bearing = ALB.build_bearing(
        _config(root.parent, {"symmetry": "c4"}, spool=(0.25, -0.4))
    )
    reference = ALBNNC4Canonical(
        load_albnn_package(root, runtime_parameters=PARAMETERS)
    )
    for e, v in (((0.1, -0.5), (0.0, 0.0)), ((-0.2, 0.3), (0.03, -0.04))):
        bearing.reset()
        reference.input(e, v, (0.25, -0.4))
        result = bearing.calculate(displacement=e, velocity=v, time=0.0)
        np.testing.assert_array_equal(result.force, reference.output().reshape(-1))


def test_c4_bearing_is_exactly_quarter_turn_equivariant(tmp_path) -> None:
    root = _package(tmp_path)
    bearing = ALB.build_bearing(
        _config(root.parent, {"symmetry": "c4"}, spool_mode="external")
    )
    turn = np.array([[0.0, -1.0], [1.0, 0.0]])
    e = np.array([0.3, 0.2])
    v = np.array([0.05, -0.08])
    s = np.array([0.2, 0.1])
    bearing.reset()
    base = bearing.calculate(displacement=e, velocity=v, time=0.0, spool=s).force
    for k in range(1, 4):
        rot = np.linalg.matrix_power(turn, k)
        bearing.reset()
        force = bearing.calculate(
            displacement=rot @ e, velocity=rot @ v, time=0.0, spool=rot @ s
        ).force
        np.testing.assert_array_equal(force, rot @ base)
