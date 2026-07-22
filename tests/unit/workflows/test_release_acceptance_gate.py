"""Unit tests for release-evidence worktree preconditions."""

from pathlib import Path

import pytest

from tools.validation import run_release_acceptance_0_2 as acceptance


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
