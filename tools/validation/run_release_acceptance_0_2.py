"""Run final pytest and mypy gates and write inspectable 0.2 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, cast
import uuid


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.validation.release_wheel_gate import build_and_validate_wheel
from tools.validation.release_phases import (
    evidence_phase,
    publish_wheel_phase,
    run_test_phase,
    select_candidate,
)


RELEASE_VERSION = "0.3.0"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs/migrations/0.3.0_release_acceptance.json"
DEFAULT_BUILD_REPORT = REPOSITORY_ROOT / "docs/migrations/0.3.0_build_acceptance.json"
DEFAULT_PUBLISH_WHEEL = REPOSITORY_ROOT / "dist/re_alb-0.3.0-1-py3-none-any.whl"
RUNTIME_ROOT = REPOSITORY_ROOT / "outputs/release_acceptance"
PYTHON = Path("E:/Anaconda2023/envs/ALB/python.exe")
MYPY_VERSION = "2.3.0"
BUILD_VERSION = "1.5.0"
IMPORT_LINTER_VERSION = "2.13"
PYTEST_VERSION = "9.0.3"
ACCEPTANCE_POLICY = (
    REPOSITORY_ROOT / "tools/validation/release_acceptance_policy_v7.json"
)
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
THIRD_REVIEW_NODEIDS = {
    (
        "tests/regression/test_third_review_compatibility_reference.py::"
        "test_third_review_valid_behavior_matches_v3_reference_exactly"
    ),
    *{
        (
            "tests/unit/systems/test_controller_compatibility.py::"
            "test_alb_control_process_accepts_strict_and_legacy_controllers"
            f"[{controller}]"
        )
        for controller in ("legacy", "lqg", "repetitive")
    },
    *{
        (
            "tests/unit/systems/test_controller_compatibility.py::"
            "test_harmonic_control_path_accepts_strict_and_legacy_controllers"
            f"[{controller}]"
        )
        for controller in ("legacy", "lqg", "repetitive")
    },
    (
        "tests/integration/dynamics/test_coupling_step_commit.py::"
        "test_mid_step_failure_invalidates_coupler_until_explicit_reinitialization"
    ),
    (
        "tests/unit/config/test_config_validate.py::TestALBConfigValidation::"
        "test_no_controller_config_is_explicit_and_round_trippable"
    ),
    (
        "tests/unit/control/test_blocks.py::"
        "test_servo_valve_requires_evaluate_and_repeated_reads_do_not_advance"
    ),
    *{
        (
            "tests/unit/dynamics/test_rotor_lifecycle.py::"
            "test_current_state_rejects_non_integer_node_indices_without_truncation"
            f"[{node_id}]"
        )
        for node_id in ("0.9", "-0.1", "True", "node3")
    },
    *{
        (
            "tests/unit/dynamics/test_rotor_lifecycle.py::"
            f"test_current_state_rejects_out_of_range_node_indices[{node_id}]"
        )
        for node_id in ("-1", "2")
    },
}
FOURTH_REVIEW_NODEIDS = {
    (
        "tests/regression/test_fourth_review_release_reference.py::"
        "test_fourth_review_valid_behavior_matches_v4_reference_exactly"
    ),
    *{
        (
            "tests/unit/systems/test_controller_compatibility.py::"
            "test_harmonic_public_lifecycle_supports_injected_controllers"
            f"[{controller}]"
        )
        for controller in ("legacy", "lqg", "repetitive")
    },
    (
        "tests/unit/systems/test_controller_compatibility.py::"
        "test_switch_false_stays_disabled_for_nonnegative_times"
    ),
    (
        "tests/unit/systems/test_controller_compatibility.py::"
        "test_missing_controller_produces_zero_command"
    ),
    (
        "tests/unit/systems/test_controller_compatibility.py::"
        "test_timed_start_is_recomputed_after_reinitialization"
    ),
    (
        "tests/unit/config/test_config_validate.py::TestALBConfigValidation::"
        "test_controller_type_and_nondefault_values_round_trip_exactly"
    ),
    *{
        (
            "tests/integration/dynamics/test_coupling_step_commit.py::"
            f"test_topology_change_requires_reinitialization[{topology}]"
        )
        for topology in ("bearing", "static-force", "unbalance")
    },
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_release_acceptance_rejects_dirty_tracked_worktree_before_tests"
    ),
}
FIFTH_REVIEW_NODEIDS = {
    (
        "tests/regression/test_fifth_review_release_reference.py::"
        "test_fifth_review_valid_behavior_matches_v5_reference_exactly"
    ),
    *{
        (
            "tests/unit/systems/test_controller_compatibility.py::"
            "test_failed_harmonic_reinitialization_invalidates_runtime"
            f"[{failure_point}]"
        )
        for failure_point in ("factory", "controller-init", "warm-up")
    },
    (
        "tests/unit/systems/test_controller_compatibility.py::"
        "test_public_alb_subclass_defaults_are_fresh_per_instance"
    ),
    (
        "tests/unit/config/test_config_validate.py::TestALBConfigValidation::"
        "test_controller_tag_and_nested_payload_type_must_agree"
    ),
    (
        "tests/unit/config/test_config_validate.py::TestALBConfigValidation::"
        "test_nested_controller_payload_rejects_unknown_fields"
    ),
    (
        "tests/unit/config/test_config_validate.py::TestALBConfigValidation::"
        "test_legacy_flat_controller_payload_remains_permissive"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_release_acceptance_rejects_sensitive_untracked_or_ignored_inputs"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_sensitive_runtime_input_filter_ignores_cache_and_output_artifacts"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_candidate_head_must_remain_unchanged"
    ),
}
SIXTH_REVIEW_NODEIDS = {
    (
        "tests/regression/test_sixth_review_runtime_reference.py::"
        "test_sixth_review_valid_behavior_matches_v6_reference_exactly"
    ),
    *{
        (
            "tests/unit/systems/test_controller_compatibility.py::"
            "test_harmonic_runtime_failure_invalidates_partial_step"
            f"[{failure_point}]"
        )
        for failure_point in ("controller", "command-shape", "second-valve")
    },
    (
        "tests/unit/systems/test_controller_compatibility.py::"
        "test_harmonic_output_failure_invalidates_partial_result"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_sensitive_scanner_catches_shadow_packages_and_devtools"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_acceptance_environment_removes_python_injection_variables"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_detached_acceptance_command_is_isolated_and_internal"
    ),
}


SEVENTH_REVIEW_NODEIDS = {
    (
        "tests/regression/test_seventh_review_release_reference.py::"
        "test_seventh_review_valid_behavior_matches_v7_reference_exactly"
    ),
    *{
        (
            "tests/unit/systems/test_controller_compatibility.py::"
            "test_harmonic_complex_runtime_input_requires_reinitialization"
            f"[{failure_source}]"
        )
        for failure_source in (
            "controller",
            "valve",
            "bearing-position",
            "bearing-velocity",
        )
    },
    (
        "tests/unit/systems/test_controller_compatibility.py::"
        "test_harmonic_runtime_failure_invalidates_partial_step"
        "[controller-nonfinite]"
    ),
    (
        "tests/unit/systems/test_controller_compatibility.py::"
        "test_harmonic_runtime_failure_invalidates_partial_step"
        "[valve-nonfinite]"
    ),
    (
        "tests/unit/systems/test_controller_compatibility.py::"
        "test_harmonic_output_overflow_invalidates_runtime"
    ),
}


EIGHTH_REVIEW_NODEIDS = {
    (
        "tests/regression/test_eighth_review_wheel_identity_reference.py::"
        "test_candidate_release_blobs_and_v7_behavior_reference_remain_exact"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_wheel_build_materializes_candidate_git_blobs"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_publish_staged_wheel_preserves_detached_sha"
    ),
    (
        "tests/validation/test_build_acceptance_report.py::"
        "test_wheel_metadata_cli_and_namespace_smokes_passed"
    ),
}


P2_ARCHITECTURE_NODEIDS = {
    (
        "tests/regression/control/test_native_control_lifecycle_reference_v9.py::"
        "test_native_control_trajectories_match_pre_migration_reference_exactly"
    ),
    (
        "tests/unit/control/test_native_lifecycle.py::"
        "test_native_controller_output_is_read_only[_lqg_controller]"
    ),
    (
        "tests/unit/control/test_native_lifecycle.py::"
        "test_native_controller_output_is_read_only[_repetitive_controller]"
    ),
    (
        "tests/unit/control/test_native_lifecycle.py::"
        "test_legacy_controller_adapter_contains_calculation_in_evaluate"
    ),
    (
        "tests/unit/control/test_native_lifecycle.py::"
        "test_servovalve_input_does_not_advance_and_output_is_read_only"
    ),
    (
        "tests/unit/control/test_native_lifecycle.py::"
        "test_pid_failure_is_terminal_until_explicit_init"
    ),
    (
        "tests/unit/config/test_versioned_schema.py::"
        "test_current_loader_rejects_unversioned_and_old_envelopes"
    ),
    (
        "tests/unit/config/test_versioned_schema.py::"
        "test_legacy_migration_is_non_mutating_one_way_and_auditable"
    ),
    (
        "tests/unit/contracts/test_numeric_boundaries.py::"
        "test_scalar_and_vector_validators_do_not_silently_change_shape"
    ),
    (
        "tests/unit/dynamics/test_rotor_lifecycle.py::"
        "test_rotor_advance_failure_requires_successful_reinitialization"
    ),
    (
        "tests/unit/dynamics/test_rotor_lifecycle.py::"
        "test_rotor_results_and_persistence_are_read_only_after_advance"
    ),
    (
        "tests/regression/bearing/test_alb_harmonic_linear.py::"
        "test_builtin_coefficient_contract_and_base_match"
    ),
    (
        "tests/unit/workflows/test_layered_mypy_gate.py::"
        "test_layered_gate_covers_every_python_file_in_target_namespaces"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_release_candidate_and_source_export_are_independent_phases"
    ),
    (
        "tests/unit/workflows/test_release_acceptance_gate.py::"
        "test_build_install_test_and_evidence_phases_have_explicit_boundaries"
    ),
}

REQUIRED_NODESETS = {
    "s0011": S0011_NODEIDS,
    "ross_rotor_time": ROSS_ROTOR_TIME_NODEIDS,
    "second_review": SECOND_REVIEW_NODEIDS,
    "third_review": THIRD_REVIEW_NODEIDS,
    "fourth_review": FOURTH_REVIEW_NODEIDS,
    "fifth_review": FIFTH_REVIEW_NODEIDS,
    "sixth_review": SIXTH_REVIEW_NODEIDS,
    "seventh_review": SEVENTH_REVIEW_NODEIDS,
    "eighth_review": EIGHTH_REVIEW_NODEIDS,
    "p2_architecture": P2_ARCHITECTURE_NODEIDS,
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
        stderr=subprocess.PIPE,
    ).rstrip("\r\n")


def _tracked_status() -> list[str]:
    output = _git("status", "--porcelain=v1", "--untracked-files=no")
    return output.splitlines() if output else []


def _is_sensitive_runtime_input(path: str) -> bool:
    """Return whether an uncommitted path can alter imports or test execution."""

    normalized = path.replace("\\", "/").lstrip("./")
    if normalized.endswith((".py", ".pyi", ".pyd", ".so")):
        return True
    return normalized in {"pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"}


def _sensitive_uncommitted_inputs() -> dict[str, list[str]]:
    """List untracked and ignored files that can influence acceptance."""

    pathspecs = (
        ":(glob)**/*.py",
        ":(glob)**/*.pyi",
        ":(glob)**/*.pyd",
        ":(glob)**/*.so",
        ":(top,glob)*.py",
        ":(top,glob)*.pyi",
        ":(top,glob)*.pyd",
        ":(top,glob)*.so",
        "pytest.ini",
        "tox.ini",
        "setup.cfg",
        "pyproject.toml",
    )
    groups = {
        "untracked": _git(
            "ls-files", "--others", "--exclude-standard", "--", *pathspecs
        ),
        "ignored": _git(
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--",
            *pathspecs,
        ),
    }
    return {
        name: sorted(
            path for path in output.splitlines() if _is_sensitive_runtime_input(path)
        )
        for name, output in groups.items()
    }


def _acceptance_environment() -> dict[str, str]:
    """Return an environment without caller-controlled Python/test injection."""

    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith(("PYTHON", "PYTEST")):
            environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _detached_acceptance_command(worktree: Path, output: Path) -> list[str]:
    """Return the isolated command executed inside a detached candidate tree."""

    return [
        str(PYTHON),
        "-I",
        str(worktree / "tools/validation/run_release_acceptance_0_2.py"),
        "--python",
        str(PYTHON),
        "--internal-detached",
        "--output",
        str(output),
    ]


def _assert_candidate_head(candidate_commit: str) -> str:
    """Require HEAD to remain pinned to the candidate throughout acceptance."""

    current = _git("rev-parse", "HEAD")
    if current != candidate_commit:
        raise AssertionError(
            "Candidate HEAD changed during acceptance: "
            f"before={candidate_commit}, after={current}"
        )
    return current


def _status_digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _summary_counts(output: str) -> dict[str, int]:
    patterns = {
        "passed": r"(\d+) passed",
        "skipped": r"(\d+) skipped",
        "subtests_passed": r"(\d+) subtests? passed",
    }
    counts: dict[str, int] = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, output)
        counts[name] = int(matches[-1]) if matches else 0
    return counts


def _validate_required_nodeid_collection(output: str) -> dict[str, int]:
    """Fail before the expensive build when a required nodeid has drifted."""

    collected = {
        line.strip().replace("\\", "/")
        for line in output.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    }
    missing = {
        name: sorted(expected - collected)
        for name, expected in REQUIRED_NODESETS.items()
        if expected - collected
    }
    if missing:
        raise AssertionError(
            "Required release nodeids are absent from collection:\n"
            + json.dumps(missing, ensure_ascii=False, indent=2)
        )
    return {
        "collected": len(collected),
        "required_unique": len(set().union(*REQUIRED_NODESETS.values())),
    }


def _python_module_command(
    module: str,
    *args: str,
    prepend_path: Path | None = None,
) -> list[str]:
    """Run one module with caller Python variables and user site disabled."""

    if prepend_path is None:
        return [str(PYTHON), "-E", "-s", "-m", module, *args]
    bootstrap = (
        "import runpy,sys;"
        f"sys.path.insert(0, {str(prepend_path)!r});"
        f"sys.argv=[{module!r}, *sys.argv[1:]];"
        f"runpy.run_module({module!r}, run_name='__main__')"
    )
    return [str(PYTHON), "-E", "-s", "-c", bootstrap, *args]


def _mypy_version(target: Path, environment: dict[str, str]) -> str:
    completed = _run(
        [
            str(PYTHON),
            "-E",
            "-s",
            "-c",
            (
                "import importlib.metadata,sys;"
                f"sys.path.insert(0, {str(target)!r});"
                "print(importlib.metadata.version('mypy'))"
            ),
        ],
        environment=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)
    return completed.stdout.strip()


def _install_fresh_validation_tools(
    target: Path,
    environment: dict[str, str],
) -> tuple[list[str], subprocess.CompletedProcess[str]]:
    """Install pinned build and type-check tools into a new run-owned directory."""

    if target.exists() and any(target.iterdir()):
        raise RuntimeError(f"Fresh mypy target is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    command = _python_module_command(
        "pip",
        "install",
        "--isolated",
        "--disable-pip-version-check",
        "--no-input",
        "--no-compile",
        "--target",
        str(target),
        f"mypy=={MYPY_VERSION}",
        f"build=={BUILD_VERSION}",
        f"import-linter=={IMPORT_LINTER_VERSION}",
        f"pytest=={PYTEST_VERSION}",
    )
    completed = _run(command, environment=environment)
    if completed.returncode != 0:
        raise RuntimeError(
            "Fresh mypy installation failed:\n"
            + completed.stdout
            + completed.stderr
        )
    return command, completed


def _load_acceptance_policy() -> dict[str, Any]:
    """Load the versioned pytest evidence policy committed with the candidate."""

    policy = cast(
        dict[str, Any],
        json.loads(ACCEPTANCE_POLICY.read_text(encoding="utf-8")),
    )
    if policy.get("schema") != "alb.release-acceptance-policy.v1":
        raise ValueError("Unsupported release acceptance policy schema")
    return policy


def _validate_pytest_evidence(
    evidence: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Require exact pytest version, plugin, skip, xfail, and warning evidence."""

    pytest_version = str(evidence.get("pytest_version", ""))
    try:
        pytest_major = int(pytest_version.split(".", maxsplit=1)[0])
    except ValueError as exc:
        raise AssertionError(f"Invalid pytest version evidence: {pytest_version!r}") from exc
    if pytest_major != int(policy["pytest_major"]):
        raise AssertionError(
            f"pytest major mismatch: expected={policy['pytest_major']}, "
            f"actual={pytest_version}"
        )
    if pytest_version != policy["pytest_version"]:
        raise AssertionError(
            f"pytest version mismatch: expected={policy['pytest_version']}, "
            f"actual={pytest_version}"
        )

    active_plugins = sorted(evidence.get("active_plugins", []))
    expected_plugins = sorted(policy["active_plugins"])
    if active_plugins != expected_plugins:
        raise AssertionError(
            "Active pytest plugin set differs from the release allowlist:\n"
            + json.dumps(
                {"expected": expected_plugins, "actual": active_plugins},
                ensure_ascii=False,
                indent=2,
            )
        )

    reports = evidence.get("reports", [])
    xfail_reports = [item for item in reports if item.get("wasxfail") is not None]
    if xfail_reports:
        raise AssertionError(
            "Release acceptance does not permit xfail/xpass reports:\n"
            + json.dumps(xfail_reports, ensure_ascii=False, indent=2)
        )

    skipped = [item for item in reports if item.get("outcome") == "skipped"]
    skip_policy = policy["allowed_skip"]
    expected_skips = sorted(
        (
            nodeid,
            skip_policy["when"],
            skip_policy["reason"],
        )
        for nodeid in skip_policy["nodeids"]
    )
    actual_skips = sorted(
        (item.get("nodeid"), item.get("when"), item.get("reason"))
        for item in skipped
    )
    if actual_skips != expected_skips:
        raise AssertionError(
            "Observed pytest skips differ from the exact release allowlist:\n"
            + json.dumps(
                {"expected": expected_skips, "actual": actual_skips},
                ensure_ascii=False,
                indent=2,
            )
        )

    warnings = evidence.get("warnings", [])
    if warnings != policy["allowed_warnings"]:
        raise AssertionError(
            "Observed pytest warnings differ from the release allowlist:\n"
            + json.dumps(warnings, ensure_ascii=False, indent=2)
        )
    return skipped, warnings


