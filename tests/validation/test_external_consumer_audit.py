"""Validate declared read-only external consumer snapshot coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_external_consumer_audit.json"


def test_declared_external_snapshot_has_exact_required_counts() -> None:
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    projects = {project["project"]: project for project in audit["projects"]}

    assert audit["read_only"] is True
    assert projects["SURROGATE_TRAIN"]["declared_count"] == 23
    assert projects["SURROGATE_TRAIN"]["counts"] == {"direct": 19, "context": 4}
    assert projects["PAPER_WORK"]["declared_count"] == 27
    assert projects["PAPER_WORK"]["counts"] == {"direct": 25, "transitive": 2}


def test_external_snapshot_hashes_still_match_without_writes() -> None:
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    for project in audit["projects"]:
        root = Path(project["root"])
        for entry in project["entries"]:
            path = root / entry["path"]
            assert path.is_file()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
            assert entry["external_file_modified"] is False
            if entry["kind"] == "direct":
                assert entry["old_imports"]
                assert entry["target_namespaces"]
