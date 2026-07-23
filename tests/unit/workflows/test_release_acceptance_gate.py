"""Unit tests for release-evidence worktree preconditions."""

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tools.validation import run_release_acceptance_0_2 as acceptance
from tools.validation import release_phases
from tools.validation.release_source_identity import (
    materialize_candidate_source,
    source_tree_evidence,
)


def test_release_acceptance_rejects_dirty_tracked_worktree_before_tests(monkeypatch):
    """A dirty tracked tree must fail before pytest or mypy is launched."""

    monkeypatch.setattr(
        acceptance,
        "_tracked_status",
        lambda: [" M ALB/systems/alb/assembly.py"],
    )

    def fail_if_run(*args, **kwargs):
        del args, kwargs
        raise AssertionError("acceptance subprocess must not start on a dirty tree")

    monkeypatch.setattr(acceptance, "_run", fail_if_run)

    with pytest.raises(RuntimeError, match="clean tracked worktree"):
        acceptance.run_acceptance()


def test_release_acceptance_rejects_sensitive_untracked_or_ignored_inputs(
    monkeypatch,
):
    """Uncommitted import and test inputs must fail before execution starts."""

    monkeypatch.setattr(acceptance, "_tracked_status", lambda: [])
    monkeypatch.setattr(
        acceptance,
        "_sensitive_uncommitted_inputs",
        lambda: {
            "untracked": ["tests/conftest.py"],
            "ignored": ["ALB/injected_module.py"],
        },
    )

    def fail_if_run(*args, **kwargs):
        del args, kwargs
        raise AssertionError("acceptance subprocess must not start")

    monkeypatch.setattr(acceptance, "_run", fail_if_run)

    with pytest.raises(RuntimeError, match="committed runtime and test inputs"):
        acceptance.run_acceptance()


def test_sensitive_runtime_input_filter_ignores_cache_and_output_artifacts():
    """Caches and result artifacts do not affect imports or test collection."""

    assert acceptance._is_sensitive_runtime_input("tests/conftest.py")
    assert acceptance._is_sensitive_runtime_input("ALB/local_override.py")
    assert acceptance._is_sensitive_runtime_input("tools/local_plugin.py")
    assert not acceptance._is_sensitive_runtime_input(
        "tests/__pycache__/conftest.cpython-310.pyc"
    )
    assert not acceptance._is_sensitive_runtime_input("outputs/run/result.json")
    assert not acceptance._is_sensitive_runtime_input(".codex/settings.json")


def test_wheel_build_materializes_candidate_git_blobs(tmp_path: Path) -> None:
    """Wheel inputs come from immutable candidate blobs, not checkout filters."""

    source_root = tmp_path / "wheel-source"
    evidence = materialize_candidate_source(
        acceptance.REPOSITORY_ROOT,
        "HEAD",
        source_root,
    )
    expected_pyproject = subprocess.check_output(
        ["git", "cat-file", "blob", "HEAD:pyproject.toml"],
        cwd=acceptance.REPOSITORY_ROOT,
    )

    assert (source_root / "pyproject.toml").read_bytes() == expected_pyproject
    assert evidence["source_kind"] == "git_blobs"
    assert evidence["file_count"] == source_tree_evidence(
        acceptance.REPOSITORY_ROOT, "HEAD"
    )["file_count"]
    assert evidence["file_count"] > 119
    assert not (source_root / "tests").exists()


def test_release_candidate_and_source_export_are_independent_phases(tmp_path):
    """Candidate selection and canonical export can be reused independently."""

    candidate = release_phases.select_candidate(acceptance.REPOSITORY_ROOT)
    exported = release_phases.export_source_phase(candidate, tmp_path / "source")

    assert candidate.evidence()["phase"] == "candidate_selection"
    assert exported.evidence()["phase"] == "source_export"
    assert exported.source_evidence == candidate.source_evidence
    assert (exported.root / "pyproject.toml").is_file()


