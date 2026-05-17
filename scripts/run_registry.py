# coding: utf-8
"""Project-local JSONL run registry helpers.

The registry keeps the current path locator for each registered run in each
project's ``docs/run_registry.jsonl`` file while human-facing rules stay in
``ALB_MAIN/docs/run_index.md``. It is intentionally not a history log.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


PROJECT_PREFIXES = {
    "ALB_MAIN": "A",
    "SURROGATE_TRAIN": "S",
    "PARAM_SCAN": "P",
    "DATA_POSTPROCESS": "D",
    "VALIDATION": "V",
    "ARTIFACTS_ARCHIVE": "X",
}

PREFIX_PROJECTS = {prefix: owner for owner, prefix in PROJECT_PREFIXES.items()}
REGISTRY_RELATIVE_PATH = Path("docs") / "run_registry.jsonl"
RUN_NO_PATTERN = re.compile(r"^([A-Z])(\d{4})$")


class RunRegistryError(RuntimeError):
    """Raised when a run registry operation cannot be completed safely."""


@dataclass(frozen=True)
class RegistryEntry:
    """One current run registry locator record."""

    event: str
    timestamp: str
    run_no: str
    run_id: str
    owner: str
    domain: str
    state: str
    config: str | None
    outputs: str | None
    logs: Any
    archive: str | None
    notes: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "RegistryEntry":
        """Build an entry from a decoded JSON object."""
        missing = [
            key
            for key in (
                "event",
                "timestamp",
                "run_no",
                "run_id",
                "owner",
                "domain",
                "state",
                "config",
                "outputs",
                "logs",
                "archive",
                "notes",
            )
            if key not in data
        ]
        if missing:
            raise RunRegistryError(
                "Registry entry is missing required field(s): " + ", ".join(missing)
            )
        return cls(
            event=str(data["event"]),
            timestamp=str(data["timestamp"]),
            run_no=str(data["run_no"]),
            run_id=str(data["run_id"]),
            owner=str(data["owner"]),
            domain=str(data["domain"]),
            state=str(data["state"]),
            config=None if data["config"] is None else str(data["config"]),
            outputs=None if data["outputs"] is None else str(data["outputs"]),
            logs=data["logs"],
            archive=None if data["archive"] is None else str(data["archive"]),
            notes=str(data["notes"]),
        )

    def to_mapping(self) -> dict[str, Any]:
        """Return a stable JSON-serializable mapping."""
        return {
            "run_no": self.run_no,
            "run_id": self.run_id,
            "event": self.event,
            "timestamp": self.timestamp,
            "owner": self.owner,
            "domain": self.domain,
            "state": self.state,
            "config": self.config,
            "outputs": self.outputs,
            "logs": self.logs,
            "archive": self.archive,
            "notes": self.notes,
        }


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp for registry events."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_owner(owner: str) -> str:
    """Return the canonical project owner name for ``owner``."""
    normalized = owner.strip().upper()
    if normalized not in PROJECT_PREFIXES:
        raise RunRegistryError(
            f"Unknown project owner {owner!r}; expected one of "
            + ", ".join(sorted(PROJECT_PREFIXES))
        )
    return normalized


def registry_path(project_root: str | Path) -> Path:
    """Return the JSONL registry path for one project root."""
    return Path(project_root).resolve() / REGISTRY_RELATIVE_PATH


def find_project_root(path: str | Path) -> Path | None:
    """Find the nearest parent directory named like an ALB_PROJECTS project."""
    current = Path(path).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if candidate.name.upper() in PROJECT_PREFIXES:
            return candidate
    return None


def owner_from_project_root(project_root: str | Path) -> str:
    """Return the registry owner implied by a project root directory name."""
    return normalize_owner(Path(project_root).resolve().name)


def read_entries(path: str | Path) -> list[RegistryEntry]:
    """Read all registry entries from ``path``."""
    registry = Path(path)
    if not registry.exists():
        return []
    entries: list[RegistryEntry] = []
    with registry.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RunRegistryError(
                    f"Invalid JSON in {registry} line {line_no}: {exc}"
                ) from exc
            if not isinstance(data, dict):
                raise RunRegistryError(f"Registry line {line_no} must be a JSON object")
            entries.append(RegistryEntry.from_mapping(data))
    return entries


def write_entries(path: str | Path, entries: list[RegistryEntry]) -> None:
    """Replace ``path`` with the supplied current registry entries."""
    registry = Path(path)
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("w", encoding="utf-8", newline="\n") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_mapping(), ensure_ascii=False))
            f.write("\n")


def current_entries(entries: list[RegistryEntry]) -> list[RegistryEntry]:
    """Return one latest locator entry per run ID, preserving first-seen order."""
    order: list[str] = []
    latest: dict[str, RegistryEntry] = {}
    for entry in entries:
        if entry.run_id not in latest:
            order.append(entry.run_id)
        latest[entry.run_id] = entry
    return [latest[run_id] for run_id in order]


def latest_by_run_id(entries: list[RegistryEntry]) -> dict[str, RegistryEntry]:
    """Return the latest event for every run ID."""
    latest: dict[str, RegistryEntry] = {}
    for entry in entries:
        latest[entry.run_id] = entry
    return latest


def latest_by_run_no(entries: list[RegistryEntry]) -> dict[str, RegistryEntry]:
    """Return the latest event for every project-local run number."""
    latest: dict[str, RegistryEntry] = {}
    for entry in entries:
        latest[entry.run_no] = entry
    return latest


def next_run_no(owner: str, entries: list[RegistryEntry]) -> str:
    """Allocate the next project-local run number for ``owner``."""
    owner = normalize_owner(owner)
    prefix = PROJECT_PREFIXES[owner]
    max_seen = 0
    for entry in entries:
        match = RUN_NO_PATTERN.match(entry.run_no)
        if match and match.group(1) == prefix:
            max_seen = max(max_seen, int(match.group(2)))
    return f"{prefix}{max_seen + 1:04d}"


def validate_run_no_for_owner(run_no: str, owner: str) -> None:
    """Ensure ``run_no`` uses the prefix assigned to ``owner``."""
    owner = normalize_owner(owner)
    match = RUN_NO_PATTERN.match(run_no)
    if not match:
        raise RunRegistryError(f"Invalid run_no {run_no!r}; expected e.g. S0001")
    expected = PROJECT_PREFIXES[owner]
    if match.group(1) != expected:
        raise RunRegistryError(
            f"run_no {run_no!r} does not match owner {owner}; expected prefix {expected}"
        )


def build_run_id(domain: str, purpose: str, size_or_key: str, date: str, run_no: str) -> str:
    """Build a semantic run ID prefixed by the project-local run number."""
    parts = [run_no, domain, purpose, size_or_key, date]
    cleaned = [re.sub(r"[^A-Za-z0-9_.-]+", "_", part.strip()).strip("_") for part in parts]
    if any(not part for part in cleaned):
        raise RunRegistryError("domain, purpose, size_or_key, date, and run_no are required")
    return "_".join(cleaned)


def default_paths(domain: str, run_id: str) -> dict[str, Any]:
    """Return default relative config and output paths for a run."""
    return {
        "config": f"run/remote/configs/{run_id}.json",
        "outputs": f"outputs/{domain}/{run_id}",
        "logs": None,
        "archive": None,
    }


def parse_log_values(values: list[str] | None) -> Any:
    """Parse ``--log key=value`` values into a mapping when provided."""
    if not values:
        return None
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise RunRegistryError(f"Log path must use key=value form: {value}")
        key, path = value.split("=", 1)
        key = key.strip()
        path = path.strip()
        if not key or not path:
            raise RunRegistryError(f"Log path must use key=value form: {value}")
        parsed[key] = path
    return parsed


def register_run(
    *,
    project_root: str | Path,
    owner: str | None = None,
    domain: str,
    purpose: str,
    size_or_key: str,
    date: str,
    run_id: str | None = None,
    state: str = "registered",
    config: str | None = None,
    outputs: str | None = None,
    logs: Any = None,
    archive: str | None = None,
    notes: str = "",
    timestamp: str | None = None,
    allow_archive_owner: bool = False,
) -> RegistryEntry:
    """Allocate and write a new run registration locator."""
    project_root = Path(project_root).resolve()
    owner = normalize_owner(owner or owner_from_project_root(project_root))
    if owner == "ARTIFACTS_ARCHIVE" and not allow_archive_owner:
        raise RunRegistryError(
            "ARTIFACTS_ARCHIVE is archive-only by default; pass --allow-archive-owner "
            "only for an explicitly approved archive-owned run"
        )
    path = registry_path(project_root)
    entries = read_entries(path)
    run_no = next_run_no(owner, entries)
    run_id = run_id or build_run_id(domain, purpose, size_or_key, date, run_no)
    if run_id in latest_by_run_id(entries):
        raise RunRegistryError(f"run_id already exists in registry: {run_id}")
    defaults = default_paths(domain, run_id)
    entry = RegistryEntry(
        event="register",
        timestamp=timestamp or utc_timestamp(),
        run_no=run_no,
        run_id=run_id,
        owner=owner,
        domain=domain,
        state=state,
        config=config if config is not None else defaults["config"],
        outputs=outputs if outputs is not None else defaults["outputs"],
        logs=logs if logs is not None else defaults["logs"],
        archive=archive if archive is not None else defaults["archive"],
        notes=notes,
    )
    write_entries(path, current_entries(entries) + [entry])
    return entry


def update_run(
    *,
    project_root: str | Path,
    run_id: str,
    state: str,
    event: str = "update",
    config: str | None = None,
    outputs: str | None = None,
    logs: Any = None,
    clear_logs: bool = False,
    archive: str | None = None,
    clear_archive: bool = False,
    notes: str = "",
    timestamp: str | None = None,
) -> RegistryEntry:
    """Append a state update event for an existing registered run."""
    if clear_logs and logs is not None:
        raise RunRegistryError("--clear-logs cannot be combined with --log")
    if clear_archive and archive is not None:
        raise RunRegistryError("--clear-archive cannot be combined with --archive")
    project_root = Path(project_root).resolve()
    path = registry_path(project_root)
    entries = read_entries(path)
    latest = latest_by_run_id(entries).get(run_id)
    if latest is None:
        raise RunRegistryError(f"run_id is not registered in {path}: {run_id}")
    entry = RegistryEntry(
        event=event,
        timestamp=timestamp or utc_timestamp(),
        run_no=latest.run_no,
        run_id=latest.run_id,
        owner=latest.owner,
        domain=latest.domain,
        state=state,
        config=latest.config if config is None else config,
        outputs=latest.outputs if outputs is None else outputs,
        logs=None if clear_logs else (latest.logs if logs is None else logs),
        archive=None if clear_archive else (latest.archive if archive is None else archive),
        notes=notes,
    )
    compacted = [existing for existing in current_entries(entries) if existing.run_id != run_id]
    write_entries(path, compacted + [entry])
    return entry


def _is_relative_project_path(value: str) -> bool:
    """Return whether ``value`` looks like a project-relative path."""
    path = Path(value)
    if path.is_absolute():
        return False
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return False
    if value.startswith(("/", "\\")):
        return False
    return True


def _resolve_project_paths(project_root: Path, value: Any) -> Any:
    """Resolve project-relative string paths while preserving remote paths."""
    if isinstance(value, str):
        item = {"path": value}
        if _is_relative_project_path(value):
            item["abs_path"] = str((project_root / value).resolve())
        return item
    if isinstance(value, dict):
        return {key: _resolve_project_paths(project_root, path) for key, path in value.items()}
    return value


def run_paths_by_run_no(*, project_root: str | Path, run_no: str) -> dict[str, Any]:
    """Return the latest path locator view for ``run_no``."""
    project_root = Path(project_root).resolve()
    latest = latest_by_run_no(read_entries(registry_path(project_root))).get(run_no)
    if latest is None:
        raise RunRegistryError(f"run_no is not registered in {registry_path(project_root)}: {run_no}")
    return {
        "project_root": str(project_root),
        "run_no": latest.run_no,
        "run_id": latest.run_id,
        "owner": latest.owner,
        "domain": latest.domain,
        "state": latest.state,
        "paths": {
            "config": _resolve_project_paths(project_root, latest.config),
            "outputs": _resolve_project_paths(project_root, latest.outputs),
            "logs": _resolve_project_paths(project_root, latest.logs),
            "archive": _resolve_project_paths(project_root, latest.archive),
        },
        "latest_event": latest.event,
        "timestamp": latest.timestamp,
        "notes": latest.notes,
    }


def validate_registered_run(
    *,
    project_root: str | Path,
    run_id: str,
    owner: str | None = None,
) -> RegistryEntry:
    """Return the latest entry for ``run_id`` or raise a validation error."""
    path = registry_path(project_root)
    latest = latest_by_run_id(read_entries(path)).get(run_id)
    if latest is None:
        raise RunRegistryError(
            f"run_id {run_id!r} is not registered in {path}. "
            "Register it first with: python scripts/run_registry.py register ..."
        )
    expected_owner = normalize_owner(owner) if owner else owner_from_project_root(project_root)
    if latest.owner != expected_owner:
        raise RunRegistryError(
            f"run_id {run_id!r} is owned by {latest.owner}, not {expected_owner}"
        )
    validate_run_no_for_owner(latest.run_no, latest.owner)
    if not latest.run_id.startswith(f"{latest.run_no}_"):
        raise RunRegistryError(
            f"run_id {latest.run_id!r} must start with run_no {latest.run_no}"
        )
    return latest


def validate_config_registration(config: dict[str, Any]) -> RegistryEntry:
    """Validate that a launch config references a registered run ID."""
    run_id = str(config.get("run_id") or "").strip()
    if not run_id:
        raise RunRegistryError(
            "Remote launch/queue configs must include a top-level 'run_id'. "
            "Register the run first with: python scripts/run_registry.py register ..."
        )
    registry_cfg = config.get("run_registry") or {}
    if registry_cfg and not isinstance(registry_cfg, dict):
        raise RunRegistryError("run_registry must be a JSON object when provided")

    owner = config.get("owner") or registry_cfg.get("owner")
    config_dir = config.get("_config_dir")
    project_root = registry_cfg.get("project_root")
    if project_root is not None:
        project_root = Path(str(project_root))
        if not project_root.is_absolute() and config_dir is not None:
            project_root = Path(str(config_dir)) / project_root
    if project_root is None:
        if config_dir is not None:
            found = find_project_root(config_dir)
            if found is not None:
                project_root = found
    if project_root is None:
        raise RunRegistryError(
            "Cannot locate the owning project root for run registry validation. "
            "Set run_registry.project_root in the config."
        )
    return validate_registered_run(
        project_root=project_root,
        run_id=run_id,
        owner=None if owner is None else str(owner),
    )


def _print_entry(entry: RegistryEntry) -> None:
    print(json.dumps(entry.to_mapping(), indent=2, ensure_ascii=False))


def _add_common_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=".")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for ``python scripts/run_registry.py``."""
    parser = argparse.ArgumentParser(description="ALB_PROJECTS run registry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register", help="Allocate and write a new run locator")
    _add_common_project_args(register)
    register.add_argument("--owner")
    register.add_argument("--domain", required=True)
    register.add_argument("--purpose", required=True)
    register.add_argument("--size-or-key", required=True)
    register.add_argument("--date", required=True)
    register.add_argument("--run-id")
    register.add_argument("--state", default="registered")
    register.add_argument("--config")
    register.add_argument("--outputs")
    register.add_argument("--log", action="append", default=[])
    register.add_argument("--archive")
    register.add_argument("--notes", default="")
    register.add_argument("--allow-archive-owner", action="store_true")

    update = subparsers.add_parser("update", help="Append a state update event")
    _add_common_project_args(update)
    update.add_argument("--run-id", required=True)
    update.add_argument("--state", required=True)
    update.add_argument("--event", default="update")
    update.add_argument("--config")
    update.add_argument("--outputs")
    update.add_argument("--log", action="append", default=[])
    update.add_argument("--clear-logs", action="store_true")
    update.add_argument("--archive")
    update.add_argument("--clear-archive", action="store_true")
    update.add_argument("--notes", default="")

    list_parser = subparsers.add_parser("list", help="List latest run registry state")
    _add_common_project_args(list_parser)
    list_parser.add_argument("--all-events", action="store_true")

    paths = subparsers.add_parser("paths", help="Show project file paths for one run_no")
    _add_common_project_args(paths)
    paths.add_argument("--run-no", required=True)

    validate = subparsers.add_parser("validate", help="Validate one registered run")
    _add_common_project_args(validate)
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--owner")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for run registry commands."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "register":
            logs = parse_log_values(args.log)
            entry = register_run(
                project_root=args.project_root,
                owner=args.owner,
                domain=args.domain,
                purpose=args.purpose,
                size_or_key=args.size_or_key,
                date=args.date,
                run_id=args.run_id,
                state=args.state,
                config=args.config,
                outputs=args.outputs,
                logs=logs,
                archive=args.archive,
                notes=args.notes,
                allow_archive_owner=args.allow_archive_owner,
            )
            _print_entry(entry)
            return 0
        if args.command == "update":
            logs = parse_log_values(args.log)
            entry = update_run(
                project_root=args.project_root,
                run_id=args.run_id,
                state=args.state,
                event=args.event,
                config=args.config,
                outputs=args.outputs,
                logs=logs,
                clear_logs=args.clear_logs,
                archive=args.archive,
                clear_archive=args.clear_archive,
                notes=args.notes,
            )
            _print_entry(entry)
            return 0
        if args.command == "list":
            entries = read_entries(registry_path(args.project_root))
            if not args.all_events:
                entries = list(latest_by_run_id(entries).values())
            for entry in entries:
                print(json.dumps(entry.to_mapping(), ensure_ascii=False))
            return 0
        if args.command == "paths":
            print(
                json.dumps(
                    run_paths_by_run_no(
                        project_root=args.project_root,
                        run_no=args.run_no,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "validate":
            _print_entry(
                validate_registered_run(
                    project_root=args.project_root,
                    run_id=args.run_id,
                    owner=args.owner,
                )
            )
            return 0
    except RunRegistryError as exc:
        print(f"RUN_REGISTRY_ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
