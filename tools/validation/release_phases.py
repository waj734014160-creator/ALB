"""Reusable phases for selecting, building, testing, and recording a release.

The functions in this module deliberately avoid repository-specific policy.  They
form a small execution layer that can be reused by the ALB 0.2 acceptance runner,
future release runners, and focused unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from tools.validation.release_source_identity import (
    materialize_candidate_source,
    resolve_candidate,
    source_tree_evidence,
)


@dataclass(frozen=True)
class CandidateSelection:
    """Immutable candidate revision and canonical release-source identity."""

    repository_root: Path
    revision: str
    commit: str
    source_evidence: dict[str, Any]

    def evidence(self) -> dict[str, Any]:
        """Return JSON-compatible evidence for the candidate-selection phase."""

        return {
            "phase": "candidate_selection",
            "status": "passed",
            "revision": self.revision,
            "candidate_commit": self.commit,
            "source": self.source_evidence,
        }


@dataclass(frozen=True)
class ExportedSource:
    """Materialized canonical candidate source and its verified identity."""

    candidate: CandidateSelection
    root: Path
    source_evidence: dict[str, Any]

    def evidence(self) -> dict[str, Any]:
        """Return JSON-compatible evidence for the source-export phase."""

        return {
            "phase": "source_export",
            "status": "passed",
            "candidate_commit": self.candidate.commit,
            "root": str(self.root),
            "source": self.source_evidence,
        }


@dataclass(frozen=True)
class CommandPhaseResult:
    """Result of one isolated build, install, or test subprocess."""

    phase: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    def require_success(self) -> "CommandPhaseResult":
        """Return this result or raise with the complete failed subprocess output."""

        if self.returncode != 0:
            raise RuntimeError(
                f"Release {self.phase} phase failed:\n{self.stdout}{self.stderr}"
            )
        return self

    def evidence(self) -> dict[str, Any]:
        """Return compact JSON-compatible evidence for this command phase."""

        return {
            "phase": self.phase,
            "status": "passed" if self.returncode == 0 else "failed",
            "command": subprocess.list2cmdline(list(self.command)),
            "returncode": self.returncode,
            "stdout_tail": self.stdout.splitlines()[-20:],
            "stderr_tail": self.stderr.splitlines()[-20:],
        }


@dataclass(frozen=True)
class BuiltWheel:
    """Wheel produced from one exported candidate source tree."""

    exported_source: ExportedSource
    wheel: Path
    result: CommandPhaseResult

    def evidence(self) -> dict[str, Any]:
        """Return JSON-compatible evidence for the build phase."""

        payload = self.result.evidence()
        payload.update(
            {
                "candidate_commit": self.exported_source.candidate.commit,
                "source_root": str(self.exported_source.root),
                "wheel": str(self.wheel),
            }
        )
        return payload


@dataclass(frozen=True)
class InstalledWheel:
    """Isolated installation produced from one exact wheel file."""

    wheel: Path
    root: Path
    result: CommandPhaseResult

    def evidence(self) -> dict[str, Any]:
        """Return JSON-compatible evidence for the installation phase."""

        payload = self.result.evidence()
        payload.update({"wheel": str(self.wheel), "root": str(self.root)})
        return payload


def _run_command(
    phase: str,
    command: Sequence[str],
    *,
    repository_root: Path,
    environment: Mapping[str, str],
) -> CommandPhaseResult:
    completed = subprocess.run(
        list(command),
        cwd=repository_root,
        env=dict(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return CommandPhaseResult(
        phase=phase,
        command=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def isolated_module_command(
    python: Path,
    module: str,
    *args: str,
    dependency_paths: tuple[Path, ...] = (),
) -> list[str]:
    """Return an isolated Python module command with explicit dependency roots."""

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


def select_candidate(
    repository_root: Path,
    revision: str = "HEAD",
) -> CandidateSelection:
    """Resolve one revision and bind it to canonical Git-blob source evidence."""

    root = repository_root.resolve()
    commit = resolve_candidate(root, revision)
    return CandidateSelection(
        repository_root=root,
        revision=revision,
        commit=commit,
        source_evidence=source_tree_evidence(root, commit),
    )


def export_source_phase(
    candidate: CandidateSelection,
    destination_root: Path,
) -> ExportedSource:
    """Export exact candidate blobs and verify the resulting source identity."""

    evidence = materialize_candidate_source(
        candidate.repository_root,
        candidate.commit,
        destination_root,
    )
    if evidence != candidate.source_evidence:
        raise AssertionError("Exported source differs from selected candidate identity")
    return ExportedSource(candidate, destination_root.resolve(), evidence)


def build_wheel_phase(
    *,
    python: Path,
    exported_source: ExportedSource,
    output_root: Path,
    environment: Mapping[str, str],
    dependency_paths: tuple[Path, ...] = (),
    build_tag: str = "1",
) -> BuiltWheel:
    """Build exactly one wheel from one exported candidate source tree."""

    if output_root.exists():
        raise FileExistsError(f"Release wheel output exists: {output_root}")
    output_root.mkdir(parents=True)
    build_environment = dict(environment)
    build_environment["SOURCE_DATE_EPOCH"] = str(
        exported_source.source_evidence["source_date_epoch"]
    )
    command = isolated_module_command(
        python,
        "build",
        "--wheel",
        "--outdir",
        str(output_root),
        f"-C--build-option=--build-number={build_tag}",
        str(exported_source.root),
        dependency_paths=dependency_paths,
    )
    result = _run_command(
        "build",
        command,
        repository_root=exported_source.candidate.repository_root,
        environment=build_environment,
    ).require_success()
    wheels = list(output_root.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one release wheel, found {len(wheels)}")
    return BuiltWheel(exported_source, wheels[0].resolve(), result)


def install_wheel_phase(
    *,
    python: Path,
    repository_root: Path,
    wheel: Path,
    destination_root: Path,
    environment: Mapping[str, str],
) -> InstalledWheel:
    """Install one exact wheel into a fresh isolated target directory."""

    if destination_root.exists():
        raise FileExistsError(f"Release installation target exists: {destination_root}")
    command = [
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
        str(destination_root),
        str(wheel),
    ]
    result = _run_command(
        "install",
        command,
        repository_root=repository_root,
        environment=environment,
    ).require_success()
    return InstalledWheel(wheel.resolve(), destination_root.resolve(), result)


def run_test_phase(
    command: Sequence[str],
    *,
    repository_root: Path,
    environment: Mapping[str, str],
    phase: str = "test",
) -> CommandPhaseResult:
    """Run an isolated test or static-analysis command as an explicit phase."""

    return _run_command(
        phase,
        command,
        repository_root=repository_root,
        environment=environment,
    )


def evidence_phase(
    output: Path,
    payload: dict[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write one UTF-8 JSON evidence artifact without accidental overwrite."""

    if output.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite release evidence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "phase": "evidence_generation",
        "status": "passed",
        "path": str(output.resolve()),
        "bytes": output.stat().st_size,
    }


def publish_wheel_phase(
    staging: Path,
    destination: Path,
    *,
    expected_sha256: str,
) -> dict[str, Any]:
    """Atomically publish staged wheel bytes after verifying their identity."""

    import hashlib

    actual = hashlib.sha256(staging.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise AssertionError("Staged wheel bytes differ from accepted identity")
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, destination)
    published = hashlib.sha256(destination.read_bytes()).hexdigest()
    if published != expected_sha256:
        raise AssertionError("Published wheel bytes differ from accepted identity")
    return {
        "phase": "publish",
        "status": "passed",
        "path": str(destination.resolve()),
        "sha256": published,
    }
