"""Validate an isolated 0.2 wheel installation and write acceptance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WHEEL = REPOSITORY_ROOT / "dist/re_alb-0.2.0-py3-none-any.whl"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs/migrations/0.2.0_build_acceptance.json"
EXPECTED_EXTRAS = {"all", "control", "dynamics", "film", "io", "surrogate", "test"}
FORBIDDEN_WHEEL_MEMBERS = {
    "ALB/alb.py",
    "ALB/base.py",
    "ALB/bearing.py",
    "ALB/controller.py",
    "ALB/couple.py",
    "ALB/film.py",
    "ALB/nn.py",
    "ALB/remote/__init__.py",
    "ALB/results.py",
    "ALB/task.py",
    "ALB/thermal.py",
    "ALB/tool.py",
    "ALB/infrastructure/persistence/legacy.py",
    "ALB/workflows/identification.py",
    "ALB/workflows/steps.py",
}


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _isolated_environment(installed_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(installed_root)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _run_python(installed_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=installed_root.parent,
        env=_isolated_environment(installed_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def validate(wheel: Path, installed_root: Path) -> dict[str, Any]:
    wheel = wheel.resolve()
    installed_root = installed_root.resolve()
    if not wheel.is_file():
        raise FileNotFoundError(wheel)
    if not (installed_root / "ALB/__init__.py").is_file():
        raise FileNotFoundError(f"isolated ALB install missing under {installed_root}")

    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())
        metadata_member = next(
            name for name in members if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_member).decode("utf-8")
    forbidden_present = sorted(FORBIDDEN_WHEEL_MEMBERS & members)
    if forbidden_present:
        raise AssertionError(f"removed modules present in wheel: {forbidden_present}")
    required_members = {
        "ALB/contracts/block.py",
        "ALB/core/steps.py",
        "ALB/dynamics/identification.py",
        "ALB/infrastructure/persistence/writers.py",
        "ALB/systems/alb/data/alb_harmonic_linear_gamma1_50hz.json",
    }
    missing_members = sorted(required_members - members)
    if missing_members:
        raise AssertionError(f"required wheel members missing: {missing_members}")

    metadata_lines = metadata.splitlines()
    version_values = [line.removeprefix("Version: ") for line in metadata_lines if line.startswith("Version: ")]
    python_values = [
        line.removeprefix("Requires-Python: ")
        for line in metadata_lines
        if line.startswith("Requires-Python: ")
    ]
    extras = {
        line.removeprefix("Provides-Extra: ")
        for line in metadata_lines
        if line.startswith("Provides-Extra: ")
    }
    if version_values != ["0.2.0"]:
        raise AssertionError("wheel metadata version is not 0.2.0")
    if python_values != [">=3.10"]:
        raise AssertionError("wheel metadata Requires-Python is not >=3.10")
    if extras != EXPECTED_EXTRAS:
        raise AssertionError(f"wheel extras mismatch: {sorted(extras)}")

    smoke_code = r'''
import importlib.util
import json
import ALB
from ALB.control import FuzzyPID, PID
from ALB.dynamics import RossRotor
from ALB.infrastructure import DirectoryArtifactWriter
from ALB.infrastructure.config_io import read_json5
from ALB.physics.bearing import HydrostaticBearing
from ALB.physics.film import SkfemNewtonFilm
from ALB.physics.thermal import ThermalHydroBearing
from ALB.surrogate import Net
from ALB.surrogate.training import TrainingConfig
from ALB.systems.alb import ALBHarmonicLinear

removed = [
    "ALB.alb", "ALB.base", "ALB.bearing", "ALB.controller", "ALB.film",
    "ALB.nn", "ALB.remote", "ALB.results", "ALB.task", "ALB.thermal", "ALB.tool",
]
print(json.dumps({
    "alb_file": ALB.__file__,
    "version": ALB.__version__,
    "root_exports": sorted(ALB.__all__),
    "removed_specs": {name: importlib.util.find_spec(name) is not None for name in removed},
    "namespace_smoke": [
        PID.__name__, FuzzyPID.__name__, RossRotor.__name__,
        DirectoryArtifactWriter.__name__, read_json5.__name__, HydrostaticBearing.__name__,
        SkfemNewtonFilm.__name__, ThermalHydroBearing.__name__, Net.__name__,
        TrainingConfig.__name__, ALBHarmonicLinear.__name__,
    ],
}))
'''
    smoke = _run_python(installed_root, "-c", smoke_code)
    if smoke.returncode != 0:
        raise RuntimeError(f"isolated import smoke failed:\n{smoke.stderr}")
    smoke_payload = json.loads(smoke.stdout)
    if Path(smoke_payload["alb_file"]).resolve().is_relative_to(REPOSITORY_ROOT / "ALB"):
        raise AssertionError("isolated smoke imported the source tree instead of the wheel")
    if smoke_payload["version"] != "0.2.0":
        raise AssertionError("isolated installation reports the wrong version")
    if any(smoke_payload["removed_specs"].values()):
        raise AssertionError("isolated installation exposes a removed flat module")

    cli_results = {}
    for name, module in {
        "alb-migrate-config": "ALB.config.cli",
        "alb-migrate-surrogate": "ALB.surrogate.cli",
    }.items():
        completed = _run_python(installed_root, "-m", module, "--help")
        cli_results[name] = {
            "module": module,
            "returncode": completed.returncode,
            "usage": next(
                (line.strip() for line in completed.stdout.splitlines() if line.startswith("usage:")),
                "",
            ),
        }
        if completed.returncode != 0 or not cli_results[name]["usage"]:
            raise RuntimeError(f"{name} --help failed:\n{completed.stderr}")

    wheel_payload = wheel.read_bytes()
    return {
        "schema": "alb.build-acceptance.v1",
        "version": "0.2.0",
        "candidate_commit": _git_head(),
        "wheel": {
            "path": wheel.relative_to(REPOSITORY_ROOT).as_posix(),
            "size_bytes": len(wheel_payload),
            "sha256": hashlib.sha256(wheel_payload).hexdigest(),
            "member_count": len(members),
            "forbidden_members_present": forbidden_present,
            "required_members_present": sorted(required_members),
        },
        "metadata": {
            "version": version_values[0],
            "requires_python": python_values[0],
            "extras": sorted(extras),
        },
        "isolated_install": {
            "root": installed_root.relative_to(REPOSITORY_ROOT).as_posix(),
            **smoke_payload,
        },
        "cli_help": cli_results,
        "overall_status": "passed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, default=DEFAULT_WHEEL)
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = validate(args.wheel, args.installed_root)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite acceptance evidence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
