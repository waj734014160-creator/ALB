"""Command-line entry point for strict ALB 0.3 configuration migration."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .migration import migrate_config_file


def build_parser() -> argparse.ArgumentParser:
    """Build the migration command-line parser."""

    parser = argparse.ArgumentParser(
        description="Save a legacy flat JSON5 configuration as ALB 0.3 JSON."
    )
    parser.add_argument("source", type=Path, help="Legacy JSON5 source path.")
    parser.add_argument("destination", type=Path, help="New output JSON path.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing destination; the source is never modified.",
    )
    parser.add_argument(
        "--unit-system",
        choices=("dimensional", "nondimensional"),
        default="dimensional",
        help="Unit system declared by the legacy ALB configuration.",
    )
    parser.add_argument(
        "--control-mode",
        choices=("controlled", "none", "direct_spool"),
        default=None,
        help="Explicit 0.3 control mode; otherwise infer from legacy fields.",
    )
    parser.add_argument(
        "--controller",
        choices=("PID", "FuzzyPID", "none"),
        default="PID",
        help="Legacy controller type used while materializing the old mapping.",
    )
    return parser


def main() -> int:
    """Run a config migration and print its machine-readable report."""

    args = build_parser().parse_args()
    controller = None if args.controller == "none" else args.controller
    report = migrate_config_file(
        args.source,
        args.destination,
        unit_system=args.unit_system,
        control_mode=args.control_mode,
        controller=controller,
        overwrite=args.overwrite,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
