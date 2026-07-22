"""Record per-node pytest outcomes for the 0.2 release acceptance runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any


_REPORTS: list[dict[str, Any]] = []
_ACTIVE_PLUGINS: list[str] = []


def pytest_configure(config: Any) -> None:
    """Record the exact plugin set active in the acceptance process."""

    global _ACTIVE_PLUGINS
    _ACTIVE_PLUGINS = sorted(
        name
        for name, plugin in config.pluginmanager.list_name_plugin()
        if plugin is not None
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
            }
        )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Write ignored intermediate evidence after the entire session."""

    del session
    output = Path(os.environ["ALB_RELEASE_PYTEST_REPORT"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "exitstatus": int(exitstatus),
                "reports": _REPORTS,
                "active_plugins": _ACTIVE_PLUGINS,
                "python_runtime": {
                    "isolated": int(sys.flags.isolated),
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
