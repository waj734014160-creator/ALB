# coding: utf-8

import json

import pytest

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
    assert first.run_id == "S0001_fd_jacobian_h_review_500_20260517"
    assert second.run_no == "S0002"
    assert second.run_id == "S0002_fd_jacobian_full_20000_h1em03_20260517"


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


def test_update_replaces_current_locator_without_history_rows(tmp_path):
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
    assert len(entries) == 1
    assert updated.event == "update"
    assert latest.state == "completed"
    assert latest.config == "run/remote/configs/S0001_fd_jacobian_h_review_500_20260517.json"
    assert latest.outputs == "outputs/fd_jacobian/S0001_fd_jacobian_h_review_500_20260517"
    assert latest.logs is None
    assert latest.archive is None


def test_update_can_clear_log_pointer(tmp_path):
    registered = run_registry.register_run(
        project_root=tmp_path,
        owner="SURROGATE_TRAIN",
        domain="fd_jacobian",
        purpose="h_review",
        size_or_key="500",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )
    with_log = run_registry.update_run(
        project_root=tmp_path,
        run_id=registered.run_id,
        state="running",
        logs={"monitor": "logs/remote/monitor.log"},
        timestamp="2026-05-17T01:00:00+00:00",
    )
    cleared = run_registry.update_run(
        project_root=tmp_path,
        run_id=registered.run_id,
        state="running",
        clear_logs=True,
        timestamp="2026-05-17T02:00:00+00:00",
    )

    assert registered.logs is None
    assert with_log.logs == {"monitor": "logs/remote/monitor.log"}
    assert cleared.logs is None


def test_update_can_set_and_clear_archive_pointer(tmp_path):
    registered = run_registry.register_run(
        project_root=tmp_path,
        owner="SURROGATE_TRAIN",
        domain="fd_jacobian",
        purpose="h_review",
        size_or_key="500",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )
    archived = run_registry.update_run(
        project_root=tmp_path,
        run_id=registered.run_id,
        state="archived",
        archive="outputs/archive/S0001_fd_jacobian_h_review_500_20260517",
        timestamp="2026-05-17T01:00:00+00:00",
    )
    cleared = run_registry.update_run(
        project_root=tmp_path,
        run_id=registered.run_id,
        state="running",
        clear_archive=True,
        timestamp="2026-05-17T02:00:00+00:00",
    )

    assert registered.archive is None
    assert archived.archive == "outputs/archive/S0001_fd_jacobian_h_review_500_20260517"
    assert cleared.archive is None


def test_paths_query_returns_latest_project_paths_by_run_no(tmp_path):
    registered = run_registry.register_run(
        project_root=tmp_path,
        owner="SURROGATE_TRAIN",
        domain="fd_jacobian",
        purpose="h_review",
        size_or_key="500",
        date="20260517",
        timestamp="2026-05-17T00:00:00+00:00",
    )
    run_registry.update_run(
        project_root=tmp_path,
        run_id=registered.run_id,
        state="running",
        outputs="outputs/fd_jacobian/current",
        logs={"monitor": "logs/remote/current/monitor.log"},
        timestamp="2026-05-17T01:00:00+00:00",
    )

    paths = run_registry.run_paths_by_run_no(project_root=tmp_path, run_no="S0001")

    assert paths["run_id"] == registered.run_id
    assert paths["state"] == "running"
    assert paths["paths"]["config"]["path"] == registered.config
    assert paths["paths"]["outputs"]["path"] == "outputs/fd_jacobian/current"
    assert paths["paths"]["outputs"]["abs_path"] == str(
        (tmp_path / "outputs/fd_jacobian/current").resolve()
    )
    assert paths["paths"]["logs"]["monitor"]["path"] == "logs/remote/current/monitor.log"


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


def test_validate_rejects_suffix_run_number_format(tmp_path):
    project_root = tmp_path / "SURROGATE_TRAIN"
    entry = run_registry.RegistryEntry(
        event="register",
        timestamp="2026-05-17T00:00:00+00:00",
        run_no="S0001",
        run_id="fd_jacobian_h_review_500_20260517_S0001",
        owner="SURROGATE_TRAIN",
        domain="fd_jacobian",
        state="registered",
        config="run/remote/configs/fd_jacobian_h_review_500_20260517_S0001.json",
        outputs="outputs/fd_jacobian/fd_jacobian_h_review_500_20260517_S0001",
        logs=None,
        archive=None,
        notes="old suffix format",
    )
    run_registry.write_entries(run_registry.registry_path(project_root), [entry])

    with pytest.raises(run_registry.RunRegistryError, match="must start with run_no"):
        run_registry.validate_registered_run(
            project_root=project_root,
            run_id=entry.run_id,
        )


def test_registry_jsonl_is_current_locator_json(tmp_path):
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
    assert list(decoded) == [
        "run_no",
        "run_id",
        "event",
        "timestamp",
        "owner",
        "domain",
        "state",
        "config",
        "outputs",
        "logs",
        "archive",
        "notes",
    ]
