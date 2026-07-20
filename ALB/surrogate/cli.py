"""Command-line entry points for surrogate package migration."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .migration import migrate_legacy_model_package


def build_parser() -> argparse.ArgumentParser:
    """Build the legacy-package migration parser."""

    parser = argparse.ArgumentParser(
        description="Copy legacy ALBNN artifacts into a validated ALB 0.2 package."
    )
    parser.add_argument("model", type=Path)
    parser.add_argument("input_scaler", type=Path)
    parser.add_argument("output_scaler", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    """Run model-package migration and print a JSON report."""

    args = build_parser().parse_args()
    report = migrate_legacy_model_package(
        args.model,
        args.input_scaler,
        args.output_scaler,
        args.destination,
        metadata=args.metadata,
        overwrite=args.overwrite,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
