"""Record per-node pytest outcomes for the 0.2 release acceptance runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_REPORTS: list[dict[str, Any]] = []


def _reason(report: Any) -> str | None:
    if not report.skipped:
        return None
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    return str(longrepr)


def pytest_runtest_logreport(report: Any) -> None:
    """Capture the decisive report for each normal test or subtest."""

    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _REPORTS.append(
            {
                "nodeid": report.nodeid.replace("\\", "/"),
                "when": report.when,
                "outcome": report.outcome,
                "reason": _reason(report),
                "report_type": type(report).__name__,
            }
        )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Write ignored intermediate evidence after the entire session."""

    del session
    output = Path(os.environ["ALB_RELEASE_PYTEST_REPORT"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"exitstatus": int(exitstatus), "reports": _REPORTS},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
