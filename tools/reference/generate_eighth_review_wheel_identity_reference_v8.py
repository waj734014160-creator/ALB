"""Freeze canonical Git-blob inputs before wheel identity maintenance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "refs/eighth_review_wheel_identity_reference_v8.json"


def _git(*args: str, text: bool = True) -> str | bytes:
    """Run Git without applying working-tree filters to candidate blobs."""

    completed = subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=True,
    )
    if text:
        return completed.stdout.decode("utf-8").strip()
    return completed.stdout


def _candidate_paths(candidate_commit: str) -> list[str]:
    raw = _git(
        "ls-tree",
        "-r",
        "-z",
        "--name-only",
        candidate_commit,
        "--",
        "ALB",
        "pyproject.toml",
        text=False,
    )
    assert isinstance(raw, bytes)
    return sorted(item.decode("utf-8") for item in raw.split(b"\0") if item)


def _blob(candidate_commit: str, relative_path: str) -> bytes:
    data = _git("cat-file", "blob", f"{candidate_commit}:{relative_path}", text=False)
    assert isinstance(data, bytes)
    return data


def _canonical_source(candidate_commit: str) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: dict[str, dict[str, Any]] = {}
    for relative_path in _candidate_paths(candidate_commit):
        data = _blob(candidate_commit, relative_path)
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
        files[relative_path] = {
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return {
        "tree_sha256": digest.hexdigest(),
        "file_count": len(files),
        "alb_file_count": sum(path.startswith("ALB/") for path in files),
        "pyproject_sha256": files["pyproject.toml"]["sha256"],
        "files": files,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(output: Path) -> dict[str, Any]:
    """Record the immutable candidate inputs and the evidence mismatch."""

    candidate_commit = str(_git("rev-parse", "HEAD"))
    build_report = json.loads(
        (REPOSITORY_ROOT / "docs/migrations/0.2.0_build_acceptance.json").read_text(
            encoding="utf-8"
        )
    )
    detached_report = json.loads(
        (
            REPOSITORY_ROOT
            / "docs/migrations/0.2.0_seventh_review_acceptance.json"
        ).read_text(encoding="utf-8")
    )
    payload = {
        "schema": "alb.eighth-review-wheel-identity-reference.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": candidate_commit,
        "canonical_source": _canonical_source(candidate_commit),
        "prior_evidence": {
            "published_build": {
                "candidate_commit": build_report["candidate_commit"],
                "source_tree_sha256": build_report["source"]["tree_sha256"],
                "wheel_path": build_report["wheel"]["path"],
                "wheel_sha256": build_report["wheel"]["sha256"],
            },
            "detached_acceptance": {
                "candidate_commit": detached_report["candidate_commit"],
                "source_tree_sha256": detached_report["wheel"]["source"][
                    "tree_sha256"
                ],
                "wheel_path": detached_report["wheel"]["wheel"]["path"],
                "wheel_sha256": detached_report["wheel"]["wheel"]["sha256"],
            },
        },
        "behavior_reference_integrity": {
            "json_sha256": _sha256(
                REPOSITORY_ROOT / "refs/seventh_review_release_reference_v7.json"
            ),
            "npz_sha256": _sha256(
                REPOSITORY_ROOT / "refs/seventh_review_release_reference_v7.npz"
            ),
        },
    }
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite reference: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = generate(args.output.resolve())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
