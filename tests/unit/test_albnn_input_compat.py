from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from ALB.surrogate.inference import (
    ALBNN,
    ALBNNC4Canonical,
    ALBNN_BASE_INPUT_COLS,
    Cq2SigLogMinMaxScaler,
    albnn_augment_frame,
    albnn,
    c4_canonicalize_albnn_frame,
    c4_restore_albnn_force,
)


class IdentityScaler:
    def __init__(self, columns):
        self.feature_names_in_ = np.asarray(columns, dtype=object)

    def transform(self, frame):
        return frame[list(self.feature_names_in_)].to_numpy(dtype=np.float32)

    def inverse_transform(self, frame):
        return np.asarray(frame, dtype=float)


class ZeroNet:
    def eval(self):
        return None

    def __call__(self, x):
        return torch.zeros((x.shape[0], 2), dtype=torch.float32)


class FirstTwoColumnsNet:
    def eval(self):
        return None

    def __call__(self, x):
        return x[:, :2]


def _rotate_canonical_pair_to_external(x, y, steps):
    values = c4_restore_albnn_force(np.column_stack([x, y]), steps)
    return values[:, 0], values[:, 1]


def test_aug_v2_allows_subset_input_columns():
    frame = pd.DataFrame(
        {
            "ex": [0.1],
            "ey": [0.2],
            "lambda_value": [1.5],
            "lr": [0.5],
        }
    )

    augmented = albnn_augment_frame(frame, feature_set="aug_v2")

    assert "e_norm" in augmented
    assert "lambda_over_lr" in augmented
    assert "cq0_over_lr" not in augmented


def test_sqrt28_feature_set_has_fixed_thermal_input_contract():
    frame = pd.DataFrame(
        {
            col: [value]
            for col, value in zip(
                ALBNN_BASE_INPUT_COLS,
                [
                    0.1,
                    -0.2,
                    0.03,
                    -0.04,
                    0.5,
                    -0.6,
                    1.5,
                    0.03,
                    0.7,
                    5.0,
                    0.02,
                    0.003,
                ],
            )
        }
    )

    augmented = albnn_augment_frame(frame, feature_set="sqrt28")

    assert augmented.shape[1] == 28
    assert (
        list(augmented.columns[: len(ALBNN_BASE_INPUT_COLS)])
        == ALBNN_BASE_INPUT_COLS
    )
    assert "sqrt_abs_ex" in augmented
    assert "sqrt_abs_cq2" in augmented
    assert "e_norm" in augmented
    assert "v_norm" in augmented
    assert "s_norm" in augmented
    assert "sqrt_lambda_over_lr" in augmented


def test_albnn_input_fills_changed_inputs_from_config_and_extra_inputs():
    input_cols = ALBNN_BASE_INPUT_COLS + ["gamma", "delta"]
    config = SimpleNamespace(
        c=1.0,
        freq=1.0,
        vf=1.0,
        ps=1.0,
        l=1.0,
        r=1.0,
        lambda_value=1.2,
        beta_nondim=0.03,
        lr=1.0,
        cq0=5.0,
        cq1=0.02,
        cq2=0.002,
        gamma=2.5,
        extra_inputs={"delta": 4.0},
    )
    net = ALBNN(
        ZeroNet(),
        IdentityScaler(input_cols),
        IdentityScaler(["fx", "fy"]),
        config=config,
        input_cols=input_cols,
        use_augment=False,
    )

    net.input([0.1, 0.2], [0.0, 0.0], [0.3, 0.4], nodim=True)
    output = net.output(nodim=True)

    assert output.shape == (1, 2)


def test_albnn_c4_wrapper_matches_manual_rotation_for_vector_pairs():
    frame = pd.DataFrame(
        {
            "ex": [0.2, -0.2, -0.2, 0.2],
            "ey": [0.3, 0.3, -0.3, -0.3],
            "vx": [0.1, -0.4, 0.4, -0.1],
            "vy": [0.4, 0.1, -0.1, -0.4],
            "sx": [0.5, -0.6, 0.6, -0.5],
            "sy": [0.6, 0.5, -0.5, -0.6],
            "lambda_value": [1.5] * 4,
            "beta_nondim": [0.03] * 4,
            "lr": [0.7] * 4,
            "cq0": [5.0] * 4,
            "cq1": [0.02] * 4,
            "cq2": [0.003] * 4,
        }
    )
    base = ALBNN(
        FirstTwoColumnsNet(),
        IdentityScaler(ALBNN_BASE_INPUT_COLS),
        IdentityScaler(["fx", "fy"]),
        input_cols=ALBNN_BASE_INPUT_COLS,
        use_augment=False,
    )
    wrapped = ALBNNC4Canonical(base)

    canonical, steps = c4_canonicalize_albnn_frame(frame)
    manual = c4_restore_albnn_force(base.predict_nondim(canonical), steps)
    actual = wrapped.predict_nondim(frame)

    np.testing.assert_allclose(actual, manual, rtol=0.0, atol=1e-12)
    assert (canonical["ex"] >= 0.0).all()
    assert (canonical["ey"] >= 0.0).all()