def test_build_install_test_and_evidence_phases_have_explicit_boundaries(
    tmp_path,
    monkeypatch,
):
    """Each mutable release action exposes one reusable result boundary."""

    candidate = release_phases.select_candidate(acceptance.REPOSITORY_ROOT)
    exported = release_phases.ExportedSource(
        candidate,
        tmp_path / "source",
        candidate.source_evidence,
    )
    exported.root.mkdir()

    def fake_run(phase, command, **kwargs):
        del kwargs
        if phase == "build":
            output = Path(command[command.index("--outdir") + 1])
            (output / "example-0.2.0-py3-none-any.whl").write_bytes(b"wheel")
        return release_phases.CommandPhaseResult(
            phase, tuple(command), 0, "passed", ""
        )

    monkeypatch.setattr(release_phases, "_run_command", fake_run)
    built = release_phases.build_wheel_phase(
        python=Path("python"),
        exported_source=exported,
        output_root=tmp_path / "wheel",
        environment={},
    )
    installed = release_phases.install_wheel_phase(
        python=Path("python"),
        repository_root=acceptance.REPOSITORY_ROOT,
        wheel=built.wheel,
        destination_root=tmp_path / "install",
        environment={},
    )
    tested = release_phases.run_test_phase(
        ["python", "-m", "pytest"],
        repository_root=acceptance.REPOSITORY_ROOT,
        environment={},
    )
    evidence_path = tmp_path / "evidence.json"
    written = release_phases.evidence_phase(
        evidence_path,
        {"phases": [built.evidence(), installed.evidence(), tested.evidence()]},
    )

    assert [
        built.evidence()["phase"],
        installed.evidence()["phase"],
        tested.evidence()["phase"],
        written["phase"],
    ] == ["build", "install", "test", "evidence_generation"]
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["phases"][0][
        "status"
    ] == "passed"
    with pytest.raises(FileExistsError, match="overwrite"):
        release_phases.evidence_phase(evidence_path, {})


def test_publish_staged_wheel_preserves_detached_sha(tmp_path, monkeypatch):
    """The published path receives the exact detached accepted wheel bytes."""

    monkeypatch.setattr(acceptance, "REPOSITORY_ROOT", tmp_path)
    staging = tmp_path / "staging.whl"
    staging.write_bytes(b"accepted-wheel")
    expected_sha256 = hashlib.sha256(staging.read_bytes()).hexdigest()
    payload = {
        "wheel": {
            "wheel": {"sha256": expected_sha256},
            "reproducible_build": {
                "first_filename": "re_alb-0.2.0-1-py3-none-any.whl"
            },
        }
    }
    publish_wheel = tmp_path / "dist/re_alb-0.2.0-1-py3-none-any.whl"

    acceptance._publish_staged_wheel(staging, publish_wheel, payload)

    assert hashlib.sha256(publish_wheel.read_bytes()).hexdigest() == expected_sha256
    assert payload["wheel"]["published_artifact"] == {
        "path": "dist/re_alb-0.2.0-1-py3-none-any.whl",
        "sha256": expected_sha256,
        "matches_detached_installed_wheel": True,
    }


def test_candidate_head_must_remain_unchanged(monkeypatch):
    """Acceptance evidence must stay bound to one immutable candidate HEAD."""

    monkeypatch.setattr(acceptance, "_git", lambda *args: "after-commit")
    with pytest.raises(AssertionError, match="Candidate HEAD changed"):
        acceptance._assert_candidate_head("before-commit")


def test_sensitive_scanner_catches_shadow_packages_and_devtools(monkeypatch):
    """Python files anywhere in the checkout are sensitive acceptance inputs."""

    def fake_git(*args):
        if "--ignored" in args:
            return "outputs/.devtools/mypy/api.py"
        return "control/__init__.py\nlocal_shadow/module.pyi"

    monkeypatch.setattr(acceptance, "_git", fake_git)
    assert acceptance._sensitive_uncommitted_inputs() == {
        "untracked": ["control/__init__.py", "local_shadow/module.pyi"],
        "ignored": ["outputs/.devtools/mypy/api.py"],
    }


def test_acceptance_environment_removes_python_injection_variables(monkeypatch):
    """Caller-controlled Python and pytest injection variables are removed."""

    injected_names = (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONOPTIMIZE",
        "PYTHONWARNINGS",
        "PYTHONHASHSEED",
        "PYTHONINSPECT",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTEST_DEBUG",
    )
    for name in injected_names:
        monkeypatch.setenv(name, f"injected-{name}")
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "0")

    environment = acceptance._acceptance_environment()
    for name in injected_names:
        assert name not in environment
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert all(
        name
        in {
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONIOENCODING",
            "PYTHONNOUSERSITE",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        }
        for name in environment
        if name.startswith(("PYTHON", "PYTEST"))
    )


