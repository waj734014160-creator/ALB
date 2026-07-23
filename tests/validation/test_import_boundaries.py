"""Validate the 0.2 namespace layering and absence of package cycles."""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from importlib.util import resolve_name
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "ALB"
IMPORT_MAP_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_import_map.json"
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
ALLOWED_DEPENDENCIES = {
    "contracts": {"contracts"},
    "core": {"contracts", "core"},
    "config": {"config", "contracts", "core"},
    "physics": {"config", "contracts", "core", "physics"},
    "infrastructure": {"config", "contracts", "core", "infrastructure"},
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
LEGACY_SIGNAL_IMPORT_PATHS = {
    "ALB/core/__init__.py",
    "ALB/core/component.py",
    "ALB/core/fem/base.py",
    "ALB/dynamics/rotor.py",
    "ALB/infrastructure/legacy_signal.py",
    "ALB/systems/alb/builder.py",
    "ALB/systems/alb/factories.py",
    "ALB/systems/alb/linear.py",
    "ALB/systems/alb/runtime.py",
    "ALB/systems/alb/switch.py",
}
LEGACY_SIGNAL_LEAD_LOOP_COUNTS = {
    "ALB/dynamics/coupling.py": 1,
    "ALB/dynamics/rotor.py": 1,
    "ALB/infrastructure/legacy_signal.py": 1,
    "ALB/physics/bearing/solver.py": 1,
    "ALB/physics/film/solver.py": 3,
    "ALB/physics/hydraulics/orifice.py": 1,
    "ALB/systems/alb/linear.py": 1,
}


def _module_name(path: Path) -> tuple[str, str]:
    relative = path.relative_to(REPOSITORY_ROOT).with_suffix("")
    module = ".".join(relative.parts)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    if module.endswith(".__init__"):
        module = module.removesuffix(".__init__")
    return module, package


def _package_modules() -> set[str]:
    return {_module_name(path)[0] for path in PACKAGE_ROOT.rglob("*.py")}


PACKAGE_MODULES = _package_modules()


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
                for alias in node.names:
                    candidate = f"ALB.{alias.name}"
                    if candidate in PACKAGE_MODULES:
                        imports.add(candidate)
            elif target.startswith("ALB."):
                imports.add(target)
                for alias in node.names:
                    candidate = f"{target}.{alias.name}"
                    if candidate in PACKAGE_MODULES:
                        imports.add(candidate)
    return imports


def _removed_flat_modules() -> set[str]:
    import_map = json.loads(IMPORT_MAP_PATH.read_text(encoding="utf-8"))
    return {
        item["source"]
        for item in import_map["module_mappings"]
        if item["status"] == "migrated"
    }


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


def _module_dependency_graph() -> dict[str, set[str]]:
    modules = PACKAGE_MODULES
    graph = {module: set() for module in modules}
    for path in PACKAGE_ROOT.rglob("*.py"):
        source_module, _ = _module_name(path)
        graph[source_module].update(
            target for target in _internal_imports(path) if target in modules
        )
    return graph


def _strongly_connected_components(
    graph: dict[str, set[str]],
) -> list[tuple[str, ...]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph[node]:
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while True:
            target = stack.pop()
            on_stack.remove(target)
            component.append(target)
            if target == node:
                break
        components.append(tuple(sorted(component)))

    for module in sorted(graph):
        if module not in indices:
            visit(module)
    return sorted(components)


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


def test_module_dependency_graph_is_acyclic() -> None:
    graph = _module_dependency_graph()
    cycles = [
        component
        for component in _strongly_connected_components(graph)
        if len(component) > 1
        or (len(component) == 1 and component[0] in graph[component[0]])
    ]
    assert cycles == []


def test_removed_flat_modules_are_absent_and_unimported() -> None:
    removed_flat_modules = _removed_flat_modules()
    imported: dict[str, list[str]] = defaultdict(list)
    for path in PACKAGE_ROOT.rglob("*.py"):
        for target in _internal_imports(path):
            for removed in removed_flat_modules:
                if target == removed or target.startswith(f"{removed}."):
                    imported[removed].append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert imported == {}
    for module in removed_flat_modules:
        relative = Path(*module.split("."))
        assert not (REPOSITORY_ROOT / relative.with_suffix(".py")).exists()
        assert not (REPOSITORY_ROOT / relative / "__init__.py").exists()


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


def test_signal_migration_debt_is_frozen_by_ast_boundary() -> None:
    """Prevent new Signal consumers while the 0.3 compatibility set is retired."""

    imports: set[str] = set()
    lead_loop_counts: dict[str, int] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        lead_loop_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = node.module or ""
                if node.level:
                    module, package = _module_name(path)
                    if path.name == "__init__.py":
                        package = module
                    target = resolve_name("." * node.level + target, package)
                if target == "ALB.core.events" and any(
                    alias.name == "Signal" for alias in node.names
                ):
                    imports.add(relative)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "lead_loop"
            ):
                lead_loop_count += 1
        if lead_loop_count:
            lead_loop_counts[relative] = lead_loop_count

    assert imports == LEGACY_SIGNAL_IMPORT_PATHS
    assert lead_loop_counts == LEGACY_SIGNAL_LEAD_LOOP_COUNTS
