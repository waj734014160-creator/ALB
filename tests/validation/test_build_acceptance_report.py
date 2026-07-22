"""Validate committed wheel and isolated-install acceptance evidence."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePath
import subprocess

from tools.validation.validate_wheel_0_2 import source_tree_evidence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_PATH = (
    REPOSITORY_ROOT / "docs/migrations/0.2.0_build_acceptance.json"
)


def _has_path_suffix(path: str, expected_suffix: Path) -> bool:
    """Compare stored evidence paths without binding them to this checkout root."""

    actual_parts = PurePath(path).parts
    expected_parts = PurePath(expected_suffix).parts
    return actual_parts[-len(expected_parts) :] == expected_parts


def test_wheel_metadata_cli_and_namespace_smokes_passed() -> None:
    report_path = Path(
        os.environ.get("ALB_BUILD_ACCEPTANCE_REPORT", DEFAULT_REPORT_PATH)
    ).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["overall_status"] == "passed"
    assert report["version"] == "0.2.0"
    candidate_commit = report["candidate_commit"]
    assert subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_commit, "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=False,
    ).returncode == 0
    assert subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            candidate_commit,
            "HEAD",
            "--",
            "ALB",
            "pyproject.toml",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
    ).returncode == 0
    assert report["source"]["tree_sha256"] == source_tree_evidence()["tree_sha256"]
    assert report["source"]["pyproject_sha256"] == source_tree_evidence()[
        "pyproject_sha256"
    ]
    assert report["source"]["missing_wheel_members"] == []
    assert report["source"]["mismatched_wheel_members"] == []
    assert report["source"]["wheel_source_files_checked"] > 0
    assert report["metadata"]["version"] == "0.2.0"
    assert report["metadata"]["requires_python"] == ">=3.10"
    assert report["metadata"]["extras"] == [
        "all",
        "control",
        "dynamics",
        "film",
        "io",
        "surrogate",
        "test",
    ]
    assert report["metadata"]["matches_pyproject"] is True
    assert report["metadata"]["requirements_by_extra"]["test"] == [
        "build>=1.2",
        "import-linter>=2.0",
        "mypy>=1.10",
        "pytest>=9",
    ]
    assert report["wheel"]["forbidden_members_present"] == []
    assert len(report["wheel"]["sha256"]) == 64
    wheel_path = REPOSITORY_ROOT / report["wheel"]["path"]
    require_disk_wheel = os.environ.get("ALB_BUILD_ACCEPTANCE_REQUIRE_WHEEL") == "1"
    if require_disk_wheel or wheel_path.is_file():
        assert wheel_path.is_file()
        assert hashlib.sha256(wheel_path.read_bytes()).hexdigest() == report["wheel"][
            "sha256"
        ]
    assert all(not present for present in report["isolated_install"]["removed_specs"].values())
    assert len(report["isolated_install"]["namespace_smoke"]) == 11
    assert set(report["extra_smokes"]) == {
        "core",
        "film",
        "control",
        "dynamics",
        "surrogate",
        "io",
        "all",
        "test",
    }
    assert all(item["returncode"] == 0 for item in report["extra_smokes"].values())
    assert all(
        _has_path_suffix(
            item["alb_file"],
            Path(report["isolated_install"]["root"]) / "ALB" / "__init__.py",
        )
        for item in report["extra_smokes"].values()
    )
    assert all(
        item["dependency_versions"] for item in report["extra_smokes"].values()
    )
    assert all(item["returncode"] == 0 for item in report["cli_help"].values())
    assert all(item["usage"].startswith("usage:") for item in report["cli_help"].values())
