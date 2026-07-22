"""Canonical candidate-source helpers for reproducible release artifacts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Iterator


RELEASE_PATHS = ("ALB", "pyproject.toml")


def _git_bytes(repository_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        capture_output=True,
        check=True,
    )
    return completed.stdout


def resolve_candidate(repository_root: Path, candidate_commit: str = "HEAD") -> str:
    """Resolve a candidate revision to one immutable commit SHA."""

    return _git_bytes(repository_root, "rev-parse", f"{candidate_commit}^{{commit}}").decode(
        "ascii"
    ).strip()


def candidate_release_paths(
    repository_root: Path,
    candidate_commit: str,
) -> list[str]:
    """List release inputs from the candidate tree without checkout filters."""

    candidate_sha = resolve_candidate(repository_root, candidate_commit)
    raw = _git_bytes(
        repository_root,
        "ls-tree",
        "-r",
        "-z",
        "--name-only",
        candidate_sha,
        "--",
        *RELEASE_PATHS,
    )
    paths = sorted(item.decode("utf-8") for item in raw.split(b"\0") if item)
    if "pyproject.toml" not in paths:
        raise RuntimeError("Candidate release inputs do not include pyproject.toml")
    if not any(path.startswith("ALB/") for path in paths):
        raise RuntimeError("Candidate release inputs do not include the ALB package")
    for relative_path in paths:
        pure_path = PurePosixPath(relative_path)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise RuntimeError(f"Unsafe candidate release path: {relative_path}")
    return paths


def candidate_blob(
    repository_root: Path,
    candidate_commit: str,
    relative_path: str,
) -> bytes:
    """Read one exact Git blob from the candidate tree."""

    candidate_sha = resolve_candidate(repository_root, candidate_commit)
    if relative_path not in candidate_release_paths(repository_root, candidate_sha):
        raise ValueError(f"Path is not a candidate release input: {relative_path}")
    return _git_bytes(
        repository_root,
        "cat-file",
        "blob",
        f"{candidate_sha}:{relative_path}",
    )


def iter_candidate_blobs(
    repository_root: Path,
    candidate_commit: str,
) -> Iterator[tuple[str, bytes]]:
    """Yield stable path/blob pairs for all release inputs."""

    candidate_sha = resolve_candidate(repository_root, candidate_commit)
    for relative_path in candidate_release_paths(repository_root, candidate_sha):
        yield relative_path, _git_bytes(
            repository_root,
            "cat-file",
            "blob",
            f"{candidate_sha}:{relative_path}",
        )


def candidate_source_epoch(repository_root: Path, candidate_commit: str) -> int:
    """Return the latest commit time that changed a release input."""

    candidate_sha = resolve_candidate(repository_root, candidate_commit)
    raw = _git_bytes(
        repository_root,
        "log",
        "-1",
        "--format=%ct",
        candidate_sha,
        "--",
        *RELEASE_PATHS,
    ).decode("ascii").strip()
    if not raw:
        raise RuntimeError("Candidate has no release-input commit timestamp")
    return int(raw)


def source_tree_evidence(
    repository_root: Path,
    candidate_commit: str = "HEAD",
) -> dict[str, Any]:
    """Hash canonical Git blobs instead of filtered working-tree bytes."""

    candidate_sha = resolve_candidate(repository_root, candidate_commit)
    digest = hashlib.sha256()
    pyproject_sha256 = ""
    file_count = 0
    for relative_path, data in iter_candidate_blobs(repository_root, candidate_sha):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
        file_count += 1
        if relative_path == "pyproject.toml":
            pyproject_sha256 = hashlib.sha256(data).hexdigest()
    return {
        "candidate_commit": candidate_sha,
        "tree_sha256": digest.hexdigest(),
        "file_count": file_count,
        "pyproject_sha256": pyproject_sha256,
        "source_date_epoch": candidate_source_epoch(repository_root, candidate_sha),
        "source_kind": "git_blobs",
    }


def materialize_candidate_source(
    repository_root: Path,
    candidate_commit: str,
    destination_root: Path,
) -> dict[str, Any]:
    """Materialize exact candidate blobs with one stable release-input mtime."""

    candidate_sha = resolve_candidate(repository_root, candidate_commit)
    if destination_root.exists():
        raise FileExistsError(f"Candidate source destination exists: {destination_root}")
    destination_root.mkdir(parents=True)
    epoch = candidate_source_epoch(repository_root, candidate_sha)
    for relative_path, data in iter_candidate_blobs(repository_root, candidate_sha):
        destination = (destination_root / Path(relative_path)).resolve()
        if not destination.is_relative_to(destination_root.resolve()):
            raise RuntimeError(f"Candidate source path escaped destination: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        os.utime(destination, (epoch, epoch))
    return source_tree_evidence(repository_root, candidate_sha)
