"""Run final pytest and mypy gates and write inspectable 0.2 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
import uuid


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs/migrations/0.2.0_release_acceptance.json"
RUNTIME_ROOT = REPOSITORY_ROOT / "outputs/release_acceptance"
DEVTOOLS_ROOT = REPOSITORY_ROOT / "outputs/.devtools"
PYTHON = Path("E:/Anaconda2023/envs/ALB/python.exe")
S0011_NODEIDS = {
    (
        "tests/unit/bearing/test_thermal_segregated_newton.py::"
        "test_fixed_point_reference_snapshot_matches_pre_change_results_exactly"
    ),
    (
        "tests/unit/bearing/test_thermal_segregated_newton.py::"
        "test_s0011_current_replay_reference_v2_matches_exactly"
    ),
    (
        "tests/unit/bearing/test_thermal_segregated_newton.py::"
        "test_direct_then_newton_reports_s0011_sample_30_without_false_convergence"
    ),
    (
        "tests/unit/bearing/test_thermal_segregated_newton.py::"
        "test_direct_then_newton_does_not_false_converge_s0011_sample_162946"
    ),
}
ROSS_ROTOR_TIME_NODEIDS = {
    (
        "tests/unit/dynamics/test_rotor_lifecycle.py::"
        "test_rotor_valid_time_trajectories_match_v2_reference_exactly"
    ),
    (
        "tests/unit/dynamics/test_rotor_lifecycle.py::"
        "test_input_force_rejects_invalid_time_without_mutating_state"
    ),
    (
        "tests/unit/dynamics/test_rotor_lifecycle.py::"
        "test_input_force2node_rejects_invalid_time_without_mutating_state"
    ),
}
SECOND_REVIEW_NODEIDS = {
    (
        "tests/regression/dynamics/test_rotor_dof_coupling_reference.py::"
        "test_real_ross_coupling_and_lqg_mapping_match_v4_exactly"
    ),
    (
        "tests/regression/control/test_control_lifecycle_reference_v2.py::"
        "test_pid_and_fuzzy_outputs_are_read_only_after_one_evaluation"
    ),
    (
        "tests/regression/control/test_control_lifecycle_reference_v2.py::"
        "test_lti_output_is_read_only_after_one_evaluation"
    ),
    (
        "tests/integration/dynamics/test_coupling_step_commit.py::"
        "test_mid_step_failure_invalidates_coupler_until_explicit_reinitialization"
    ),
    (
        "tests/unit/dynamics/test_rotor_lifecycle.py::"
        "test_six_dof_result_and_mapping_use_ross_local_layout"
    ),
    (
        "tests/unit/systems/test_alb_builder_boundaries.py::"
        "test_alb_save_accepts_explicitly_absent_controller"
    ),
    (
        "tests/unit/systems/test_alb_builder_boundaries.py::"
        "test_nondimensional_factory_accepts_explicitly_absent_controller"
    ),
}


def _run(command: list[str], *, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
    ).rstrip("\r\n")


def _tracked_status() -> list[str]:
    output = _git("status", "--porcelain=v1", "--untracked-files=no")
    return output.splitlines() if output else []


def _status_digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _summary_counts(output: str) -> dict[str, int]:
    patterns = {
        "passed": r"(\d+) passed",
        "skipped": r"(\d+) skipped",
        "warnings": r"(\d+) warnings?",
        "subtests_passed": r"(\d+) subtests? passed",
    }
    counts: dict[str, int] = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, output)
        counts[name] = int(matches[-1]) if matches else 0
    return counts


def _mypy_version(environment: dict[str, str]) -> str:
    completed = _run(
        [
            str(PYTHON),
            "-c",
            "import importlib.metadata; print(importlib.metadata.version('mypy'))",
        ],
        environment=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)
    return completed.stdout.strip()


def run_acceptance() -> dict[str, Any]:
    runtime_root = RUNTIME_ROOT.resolve()
    if not runtime_root.is_relative_to(REPOSITORY_ROOT / "outputs"):
        raise RuntimeError("release runtime directory escaped outputs")
    runtime_root.mkdir(parents=True, exist_ok=True)
    run_token = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
    pytest_report = runtime_root / f"pytest_reports_{run_token}.json"
    pytest_basetemp = runtime_root / f"pytest_tmp_{run_token}"
    mypy_cache = runtime_root / f"mypy_cache_{run_token}"

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["ALB_RELEASE_PYTEST_REPORT"] = str(pytest_report)
    before = _tracked_status()
    pytest_command = [
        str(PYTHON),
        "-m",
        "pytest",
        "tests",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "tools.validation.release_pytest_plugin",
        f"--basetemp={pytest_basetemp}",
    ]
    pytest_run = _run(pytest_command, environment=environment)
    if pytest_run.returncode != 0:
        raise RuntimeError(
            "Full pytest acceptance failed:\n"
            + (pytest_run.stdout or "")
            + (pytest_run.stderr or "")
        )
    reports = json.loads(pytest_report.read_text(encoding="utf-8"))
    skipped = [item for item in reports["reports"] if item["outcome"] == "skipped"]
    s0011_reports = [
        item for item in reports["reports"] if item["nodeid"] in S0011_NODEIDS
    ]
    if {item["nodeid"] for item in s0011_reports} != S0011_NODEIDS:
        raise AssertionError("The complete self-contained S0011 v2 node set was not recorded")
    if any(item["outcome"] != "passed" for item in s0011_reports):
        raise AssertionError("A self-contained S0011 v2 node did not pass")
    ross_rotor_time_reports = [
        item for item in reports["reports"] if item["nodeid"] in ROSS_ROTOR_TIME_NODEIDS
    ]
    if {item["nodeid"] for item in ross_rotor_time_reports} != ROSS_ROTOR_TIME_NODEIDS:
        raise AssertionError("The complete RossRotor time-validation node set was not recorded")
    if any(item["outcome"] != "passed" for item in ross_rotor_time_reports):
        raise AssertionError("A RossRotor time-validation node did not pass")
    second_review_reports = [
        item for item in reports["reports"] if item["nodeid"] in SECOND_REVIEW_NODEIDS
    ]
    if {item["nodeid"] for item in second_review_reports} != SECOND_REVIEW_NODEIDS:
        raise AssertionError("The complete second-review regression node set was not recorded")
    if any(item["outcome"] != "passed" for item in second_review_reports):
        raise AssertionError("A second-review regression node did not pass")

    mypy_environment = environment.copy()
    mypy_environment["PYTHONPATH"] = str(DEVTOOLS_ROOT)
    mypy_command = [
        str(PYTHON),
        "-m",
        "mypy",
        "ALB/contracts",
        "ALB/core",
        "--config-file",
        "pyproject.toml",
        "--no-incremental",
        "--cache-dir",
        str(mypy_cache),
    ]
    mypy_run = _run(mypy_command, environment=mypy_environment)
    if mypy_run.returncode != 0:
        raise RuntimeError("Strict mypy acceptance failed:\n" + mypy_run.stdout + mypy_run.stderr)
    after = _tracked_status()
    if before != after:
        raise AssertionError(
            "Tracked worktree changed during acceptance:\n"
            + json.dumps({"before": before, "after": after}, ensure_ascii=False, indent=2)
        )

    v1_diff = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "pre-full-repo-refactor-refs-20260720",
            "--",
            "refs/full_repo_refactor_v1",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
    ).returncode
    if v1_diff != 0:
        raise AssertionError("Frozen refs/full_repo_refactor_v1 differs from its tag")

    combined_output = pytest_run.stdout + "\n" + pytest_run.stderr
    return {
        "schema": "alb.release-acceptance.v1",
        "version": "0.2.0",
        "candidate_commit": _git("rev-parse", "HEAD"),
        "pytest": {
            "command": subprocess.list2cmdline(pytest_command),
            "returncode": pytest_run.returncode,
            "summary": _summary_counts(combined_output),
            "summary_tail": combined_output.splitlines()[-20:],
            "skipped": skipped,
            "s0011_reports": s0011_reports,
            "ross_rotor_time_reports": ross_rotor_time_reports,
            "second_review_reports": second_review_reports,
        },
        "mypy": {
            "command": subprocess.list2cmdline(mypy_command),
            "returncode": mypy_run.returncode,
            "version": _mypy_version(mypy_environment),
            "stdout": mypy_run.stdout.strip(),
            "stderr": mypy_run.stderr.strip(),
        },
        "worktree": {
            "tracked_status_before": before,
            "tracked_status_after": after,
            "before_sha256": _status_digest(before),
            "after_sha256": _status_digest(after),
            "tracked_status_delta": 0,
        },
        "references": {
            "full_repo_refactor_v1_unchanged_from_tag": True,
            "thermal_addendum": "refs/full_repo_refactor_addendum_v1",
            "thermal_segregated_newton_v2": (
                "refs/thermal_segregated_newton_reference_v2.json"
            ),
            "ross_rotor_time_validation_v2": (
                "refs/ross_rotor_time_validation_reference_v2.json"
            ),
            "control_lifecycle_v2": "refs/control_lifecycle_reference_v2.json",
            "rotor_dof_coupling_v4": "refs/rotor_dof_coupling_reference_v4.json",
        },
        "overall_status": "passed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and not args.overwrite_output:
        raise FileExistsError(f"Refusing to overwrite release evidence: {output}")
    payload = run_acceptance()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
