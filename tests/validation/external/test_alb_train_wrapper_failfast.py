"""Negative gates for removed ALBNN training compatibility wrappers."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SURROGATE_ROOT = REPO_ROOT.parent / "SURROGATE_TRAIN"


def test_only_strict_config_driven_training_entry_remains() -> None:
    train_dir = SURROGATE_ROOT / "run" / "train"
    assert (train_dir / "train_albnn.py").is_file()
    assert not (train_dir / "train_alb_agent.py").exists()
    assert not (train_dir / "train_albnn_expert.py").exists()
    assert not (train_dir / "train_albnn_residual_expert.py").exists()


def test_training_entry_is_importable_without_source_shadowing() -> None:
    script = SURROGATE_ROOT / "run" / "train" / "train_albnn.py"
    spec = importlib.util.spec_from_file_location("albnn_v04_training_entry", script)
    assert spec is not None and spec.loader is not None
