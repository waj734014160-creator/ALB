"""Exact regression for canonical release inputs and retained v7 behavior."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.validation.release_source_identity import source_tree_evidence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = REPOSITORY_ROOT / "refs/eighth_review_wheel_identity_reference_v8.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_candidate_release_blobs_and_v7_behavior_reference_remain_exact() -> None:
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    canonical = reference["canonical_source"]
    current = source_tree_evidence(REPOSITORY_ROOT, "HEAD")

    assert current["tree_sha256"] == canonical["tree_sha256"]
    assert current["file_count"] == canonical["file_count"]
    assert current["pyproject_sha256"] == canonical["pyproject_sha256"]
    assert _sha256(
        REPOSITORY_ROOT / "refs/seventh_review_release_reference_v7.json"
    ) == reference["behavior_reference_integrity"]["json_sha256"]
    assert _sha256(
        REPOSITORY_ROOT / "refs/seventh_review_release_reference_v7.npz"
    ) == reference["behavior_reference_integrity"]["npz_sha256"]
