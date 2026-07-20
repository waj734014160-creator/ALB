"""Validate the complete mapping of the frozen 0.1 pytest inventory."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_test_map.json"
FROZEN_MAP_PATH = (
    REPOSITORY_ROOT / "refs/full_repo_refactor_v1/test_node_migration_map.json"
)


def _node_digest(nodeids: list[str]) -> str:
    payload = "\n".join(sorted(set(nodeids))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _collect_nodeids() -> list[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return sorted(
        {
            line.strip().replace("\\", "/")
            for line in completed.stdout.splitlines()
            if line.strip().startswith("tests/") and "::" in line
        }
    )


def test_all_baseline_nodes_have_existing_replacements() -> None:
    migration_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    frozen_map = json.loads(FROZEN_MAP_PATH.read_text(encoding="utf-8"))
    mappings = migration_map["mappings"]
    baseline_nodeids = [item["baseline_nodeid"] for item in mappings]
    frozen_nodeids = [item["baseline_nodeid"] for item in frozen_map["mappings"]]
    replacement_nodeids = [
        nodeid for item in mappings for nodeid in item["replacement_nodeids"]
    ]
    collected_nodeids = _collect_nodeids()

    assert migration_map["baseline_node_count"] == 242
    assert len(mappings) == 242
    assert len(set(baseline_nodeids)) == 242
    assert set(baseline_nodeids) == set(frozen_nodeids)
    assert migration_map["baseline_nodeids_sha256"] == frozen_map["nodeids_sha256"]
    assert migration_map["baseline_nodeids_sha256_computed"] == _node_digest(
        baseline_nodeids
    )
    assert migration_map["baseline_recorded_digest_matches"] is True
    assert len(replacement_nodeids) == len(set(replacement_nodeids)) == 242
    assert set(replacement_nodeids).issubset(collected_nodeids)
    assert migration_map["verification"]["replacement_nodeids_sha256"] == _node_digest(
        replacement_nodeids
    )
    assert migration_map["verification"]["collected_nodeids_sha256"] == _node_digest(
        collected_nodeids
    )
    assert migration_map["verification"]["collected_node_count"] == len(
        collected_nodeids
    )

    for item in mappings:
        assert item["status"] == "implemented"
        assert item["replacement_nodeids"]
        assert (REPOSITORY_ROOT / item["target_path"]).is_file()


def test_all_non_collected_python_files_have_existing_targets() -> None:
    migration_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    entries = migration_map["non_collected_python_files"]

    assert len(entries) == 19
    for item in entries:
        assert item["status"] == "implemented"
        assert (REPOSITORY_ROOT / item["target_path"]).is_file()
