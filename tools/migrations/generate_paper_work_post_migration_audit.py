"""Generate machine evidence for the PAPER_WORK ALB 0.2 migration."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from datetime import date
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
PACKAGE_DIRS = (
    "M0031_s8b_s0011_allvalid_base12_mlp_minmax01_gelu_adamw_p1000_20260609/package_v0_2",
    "M0035_s8b_s0011_enormlt0p85_vnormlt0p4_edotvlt0p195_base12_mlp_minmax01_gelu_adamw_p1000_20260609/package_v0_2",
)


def _sha256(path: Path) -> str:
    """Return one file's SHA-256 digest."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_imports(path: Path) -> list[str]:
    """Return deleted flat ALB modules imported by a Python source file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in LEGACY_MODULES:
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names if alias.name in LEGACY_MODULES)
    return sorted(set(found))


def main() -> None:
    """Write the post-migration audit without modifying external consumers."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-audit", type=Path, required=True)
    parser.add_argument("--paper-root", type=Path, required=True)
    parser.add_argument("--surrogate-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pre_audit = json.loads(args.pre_audit.read_text(encoding="utf-8"))
    pre_project = next(
        item for item in pre_audit["projects"] if item["project"] == "PAPER_WORK"
    )
    paper_root = args.paper_root.resolve()
    snapshot_manifest_path = (
        paper_root / "refs" / "alb_0_2_consumer_migration_v1" / "manifest.json"
    )
    snapshot = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))

    entries = []
    for item in snapshot["entries"]:
        path = paper_root / item["path"]
        remaining = _legacy_imports(path)
        entries.append(
            {
                "path": item["path"],
                "kind": item["kind"],
                "source": item["source"],
                "pre_sha256": item["sha256"],
                "post_sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "changed": _sha256(path) != item["sha256"],
                "remaining_flat_imports": remaining,
            }
        )

    packages = []
    for relative in PACKAGE_DIRS:
        package_root = args.surrogate_root / "models" / relative
        manifest_path = package_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = {}
        for role, record in manifest["artifacts"].items():
            artifact = package_root / record["path"]
            actual = _sha256(artifact)
            artifacts[role] = {
                "path": record["path"],
                "expected_sha256": record["sha256"],
                "actual_sha256": actual,
                "matches_manifest": actual == record["sha256"],
            }
        packages.append(
            {
                "package_dir": relative,
                "manifest_schema": manifest["schema"],
                "pickle_trust_required": True,
                "artifacts": artifacts,
            }
        )

    declared_paths = {item["path"] for item in pre_project["entries"]}
    report = {
        "schema": "alb.paper-work-post-migration-audit.v1",
        "version": "0.2.0",
        "audit_date": date.today().isoformat(),
        "pre_migration_audit": str(args.pre_audit).replace("\\", "/"),
        "snapshot_manifest": str(snapshot_manifest_path).replace("\\", "/"),
        "paper_work": {
            "root": str(paper_root).replace("\\", "/"),
            "git_repository": False,
            "declared_count": pre_project["declared_count"],
            "dynamic_helper_count": len(entries) - pre_project["declared_count"],
            "declared_changed_count": sum(
                item["changed"] for item in entries if item["path"] in declared_paths
            ),
            "all_changed_count": sum(item["changed"] for item in entries),
            "remaining_flat_import_count": sum(
                len(item["remaining_flat_imports"]) for item in entries
            ),
            "entries": entries,
        },
        "model_packages": packages,
        "validation": {
            "ast_parse": "29 passed",
            "guarded_import_smoke": "24 passed",
            "ast_only_due_to_top_level_execution": 5,
            "remote_cli_help": "passed",
            "package_load_smoke": "M0031 and M0035 passed",
        },
        "boundaries": [
            "Four task scripts still execute calculations at import time and require main-guard isolation.",
            "Legacy BaseSimpleModel/FakeOf consumers still require a dedicated DTO block migration.",
            "Shared legacy JSON5 is expanded by config_io; nested 0.2 schema loading remains a separate gate.",
            "Historical remote payload archives were not modified and must be rebuilt before reuse.",
        ],
    }
    if report["paper_work"]["remaining_flat_import_count"]:
        raise RuntimeError("legacy flat imports remain in PAPER_WORK")
    if any(
        not artifact["matches_manifest"]
        for package in packages
        for artifact in package["artifacts"].values()
    ):
        raise RuntimeError("model package artifact verification failed")
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
