"""Compare full-refactor performance against the immutable v1 medians.

Exact numerical references are checked before timing.  The command returns a
nonzero exit status for confirmed regressions or noisy, inconclusive samples.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_REPO_ROOT))

from tools.reference.generate_full_repo_refactor_references import (
    CASE_BUILDERS,
    CaseData,
    REPO_ROOT,
    _reset_random_state,
)


DEFAULT_BASELINE = (
    REPO_ROOT / "refs" / "full_repo_refactor_v1" / "performance_baseline.json"
)
REFERENCE_DIR = REPO_ROOT / "refs" / "full_repo_refactor_v1"
CASE_TO_DOMAIN = {
    "film": "film",
    "thermal": "thermal",
    "alb": "systems_alb_harmonic",
    "albnn": "surrogate_training",
    "coupling": "dynamics_coupling",
}


def _git_head() -> str:
    """Return the candidate commit identifier."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _require_single_thread_environment() -> None:
    """Reject timing when native thread settings differ from the baseline."""

    required = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    invalid = {name: os.environ.get(name) for name in required if os.environ.get(name) != "1"}
    if invalid:
        raise RuntimeError(
            "Performance comparison requires single-thread settings: "
            + json.dumps(invalid, sort_keys=True)
        )


def _assert_exact(domain: str, actual: CaseData) -> None:
    """Require exact output identity before any runtime comparison."""

    with np.load(REFERENCE_DIR / f"{domain}.npz") as reference:
        if set(actual.arrays) != set(reference.files):
            raise AssertionError(f"Reference array keys changed for {domain}")
        for key in reference.files:
            np.testing.assert_array_equal(
                np.asarray(actual.arrays[key]),
                reference[key],
                err_msg=f"{domain}:{key}",
            )


def _measure(
    builder: Callable[[], CaseData],
    repeats: int,
    work_units: int,
) -> list[float]:
    """Warm the builder twice, then capture independent elapsed samples."""

    for _ in range(2):
        _reset_random_state()
        builder()
    samples = []
    for _ in range(repeats):
        _reset_random_state()
        start = time.perf_counter()
        for _ in range(work_units):
            builder()
        samples.append((time.perf_counter() - start) / work_units)
    return samples


def _median_absolute_deviation(values: list[float]) -> float:
    """Return the unscaled median absolute deviation."""

    median = statistics.median(values)
    return statistics.median(abs(value - median) for value in values)


def compare(
    baseline_path: Path,
    *,
    max_regression: float,
    selected: set[str] | None,
) -> dict[str, Any]:
    """Run exact gates and same-machine median comparisons."""

    _require_single_thread_environment()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_by_case = {
        item["case"]: item for item in baseline["benchmarks"]
    }
    results = []
    for name, domain in CASE_TO_DOMAIN.items():
        if selected is not None and name not in selected:
            continue
        builder = CASE_BUILDERS[domain]
        _reset_random_state()
        exact_case = builder()
        _assert_exact(domain, exact_case)
        repeats = len(baseline_by_case[name]["samples_seconds"])
        work_units = int(baseline_by_case[name].get("work_units_per_sample", 1))
        samples = _measure(builder, repeats, work_units)
        median = statistics.median(samples)
        mad = _median_absolute_deviation(samples)
        baseline_median = float(baseline_by_case[name]["median_seconds"])
        ratio = median / baseline_median
        noisy = bool(median > 0.0 and mad / median > 0.05)
        if noisy:
            status = "inconclusive"
        elif ratio <= 1.0 + max_regression:
            status = "passed"
        else:
            status = "failed"
        results.append(
            {
                "case": name,
                "domain_reference": domain,
                "exact_reference_passed": True,
                "samples_seconds": samples,
                "work_units_per_sample": work_units,
                "median_seconds": median,
                "mad_seconds": mad,
                "p25_seconds": float(np.percentile(samples, 25)),
                "p75_seconds": float(np.percentile(samples, 75)),
                "baseline_median_seconds": baseline_median,
                "candidate_to_baseline_ratio": ratio,
                "max_allowed_ratio": 1.0 + max_regression,
                "status": status,
            }
        )
    return {
        "schema": "alb.full-repo-refactor-performance-comparison.v1",
        "candidate_commit": _git_head(),
        "baseline": str(baseline_path.resolve()),
        "max_regression": max_regression,
        "benchmarks": results,
        "overall_status": (
            "passed"
            if results and all(item["status"] == "passed" for item in results)
            else "inconclusive"
            if any(item["status"] == "inconclusive" for item in results)
            else "failed"
        ),
    }


def main() -> int:
    """Run the comparison and optionally persist its JSON report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-regression", type=float, default=0.15)
    parser.add_argument(
        "--domains",
        nargs="+",
        choices=sorted(CASE_TO_DOMAIN),
        help="Limit comparison to selected performance cases.",
    )
    args = parser.parse_args()
    if args.max_regression < 0.0:
        raise ValueError("max-regression must be nonnegative")
    payload = compare(
        args.baseline.resolve(),
        max_regression=args.max_regression,
        selected=set(args.domains) if args.domains else None,
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        output = args.output.resolve()
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite comparison: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if payload["overall_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
