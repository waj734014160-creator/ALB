"""Validate the 0.2 namespace layering and absence of package cycles."""

from __future__ import annotations

import ast
from collections import defaultdict
from importlib.util import resolve_name
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "ALB"
NAMESPACES = {
    "config",
    "contracts",
    "control",
    "core",
    "dynamics",
    "infrastructure",
    "physics",
    "surrogate",
    "systems",
    "workflows",
}
REMOVED_FLAT_MODULES = {
    "ALB.alb",
    "ALB.base",
    "ALB.bearing",
    "ALB.controller",
    "ALB.couple",
    "ALB.film",
    "ALB.gas_bearing",
    "ALB.matrix",
    "ALB.nn",
    "ALB.orifice",
    "ALB.plot",
    "ALB.postprocess",
    "ALB.remote",
    "ALB.results",
    "ALB.rotor",
    "ALB.task",
    "ALB.thermal",
    "ALB.tool",
}
ALLOWED_DEPENDENCIES = {
    "contracts": {"contracts"},
    "core": {"contracts", "core"},
    "config": {"config", "contracts", "core"},
    "physics": {"config", "contracts", "core", "physics"},
    "infrastructure": {"config", "contracts", "infrastructure"},
    "dynamics": {"config", "contracts", "core", "dynamics"},
    "control": {"config", "contracts", "control", "core", "dynamics"},
    "surrogate": {"config", "contracts", "core", "infrastructure", "surrogate"},
    "systems": {
        "config",
        "contracts",
        "control",
        "core",
        "dynamics",
        "physics",
        "surrogate",
        "systems",
    },
    "workflows": NAMESPACES,
}


def _module_name(path: Path) -> tuple[str, str]:
    relative = path.relative_to(REPOSITORY_ROOT).with_suffix("")
    module = ".".join(relative.parts)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    if module.endswith(".__init__"):
        module = module.removesuffix(".__init__")
    return module, package


def _internal_imports(path: Path) -> set[str]:
    module, package = _module_name(path)
    del module
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name.startswith("ALB"))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                target = resolve_name("." * node.level + (node.module or ""), package)
            else:
                target = node.module or ""
            if target == "ALB":
                imports.update(f"ALB.{alias.name}" for alias in node.names)
            elif target.startswith("ALB."):
                imports.add(target)
    return imports


def _namespace(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "ALB":
        return None
    return parts[1] if parts[1] in NAMESPACES else None


def _dependency_graph() -> dict[str, set[str]]:
    graph = {namespace: set() for namespace in NAMESPACES}
    for path in PACKAGE_ROOT.rglob("*.py"):
        source_module, _ = _module_name(path)
        source = _namespace(source_module)
        if source is None:
            continue
        for target_module in _internal_imports(path):
            target = _namespace(target_module)
            if target is not None and target != source:
                graph[source].add(target)
    return graph


def _cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in path:
            cycle = path[path.index(node) :] + [node]
            body = cycle[:-1]
            rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
            found.add(min(rotations))
            return
        for target in graph[node]:
            visit(target, [*path, node])

    for namespace in graph:
        visit(namespace, [])
    return sorted(found)


def test_production_imports_obey_namespace_layers() -> None:
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        source_module, _ = _module_name(path)
        source = _namespace(source_module)
        if source is None:
            continue
        for target_module in _internal_imports(path):
            target = _namespace(target_module)
            if target is not None and target not in ALLOWED_DEPENDENCIES[source]:
                violations.append(f"{source_module} -> {target_module}")
    assert violations == []


def test_namespace_dependency_graph_is_acyclic() -> None:
    assert _cycles(_dependency_graph()) == []


def test_removed_flat_modules_are_absent_and_unimported() -> None:
    imported: dict[str, list[str]] = defaultdict(list)
    for path in PACKAGE_ROOT.rglob("*.py"):
        for target in _internal_imports(path):
            for removed in REMOVED_FLAT_MODULES:
                if target == removed or target.startswith(f"{removed}."):
                    imported[removed].append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert imported == {}
    for module in REMOVED_FLAT_MODULES:
        relative = Path(*module.split("."))
        assert not (REPOSITORY_ROOT / relative.with_suffix(".py")).exists()
        assert not (REPOSITORY_ROOT / relative).is_dir()


def test_numerical_namespaces_do_not_import_infrastructure() -> None:
    numerical = {"control", "core", "dynamics", "physics", "systems"}
    violations = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        source_module, _ = _module_name(path)
        if _namespace(source_module) not in numerical:
            continue
        if any(
            target == "ALB.infrastructure" or target.startswith("ALB.infrastructure.")
            for target in _internal_imports(path)
        ):
            violations.append(source_module)
    assert violations == []
