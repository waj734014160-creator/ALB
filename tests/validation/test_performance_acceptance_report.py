"""Validate the committed same-machine 0.2 performance acceptance report."""

from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPOSITORY_ROOT / "docs/migrations/0.2.0_performance.json"


def test_all_required_performance_domains_pass_exact_and_runtime_gates() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    benchmarks = {item["case"]: item for item in report["benchmarks"]}

    assert report["overall_status"] == "passed"
    assert report["max_regression"] == 0.15
    assert set(benchmarks) == {"film", "thermal", "alb", "albnn", "coupling"}
    for benchmark in benchmarks.values():
        assert benchmark["exact_reference_passed"] is True
        assert benchmark["status"] == "passed"
        assert benchmark["candidate_to_baseline_ratio"] <= 1.15
