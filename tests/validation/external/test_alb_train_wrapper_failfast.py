# coding: utf-8
"""Fail-fast coverage for experimental ALBNN training wrappers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SURROGATE_ROOT = REPO_ROOT.parent / "SURROGATE_TRAIN"


def _run_wrapper(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    script = SURROGATE_ROOT / "run" / "train" / script_name
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_expert_config_branch_fails_fast_before_placeholder_training(tmp_path):
    result = _run_wrapper(
        "train_albnn_expert.py",
        "--config",
        str(tmp_path / "missing_config.json"),
        "--epochs=7",
    )

    assert result.returncode != 0
    assert "--config is not implemented for train_albnn_expert.py yet" in result.stderr
    assert "legacy CLI arguments" in result.stderr
    assert "Explicit --epochs override was detected" in result.stderr
    assert "No such file" not in result.stderr


def test_residual_config_branch_fails_fast_before_placeholder_training(tmp_path):
    result = _run_wrapper(
        "train_albnn_residual_expert.py",
        "--config",
        str(tmp_path / "missing_config.json"),
        "--epochs=7",
    )

    assert result.returncode != 0
    assert (
        "--config is not implemented for train_albnn_residual_expert.py yet"
        in result.stderr
    )
    assert "legacy CLI arguments" in result.stderr
    assert "Explicit --epochs override was detected" in result.stderr
    assert "No such file" not in result.stderr


def test_expert_config_epoch_abbreviation_is_rejected(tmp_path):
    result = _run_wrapper(
        "train_albnn_expert.py",
        "--config",
        str(tmp_path / "missing_config.json"),
        "--epo=7",
    )

    assert result.returncode != 0
    assert "unrecognized arguments: --epo=7" in result.stderr
    assert "Explicit --epochs override was detected" not in result.stderr


def test_residual_config_epoch_abbreviation_is_rejected(tmp_path):
    result = _run_wrapper(
        "train_albnn_residual_expert.py",
        "--config",
        str(tmp_path / "missing_config.json"),
        "--epo=7",
    )

    assert result.returncode != 0
    assert "unrecognized arguments: --epo=7" in result.stderr
    assert "Explicit --epochs override was detected" not in result.stderr


def test_expert_dry_run_config_without_config_fails_before_legacy_training(tmp_path):
    output_dir = tmp_path / "expert_output"
    result = _run_wrapper(
        "train_albnn_expert.py",
        "--dry_run_config",
        "--data",
        str(tmp_path / "data.csv"),
        "--output_dir",
        str(output_dir),
    )

    assert result.returncode != 0
    assert "--dry_run_config requires --config" in result.stderr
    assert "legacy expert CLI path" in result.stderr
    assert not output_dir.exists()


def test_expert_legacy_device_without_config_fails_before_training(tmp_path):
    output_dir = tmp_path / "expert_output"
    result = _run_wrapper(
        "train_albnn_expert.py",
        "--device",
        "cpu",
        "--data",
        str(tmp_path / "data.csv"),
        "--output_dir",
        str(output_dir),
    )

    assert result.returncode != 0
    assert "--device is only supported with --config" in result.stderr
    assert not output_dir.exists()


def test_residual_dry_run_config_without_config_fails_before_legacy_training(tmp_path):
    output_dir = tmp_path / "residual_output"
    result = _run_wrapper(
        "train_albnn_residual_expert.py",
        "--dry_run_config",
        "--main_model_dir",
        str(tmp_path / "model"),
        "--output_dir",
        str(output_dir),
    )

    assert result.returncode != 0
    assert "--dry_run_config requires --config" in result.stderr
    assert "legacy residual expert CLI path" in result.stderr
    assert not output_dir.exists()


def test_residual_legacy_device_without_config_fails_before_training(tmp_path):
    output_dir = tmp_path / "residual_output"
    result = _run_wrapper(
        "train_albnn_residual_expert.py",
        "--device",
        "cpu",
        "--main_model_dir",
        str(tmp_path / "model"),
        "--output_dir",
        str(output_dir),
    )

    assert result.returncode != 0
    assert "--device is only supported with --config" in result.stderr
    assert not output_dir.exists()
