# coding: utf-8

import json

from scripts import run_registry


def test_register_allocates_project_local_run_numbers(tmp_path):
    first = run_registry.register_run(
        project_root=tmp_path,
        owner="SURROGATE_TRAIN",
        domain="fd_jacobian",
        purpose="h_review",
        size_or_key="500",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )
    second = run_registry.register_run(
        project_root=tmp_path,
        owner="SURROGATE_TRAIN",
        domain="fd_jacobian",
        purpose="full",
        size_or_key="20000_h1em03",
        date="20260517",
        timestamp="2026-05-17T00:01:00+00:00",
    )

    assert first.run_no == "S0001"
    assert first.run_id == "fd_jacobian_h_review_500_20260517_S0001"
    assert second.run_no == "S0002"
    assert second.run_id == "fd_jacobian_full_20000_h1em03_20260517_S0002"


def test_project_numbers_are_independent(tmp_path):
    alb_root = tmp_path / "ALB_MAIN"
    surrogate_root = tmp_path / "SURROGATE_TRAIN"
    alb = run_registry.register_run(
        project_root=alb_root,
        domain="remote_refs",
        purpose="baseline",
        size_or_key="v1",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )
    surrogate = run_registry.register_run(
        project_root=surrogate_root,
        domain="fd_jacobian",
        purpose="h_review",
        size_or_key="500",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )

    assert alb.run_no == "A0001"
    assert surrogate.run_no == "S0001"


def test_update_appends_latest_state_without_rewriting(tmp_path):
    registered = run_registry.register_run(
        project_root=tmp_path,
        owner="SURROGATE_TRAIN",
        domain="fd_jacobian",
        purpose="h_review",
        size_or_key="500",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )
    updated = run_registry.update_run(
        project_root=tmp_path,
        run_id=registered.run_id,
        state="completed",
        notes="finished",
        timestamp="2026-05-17T01:00:00+00:00",
    )

    entries = run_registry.read_entries(run_registry.registry_path(tmp_path))
    latest = run_registry.latest_by_run_id(entries)[registered.run_id]
    assert len(entries) == 2
    assert updated.event == "update"
    assert latest.state == "completed"
    assert latest.config == "run/remote/configs/fd_jacobian_h_review_500_20260517_S0001.json"
    assert latest.outputs == "outputs/fd_jacobian/fd_jacobian_h_review_500_20260517_S0001"
    assert latest.logs["remote"] == "logs/remote/fd_jacobian_h_review_500_20260517_S0001"


def test_validate_config_registration_uses_project_registry(tmp_path):
    project_root = tmp_path / "SURROGATE_TRAIN"
    entry = run_registry.register_run(
        project_root=project_root,
        domain="remote",
        purpose="generic",
        size_or_key="1",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )
    config_dir = project_root / "run" / "remote" / "configs"
    config_dir.mkdir(parents=True)
    config = {
        "_config_dir": str(config_dir),
        "run_id": entry.run_id,
        "run_registry": {
            "project_root": "../../..",
        },
    }

    assert run_registry.validate_config_registration(config).run_no == "S0001"


def test_registry_jsonl_is_append_only_json(tmp_path):
    run_registry.register_run(
        project_root=tmp_path,
        owner="SURROGATE_TRAIN",
        domain="fd_jacobian",
        purpose="h_review",
        size_or_key="500",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )
    lines = run_registry.registry_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert sorted(decoded) == [
        "archive",
        "config",
        "domain",
        "event",
        "logs",
        "notes",
        "outputs",
        "owner",
        "run_id",
        "run_no",
        "state",
        "timestamp",
    ]
