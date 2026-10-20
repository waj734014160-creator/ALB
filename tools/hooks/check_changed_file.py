"""Validate text files changed by the Claude Code PostToolUse hook."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    import tomli as tomllib


_MAX_FILE_SIZE = 8 * 1024 * 1024
_TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".css",
        ".html",
        ".ini",
        ".ipynb",
        ".js",
        ".json",
        ".json5",
        ".jsx",
        ".md",
        ".py",
        ".pyi",
        ".rst",
        ".sh",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)
_MOJIBAKE_CODEPOINTS = (
    (0xFFFD,),
    (0x951F, 0x65A4, 0x62F7),
    (0x70EB, 0x70EB, 0x70EB),
    (0x5C6F, 0x5C6F, 0x5C6F),
    (0x00E2, 0x20AC, 0x2122),
    (0x00E2, 0x20AC, 0x0153),
    (0x00E2, 0x20AC, 0x009D),
    (0x00F0, 0x0178),
)


def _decode_utf8(path: Path) -> tuple[str | None, list[str]]:
    """Decode a bounded text file as UTF-8 and report integrity failures."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, [f"cannot read file: {exc}"]

    if len(raw) > _MAX_FILE_SIZE:
        return None, []
    if b"\x00" in raw:
        return None, ["text file contains a NUL byte"]

    try:
        return raw.decode("utf-8-sig"), []
    except UnicodeDecodeError as exc:
        return None, [
            "file is not valid UTF-8 "
            f"(byte {exc.start}: {exc.reason})"
        ]


def _syntax_errors(path: Path, text: str) -> list[str]:
    """Return parser errors for supported structured text formats."""

    suffix = path.suffix.lower()
    try:
        if suffix in {".py", ".pyi"}:
            ast.parse(text, filename=str(path))
        elif suffix in {".json", ".ipynb"}:
            json.loads(text)
        elif suffix == ".json5":
            import json5

            json5.loads(text)
        elif suffix == ".toml":
            tomllib.loads(text)
    except (SyntaxError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        location = ""
        line = getattr(exc, "lineno", None)
        column = getattr(exc, "colno", None) or getattr(exc, "offset", None)
        if line is not None:
            location = f" at line {line}"
            if column is not None:
                location += f", column {column}"
        return [f"invalid {suffix.removeprefix('.')} syntax{location}: {exc}"]
    except ImportError as exc:
        return [f"cannot validate {suffix}: missing dependency {exc.name!r}"]
    return []


def validate_file(path: Path) -> list[str]:
    """Return integrity and syntax errors for one changed file."""

    if path.suffix.lower() not in _TEXT_SUFFIXES or not path.is_file():
        return []

    text, errors = _decode_utf8(path)
    if errors or text is None:
        return errors

    for codepoints in _MOJIBAKE_CODEPOINTS:
        marker = "".join(chr(codepoint) for codepoint in codepoints)
        if marker in text:
            printable = marker.encode("unicode_escape").decode("ascii")
            errors.append(f"possible mojibake marker found: {printable}")

    errors.extend(_syntax_errors(path, text))
    return errors


def _changed_path(payload: dict[str, Any]) -> Path | None:
    """Extract the changed path from Write, Edit, or NotebookEdit input."""

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    return Path(raw_path)


def _emit_failure(path: Path | None, errors: list[str]) -> None:
    """Emit a PostToolUse block that sends actionable feedback to Claude."""

    target = str(path) if path is not None else "hook input"
    reason = f"Changed-file validation failed for {target}: " + "; ".join(errors)
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": reason,
                "systemMessage": reason,
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    """Read one hook event from stdin and validate its changed file."""

    raw_input = sys.stdin.read()
    try:
        payload = json.loads(raw_input)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _emit_failure(None, [f"invalid hook input: {exc}"])
        return 0

    if not isinstance(payload, dict):
        _emit_failure(None, ["hook input must be a JSON object"])
        return 0

    path = _changed_path(payload)
    if path is None:
        return 0

    errors = validate_file(path)
    if errors:
        _emit_failure(path, errors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
