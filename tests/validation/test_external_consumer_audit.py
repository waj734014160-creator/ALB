"""Validate declared read-only external consumer snapshot coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_external_consumer_audit.json"
POST_AUDIT_PATH = (
    REPOSITORY_ROOT
    / "docs/migrations/0.2.0_surrogate_train_post_migration_audit.json"
)
PAPER_POST_AUDIT_PATH = (
    REPOSITORY_ROOT / "docs/migrations/0.2.0_paper_work_post_migration_audit.json"
)


def test_declared_external_snapshot_has_exact_required_counts() -> None:
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    projects = {project["project"]: project for project in audit["projects"]}

    assert audit["read_only"] is True
    assert projects["SURROGATE_TRAIN"]["declared_count"] == 23
    assert projects["SURROGATE_TRAIN"]["counts"] == {"direct": 19, "context": 4}
    assert projects["PAPER_WORK"]["declared_count"] == 27
    assert projects["PAPER_WORK"]["counts"] == {"direct": 25, "transitive": 2}


def test_paper_work_snapshot_and_post_migration_hashes_match() -> None:
    pre_audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    post_audit = json.loads(PAPER_POST_AUDIT_PATH.read_text(encoding="utf-8"))
    pre_project = next(
        item for item in pre_audit["projects"] if item["project"] == "PAPER_WORK"
    )
    pre_hashes = {entry["path"]: entry["sha256"] for entry in pre_project["entries"]}
    project = post_audit["paper_work"]

    assert project["declared_count"] == 27
    assert project["dynamic_helper_count"] == 2
    assert project["declared_changed_count"] == 25
    assert project["all_changed_count"] == 27
    assert project["remaining_flat_import_count"] == 0
    assert project["git_repository"] is False

    root = Path(project["root"])
    snapshot_root = root / "refs" / "alb_0_2_consumer_migration_v1" / "source"
    for entry in project["entries"]:
        path = root / entry["path"]
        snapshot_path = snapshot_root / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["post_sha256"]
        assert hashlib.sha256(snapshot_path.read_bytes()).hexdigest() == entry[
            "pre_sha256"
        ]
        assert entry["remaining_flat_imports"] == []
        if entry["path"] in pre_hashes:
            assert entry["pre_sha256"] == pre_hashes[entry["path"]]

    assert len(post_audit["model_packages"]) == 2
    for package in post_audit["model_packages"]:
        assert package["manifest_schema"] == "alb.surrogate-package.v0.2"
        assert package["pickle_trust_required"] is True
        for artifact in package["artifacts"].values():
            assert artifact["matches_manifest"] is True


def test_surrogate_post_migration_hashes_and_packages_match() -> None:
    pre_audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    post_audit = json.loads(POST_AUDIT_PATH.read_text(encoding="utf-8"))
    pre_project = next(
        item
        for item in pre_audit["projects"]
        if item["project"] == "SURROGATE_TRAIN"
    )
    pre_hashes = {entry["path"]: entry["sha256"] for entry in pre_project["entries"]}
    project = post_audit["surrogate_train"]

    assert project["declared_count"] == 23
    assert project["changed_count"] == 20
    assert project["remaining_flat_import_count"] == 0
    assert project["working_tree_clean"] is True

    root = Path(project["root"])
    for entry in project["entries"]:
        path = root / entry["path"]
        assert entry["pre_sha256"] == pre_hashes[entry["path"]]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["post_sha256"]
        assert entry["remaining_flat_imports"] == []

    assert len(post_audit["model_packages"]) == 3
    for package in post_audit["model_packages"]:
        package_root = root / package["package_dir"]
        assert package["manifest_schema"] == "alb.surrogate-package.v0.2"
        assert package["git_ignored"] is True
        assert package["pickle_trust_required"] is True
        for artifact in package["artifacts"].values():
            path = package_root / artifact["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact[
                "actual_sha256"
            ]
            assert artifact["matches_manifest"] is True
            assert artifact["contains_legacy_ALB_nn_reference"] is False
