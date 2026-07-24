"""Pickle-free ALBNN 0.4 package tests."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import ALB

torch = pytest.importorskip("torch")
sklearn = pytest.importorskip("sklearn")
from sklearn.preprocessing import StandardScaler

from ALB.surrogate.inference import (
    ALBNN_BASE_INPUT_COLS,
    ALBNN_OUTPUT_COLS,
    Net,
)
from ALB.surrogate.package import (
    MODEL_PACKAGE_SCHEMA,
    create_model_package,
    load_albnn_package,
    open_model_package,
)
from ALB.surrogate.scaler_io import load_scaler, write_scaler


def test_npz_scaler_round_trip_is_exact(tmp_path) -> None:
    frame = pd.DataFrame(
        np.arange(36, dtype=float).reshape(3, 12),
        columns=ALBNN_BASE_INPUT_COLS,
    )
    scaler = StandardScaler().fit(frame)
    path = write_scaler(scaler, tmp_path / "scaler.npz")

    restored = load_scaler(path)

    np.testing.assert_array_equal(
        restored.transform(frame),
        scaler.transform(frame),
    )
    assert list(restored.feature_names_in_) == ALBNN_BASE_INPUT_COLS


def test_package_rejects_v02_and_loads_v04_without_pickle(tmp_path) -> None:
    input_frame = pd.DataFrame(
        np.arange(36, dtype=float).reshape(3, 12),
        columns=ALBNN_BASE_INPUT_COLS,
    )
    output_frame = pd.DataFrame(
        np.arange(6, dtype=float).reshape(3, 2),
        columns=ALBNN_OUTPUT_COLS,
    )
    scaler_x = StandardScaler().fit(input_frame)
    scaler_y = StandardScaler().fit(output_frame)
    net = Net([12, 4, 2])
    checkpoint = tmp_path / "checkpoint.pt"
    torch.save(
        {
            "architecture": [12, 4, 2],
            "activation": "gelu",
            "model_state_dict": net.state_dict(),
        },
        checkpoint,
    )
    package_dir = tmp_path / "package"
    package = create_model_package(
        package_dir,
        checkpoint=checkpoint,
        input_scaler=scaler_x,
        output_scaler=scaler_y,
        metadata={
            "input_cols": ALBNN_BASE_INPUT_COLS,
            "output_cols": ALBNN_OUTPUT_COLS,
            "use_augment": False,
            "feature_set": "default",
            "target_output": "cartesian",
        },
    )

    assert package.manifest["schema"] == MODEL_PACKAGE_SCHEMA
    assert not list(package_dir.glob("*.pkl"))
    loaded = load_albnn_package(
        package_dir,
        runtime_parameters={
            "lambda_value": 1.0,
            "beta_nondim": 0.03,
            "lr": 1.0,
            "cq0": 5.0,
            "cq1": 0.02,
            "cq2": 0.002,
        },
    )
    loaded.input((0.1, 0.2), (0.0, 0.0), (0.0, 0.0))
    assert loaded.output().shape == (1, 2)

    manifest_path = package_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema"] = "alb.surrogate-package.v0.2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        open_model_package(package_dir)


def test_surrogate_family_uses_friendly_facade_and_explicit_spool(tmp_path) -> None:
    input_frame = pd.DataFrame(
        np.arange(36, dtype=float).reshape(3, 12),
        columns=ALBNN_BASE_INPUT_COLS,
    )
    output_frame = pd.DataFrame(
        np.arange(6, dtype=float).reshape(3, 2),
        columns=ALBNN_OUTPUT_COLS,
    )
    net = Net([12, 2])
    checkpoint = tmp_path / "checkpoint.pt"
    torch.save(
        {
            "architecture": [12, 2],
            "activation": "gelu",
            "model_state_dict": net.state_dict(),
        },
        checkpoint,
    )
    package_dir = tmp_path / "model"
    create_model_package(
        package_dir,
        checkpoint=checkpoint,
        input_scaler=StandardScaler().fit(input_frame),
        output_scaler=StandardScaler().fit(output_frame),
        metadata={
            "input_cols": ALBNN_BASE_INPUT_COLS,
            "output_cols": ALBNN_OUTPUT_COLS,
            "use_augment": False,
            "feature_set": "default",
            "target_output": "cartesian",
        },
    )
    config = ALB.BearingConfig(
        {
            "family": "surrogate",
            "unit_system": "nondimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "model_package": {"path": "model", "use_augment": False},
            "runtime": {
                "spool_mode": "external",
                "parameters": {
                    "lambda_value": 1.0,
                    "beta_nondim": 0.03,
                    "lr": 1.0,
                    "cq0": 5.0,
                    "cq1": 0.02,
                    "cq2": 0.002,
                },
            },
        },
        resource_root=tmp_path,
    )
    bearing = ALB.build_bearing(config)

    with pytest.raises(ValueError, match="requires spool"):
        bearing.calculate(displacement=(0.1, 0.2), time=0.0)
    result = bearing.calculate(
        displacement=(0.1, 0.2),
        time=0.0,
        spool=(0.3, -0.2),
    )
    assert result.force.shape == (2,)
