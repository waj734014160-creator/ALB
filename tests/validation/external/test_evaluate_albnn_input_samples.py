# coding: utf-8
"""Regression tests for prepared ALBNN input evaluation helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[3]
EVALUATOR = (
    ROOT.parent
    / "SURROGATE_TRAIN"
    / "run"
    / "train"
    / "evaluate_albnn_input_samples.py"
)


def load_evaluator():
    spec = importlib.util.spec_from_file_location("evaluate_albnn_input_samples", EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def input_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "input_sample_id": [10, 11],
            "sample_group": ["lhs", "lhs"],
            "ex": [0.1, 0.2],
            "ey": [0.0, 0.1],
            "vx": [0.3, 0.4],
            "vy": [0.5, 0.6],
            "sx": [0.7, 0.8],
            "sy": [0.2, 0.3],
            "lambda_value": [1.2, 1.3],
            "beta_nondim": [0.1, 0.1],
            "lr": [0.75, 0.75],
            "cq0": [4.5, 4.5],
            "cq1": [0.04, 0.04],
            "cq2": [0.003, 0.003],
        }
    )


def test_resume_output_must_match_input_prefix():
    evaluator = load_evaluator()
    inputs = input_rows()
    matching = inputs.iloc[:1].copy()
    matching["fx"] = 1.0
    matching["fy"] = 2.0

    evaluator._validate_resume_output(matching, inputs, list(evaluator.INPUT_COLS))

    stale = matching.copy()
    stale.loc[0, "input_sample_id"] = 99
    with pytest.raises(ValueError, match="does not match"):
        evaluator._validate_resume_output(stale, inputs, list(evaluator.INPUT_COLS))


def test_resume_output_detects_input_value_mismatch_without_ids():
    evaluator = load_evaluator()
    inputs = input_rows().drop(columns=["input_sample_id", "sample_group"])
    matching = inputs.iloc[:1].copy()
    matching["fx"] = 1.0
    matching["fy"] = 2.0

    evaluator._validate_resume_output(matching, inputs, list(evaluator.INPUT_COLS))

    stale = matching.copy()
    stale.loc[0, "lambda_value"] = 2.0
    with pytest.raises(ValueError, match="lambda_value"):
        evaluator._validate_resume_output(stale, inputs, list(evaluator.INPUT_COLS))
