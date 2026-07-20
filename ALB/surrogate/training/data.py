# coding: utf-8
"""Data-loading helpers shared by ALB surrogate trainers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


def valid_mask(frame: pd.DataFrame) -> pd.Series:
    """Return the boolean row mask used for valid ALBNN force labels."""
    if "valid" not in frame.columns:
        return pd.Series(True, index=frame.index)
    valid = frame["valid"]
    if pd.api.types.is_bool_dtype(valid):
        return valid.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(valid):
        return valid.fillna(0).astype(float) != 0.0
    return valid.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def load_frame(
    path: str,
    *,
    input_cols: list[str],
    target_cols: list[str],
    valid_only: bool = True,
) -> pd.DataFrame:
    """Read a CSV and enforce the configured input/target columns."""
    frame = pd.read_csv(path)
    missing = [col for col in input_cols + target_cols if col not in frame.columns]
    if missing:
        raise ValueError(f"Training CSV is missing columns: {missing}")
    finite = _finite_mask(frame, input_cols + target_cols)
    frame = frame[finite].copy()
    if valid_only:
        frame = frame[valid_mask(frame)].copy()
    if frame.empty:
        raise ValueError(f"No usable rows found in {path}")
    return frame.reset_index(drop=True)


def _finite_mask(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Return rows with finite numeric values in every configured data column."""
    values = frame[columns].apply(pd.to_numeric, errors="coerce")
    not_null = values.notna().all(axis=1)
    finite = pd.Series(
        np.isfinite(values.to_numpy(dtype=float)).all(axis=1),
        index=frame.index,
    )
    return not_null & finite


def train_validation_frames(
    train_csv: str,
    validation_csv: str | None,
    *,
    input_cols: list[str],
    target_cols: list[str],
    valid_only: bool,
    test_size: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load train/validation frames or split a single train CSV."""
    train = load_frame(
        train_csv,
        input_cols=input_cols,
        target_cols=target_cols,
        valid_only=valid_only,
    )
    if validation_csv:
        validation = load_frame(
            validation_csv,
            input_cols=input_cols,
            target_cols=target_cols,
            valid_only=valid_only,
        )
        return train, validation
    train_part, validation_part = train_test_split(
        train,
        test_size=float(test_size),
        random_state=int(seed),
        shuffle=True,
    )
    return train_part.reset_index(drop=True), validation_part.reset_index(drop=True)