def _cleanup_runtime_paths(*paths: Path) -> None:
    """Remove only run-owned paths beneath the validated runtime root."""

    runtime_root = RUNTIME_ROOT.resolve()
    for path in paths:
        resolved = path.resolve()
        if resolved == runtime_root or not resolved.is_relative_to(runtime_root):
            raise RuntimeError(f"Refusing to clean path outside runtime root: {resolved}")
        if resolved.is_dir():
            shutil.rmtree(resolved)
        elif resolved.exists():
            resolved.unlink()


def run_acceptance() -> dict[str, Any]:
    runtime_root = RUNTIME_ROOT.resolve()
    if not runtime_root.is_relative_to(REPOSITORY_ROOT / "outputs"):
        raise RuntimeError("release runtime directory escaped outputs")
    runtime_root.mkdir(parents=True, exist_ok=True)
    run_token = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
    pytest_report = runtime_root / f"pytest_reports_{run_token}.json"
    pytest_basetemp = runtime_root / f"pytest_tmp_{run_token}"
    mypy_cache = runtime_root / f"mypy_cache_{run_token}"
    fresh_devtools = runtime_root / f"devtools_{run_token}"

    environment = _acceptance_environment()
    environment["ALB_RELEASE_PYTEST_REPORT"] = str(pytest_report)
    before = _tracked_status()
    if before:
        raise RuntimeError(
            "Release acceptance requires a clean tracked worktree before tests:\n"
            + json.dumps(before, ensure_ascii=False, indent=2)
        )
    sensitive_before = _sensitive_uncommitted_inputs()
    if any(sensitive_before.values()):
        raise RuntimeError(
            "Release acceptance requires committed runtime and test inputs:\n"
            + json.dumps(sensitive_before, ensure_ascii=False, indent=2)
        )
    candidate = select_candidate(REPOSITORY_ROOT, "HEAD")
    candidate_commit = candidate.commit
    mypy_environment = environment.copy()
    mypy_install_command, mypy_install = _install_fresh_validation_tools(
        fresh_devtools, mypy_environment
    )
    collection_command = _python_module_command(
        "pytest",
        "tests",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        prepend_path=fresh_devtools,
    )
    collection_run = run_test_phase(
        collection_command,
        repository_root=REPOSITORY_ROOT,
        environment=environment,
        phase="required_nodeid_collection",
    ).require_success()
    collection_summary = _validate_required_nodeid_collection(collection_run.stdout)
    wheel_gate = build_and_validate_wheel(
        python=PYTHON,
        repository_root=REPOSITORY_ROOT,
        runtime_root=runtime_root,
        run_token=run_token,
        environment=environment,
        dependency_paths=(fresh_devtools,),
        candidate_commit=candidate_commit,
        build_tag="1",
    )
    environment["ALB_BUILD_ACCEPTANCE_REPORT"] = str(wheel_gate.report_path)
    environment["ALB_BUILD_ACCEPTANCE_REQUIRE_WHEEL"] = "1"
    pytest_command = _python_module_command(
        "pytest",
        "tests",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "tools.validation.release_pytest_plugin",
        f"--basetemp={pytest_basetemp}",
        prepend_path=fresh_devtools,
    )
    pytest_run = run_test_phase(
        pytest_command,
        repository_root=REPOSITORY_ROOT,
        environment=environment,
        phase="test",
    )
    if pytest_run.returncode != 0:
        raise RuntimeError(
            "Full pytest acceptance failed:\n"
            + (pytest_run.stdout or "")
            + (pytest_run.stderr or "")
        )
    reports = cast(
        dict[str, Any],
        json.loads(pytest_report.read_text(encoding="utf-8")),
    )
    acceptance_policy = _load_acceptance_policy()
    skipped, recorded_warnings = _validate_pytest_evidence(
        reports, acceptance_policy
    )
    python_runtime = reports.get("python_runtime", {})
    expected_runtime = {
        "ignore_environment": 1,
        "no_user_site": 1,
        "optimize": 0,
        "warnoptions": [],
        "pytest_disable_plugin_autoload": "1",
    }
    runtime_mismatches = {
        name: {"expected": expected, "actual": python_runtime.get(name)}
        for name, expected in expected_runtime.items()
        if python_runtime.get(name) != expected
    }
    if runtime_mismatches:
        raise AssertionError(
            "Pytest interpreter was not isolated from caller injection:\n"
            + json.dumps(runtime_mismatches, ensure_ascii=False, indent=2)
        )
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
    third_review_reports = [
        item for item in reports["reports"] if item["nodeid"] in THIRD_REVIEW_NODEIDS
    ]
    if {item["nodeid"] for item in third_review_reports} != THIRD_REVIEW_NODEIDS:
        raise AssertionError("The complete third-review regression node set was not recorded")
    if any(item["outcome"] != "passed" for item in third_review_reports):
        raise AssertionError("A third-review regression node did not pass")
    fourth_review_reports = [
        item for item in reports["reports"] if item["nodeid"] in FOURTH_REVIEW_NODEIDS
    ]
    if {item["nodeid"] for item in fourth_review_reports} != FOURTH_REVIEW_NODEIDS:
        raise AssertionError("The complete fourth-review regression node set was not recorded")
    if any(item["outcome"] != "passed" for item in fourth_review_reports):
        raise AssertionError("A fourth-review regression node did not pass")
    fifth_review_reports = [
        item for item in reports["reports"] if item["nodeid"] in FIFTH_REVIEW_NODEIDS
    ]
    if {item["nodeid"] for item in fifth_review_reports} != FIFTH_REVIEW_NODEIDS:
        raise AssertionError("The complete fifth-review regression node set was not recorded")
    if any(item["outcome"] != "passed" for item in fifth_review_reports):
        raise AssertionError("A fifth-review regression node did not pass")
    sixth_review_reports = [
        item for item in reports["reports"] if item["nodeid"] in SIXTH_REVIEW_NODEIDS
    ]
    if {item["nodeid"] for item in sixth_review_reports} != SIXTH_REVIEW_NODEIDS:
        raise AssertionError("The complete sixth-review regression node set was not recorded")
    if any(item["outcome"] != "passed" for item in sixth_review_reports):
        raise AssertionError("A sixth-review regression node did not pass")
    seventh_review_reports = [
        item for item in reports["reports"] if item["nodeid"] in SEVENTH_REVIEW_NODEIDS
    ]
    if {item["nodeid"] for item in seventh_review_reports} != SEVENTH_REVIEW_NODEIDS:
        raise AssertionError("The complete seventh-review regression node set was not recorded")
    if any(item["outcome"] != "passed" for item in seventh_review_reports):
        raise AssertionError("A seventh-review regression node did not pass")
    eighth_review_reports = [
        item for item in reports["reports"] if item["nodeid"] in EIGHTH_REVIEW_NODEIDS
    ]
    if {item["nodeid"] for item in eighth_review_reports} != EIGHTH_REVIEW_NODEIDS:
        raise AssertionError("The complete eighth-review artifact node set was not recorded")
    if any(item["outcome"] != "passed" for item in eighth_review_reports):
        raise AssertionError("An eighth-review artifact identity node did not pass")
    p2_architecture_reports = [
        item for item in reports["reports"] if item["nodeid"] in P2_ARCHITECTURE_NODEIDS
    ]
    if {
        item["nodeid"] for item in p2_architecture_reports
    } != P2_ARCHITECTURE_NODEIDS:
        raise AssertionError("The complete P2 architecture node set was not recorded")
    if any(item["outcome"] != "passed" for item in p2_architecture_reports):
        raise AssertionError("A P2 architecture node did not pass")

    mypy_command = [
        str(PYTHON),
        "-E",
        "-s",
        str(REPOSITORY_ROOT / "tools/validation/run_layered_mypy.py"),
        "--mypy-target",
        str(fresh_devtools),
        "--cache-root",
        str(mypy_cache),
    ]
    mypy_run = run_test_phase(
        mypy_command,
        repository_root=REPOSITORY_ROOT,
        environment=mypy_environment,
        phase="layered_type_check",
    )
    if mypy_run.returncode != 0:
        raise RuntimeError(
            "Layered mypy acceptance failed:\n" + mypy_run.stdout + mypy_run.stderr
        )
    mypy_summary = cast(dict[str, Any], json.loads(mypy_run.stdout))
    mypy_version = _mypy_version(fresh_devtools, mypy_environment)
    if mypy_version != MYPY_VERSION:
        raise AssertionError(
            f"Fresh mypy version mismatch: expected={MYPY_VERSION}, "
            f"actual={mypy_version}"
        )
    # Keep the first verified wheel until the outer launcher stages its exact bytes.
    _cleanup_runtime_paths(
        pytest_report,
        pytest_basetemp,
        mypy_cache,
        fresh_devtools,
        wheel_gate.report_path,
        wheel_gate.installed_root,
        wheel_gate.build_source_root,
        wheel_gate.reproducibility_wheel_root,
        wheel_gate.reproducibility_build_source_root,
    )
    after = _tracked_status()
    if after:
        raise AssertionError(
            "Tracked worktree changed during acceptance:\n"
            + json.dumps({"before": before, "after": after}, ensure_ascii=False, indent=2)
        )
    sensitive_after = _sensitive_uncommitted_inputs()
    if any(sensitive_after.values()):
        raise AssertionError(
            "Runtime or test inputs changed during acceptance:\n"
            + json.dumps(
                {"before": sensitive_before, "after": sensitive_after},
                ensure_ascii=False,
                indent=2,
            )
        )
    candidate_commit_after = _assert_candidate_head(candidate_commit)

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
    pytest_summary = _summary_counts(combined_output)
    pytest_summary["warnings"] = len(recorded_warnings)
    return {
        "schema": "alb.release-acceptance.v1",
        "version": RELEASE_VERSION,
        "candidate_commit": candidate_commit,
        "pytest": {
            "command": subprocess.list2cmdline(pytest_command),
            "returncode": pytest_run.returncode,
            "summary": pytest_summary,
            "collection_preflight": {
                "command": subprocess.list2cmdline(collection_command),
                "returncode": collection_run.returncode,
                **collection_summary,
            },
            "summary_tail": combined_output.splitlines()[-20:],
            "version": reports.get("pytest_version"),
            "policy": ACCEPTANCE_POLICY.relative_to(REPOSITORY_ROOT).as_posix(),
            "python_runtime": python_runtime,
            "active_plugins": reports.get("active_plugins", []),
            "warnings": recorded_warnings,
            "skipped": skipped,
            "s0011_reports": s0011_reports,
            "ross_rotor_time_reports": ross_rotor_time_reports,
            "second_review_reports": second_review_reports,
            "third_review_reports": third_review_reports,
            "fourth_review_reports": fourth_review_reports,
            "fifth_review_reports": fifth_review_reports,
            "sixth_review_reports": sixth_review_reports,
            "seventh_review_reports": seventh_review_reports,
            "eighth_review_reports": eighth_review_reports,
            "p2_architecture_reports": p2_architecture_reports,
        },
        "mypy": {
            "install_command": subprocess.list2cmdline(mypy_install_command),
            "install_returncode": mypy_install.returncode,
            "install_summary_tail": (
                mypy_install.stdout + "\n" + mypy_install.stderr
            ).splitlines()[-20:],
            "command": subprocess.list2cmdline(mypy_command),
            "returncode": mypy_run.returncode,
            "version": mypy_version,
            "stdout": mypy_run.stdout.strip(),
            "stderr": mypy_run.stderr.strip(),
            "layered_summary": mypy_summary,
        },
        "wheel": wheel_gate.payload,
        "worktree": {
            "tracked_status_before": before,
            "tracked_status_after": after,
            "before_sha256": _status_digest(before),
            "after_sha256": _status_digest(after),
            "tracked_status_delta": 0,
            "sensitive_inputs_before": sensitive_before,
            "sensitive_inputs_after": sensitive_after,
            "candidate_head_before": candidate_commit,
            "candidate_head_after": candidate_commit_after,
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
            "third_review_compatibility_v3": (
                "refs/third_review_compatibility_reference_v3.json"
            ),
            "fourth_review_release_v4": (
                "refs/fourth_review_release_reference_v4.json"
            ),
            "fifth_review_release_v5": (
                "refs/fifth_review_release_reference_v5.json"
            ),
            "sixth_review_runtime_v6": (
                "refs/sixth_review_runtime_reference_v6.json"
            ),
            "seventh_review_release_v7": (
                "refs/seventh_review_release_reference_v7.json"
            ),
            "eighth_review_wheel_identity_v8": (
                "refs/eighth_review_wheel_identity_reference_v8.json"
            ),
        },
        "release_phases": {
            "candidate_selection": candidate.evidence(),
            "source_export": wheel_gate.payload["phases"]["source_export"],
            "build": wheel_gate.payload["phases"]["build"],
            "install": wheel_gate.payload["phases"]["install"],
            "test": pytest_run.evidence(),
            "required_nodeid_collection": collection_run.evidence(),
            "layered_type_check": mypy_run.evidence(),
            "evidence_generation": {
                "phase": "evidence_generation",
                "status": "passed",
            },
        },
        "overall_status": "passed",
    }


