"""Validate committed wheel and isolated-install acceptance evidence."""

from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_build_acceptance.json"


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
    assert all(item["returncode"] == 0 for item in report["cli_help"].values())
    assert all(item["usage"].startswith("usage:") for item in report["cli_help"].values())
