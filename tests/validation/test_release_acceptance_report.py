"""Validate the committed final release acceptance evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_release_acceptance.json"


def test_release_acceptance_reports_real_pytest_mypy_and_status_gates() -> None:
    if not REPORT_PATH.exists():
        pytest.skip("Release evidence is created by the acceptance runner")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert report["overall_status"] == "passed"
    assert report["version"] == "0.2.0"
    assert report["pytest"]["returncode"] == 0
    assert report["pytest"]["summary"]["passed"] > 0
    assert report["pytest"]["summary"]["skipped"] == len(
        report["pytest"]["skipped"]
    )
    assert report["pytest"]["known_newton_skip"]["nodeid"].endswith(
        "test_fixed_point_reference_snapshot_matches_pre_change_results_exactly"
    )
    assert report["mypy"]["returncode"] == 0
    assert "Success: no issues found" in report["mypy"]["stdout"]
    assert report["worktree"]["tracked_status_delta"] == 0
    assert report["worktree"]["before_sha256"] == report["worktree"]["after_sha256"]
    assert report["worktree"]["tracked_status_before"] == [
        " M test/bearing/_thermal_plots/alb_thermal_4pads.png",
        " M test/bearing/_thermal_plots/orifice_thermal_comparison.png",
    ]
    assert (
        report["worktree"]["tracked_status_after"]
        == report["worktree"]["tracked_status_before"]
    )
    assert report["references"]["full_repo_refactor_v1_unchanged_from_tag"] is True
