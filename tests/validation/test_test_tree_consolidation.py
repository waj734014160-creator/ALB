"""Protect assets moved from the retired root ``test`` directory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "refs" / "test_tree_consolidation_reference_v1.json"


def test_tracked_legacy_assets_match_pre_consolidation_reference() -> None:
    """Require every tracked legacy asset to survive the move byte-for-byte."""

    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))

    for asset in reference["tracked_assets"]:
        source = ROOT / asset["source"]
        target = ROOT / asset["target"]

        assert not source.exists()
        assert target.is_file()
        assert target.stat().st_size == asset["bytes"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == asset["sha256"]


def test_retired_root_test_directory_does_not_return() -> None:
    """Keep ``tests`` as the repository's single test-tree root."""

    assert not (ROOT / "test").exists()