def _remove_detached_worktree(worktree: Path) -> None:
    """Remove only the run-owned detached worktree under the project parent."""

    resolved = worktree.resolve()
    expected_parent = REPOSITORY_ROOT.resolve().parent
    if (
        resolved.parent != expected_parent
        or not resolved.name.startswith(".alb_release_acceptance_")
    ):
        raise RuntimeError(f"Refusing to remove unexpected worktree: {resolved}")
    completed = subprocess.run(
        ["git", "worktree", "remove", "--force", str(resolved)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Detached acceptance worktree removal failed:\n"
            + completed.stdout
            + completed.stderr
        )
    if resolved.exists():
        shutil.rmtree(resolved)


def _stage_detached_wheel(worktree: Path, payload: dict[str, Any]) -> Path:
    """Copy the verified detached wheel to a launcher-owned staging path."""

    relative_wheel = Path(payload["wheel"]["wheel"]["path"])
    detached_wheel = (worktree / relative_wheel).resolve()
    if not detached_wheel.is_relative_to(worktree.resolve()):
        raise RuntimeError(f"Detached wheel escaped candidate worktree: {detached_wheel}")
    if not detached_wheel.is_file():
        raise FileNotFoundError(detached_wheel)
    expected_sha256 = payload["wheel"]["wheel"]["sha256"]
    if hashlib.sha256(detached_wheel.read_bytes()).hexdigest() != expected_sha256:
        raise AssertionError("Detached wheel bytes differ from acceptance evidence")
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    staging = RUNTIME_ROOT / f"published_wheel_{uuid.uuid4().hex}.whl"
    shutil.copyfile(detached_wheel, staging)
    if hashlib.sha256(staging.read_bytes()).hexdigest() != expected_sha256:
        raise AssertionError("Staged wheel bytes differ from detached acceptance")
    return staging


def _publish_staged_wheel(
    staging: Path,
    publish_wheel: Path,
    payload: dict[str, Any],
) -> None:
    """Atomically publish the exact wheel installed by detached acceptance."""

    publish_wheel = publish_wheel.resolve()
    expected_dist = (REPOSITORY_ROOT / "dist").resolve()
    if publish_wheel.parent != expected_dist:
        raise RuntimeError(f"Release wheel must be published under {expected_dist}")
    expected_name = payload["wheel"]["reproducible_build"]["first_filename"]
    if publish_wheel.name != expected_name:
        raise RuntimeError(
            f"Published wheel name mismatch: expected={expected_name}, "
            f"actual={publish_wheel.name}"
        )
    expected_sha256 = payload["wheel"]["wheel"]["sha256"]
    published = publish_wheel_phase(
        staging,
        publish_wheel,
        expected_sha256=expected_sha256,
    )
    published_sha256 = published["sha256"]
    relative_path = publish_wheel.relative_to(REPOSITORY_ROOT).as_posix()
    payload["wheel"]["wheel"]["path"] = relative_path
    payload["wheel"]["published_artifact"] = {
        "path": relative_path,
        "sha256": published_sha256,
        "matches_detached_installed_wheel": True,
    }


def run_acceptance_in_detached_worktree(publish_wheel: Path) -> dict[str, Any]:
    """Run acceptance only from a detached checkout of the candidate SHA."""

    before = _tracked_status()
    if before:
        raise RuntimeError(
            "Detached acceptance requires a clean tracked launcher worktree:\n"
            + json.dumps(before, ensure_ascii=False, indent=2)
        )
    candidate_commit = select_candidate(REPOSITORY_ROOT, "HEAD").commit
    worktree = REPOSITORY_ROOT.resolve().parent / (
        f".alb_release_acceptance_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    )
    if worktree.exists():
        raise FileExistsError(f"Detached acceptance path already exists: {worktree}")

    added = subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree), candidate_commit],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if added.returncode != 0:
        raise RuntimeError(
            "Detached acceptance worktree creation failed:\n"
            + added.stdout
            + added.stderr
        )

    internal_output = worktree / "outputs/release_acceptance/evidence.json"
    command = _detached_acceptance_command(worktree, internal_output)
    environment = _acceptance_environment()
    staging_wheel: Path | None = None
    try:
        completed = subprocess.run(
            command,
            cwd=worktree,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Detached release acceptance failed:\n"
                + completed.stdout
                + completed.stderr
            )
        payload = cast(
            dict[str, Any],
            json.loads(internal_output.read_text(encoding="utf-8")),
        )
        staging_wheel = _stage_detached_wheel(worktree, payload)
    finally:
        _remove_detached_worktree(worktree)

    after = _tracked_status()
    if after != before:
        raise AssertionError(
            "Launcher worktree changed during detached acceptance:\n"
            + json.dumps({"before": before, "after": after}, ensure_ascii=False)
        )
    candidate_after = _assert_candidate_head(candidate_commit)
    if payload.get("candidate_commit") != candidate_commit:
        raise AssertionError("Detached report is not bound to the launcher candidate")
    if staging_wheel is None:
        raise AssertionError("Detached acceptance did not stage a release wheel")
    try:
        _publish_staged_wheel(staging_wheel, publish_wheel, payload)
    finally:
        if staging_wheel.exists():
            staging_wheel.unlink()
    payload["execution"] = {
        "mode": "detached_worktree",
        "python_isolated_mode": True,
        "python_subprocess_environment_sanitized": True,
        "python_subprocess_flags": ["-E", "-s"],
        "pytest_plugin_autoload_disabled": True,
        "python": str(PYTHON),
        "candidate_head_before": candidate_commit,
        "candidate_head_after": candidate_after,
        "launcher_tracked_status_before": before,
        "launcher_tracked_status_after": after,
        "published_wheel": payload["wheel"]["published_artifact"],
    }
    return payload


