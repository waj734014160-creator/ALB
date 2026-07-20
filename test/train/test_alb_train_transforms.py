# coding: utf-8
"""Focused contract tests for surrogate transform pipelines and scalers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import torch

from ALB.surrogate.scalers import SelectiveMinMaxScaler
from ALB.surrogate.training.transforms import (
    ColumnTransformError,
    ColumnTransformPipeline,
)


def _evs_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ex": [0.1, -0.2],
            "ey": [0.2, 0.3],
            "vx": [0.4, -0.1],
            "vy": [-0.2, 0.5],
            "sx": [0.7, -0.4],
            "sy": [0.6, 0.2],
        }
    )


def test_derived_source_must_reference_prior_fitted_step():
    frame = _evs_frame()

    with pytest.raises(ColumnTransformError, match="source 'base_minmax'.*not been fitted"):
        ColumnTransformPipeline(
            [{"name": "scaled_evs", "transform": "scaled_evs", "source": "base_minmax"}]
        ).fit(frame)

    pipeline = ColumnTransformPipeline(
        [
            {"name": "base_minmax", "transform": "minmax", "columns": "all"},
            {"name": "scaled_evs", "transform": "scaled_evs", "source": "base_minmax"},
        ]
    )

    transformed = pipeline.fit_transform(frame)

    assert transformed.shape == (len(frame), len(frame.columns) + 4)
    assert list(pipeline.feature_names_out_)[-4:] == [
        "evs_geom",
        "edotv",
        "edots",
        "sdotv",
    ]


def test_selective_minmax_inverse_restores_constant_columns():
    frame = pd.DataFrame(
        {
            "constant": [3.0, 3.0, 3.0],
            "varying": [1.0, 2.0, 5.0],
            "pass": [-4.0, -5.0, -6.0],
        }
    )
    scaler = SelectiveMinMaxScaler(
        feature_range=(-1.0, 1.0),
        pass_through_columns=("pass",),
    )
    scaled = scaler.fit_transform(frame)
    constant_idx = list(scaler.feature_names_in_).index("constant")
    scaled[:, constant_idx] = np.asarray([-1.0, 0.0, 1.0])

    recovered = scaler.inverse_transform(scaled)
    recovered_torch = scaler.inverse_transform_torch(torch.tensor(scaled)).numpy()

    np.testing.assert_allclose(recovered[:, constant_idx], 3.0, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(recovered_torch[:, constant_idx], 3.0, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(recovered[:, -1], frame["pass"].to_numpy(), rtol=0.0, atol=0.0)
