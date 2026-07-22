"""Validate committed wheel and isolated-install acceptance evidence."""

from __future__ import annotations

import json
from pathlib import Path, PurePath


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_build_acceptance.json"


def _has_path_suffix(path: str, expected_suffix: Path) -> bool:
    """Compare stored evidence paths without binding them to this checkout root."""

    actual_parts = PurePath(path).parts
    expected_parts = PurePath(expected_suffix).parts
    return actual_parts[-len(expected_parts) :] == expected_parts


def test_wheel_metadata_cli_and_namespace_smokes_passed() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    assert report["overall_status"] == "passed"
    assert report["version"] == "0.2.0"
    assert report["metadata"] == {
        "version": "0.2.0",
        "requires_python": ">=3.10",
        "extras": ["all", "control", "dynamics", "film", "io", "surrogate", "test"],
    }
    assert report["wheel"]["forbidden_members_present"] == []
    assert len(report["wheel"]["sha256"]) == 64
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
