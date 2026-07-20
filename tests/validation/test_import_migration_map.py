"""Validate coverage and targets in the 0.2 import migration map."""

from __future__ import annotations

import ast
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_import_map.json"
EXTERNAL_AUDIT_PATH = (
    REPOSITORY_ROOT / "docs/migrations/0.2.0_external_consumer_audit.json"
)


def _module_exists(module: str) -> bool:
    parts = module.split(".")
    base = REPOSITORY_ROOT.joinpath(*parts)
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def _module_path(module: str) -> Path | None:
    base = REPOSITORY_ROOT.joinpath(*module.split("."))
    file_path = base.with_suffix(".py")
    if file_path.is_file():
        return file_path
    init_path = base / "__init__.py"
    return init_path if init_path.is_file() else None


def _public_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.asname for alias in node.names if alias.asname)
        elif isinstance(node, ast.Assign):
            assigned = {
                target.id for target in node.targets if isinstance(target, ast.Name)
            }
            names.update(assigned)
            if "_EXPORTS" in assigned and isinstance(node.value, ast.Dict):
                names.update(
                    key.value
                    for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
            if "__all__" in assigned:
                try:
                    names.update(ast.literal_eval(node.value))
                except (ValueError, TypeError):
                    pass
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {name for name in names if not name.startswith("_")}


def _symbol_exists(target: str) -> bool:
    parts = target.split(".")
    for split_at in range(len(parts) - 1, 0, -1):
        module = ".".join(parts[:split_at])
        path = _module_path(module)
        if path is None:
            continue
        attributes = parts[split_at:]
        return len(attributes) == 1 and attributes[0] in _public_names(path)
    return False


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


def test_all_symbol_alias_and_root_targets_exist() -> None:
    import_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    mappings = [
        *import_map["symbol_mappings"],
        *import_map["public_alias_mappings"],
        *import_map["root_export_mappings"],
    ]

    assert len(import_map["root_export_mappings"]) == 68
    assert len({item["source"] for item in import_map["root_export_mappings"]}) == 68
    assert all(
        _symbol_exists(target)
        for item in mappings
        if item["status"] != "removed"
        for target in item["targets"]
    )
    assert not any(
        target.startswith("ALB.config._models.")
        for item in mappings
        for target in item["targets"]
    )


def test_declared_external_imported_symbols_have_machine_mappings() -> None:
    import_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    audit = json.loads(EXTERNAL_AUDIT_PATH.read_text(encoding="utf-8"))
    mapped_sources = {
        item["source"]
        for key in ("symbol_mappings", "public_alias_mappings", "root_export_mappings")
        for item in import_map[key]
    }
    missing: set[str] = set()
    for project in audit["projects"]:
        for entry in project["entries"]:
            for imported in entry["old_imports"]:
                module = imported["module"]
                for name in imported["names"]:
                    source = f"{module}.{name}"
                    if source not in mapped_sources:
                        missing.add(source)
    assert missing == set()
