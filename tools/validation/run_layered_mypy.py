"""Run strict 0.4 boundary typing plus an exact numerical-core baseline."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPOSITORY_ROOT / "tools/validation/mypy_layer_baseline_0_4.json"
DIAGNOSTIC_PATTERN = re.compile(
    r"^(ALB[\\/][^:]+):\d+: error: .*\[([^\]]+)\]$"
)

STRICT_TARGETS = (
    "ALB/contracts",
    "ALB/core",
    "ALB/api",
    "ALB/control/blocks.py",
    "ALB/dynamics/rotor_layout.py",
    "ALB/dynamics/rotor_results.py",
    "ALB/dynamics/coupling_runtime.py",
    "ALB/dynamics/bindings.py",
    "ALB/infrastructure/recording.py",
    "ALB/systems/alb/scales.py",
    "ALB/systems/alb/_harmonic_runtime.py",
    "ALB/systems/alb/harmonic_coefficients.py",
    "ALB/systems/alb/harmonic_results.py",
    "ALB/surrogate/package.py",
    "ALB/surrogate/scaler_io.py",
    "ALB/surrogate/runtime.py",
    "ALB/physics/gas/runtime.py",
    "tools/validation/release_phases.py",
    "tools/validation/release_source_identity.py",
    "tools/validation/run_resource_acceptance_0_4.py",
    "tools/validation/run_release_acceptance_0_4.py",
)
COVERED_NAMESPACES = (
    "ALB/api",
    "ALB/contracts",
    "ALB/core",
    "ALB/config",
    "ALB/control",
    "ALB/dynamics",
    "ALB/infrastructure",
    "ALB/physics",
    "ALB/surrogate",
    "ALB/systems",
    "ALB/workflows",
)
IMPLEMENTATION_RELAXATIONS = (
    "--allow-untyped-defs",
    "--allow-incomplete-defs",
    "--allow-untyped-calls",
    "--allow-any-generics",
    "--ignore-missing-imports",
    "--no-warn-unused-ignores",
    "--disable-error-code=no-any-return",
    "--disable-error-code=var-annotated",
)


def diagnostic_counts(output: str) -> Counter[str]:
    """Normalize mypy diagnostics to stable file-and-code counts."""

    counts: Counter[str] = Counter()
    for line in output.splitlines():
        match = DIAGNOSTIC_PATTERN.match(line.strip())
        if match is None:
            continue
        path = match.group(1).replace("\\", "/")
        counts[f"{path}|{match.group(2)}"] += 1
    return counts


def discover_covered_sources(root: Path = REPOSITORY_ROOT) -> tuple[str, ...]:
    """Return every Python implementation examined by the layered gate."""

    files = {
        path.relative_to(root).as_posix()
        for namespace in COVERED_NAMESPACES
        for path in (root / namespace).rglob("*.py")
    }
    return tuple(sorted(files))


def _mypy_command(
    targets: Iterable[str],
    *,
    mypy_target: Path,
    cache_dir: Path,
    relaxations: Iterable[str] = (),
) -> list[str]:
    bootstrap = (
        "import runpy,sys;"
        f"sys.path.insert(0, {str(mypy_target)!r});"
        "sys.argv=['mypy', *sys.argv[1:]];"
        "runpy.run_module('mypy', run_name='__main__')"
    )
    return [
        sys.executable,
        "-E",
        "-s",
        "-c",
        bootstrap,
        *targets,
        "--config-file",
        str(REPOSITORY_ROOT / "pyproject.toml"),
        "--no-incremental",
        "--cache-dir",
        str(cache_dir),
        "--no-error-summary",
        "--no-color-output",
        *relaxations,
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _baseline_payload(counts: Counter[str]) -> dict[str, object]:
    return {
        "schema": "alb.layered-mypy-baseline.v1",
        "strict_targets": list(STRICT_TARGETS),
        "covered_namespaces": list(COVERED_NAMESPACES),
        "covered_source_files": list(discover_covered_sources()),
        "implementation_relaxations": list(IMPLEMENTATION_RELAXATIONS),
        "implementation_diagnostics": dict(sorted(counts.items())),
    }


def run_layered_mypy(
    *,
    mypy_target: Path,
    cache_root: Path,
    update_baseline: bool = False,
) -> dict[str, object]:
    """Execute both layers and require an exact committed legacy baseline."""

    strict = _run(
        _mypy_command(
            STRICT_TARGETS,
            mypy_target=mypy_target,
            cache_dir=cache_root / "strict",
        )
    )
    if strict.returncode != 0:
        raise RuntimeError("strict mypy layer failed:\n" + strict.stdout + strict.stderr)

    legacy = _run(
        _mypy_command(
            COVERED_NAMESPACES,
            mypy_target=mypy_target,
            cache_dir=cache_root / "covered",
            relaxations=IMPLEMENTATION_RELAXATIONS,
        )
    )
    combined = legacy.stdout + legacy.stderr
    counts = diagnostic_counts(combined)
    if legacy.returncode not in {0, 1}:
        raise RuntimeError("mypy coverage layer did not complete:\n" + combined)
    if legacy.returncode == 1 and not counts:
        raise RuntimeError("mypy coverage layer failed without parsed diagnostics:\n" + combined)

    payload = _baseline_payload(counts)
    if update_baseline:
        BASELINE_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    else:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        if payload != baseline:
            raise RuntimeError(
                "layered mypy baseline changed; inspect diagnostics and update "
                "the baseline only after resolving or accepting the exact delta"
            )
    return {
        "strict_returncode": strict.returncode,
        "strict_targets": len(STRICT_TARGETS),
        "covered_source_files": len(payload["covered_source_files"]),
        "implementation_diagnostics": sum(counts.values()),
        "implementation_diagnostic_groups": len(counts),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mypy-target",
        type=Path,
        default=REPOSITORY_ROOT / "outputs/.devtools",
        help="Directory containing the isolated mypy package.",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=REPOSITORY_ROOT / "outputs/mypy_layered_cache",
    )
    parser.add_argument("--update-baseline", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = run_layered_mypy(
        mypy_target=args.mypy_target.resolve(),
        cache_root=args.cache_root.resolve(),
        update_baseline=args.update_baseline,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
