"""Verify that the friendly root does not eagerly import optional stacks."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "missing",
    ["matplotlib", "skfem", "skfuzzy", "ross", "torch", "json5"],
)
def test_public_root_import_does_not_require_optional_dependency(
    missing: str,
) -> None:
    code = f"""
import importlib.abc
import sys

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == {missing!r} or fullname.startswith({missing!r} + '.'):
            raise ModuleNotFoundError('blocked optional dependency', name={missing!r})
        return None

sys.meta_path.insert(0, Blocker())
import ALB
assert ALB.__version__ == "0.4.1"
assert callable(ALB.build_bearing)
"""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
