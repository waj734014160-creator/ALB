"""Helpers for tests that reach across the split ALB workspace."""

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
import types
from typing import Iterable
from uuid import uuid4


_MISSING = object()


def find_split_workspace_root(start: Path | None = None) -> Path:
    """Return the directory that owns ALB_MAIN and its sibling projects."""
    current = (start or Path(__file__)).resolve()
    for parent in (current, *current.parents):
        if parent.name == "ALB_MAIN" and (parent.parent / "VALIDATION").is_dir():
            return parent.parent
        if (parent / "ALB_MAIN").is_dir() and (parent / "VALIDATION").is_dir():
            return parent
    raise FileNotFoundError(
        f"Could not locate split workspace root from {current}. "
        "Expected sibling projects such as ALB_MAIN and VALIDATION."
    )


def _load_module_from_file(file_path: Path, project: str, module_name: str):
    unique_name = f"_split_{project.lower()}_run_{module_name}_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not build import spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(unique_name, None)
        raise
    return module


@contextmanager
def _temporary_run_package(run_dir: Path, preloaded_modules: dict[str, object]):
    saved_modules = {
        key: sys.modules.get(key, _MISSING)
        for key in list(sys.modules)
        if key == "run" or key.startswith("run.")
    }

    package = types.ModuleType("run")
    package.__file__ = str(run_dir / "__init__.py")
    package.__path__ = [str(run_dir)]
    package.__package__ = "run"
    sys.modules["run"] = package
    for name, module in preloaded_modules.items():
        setattr(package, name, module)
        sys.modules[f"run.{name}"] = module

    try:
        yield
    finally:
        for key in list(sys.modules):
            if key == "run" or key.startswith("run."):
                sys.modules.pop(key, None)
        for key, module in saved_modules.items():
            if module is _MISSING:
                continue
            sys.modules[key] = module


def import_project_run_module(
    project: str,
    name: str,
    *,
    dependencies: Iterable[str] = (),
):
    """Load a sibling project's run script by absolute path with an isolated name."""
    workspace_root = find_split_workspace_root()
    run_dir = workspace_root / project / "run"
    file_path = run_dir / f"{name}.py"
    if not file_path.exists():
        raise ImportError(f"Could not locate {project}/run/{name}.py at {file_path}")

    preloaded = {}
    for dependency in dependencies:
        dependency_path = run_dir / f"{dependency}.py"
        if not dependency_path.exists():
            raise ImportError(
                f"Could not locate dependency {project}/run/{dependency}.py "
                f"at {dependency_path}"
            )
        preloaded[dependency] = _load_module_from_file(
            dependency_path,
            project,
            dependency,
        )

    with _temporary_run_package(run_dir, preloaded):
        return _load_module_from_file(file_path, project, name)


def import_validation_run_module(name: str, *, dependencies: Iterable[str] = ()):
    """Load a VALIDATION/run script without relying on sys.path ordering."""
    return import_project_run_module("VALIDATION", name, dependencies=dependencies)


def missing_required_files(
    config_dir: Path,
    required_files: Iterable[str],
) -> tuple[str, ...]:
    """Return required files that are absent from a config directory."""
    return tuple(name for name in required_files if not (config_dir / name).is_file())


def select_paper_config_dir(repo_root: Path, required_files: Iterable[str]) -> Path:
    """Select the complete PAPER config directory, preferring PARAM_SCAN."""
    required = tuple(required_files)
    candidates = (
        (
            "PARAM_SCAN sibling",
            repo_root.parent / "PARAM_SCAN" / "task" / "PAPER" / "config",
        ),
        ("ALB_MAIN local fallback", repo_root / "task" / "PAPER" / "config"),
    )

    failures = []
    for label, config_dir in candidates:
        if not config_dir.is_dir():
            failures.append(f"{label}: directory missing at {config_dir}")
            continue
        missing = missing_required_files(config_dir, required)
        if not missing:
            return config_dir
        failures.append(f"{label}: missing {', '.join(missing)} at {config_dir}")

    raise FileNotFoundError(
        "Could not locate a complete PAPER config directory. "
        f"Required files: {', '.join(required)}. Checked: "
        + " | ".join(failures)
    )
