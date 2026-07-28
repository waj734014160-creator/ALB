"""Contract tests for the public MkDocs site configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPOSITORY_ROOT / "mkdocs.yml"


def _nav_paths(value: Any) -> tuple[str, ...]:
    """Return every Markdown source path from a nested MkDocs nav value."""

    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(path for item in value for path in _nav_paths(item))
    if isinstance(value, dict):
        return tuple(path for item in value.values() for path in _nav_paths(item))
    return ()


def test_public_site_navigation_is_explicit_and_resolvable() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    nav_paths = _nav_paths(config["nav"])

    assert nav_paths
    assert nav_paths[0] == "index.md"
    assert len(nav_paths) == len(set(nav_paths))
    assert "api/public_api_reference.md" in nav_paths
    assert "api/bearing_config_reference.md" in nav_paths
    assert {
        "api/namespaces/control.md",
        "api/namespaces/dynamics.md",
        "api/namespaces/surrogate.md",
    }.issubset(nav_paths)
    assert all((REPOSITORY_ROOT / "docs" / path).is_file() for path in nav_paths)


def test_public_site_excludes_operational_and_evidence_documents() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    excluded = set(config["exclude_docs"].splitlines())

    assert {
        "current_state.md",
        "daily_summary_log.md",
        "daily_maintenance/",
        "remote_workstation_connection.md",
        "run_index.md",
        "audits/",
        "**/*.json",
        "**/*status*.txt",
        "api/public_api_docs.json",
        "api/namespace_reference_docs.json",
    }.issubset(excluded)
    assert not any(
        path.startswith(("current_state", "daily_maintenance", "remote_workstation"))
        for path in _nav_paths(config["nav"])
    )


def test_public_site_has_bilingual_search_and_no_placeholder_repository() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    search = config["plugins"][0]["search"]

    assert search["lang"] == ["zh", "en"]
    assert config["strict"] is True
    assert config["site_dir"] == "site"
    assert config.get("repo_url") != "https://github.com/"
