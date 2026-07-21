"""Validate the audited PAPER_WORK consumer migration without running jobs."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import sys
from pathlib import Path


LEGACY_MODULES = {
    "ALB.alb",
    "ALB.base",
    "ALB.bearing",
    "ALB.config",
    "ALB.film",
    "ALB.nn",
    "ALB.nondim",
    "ALB.orbit",
    "ALB.orifice",
    "ALB.remote",
    "ALB.results",
    "ALB.tool",
}


def _has_main_guard(tree: ast.Module) -> bool:
    """Return whether a module has a conventional ``__main__`` guard."""

    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        if any(
            isinstance(item, ast.Constant) and item.value == "__main__"
            for item in ast.walk(node.test)
        ):
            return True
    return False


def main() -> None:
    """Check syntax, imports, package paths, and safe import-time behavior."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-root", type=Path, required=True)
    args = parser.parse_args()
    paper_root = args.paper_root.resolve()
    manifest_path = (
        paper_root / "refs" / "alb_0_2_consumer_migration_v1" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    os.environ.setdefault("MPLBACKEND", "Agg")
    for path in (Path(__file__).resolve().parents[2], paper_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    imported = []
    ast_only = []
    failures = []
    for index, entry in enumerate(manifest["entries"]):
        relative = entry["path"]
        path = paper_root / relative
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in LEGACY_MODULES:
                        failures.append(f"{relative}: legacy import {alias.name}")
            if module in LEGACY_MODULES:
                failures.append(f"{relative}: legacy import {module}")
        if '"ALB" / "alb.py"' in text:
            failures.append(f"{relative}: deleted ALB/alb.py sentinel")

        if not _has_main_guard(tree) or relative == "run/remote/remote_job.py":
            ast_only.append(relative)
            continue
        name = f"_paper_migration_smoke_{index}"
        try:
            parent = str(path.parent)
            if parent not in sys.path:
                sys.path.insert(0, parent)
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError("cannot create import specification")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            imported.append(relative)
        except Exception as error:  # pragma: no cover - CLI diagnostic path
            failures.append(f"{relative}: {type(error).__name__}: {error}")

    report = {
        "schema": "alb.paper-work-migration-validation.v0.2",
        "declared_and_helper_count": len(manifest["entries"]),
        "import_smoke_count": len(imported),
        "ast_only_count": len(ast_only),
        "imported": imported,
        "ast_only": ast_only,
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
