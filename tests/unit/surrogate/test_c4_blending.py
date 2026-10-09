"""Continuity, rotation, and compatibility contracts for C4 blending."""

import numpy as np
import pandas as pd
import pytest

from ALB.surrogate.features import C4_DEFAULT_BLEND_RATIO
from ALB.surrogate.inference import (
    ALBNNC4Canonical,
    ALBNN_C4_VECTOR_PAIRS,
    _c4_rotate_pair_to_canonical,
    c4_canonicalize_albnn_frame,
    c4_restore_albnn_force,
)


class AsymmetricModel:
    """Double-precision non-equivariant model with observable batch calls."""

    def __init__(self):
        self.calls = []

    def _base_frame(self, x):
        return x.copy()

    def predict_nondim(self, frame):
        self.calls.append(frame.copy())
        ex, ey, vx, vy, sx, sy, scalar = frame.to_numpy().T
        return np.column_stack((
            2.0 + ex**2 + 0.3 * ey + vx - 0.5 * sy + scalar,
            -1.0 + ey**2 - 0.2 * ex + vy + 0.7 * sx - scalar,
        ))

    def transform_inputs(self, frame):
        return frame.to_numpy()


def query(angles):
    angles = np.asarray(angles)
    return pd.DataFrame({
        "ex": 0.5 * np.cos(angles), "ey": 0.5 * np.sin(angles),
        "vx": 0.03, "vy": -0.07, "sx": 0.2, "sy": -0.1, "scalar": 0.4,
    }, index=np.arange(len(angles)) // 2)


def explicit_force(base, frame, steps):
    rotated = frame.copy()
    for x_col, y_col in ALBNN_C4_VECTOR_PAIRS:
        rotated[x_col], rotated[y_col] = _c4_rotate_pair_to_canonical(
            frame[x_col], frame[y_col], steps
        )
    return c4_restore_albnn_force(base.predict_nondim(rotated), steps)


@pytest.mark.parametrize("axis", range(4))
def test_default_blend_is_continuous_across_each_half_axis(axis):
    frame = query(axis * np.pi / 2 + np.array([-1e-12, 1e-12]))
    blended = ALBNNC4Canonical(AsymmetricModel()).predict_nondim(frame)
    plain = ALBNNC4Canonical(AsymmetricModel(), blend_ratio=0).predict_nondim(frame)
    assert np.linalg.norm(blended[1] - blended[0]) / np.linalg.norm(blended[0]) < 1e-9
    assert np.linalg.norm(plain[1] - plain[0]) / np.linalg.norm(plain[0]) > 0.1


def test_outside_band_is_bit_identical_and_only_band_rows_evaluate_twice():
    angles = np.deg2rad([0, 5, 20, 45, 70, 90, 130, 170, 200, 250, 300, 350])
    frame = query(angles)
    base = AsymmetricModel()
    wrapped = ALBNNC4Canonical(base)
    actual = wrapped.predict_nondim(frame)
    plain = ALBNNC4Canonical(AsymmetricModel(), blend_ratio=0).predict_nondim(frame)
    phi = (angles + np.pi / 4) % (np.pi / 2) - np.pi / 4
    outside = np.abs(phi) >= C4_DEFAULT_BLEND_RATIO * (np.pi / 2)
    np.testing.assert_array_equal(actual[outside], plain[outside])
    assert [len(call) for call in base.calls] == [len(frame), np.count_nonzero(~outside)]
    canonical, _ = c4_canonicalize_albnn_frame(frame)
    np.testing.assert_array_equal(wrapped.transform_inputs(frame), canonical.to_numpy())
    base.calls.clear()
    wrapped.predict_nondim(frame.iloc[np.flatnonzero(outside)])
    assert len(base.calls) == 1


@pytest.mark.parametrize("turn", [1, 2, 3])
def test_blending_is_quarter_turn_equivariant(turn):
    frame = query(np.deg2rad([-8, 0, 7, 40, 82, 90, 98, 180, 188, 265, 270, 277]))
    rotated = frame.copy()
    for x_col, y_col in ALBNN_C4_VECTOR_PAIRS:
        rotated[x_col], rotated[y_col] = _c4_rotate_pair_to_canonical(
            frame[x_col], frame[y_col], np.full(len(frame), (4 - turn) % 4)
        )
    model = ALBNNC4Canonical(AsymmetricModel())
    expected = c4_restore_albnn_force(model.predict_nondim(frame), np.full(len(frame), turn))
    np.testing.assert_allclose(model.predict_nondim(rotated), expected, rtol=1e-12, atol=1e-12)


def test_zero_blend_reproduces_historical_path_bit_for_bit():
    frame = query(np.linspace(0, 2 * np.pi, 81))
    frame.loc[frame.index == 0, ["ex", "ey"]] = 0.0
    base = AsymmetricModel()
    canonical, steps = c4_canonicalize_albnn_frame(frame)
    expected = c4_restore_albnn_force(base.predict_nondim(canonical), steps)
    base.calls.clear()
    np.testing.assert_array_equal(ALBNNC4Canonical(base, blend_ratio=0).predict_nondim(frame), expected)
    assert len(base.calls) == 1


def test_blend_matches_explicit_quintic_rule_including_zero_eccentricity():
    frame = query(np.deg2rad([-13, -3, 0, 6, 13, 86, 94, 175, 185, 268, 272]))
    frame.iloc[2, :2] = 0.0
    theta = np.mod(np.arctan2(frame["ey"], frame["ex"]), 2 * np.pi).to_numpy()
    right = np.rint(theta / (np.pi / 2)).astype(int) % 4
    left = (right - 1) % 4
    phi = (theta - right * np.pi / 2 + np.pi) % (2 * np.pi) - np.pi
    delta = C4_DEFAULT_BLEND_RATIO * (np.pi / 2)
    t = (phi + delta) / (2 * delta)
    sigma = (t**3 * (10 - 15 * t + 6 * t**2))[:, None]
    base = AsymmetricModel()
    expected = (1 - sigma) * explicit_force(base, frame, left) + sigma * explicit_force(base, frame, right)
    np.testing.assert_array_equal(ALBNNC4Canonical(base).predict_nondim(frame), expected)


@pytest.mark.parametrize("value", [-0.01, 0.5, 1.0, np.nan, np.inf, -np.inf, True, "0.15", None])
def test_invalid_blend_width_is_rejected(value):
    with pytest.raises(ValueError, match="blend_ratio"):
        ALBNNC4Canonical(AsymmetricModel(), blend_ratio=value)
