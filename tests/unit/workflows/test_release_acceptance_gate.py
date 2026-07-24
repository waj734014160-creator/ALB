"""Unit tests for the ALB 0.4 detached release acceptance gate."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from tools.validation import run_release_acceptance_0_4 as acceptance


def _write_wheel(path: Path, members: dict[str, str]) -> None:
    """Create a minimal ZIP-shaped wheel for content-gate tests."""

    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_feature_manifest_has_contiguous_v4_ids_and_nodeids() -> None:
    payload = json.loads(
        acceptance.FEATURE_MANIFEST.read_text(encoding="utf-8")
    )

    assert [item["id"] for item in payload["features"]] == [
        f"V4-{index:02d}" for index in range(1, 25)
    ]
    assert acceptance._feature_nodeids()


def test_wheel_content_gate_accepts_only_current_runtime(tmp_path: Path) -> None:
    wheel = tmp_path / "re_alb-0.4.0-py3-none-any.whl"
    _write_wheel(
        wheel,
        {
            "ALB/__init__.py": '__version__ = "0.4.0"\n',
            "ALB/api/bearing.py": "class Bearing:\n    pass\n",
            "re_alb-0.4.0.dist-info/METADATA": "Version: 0.4.0\n",
        },
    )

    evidence = acceptance._inspect_wheel(wheel)

    assert evidence["member_count"] == 3
    assert evidence["forbidden_members"] == []
    assert evidence["forbidden_token_hits"] == []
    assert len(evidence["sha256"]) == 64


@pytest.mark.parametrize(
    ("member", "content", "match"),
    [
        ("ALB/config/legacy.py", "pass\n", "forbidden_members"),
        ("tools/migrations/convert.py", "pass\n", "tool_members"),
        (
            "ALB/control/controller.py",
            "class LegacyControllerAdapter:\n    pass\n",
            "token_hits",
        ),
    ],
)
def test_wheel_content_gate_rejects_removed_surfaces(
    tmp_path: Path,
    member: str,
    content: str,
    match: str,
) -> None:
    wheel = tmp_path / "re_alb-0.4.0-py3-none-any.whl"
    _write_wheel(wheel, {member: content})

    with pytest.raises(RuntimeError, match=match):
        acceptance._inspect_wheel(wheel)


def test_release_report_is_bound_to_resolved_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Candidate resolution must happen before any detached worktree mutation."""

    monkeypatch.setattr(acceptance, "ROOT", tmp_path)
    monkeypatch.setattr(acceptance, "_output", lambda *args, **kwargs: "fixedsha")

    def fail_before_mutation(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("stop-before-worktree")

    monkeypatch.setattr(acceptance, "_run", fail_before_mutation)

    with pytest.raises(RuntimeError, match="stop-before-worktree"):
        acceptance.run_acceptance("candidate", publish=False)

    reports = list((tmp_path / "outputs/release_acceptance").glob("*/report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["candidate_commit"] == "fixedsha"
    assert report["status"] == "running"
