"""Validate coverage and targets in the 0.2 import migration map."""

from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_import_map.json"


def _module_exists(module: str) -> bool:
    parts = module.split(".")
    base = REPOSITORY_ROOT.joinpath(*parts)
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def test_all_baseline_modules_have_existing_namespace_targets() -> None:
    import_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    modules = import_map["module_mappings"]

    assert len(modules) == 65
    assert len({item["source"] for item in modules}) == 65
    for item in modules:
        assert item["targets"]
        assert all(_module_exists(target) for target in item["targets"])


def test_every_public_definition_has_a_target_or_explicit_removal() -> None:
    import_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    symbols = import_map["symbol_mappings"]
    removed = [item for item in symbols if item["status"] == "removed"]

    assert len(symbols) == 479
    assert {item["source"] for item in removed} == {
        "ALB.tool.create_latex_symbol",
        "ALB.tool.get",
    }
    assert all(item["rationale"] for item in removed)
    assert all(item["targets"] for item in symbols if item["status"] != "removed")
