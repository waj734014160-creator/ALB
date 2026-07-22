"""Record per-node pytest outcomes for the 0.2 release acceptance runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest


_REPORTS: list[dict[str, Any]] = []
_WARNINGS: list[dict[str, Any]] = []


def _active_plugins(pluginmanager: Any) -> list[str]:
    """Return stable names for every plugin active at session completion."""

    return sorted(
        name
        for name, plugin in pluginmanager.list_name_plugin()
        if plugin is not None and not name.isdecimal()
    )


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
                "wasxfail": getattr(report, "wasxfail", None),
            }
        )


def pytest_warning_recorded(
    warning_message: Any,
    when: str,
    nodeid: str,
    location: tuple[str, int, str] | None,
) -> None:
    """Capture structured warning evidence instead of parsing terminal text."""

    category = warning_message.category
    _WARNINGS.append(
        {
            "category": f"{category.__module__}.{category.__qualname__}",
            "message": str(warning_message.message),
            "when": when,
            "nodeid": nodeid.replace("\\", "/"),
            "location": list(location) if location is not None else None,
        }
    )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Write ignored intermediate evidence after the entire session."""

    output = Path(os.environ["ALB_RELEASE_PYTEST_REPORT"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "exitstatus": int(exitstatus),
                "reports": _REPORTS,
                "warnings": _WARNINGS,
                "pytest_version": pytest.__version__,
                "active_plugins": _active_plugins(session.config.pluginmanager),
                "python_runtime": {
                    "isolated": int(sys.flags.isolated),
                    "ignore_environment": int(sys.flags.ignore_environment),
                    "no_user_site": int(sys.flags.no_user_site),
                    "optimize": int(sys.flags.optimize),
                    "warnoptions": list(sys.warnoptions),
                    "pytest_disable_plugin_autoload": os.environ.get(
                        "PYTEST_DISABLE_PLUGIN_AUTOLOAD"
                    ),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
