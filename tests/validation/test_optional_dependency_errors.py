"""Verify actionable errors for every namespace backed by an optional extra."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


CASES = [
    ("ALB.physics.film", "from ALB.physics.film import SkfemNewtonFilm", "skfem", "film"),
    ("ALB.physics.bearing", "from ALB.physics.bearing import HydrostaticBearing", "skfem", "film"),
    ("ALB.physics.gas", "from ALB.physics.gas import GasBearing", "skfem", "film"),
    ("ALB.physics.thermal", "from ALB.physics.thermal import ThermalHydroBearing", "skfem", "film"),
    ("ALB.control", "from ALB.control import FuzzyPID", "skfuzzy", "control"),
    ("ALB.dynamics", "from ALB.dynamics import RossRotor", "ross", "dynamics"),
    ("ALB.surrogate", "from ALB.surrogate import Net", "torch", "surrogate"),
    (
        "ALB.surrogate.training",
        "from ALB.surrogate.training import AlbnnMlpTrainer",
        "torch",
        "surrogate",
    ),
    ("ALB.systems.alb", "from ALB.systems.alb import ALB", "skfem", "all"),
    ("ALB.infrastructure.config_io", "import ALB.infrastructure.config_io", "json5", "io"),
]


@pytest.mark.parametrize(("namespace", "statement", "missing", "extra"), CASES)
def test_missing_optional_dependency_has_install_hint(
    namespace: str,
    statement: str,
    missing: str,
    extra: str,
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
{statement}
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

    assert completed.returncode != 0
    assert f"{namespace} requires the optional '{extra}' extra" in completed.stderr
    assert f"pip install re-alb[{extra}]" in completed.stderr
    assert f"missing module: {missing}" in completed.stderr
