"""Capture and compare the fixed ALB 0.3 ADR performance and memory gates.

The baseline and candidate must run on the same machine and interpreter. Each
case is checked against the immutable numerical references before timing.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tracemalloc
from typing import Any, Callable

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.reference.generate_full_repo_refactor_references import (
    CASE_BUILDERS,
    CaseData,
    _reset_random_state,
)


REFERENCE_ROOT = REPOSITORY_ROOT / "refs/full_repo_refactor_v1"
LEGACY_BASELINE = REFERENCE_ROOT / "performance_baseline.json"
CASE_TO_DOMAIN = {
    "film": "film",
    "thermal": "thermal",
    "alb": "systems_alb_harmonic",
    "albnn": "surrogate_training",
    "coupling": "dynamics_coupling",
}
WARMUP_COUNT = 3
SAMPLE_COUNT = 9
MEMORY_SAMPLE_COUNT = 5
MIN_SAMPLE_SECONDS = 0.05
MAX_TIME_RATIO = 1.15
MAX_MEMORY_RATIO = 1.15
MAX_MEMORY_ABSOLUTE_INCREASE = 16 * 1024 * 1024


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _require_single_thread_environment() -> dict[str, str]:
    required = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    values = {name: os.environ.get(name, "") for name in required}
    invalid = {name: value for name, value in values.items() if value != "1"}
    if invalid:
        raise RuntimeError(
            "benchmark requires single-thread native libraries: "
            + json.dumps(invalid, sort_keys=True)
        )
    return values


def _power_plan() -> str:
    if os.name != "nt":
        return "not-windows"
    completed = subprocess.run(
        ["powercfg", "/getactivescheme"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return (completed.stdout or completed.stderr).strip()


def _environment() -> dict[str, Any]:
    packages = {}
    for name in ("numpy", "scipy", "torch", "ross-rotordynamics"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "python": sys.version,
        "executable": str(Path(sys.executable).resolve()),
        "packages": packages,
        "native_threads": _require_single_thread_environment(),
        "power_plan": _power_plan(),
        "measurement_process": os.getpid(),
        "memory_tool": "tracemalloc",
    }


def _array_descriptors(actual: CaseData) -> dict[str, dict[str, object]]:
    return {
        name: {
            "shape": list(np.asarray(value).shape),
            "dtype": str(np.asarray(value).dtype),
            "sha256": hashlib.sha256(
                np.ascontiguousarray(value).tobytes()
            ).hexdigest(),
        }
        for name, value in sorted(actual.arrays.items())
    }


def _assert_legacy_exact(domain: str, actual: CaseData) -> None:
    with np.load(REFERENCE_ROOT / f"{domain}.npz", allow_pickle=False) as frozen:
        if set(actual.arrays) != set(frozen.files):
            raise AssertionError(f"reference array keys changed for {domain}")
        for name in frozen.files:
            np.testing.assert_array_equal(
                np.asarray(actual.arrays[name]),
                frozen[name],
                err_msg=f"{domain}:{name}",
            )


def _assert_candidate_exact(
    actual: CaseData,
    expected: dict[str, dict[str, object]],
) -> None:
    observed = _array_descriptors(actual)
    if observed != expected:
        raise AssertionError("candidate arrays differ from the ADR baseline")


def _work_units() -> dict[str, int]:
    payload = json.loads(LEGACY_BASELINE.read_text(encoding="utf-8"))
    return {
        item["case"]: int(item.get("work_units_per_sample", 1))
        for item in payload["benchmarks"]
    }


def _median_absolute_deviation(samples: list[float]) -> float:
    median = statistics.median(samples)
    return statistics.median(abs(value - median) for value in samples)


def _time_case(
    builder: Callable[[], CaseData],
    work_units: int,
) -> list[float]:
    for _ in range(WARMUP_COUNT):
        _reset_random_state()
        builder()
    samples = []
    for _ in range(SAMPLE_COUNT):
        _reset_random_state()
        started = time.perf_counter()
        for _ in range(work_units):
            builder()
        samples.append(time.perf_counter() - started)
    if statistics.median(samples) < MIN_SAMPLE_SECONDS:
        raise RuntimeError("timed sample is shorter than the 50 ms gate")
    return samples


def _memory_case(builder: Callable[[], CaseData]) -> list[int]:
    peaks = []
    for _ in range(MEMORY_SAMPLE_COUNT):
        gc.collect()
        _reset_random_state()
        tracemalloc.start()
        try:
            builder()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        peaks.append(int(peak))
    return peaks


def _capture_case(
    name: str,
    domain: str,
    work_units: int,
    *,
    expected_exact: dict[str, dict[str, object]] | None = None,
) -> dict[str, Any]:
    builder = CASE_BUILDERS[domain]
    _reset_random_state()
    exact_case = builder()
    if expected_exact is None:
        if name != "coupling":
            _assert_legacy_exact(domain, exact_case)
    else:
        _assert_candidate_exact(exact_case, expected_exact)
    samples = _time_case(builder, work_units)
    memory_samples = _memory_case(builder)
    median = statistics.median(samples)
    mad = _median_absolute_deviation(samples)
    return {
        "case": name,
        "domain_reference": domain,
        "exact_reference_passed": True,
        "exact_arrays": _array_descriptors(exact_case),
        "warmup_count": WARMUP_COUNT,
        "sample_count": SAMPLE_COUNT,
        "work_units_per_sample": work_units,
        "samples_seconds": samples,
        "median_seconds_per_sample": median,
        "median_seconds_per_work_unit": median / work_units,
        "mad_seconds_per_sample": mad,
        "p25_seconds_per_sample": float(np.percentile(samples, 25)),
        "p75_seconds_per_sample": float(np.percentile(samples, 75)),
        "memory_sample_count": MEMORY_SAMPLE_COUNT,
        "peak_memory_samples_bytes": memory_samples,
        "peak_memory_median_bytes": int(statistics.median(memory_samples)),
        "timing_noise_ratio": mad / median if median else 0.0,
    }


def capture() -> dict[str, Any]:
    units = _work_units()
    benchmarks = [
        _capture_case(name, domain, units[name])
        for name, domain in CASE_TO_DOMAIN.items()
    ]
    return {
        "schema": "alb.adr-review-performance-baseline.v1",
        "candidate_commit": _git_head(),
        "environment": _environment(),
        "gate": {
            "minimum_sample_seconds": MIN_SAMPLE_SECONDS,
            "maximum_time_ratio": MAX_TIME_RATIO,
            "maximum_memory_ratio": MAX_MEMORY_RATIO,
            "maximum_memory_absolute_increase_bytes": (
                MAX_MEMORY_ABSOLUTE_INCREASE
            ),
        },
        "benchmarks": benchmarks,
        "overall_status": (
            "passed"
            if all(item["timing_noise_ratio"] <= 0.05 for item in benchmarks)
            else "inconclusive"
        ),
    }


def compare(baseline: dict[str, Any]) -> dict[str, Any]:
    current_environment = _environment()
    baseline_environment = baseline["environment"]
    identity_fields = (
        "platform",
        "processor",
        "logical_cpu_count",
        "executable",
        "native_threads",
        "power_plan",
    )
    mismatches = {
        field: {
            "baseline": baseline_environment[field],
            "candidate": current_environment[field],
        }
        for field in identity_fields
        if baseline_environment[field] != current_environment[field]
    }
    if mismatches:
        raise RuntimeError(
            "candidate environment differs from baseline: "
            + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )

    baseline_by_case = {
        item["case"]: item for item in baseline["benchmarks"]
    }
    benchmarks = []
    for name, domain in CASE_TO_DOMAIN.items():
        baseline_case = baseline_by_case[name]
        candidate = _capture_case(
            name,
            domain,
            int(baseline_case["work_units_per_sample"]),
            expected_exact=baseline_case["exact_arrays"],
        )
        time_ratio = (
            candidate["median_seconds_per_sample"]
            / baseline_case["median_seconds_per_sample"]
        )
        memory_delta = (
            candidate["peak_memory_median_bytes"]
            - baseline_case["peak_memory_median_bytes"]
        )
        baseline_memory = baseline_case["peak_memory_median_bytes"]
        memory_ratio = (
            candidate["peak_memory_median_bytes"] / baseline_memory
            if baseline_memory
            else 1.0
        )
        time_failed = time_ratio > MAX_TIME_RATIO
        memory_failed = (
            memory_ratio > MAX_MEMORY_RATIO
            and memory_delta > MAX_MEMORY_ABSOLUTE_INCREASE
        )
        noisy = candidate["timing_noise_ratio"] > 0.05
        candidate.update(
            {
                "baseline_median_seconds_per_sample": baseline_case[
                    "median_seconds_per_sample"
                ],
                "candidate_to_baseline_time_ratio": time_ratio,
                "baseline_peak_memory_median_bytes": baseline_memory,
                "candidate_to_baseline_memory_ratio": memory_ratio,
                "peak_memory_increase_bytes": memory_delta,
                "status": (
                    "inconclusive"
                    if noisy
                    else "failed"
                    if time_failed or memory_failed
                    else "passed"
                ),
            }
        )
        benchmarks.append(candidate)
    return {
        "schema": "alb.adr-review-performance-comparison.v1",
        "candidate_commit": _git_head(),
        "baseline_commit": baseline["candidate_commit"],
        "environment": current_environment,
        "gate": baseline["gate"],
        "benchmarks": benchmarks,
        "overall_status": (
            "passed"
            if all(item["status"] == "passed" for item in benchmarks)
            else "inconclusive"
            if any(item["status"] == "inconclusive" for item in benchmarks)
            else "failed"
        ),
    }


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite benchmark report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    payload = (
        capture()
        if args.baseline is None
        else compare(
            json.loads(args.baseline.read_text(encoding="utf-8"))
        )
    )
    _write_new(args.output.resolve(), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["overall_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
