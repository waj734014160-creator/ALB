"""Command-line entry point for ALB 0.2 configuration migration."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .migration import migrate_config_file


def build_parser() -> argparse.ArgumentParser:
    """Build the migration command-line parser."""

    parser = argparse.ArgumentParser(
        description="Save a legacy flat JSON5 configuration as ALB 0.2 JSON."
    )
    parser.add_argument("source", type=Path, help="Legacy JSON5 source path.")
    parser.add_argument("destination", type=Path, help="New output JSON path.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing destination; the source is never modified.",
    )
    return parser


def main() -> int:
    """Run a config migration and print its machine-readable report."""

    args = build_parser().parse_args()
    report = migrate_config_file(args.source, args.destination, overwrite=args.overwrite)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