def test_m0031_c4_wrapper_matches_manual_rotation_on_ten_validation_samples():
    project_root = Path(__file__).resolve().parents[2]
    model_dir = (
        project_root
        / "SURROGATE_TRAIN"
        / "models"
        / "M0031_s8b_s0011_allvalid_base12_mlp_minmax01_gelu_adamw_p1000_20260609"
    )
    validation_csv = (
        project_root
        / "SURROGATE_TRAIN"
        / "data"
        / "albnn_master_dataset_20260521"
        / "filtered"
        / "s8b_s0011_valid171984_train137587_valid34397_20260609"
        / "validation_s8b_s0011_allvalid_base12_20260609.csv"
    )
    required = [
        model_dir / "best_albnn.pth",
        model_dir / "scaler_X.pkl",
        model_dir / "scaler_y.pkl",
        model_dir / "metadata.json",
        validation_csv,
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        pytest.skip(f"M0031 C4 integration artifacts are not available: {missing}")

    config = SimpleNamespace(
        model=str(model_dir / "best_albnn.pth"),
        scaler_X=str(model_dir / "scaler_X.pkl"),
        scaler_y=str(model_dir / "scaler_y.pkl"),
        metadata=str(model_dir / "metadata.json"),
    )
    base_config = SimpleNamespace(**vars(config), inference_symmetry="none")
    wrapped_model = albnn(config)
    base_model = albnn(base_config)

    validation = pd.read_csv(validation_csv, usecols=ALBNN_BASE_INPUT_COLS)
    canonical = validation.sample(n=10, random_state=20260609).reset_index(drop=True)
    external_parts = []
    step_parts = []
    for step in range(4):
        steps = np.full(len(canonical), step, dtype=np.int64)
        external = canonical.copy()
        for x_col, y_col in (("ex", "ey"), ("vx", "vy"), ("sx", "sy")):
            external[x_col], external[y_col] = _rotate_canonical_pair_to_external(
                canonical[x_col].to_numpy(dtype=float),
                canonical[y_col].to_numpy(dtype=float),
                steps,
            )
        external_parts.append(external)
        step_parts.append(steps)
    external_frame = pd.concat(external_parts, ignore_index=True)
    steps = np.concatenate(step_parts)

    canonical_repeat = pd.concat([canonical] * 4, ignore_index=True)
    manual = c4_restore_albnn_force(base_model.predict_nondim(canonical_repeat), steps)
    actual = wrapped_model.predict_nondim(external_frame)

    np.testing.assert_allclose(actual, manual, rtol=0.0, atol=1e-6)


def test_cq2_sig_log_minmax01_maps_inputs_to_unit_range():
    frame = pd.DataFrame(
        {
            "ex": [-0.5, 0.5],
            "ey": [-0.25, 0.25],
            "vx": [-0.1, 0.1],
            "vy": [-0.2, 0.2],
            "sx": [-0.3, 0.3],
            "sy": [-0.4, 0.4],
            "lambda_value": [0.1, 5.0],
            "beta_nondim": [0.0, 0.12],
            "lr": [0.3, 10.0],
            "cq0": [0.5, 51.0],
            "cq1": [2e-5, 0.8],
            "cq2": [2e-4, 2.2e-2],
        }
    )

    scaler = Cq2SigLogMinMaxScaler(feature_range=(0.0, 1.0))
    scaled = scaler.fit_transform(frame)
    recovered = scaler.inverse_transform(scaled)

    assert np.nanmin(scaled) >= 0.0
    assert np.nanmax(scaled) <= 1.0
    assert scaled[:, list(frame.columns).index("cq2")].tolist() == [0.0, 1.0]
    np.testing.assert_allclose(recovered, frame.to_numpy(dtype=float), rtol=1e-12)
