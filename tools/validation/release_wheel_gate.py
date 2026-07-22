"""Build and validate the exact wheel consumed by release acceptance."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from tools.validation.validate_wheel_0_2 import validate


@dataclass(frozen=True)
class ReleaseWheelGateResult:
    """Inspectable paths, commands, and payload from one wheel gate run."""

    payload: dict[str, Any]
    build_command: list[str]
    install_command: list[str]
    wheel: Path
    installed_root: Path
    report_path: Path
    wheel_root: Path
    build_source_root: Path


def _run(
    command: list[str],
    *,
    repository_root: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _isolated_module_command(
    python: Path,
    module: str,
    *args: str,
    dependency_paths: tuple[Path, ...] = (),
) -> list[str]:
    """Run a module in isolated mode with only explicit tool roots prepended."""

    path_bootstrap = "".join(
        f"sys.path.insert({index}, {str(path)!r});"
        for index, path in reversed(list(enumerate(dependency_paths)))
    )
    bootstrap = (
        "import runpy,sys;"
        f"{path_bootstrap}"
        f"sys.argv=[{module!r}, *sys.argv[1:]];"
        f"runpy.run_module({module!r}, run_name='__main__')"
    )
    return [str(python), "-I", "-c", bootstrap, *args]


def _copy_tracked_build_inputs(
    repository_root: Path,
    build_source_root: Path,
) -> None:
    """Copy only committed package inputs into a run-owned build directory."""

    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "ALB", "pyproject.toml"],
        cwd=repository_root,
        capture_output=True,
        check=True,
    )
    relative_paths = [
        Path(item.decode("utf-8"))
        for item in completed.stdout.split(b"\0")
        if item
    ]
    if Path("pyproject.toml") not in relative_paths:
        raise RuntimeError("Tracked wheel inputs do not include pyproject.toml")
    if not any(path.parts and path.parts[0] == "ALB" for path in relative_paths):
        raise RuntimeError("Tracked wheel inputs do not include the ALB package")
    build_source_root.mkdir(parents=True)
    for relative_path in relative_paths:
        source = (repository_root / relative_path).resolve()
        destination = (build_source_root / relative_path).resolve()
        if not source.is_relative_to(repository_root.resolve()):
            raise RuntimeError(f"Build input escaped repository root: {source}")
        if not destination.is_relative_to(build_source_root.resolve()):
            raise RuntimeError(f"Build input escaped runtime root: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_and_validate_wheel(
    *,
    python: Path,
    repository_root: Path,
    runtime_root: Path,
    run_token: str,
    environment: dict[str, str],
    dependency_paths: tuple[Path, ...],
) -> ReleaseWheelGateResult:
    """Build one wheel, install it in isolation, and validate source identity."""

    wheel_root = runtime_root / f"wheel_{run_token}"
    installed_root = runtime_root / f"wheel_install_{run_token}"
    report_path = runtime_root / f"wheel_report_{run_token}.json"
    build_source_root = runtime_root / f"wheel_source_{run_token}"
    for path in (wheel_root, installed_root, report_path, build_source_root):
        if path.exists():
            raise FileExistsError(f"Release wheel path already exists: {path}")
    wheel_root.mkdir(parents=True)
    _copy_tracked_build_inputs(repository_root, build_source_root)

    build_command = _isolated_module_command(
        python,
        "build",
        "--wheel",
        "--outdir",
        str(wheel_root),
        str(build_source_root),
        dependency_paths=dependency_paths,
    )
    build_run = _run(
        build_command,
        repository_root=repository_root,
        environment=environment,
    )
    if build_run.returncode != 0:
        raise RuntimeError(
            "Release wheel build failed:\n" + build_run.stdout + build_run.stderr
        )
    wheels = list(wheel_root.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one release wheel, found {len(wheels)}")
    wheel = wheels[0].resolve()

    install_command = [
        str(python),
        "-I",
        "-m",
        "pip",
        "install",
        "--isolated",
        "--disable-pip-version-check",
        "--no-input",
        "--no-compile",
        "--no-deps",
        "--target",
        str(installed_root),
        str(wheel),
    ]
    install_run = _run(
        install_command,
        repository_root=repository_root,
        environment=environment,
    )
    if install_run.returncode != 0:
        raise RuntimeError(
            "Release wheel isolated installation failed:\n"
            + install_run.stdout
            + install_run.stderr
        )

    payload = validate(
        wheel,
        installed_root,
        dependency_paths=dependency_paths,
    )
    payload["commands"] = {
        "build": subprocess.list2cmdline(build_command),
        "build_returncode": build_run.returncode,
        "install": subprocess.list2cmdline(install_command),
        "install_returncode": install_run.returncode,
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ReleaseWheelGateResult(
        payload=payload,
        build_command=build_command,
        install_command=install_command,
        wheel=wheel,
        installed_root=installed_root,
        report_path=report_path,
        wheel_root=wheel_root,
        build_source_root=build_source_root,
    )
