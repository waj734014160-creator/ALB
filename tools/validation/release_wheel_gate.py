"""Build and validate the exact wheel consumed by release acceptance."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from tools.validation.release_source_identity import (
    materialize_candidate_source,
    resolve_candidate,
)
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
    reproducibility_wheel_root: Path
    reproducibility_build_source_root: Path


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _one_wheel(path: Path) -> Path:
    wheels = list(path.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one release wheel, found {len(wheels)}")
    return wheels[0].resolve()


def build_and_validate_wheel(
    *,
    python: Path,
    repository_root: Path,
    runtime_root: Path,
    run_token: str,
    environment: dict[str, str],
    dependency_paths: tuple[Path, ...],
    candidate_commit: str = "HEAD",
    build_tag: str = "1",
) -> ReleaseWheelGateResult:
    """Build one wheel, install it in isolation, and validate source identity."""

    candidate_sha = resolve_candidate(repository_root, candidate_commit)
    wheel_root = runtime_root / f"wheel_{run_token}"
    reproducibility_wheel_root = runtime_root / f"wheel_repeat_{run_token}"
    installed_root = runtime_root / f"wheel_install_{run_token}"
    report_path = runtime_root / f"wheel_report_{run_token}.json"
    build_source_root = runtime_root / f"wheel_source_{run_token}"
    reproducibility_build_source_root = runtime_root / f"wheel_source_repeat_{run_token}"
    for path in (
        wheel_root,
        reproducibility_wheel_root,
        installed_root,
        report_path,
        build_source_root,
        reproducibility_build_source_root,
    ):
        if path.exists():
            raise FileExistsError(f"Release wheel path already exists: {path}")
    wheel_root.mkdir(parents=True)
    reproducibility_wheel_root.mkdir(parents=True)
    source_evidence = materialize_candidate_source(
        repository_root,
        candidate_sha,
        build_source_root,
    )
    repeated_source_evidence = materialize_candidate_source(
        repository_root,
        candidate_sha,
        reproducibility_build_source_root,
    )
    if source_evidence != repeated_source_evidence:
        raise AssertionError("Repeated candidate source materialization changed identity")

    build_environment = environment.copy()
    build_environment["SOURCE_DATE_EPOCH"] = str(source_evidence["source_date_epoch"])

    build_command = _isolated_module_command(
        python,
        "build",
        "--wheel",
        "--outdir",
        str(wheel_root),
        f"-C--build-option=--build-number={build_tag}",
        str(build_source_root),
        dependency_paths=dependency_paths,
    )
    build_run = _run(
        build_command,
        repository_root=repository_root,
        environment=build_environment,
    )
    if build_run.returncode != 0:
        raise RuntimeError(
            "Release wheel build failed:\n" + build_run.stdout + build_run.stderr
        )
    wheel = _one_wheel(wheel_root)
    reproducibility_build_command = _isolated_module_command(
        python,
        "build",
        "--wheel",
        "--outdir",
        str(reproducibility_wheel_root),
        f"-C--build-option=--build-number={build_tag}",
        str(reproducibility_build_source_root),
        dependency_paths=dependency_paths,
    )
    reproducibility_build_run = _run(
        reproducibility_build_command,
        repository_root=repository_root,
        environment=build_environment,
    )
    if reproducibility_build_run.returncode != 0:
        raise RuntimeError(
            "Repeated release wheel build failed:\n"
            + reproducibility_build_run.stdout
            + reproducibility_build_run.stderr
        )
    repeated_wheel = _one_wheel(reproducibility_wheel_root)
    wheel_sha256 = _sha256(wheel)
    repeated_wheel_sha256 = _sha256(repeated_wheel)
    if wheel.name != repeated_wheel.name or wheel_sha256 != repeated_wheel_sha256:
        raise AssertionError(
            "Same candidate did not produce identical wheel bytes: "
            f"first={wheel.name}:{wheel_sha256}, "
            f"second={repeated_wheel.name}:{repeated_wheel_sha256}"
        )

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
        candidate_commit=candidate_sha,
        expected_build_tag=build_tag,
    )
    payload["reproducible_build"] = {
        "candidate_commit": candidate_sha,
        "source_kind": source_evidence["source_kind"],
        "source_date_epoch": source_evidence["source_date_epoch"],
        "build_tag": build_tag,
        "first_filename": wheel.name,
        "second_filename": repeated_wheel.name,
        "first_sha256": wheel_sha256,
        "second_sha256": repeated_wheel_sha256,
        "sha256_equal": True,
    }
    payload["commands"] = {
        "build": subprocess.list2cmdline(build_command),
        "build_returncode": build_run.returncode,
        "reproducibility_build": subprocess.list2cmdline(
            reproducibility_build_command
        ),
        "reproducibility_build_returncode": reproducibility_build_run.returncode,
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
        reproducibility_wheel_root=reproducibility_wheel_root,
        reproducibility_build_source_root=reproducibility_build_source_root,
    )
