"""Build and validate the exact wheel consumed by release acceptance."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from tools.validation.release_phases import (
    build_wheel_phase,
    export_source_phase,
    install_wheel_phase,
    select_candidate,
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    candidate = select_candidate(repository_root, candidate_commit)
    candidate_sha = candidate.commit
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
    exported_source = export_source_phase(candidate, build_source_root)
    repeated_exported_source = export_source_phase(
        candidate, reproducibility_build_source_root
    )
    source_evidence = exported_source.source_evidence
    repeated_source_evidence = repeated_exported_source.source_evidence
    if source_evidence != repeated_source_evidence:
        raise AssertionError("Repeated candidate source materialization changed identity")

    built_wheel = build_wheel_phase(
        python=python,
        exported_source=exported_source,
        output_root=wheel_root,
        environment=environment,
        dependency_paths=dependency_paths,
        build_tag=build_tag,
    )
    repeated_built_wheel = build_wheel_phase(
        python=python,
        exported_source=repeated_exported_source,
        output_root=reproducibility_wheel_root,
        environment=environment,
        dependency_paths=dependency_paths,
        build_tag=build_tag,
    )
    wheel = built_wheel.wheel
    repeated_wheel = repeated_built_wheel.wheel
    wheel_sha256 = _sha256(wheel)
    repeated_wheel_sha256 = _sha256(repeated_wheel)
    if wheel.name != repeated_wheel.name or wheel_sha256 != repeated_wheel_sha256:
        raise AssertionError(
            "Same candidate did not produce identical wheel bytes: "
            f"first={wheel.name}:{wheel_sha256}, "
            f"second={repeated_wheel.name}:{repeated_wheel_sha256}"
        )

    installed_wheel = install_wheel_phase(
        python=python,
        repository_root=repository_root,
        wheel=wheel,
        destination_root=installed_root,
        environment=environment,
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
        "build": subprocess.list2cmdline(list(built_wheel.result.command)),
        "build_returncode": built_wheel.result.returncode,
        "reproducibility_build": subprocess.list2cmdline(
            list(repeated_built_wheel.result.command)
        ),
        "reproducibility_build_returncode": repeated_built_wheel.result.returncode,
        "install": subprocess.list2cmdline(list(installed_wheel.result.command)),
        "install_returncode": installed_wheel.result.returncode,
    }
    payload["phases"] = {
        "candidate_selection": candidate.evidence(),
        "source_export": exported_source.evidence(),
        "build": built_wheel.evidence(),
        "reproducibility_source_export": repeated_exported_source.evidence(),
        "reproducibility_build": repeated_built_wheel.evidence(),
        "install": installed_wheel.evidence(),
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ReleaseWheelGateResult(
        payload=payload,
        build_command=list(built_wheel.result.command),
        install_command=list(installed_wheel.result.command),
        wheel=wheel,
        installed_root=installed_root,
        report_path=report_path,
        wheel_root=wheel_root,
        build_source_root=build_source_root,
        reproducibility_wheel_root=reproducibility_wheel_root,
        reproducibility_build_source_root=reproducibility_build_source_root,
    )