def main() -> int:
    global PYTHON

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--build-report", type=Path, default=DEFAULT_BUILD_REPORT)
    parser.add_argument("--publish-wheel", type=Path, default=DEFAULT_PUBLISH_WHEEL)
    parser.add_argument(
        "--python",
        type=Path,
        default=PYTHON,
        help="Python interpreter used for every release subprocess.",
    )
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--overwrite-build-report", action="store_true")
    parser.add_argument("--internal-detached", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    PYTHON = args.python.resolve()
    if not PYTHON.is_file():
        raise FileNotFoundError(f"Release Python interpreter not found: {PYTHON}")
    output = args.output.resolve()
    if output.exists() and not args.overwrite_output:
        raise FileExistsError(f"Refusing to overwrite release evidence: {output}")
    build_report = args.build_report.resolve()
    if (
        not args.internal_detached
        and build_report.exists()
        and not args.overwrite_build_report
    ):
        raise FileExistsError(
            f"Refusing to overwrite build evidence: {build_report}"
        )
    payload = (
        run_acceptance()
        if args.internal_detached
        else run_acceptance_in_detached_worktree(args.publish_wheel)
    )
    if not args.internal_detached:
        evidence_phase(
            build_report,
            payload["wheel"],
            overwrite=args.overwrite_build_report,
        )
    evidence_phase(
        output,
        payload,
        overwrite=args.overwrite_output,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
