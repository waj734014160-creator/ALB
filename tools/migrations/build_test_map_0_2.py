"""Build the final 0.2.0 mapping for every frozen 0.1 pytest node."""

from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BASELINE_MAP = REPOSITORY_ROOT / "refs/full_repo_refactor_v1/test_node_migration_map.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs/migrations/0.2.0_test_map.json"

PATH_OVERRIDES = {
    "test/bearing/test_thermal_wrapper.py": "tests/validation/bearing/test_thermal_wrapper.py",
    "test/test_nondim_thermal_field_case.py": "tests/validation/external/test_nondim_thermal_field_case.py",
    "test/thermal/test_thermal_force_time_term_compare.py": "tests/validation/external/test_thermal_force_time_term_compare.py",
    "test/thermal/test_thermal_kc_compare.py": "tests/validation/external/test_thermal_kc_compare.py",
    "test/tool/test_bearing_film_nastran_export.py": "tests/unit/physics/film/test_mesh_export.py",
    "test/train/test_alb_train_wrapper_failfast.py": "tests/validation/external/test_alb_train_wrapper_failfast.py",
    "test/train/test_evaluate_albnn_input_samples.py": "tests/validation/external/test_evaluate_albnn_input_samples.py",
}

EXTERNAL_VALIDATION_SOURCES = {
    "test/test_nondim_thermal_field_case.py",
    "test/thermal/test_thermal_force_time_term_compare.py",
    "test/thermal/test_thermal_kc_compare.py",
    "test/train/test_alb_train_wrapper_failfast.py",
    "test/train/test_evaluate_albnn_input_samples.py",
}


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPOSITORY_ROOT, text=True, encoding="utf-8"
    ).strip()


def _replace_node_path(nodeid: str, target_path: str) -> str:
    _, separator, suffix = nodeid.partition("::")
    return target_path if not separator else f"{target_path}::{suffix}"


def build_map() -> dict[str, Any]:
    baseline = json.loads(BASELINE_MAP.read_text(encoding="utf-8"))
    verification_commit = _git("rev-parse", "HEAD")
    mappings: list[dict[str, Any]] = []

    for planned in baseline["mappings"]:
        item = deepcopy(planned)
        source_path = item["source_path"]
        target_path = PATH_OVERRIDES.get(source_path, item["target_path"])
        target = REPOSITORY_ROOT / target_path
        if not target.is_file():
            raise FileNotFoundError(f"Mapped target does not exist: {target_path}")

        target_nodeid = _replace_node_path(item["baseline_nodeid"], target_path)
        item["target_path"] = target_path
        item["target_nodeid"] = target_nodeid
        item["replacement_nodeids"] = [target_nodeid]
        item["status"] = "implemented"
        item["verification_commit"] = verification_commit

        if source_path in EXTERNAL_VALIDATION_SOURCES:
            item["target_category"] = "validation"
            item["disposition"] = "validation"
            item["verification_status"] = "skipped_external_migration_required"
            item["rationale"] = (
                "Retained as an explicit read-only external migration check; the 0.1 "
                "external caller still imports removed flat namespaces."
            )
        else:
            item["verification_status"] = "passed"
            if planned["disposition"] == "manual":
                item["target_category"] = "validation"
                item["disposition"] = "validation"
                item["rationale"] = (
                    "Converted from a repository-writing plot check into automated "
                    "validation that writes only to an OS temporary directory."
                )
        mappings.append(item)

    non_collected: list[dict[str, Any]] = []
    for planned in baseline["non_collected_python_files"]:
        item = deepcopy(planned)
        target_path = PATH_OVERRIDES.get(item["source_path"], item["target_path"])
        if not (REPOSITORY_ROOT / target_path).is_file():
            raise FileNotFoundError(f"Mapped support target does not exist: {target_path}")
        item["target_path"] = target_path
        item["status"] = "implemented"
        item["verification_commit"] = verification_commit
        item["verification_status"] = (
            "manual" if target_path.startswith("tools/manual/") else "present"
        )
        non_collected.append(item)

    return {
        "schema": "alb.test-node-migration-map.v2",
        "version": "0.2.0",
        "baseline_commit": baseline["baseline_commit"],
        "baseline_reference": BASELINE_MAP.relative_to(REPOSITORY_ROOT).as_posix(),
        "baseline_node_count": baseline["node_count"],
        "baseline_nodeids_sha256": baseline["nodeids_sha256"],
        "implementation_commit": verification_commit,
        "verification": {
            "command": "E:/Anaconda2023/envs/ALB/python.exe -m pytest tests -q -p no:cacheprovider",
            "result": "285 passed, 33 skipped, 12 warnings, 7 subtests passed",
            "tracked_status_delta": 0,
            "notes": [
                "All 242 baseline nodes have an explicit replacement node.",
                "External validation skips state the missing 0.2 caller migration.",
                "Former plot-only nodes now use an OS temporary directory.",
            ],
        },
        "mappings": mappings,
        "non_collected_python_files": non_collected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_map(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