def test_detached_acceptance_command_is_isolated_and_internal():
    """The candidate subprocess uses Python isolated mode and no recursion."""

    worktree = Path("C:/candidate-worktree")
    output = worktree / "outputs/evidence.json"
    command = acceptance._detached_acceptance_command(worktree, output)

    assert command[1] == "-I"
    assert "--internal-detached" in command
    assert command[-1] == str(output)


def test_required_nodeid_preflight_detects_renamed_nodes_before_build():
    """Required nodeid drift must fail before wheel construction starts."""

    all_required = set().union(*acceptance.REQUIRED_NODESETS.values())
    summary = acceptance._validate_required_nodeid_collection(
        "\n".join(sorted(all_required))
    )
    assert summary == {
        "collected": len(all_required),
        "required_unique": len(all_required),
    }

    renamed = sorted(all_required)[0]
    with pytest.raises(AssertionError, match="absent from collection"):
        acceptance._validate_required_nodeid_collection(
            "\n".join(sorted(all_required - {renamed}))
        )


def test_release_feature_manifest_covers_f01_f64_with_one_declared_deferral():
    features = acceptance.FEATURE_MANIFEST["features"]

    assert {item["id"] for item in features} == {
        f"F{index:02d}" for index in range(1, 65)
    }
    assert sum(item["status"] == "implemented" for item in features) == 63
    assert [
        item["id"]
        for item in features
        if item["status"] == "deferred_to_0.4.0"
    ] == ["F35"]
    assert acceptance.FEATURE_NODEIDS


def test_python_module_commands_ignore_environment_and_user_site():
    """Every worker Python module command carries explicit isolation flags."""

    command = acceptance._python_module_command("pytest", "tests", "-q")
    assert command[1:4] == ["-E", "-s", "-m"]
    assert command[4:] == ["pytest", "tests", "-q"]

    target = Path("C:/fresh-mypy")
    bootstrap = acceptance._python_module_command(
        "mypy", "ALB/core", prepend_path=target
    )
    assert bootstrap[1:4] == ["-E", "-s", "-c"]
    assert repr(str(target)) in bootstrap[4]


def _valid_pytest_evidence():
    policy = acceptance._load_acceptance_policy()
    skip_policy = policy["allowed_skip"]
    reports = [
        {
            "nodeid": nodeid,
            "when": skip_policy["when"],
            "outcome": "skipped",
            "reason": skip_policy["reason"],
            "report_type": "TestReport",
            "wasxfail": None,
        }
        for nodeid in skip_policy["nodeids"]
    ]
    return policy, {
        "pytest_version": "9.0.3",
        "active_plugins": policy["active_plugins"],
        "warnings": [],
        "reports": reports,
    }


@pytest.mark.parametrize("drift", ["skip", "warning", "xfail"])
def test_pytest_policy_rejects_skip_warning_and_xfail_drift(drift):
    """Release evidence fails for any unapproved outcome or warning drift."""

    policy, evidence = _valid_pytest_evidence()
    if drift == "skip":
        evidence["reports"].append(
            {
                "nodeid": "tests/unit/test_injected.py::test_hidden",
                "when": "call",
                "outcome": "skipped",
                "reason": "Skipped: injected",
                "report_type": "TestReport",
                "wasxfail": None,
            }
        )
    elif drift == "warning":
        evidence["warnings"] = [
            {
                "category": "builtins.RuntimeWarning",
                "message": "injected warning",
                "when": "runtest",
                "nodeid": "tests/unit/test_injected.py::test_hidden",
                "location": None,
            }
        ]
    else:
        evidence["reports"][0]["wasxfail"] = "known failure"

    with pytest.raises(AssertionError, match="skip|warning|xfail"):
        acceptance._validate_pytest_evidence(evidence, policy)


@pytest.mark.parametrize("drift", ["pytest-version", "plugin"])
def test_pytest_policy_rejects_version_or_plugin_drift(drift):
    """An old pytest or an auto-loaded plugin cannot certify a release."""

    policy, evidence = _valid_pytest_evidence()
    if drift == "pytest-version":
        evidence["pytest_version"] = "8.4.2"
    else:
        evidence["active_plugins"] = [*evidence["active_plugins"], "injected"]

    with pytest.raises(AssertionError, match="pytest major|plugin"):
        acceptance._validate_pytest_evidence(evidence, policy)
