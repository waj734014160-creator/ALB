"""File-oriented ALB construction workflow."""

from __future__ import annotations

from pathlib import Path

from ALB.config import load_current_config
from ALB.infrastructure.config_io import read_json5
from ALB.systems.alb.building import (
    BearingBuildDependencies,
    BuiltBearing,
    build_typed_bearing,
)


def build_alb_from_file(
    path: str | Path,
    *,
    dependencies: BearingBuildDependencies | None = None,
) -> BuiltBearing:
    """Read one strict current JSON5 envelope and build its typed runtime.

    Unversioned and 0.2 documents are rejected.  Use ``alb-migrate-config`` to
    save a separate 0.3 envelope before invoking this workflow.
    """

    payload = read_json5(path)
    try:
        config = load_current_config(payload)
    except (TypeError, ValueError) as exc:
        declared = payload.get("schema_version")
        if declared != "0.3.0":
            raise ValueError(
                "build_alb_from_file() accepts only ALB 0.3 envelopes; "
                "run 'alb-migrate-config SOURCE DESTINATION' first"
            ) from exc
        raise
    return build_typed_bearing(config, dependencies=dependencies)


__all__ = ["build_alb_from_file"]
