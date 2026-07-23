"""Validate the committed same-machine 0.3 performance and memory report."""

from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPOSITORY_ROOT / "docs/migrations/0.3.0_performance.json"


def test_all_required_performance_domains_pass_exact_runtime_and_memory_gates() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    benchmarks = {item["case"]: item for item in report["benchmarks"]}

    assert report["schema"] == "alb.adr-review-performance-comparison.v1"
    assert report["overall_status"] == "passed"
    assert report["gate"]["maximum_time_ratio"] == 1.15
    assert report["gate"]["maximum_memory_ratio"] == 1.15
    assert (
        report["gate"]["maximum_memory_absolute_increase_bytes"]
        == 16 * 1024 * 1024
    )
    assert set(benchmarks) == {"film", "thermal", "alb", "albnn", "coupling"}
    for benchmark in benchmarks.values():
        assert benchmark["exact_reference_passed"] is True
        assert benchmark["status"] == "passed"
        assert benchmark["candidate_to_baseline_time_ratio"] <= 1.15
        memory_failed = (
            benchmark["candidate_to_baseline_memory_ratio"] > 1.15
            and benchmark["peak_memory_increase_bytes"] > 16 * 1024 * 1024
        )
        assert memory_failed is False
