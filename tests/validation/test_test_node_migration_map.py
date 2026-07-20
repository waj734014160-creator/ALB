"""Validate the complete mapping of the frozen 0.1 pytest inventory."""

from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_test_map.json"


def test_all_baseline_nodes_have_existing_replacements() -> None:
    migration_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    mappings = migration_map["mappings"]

    assert migration_map["baseline_node_count"] == 242
    assert len(mappings) == 242
    assert len({item["baseline_nodeid"] for item in mappings}) == 242

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
