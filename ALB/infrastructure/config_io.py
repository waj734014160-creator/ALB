"""UTF-8-first JSON5 and tabular configuration IO."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ALB.contracts.optional import missing_optional_dependency

try:
    import json5
except ModuleNotFoundError as error:
    raise missing_optional_dependency("ALB.infrastructure.config_io", "io", error) from error


def read_json5(path: str | Path) -> dict[str, Any]:
    """Read one UTF-8 JSON5 object."""

    source = Path(path)
    text = source.read_text(encoding="utf-8")
    payload = json5.loads(text)
    if not isinstance(payload, dict):
        raise TypeError(f"JSON5 root must be an object: {source}")
    return dict(payload)


def write_json5(
    path: str | Path,
    payload: dict[str, Any],
    *,
    overwrite: bool = False,
) -> Path:
    """Write one JSON5 object as UTF-8 without replacing a file by default."""

    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"destination exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json5.dumps(payload, indent=4) + "\n", encoding="utf-8")
    return destination


def list_directories(path: str | Path, *, full: bool = True) -> list[str]:
    """List immediate child directories in filesystem order."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"{source} does not exist")
    if source.is_file():
        raise NotADirectoryError(str(source))
    directories = [child for child in source.iterdir() if child.is_dir()]
    if full:
        return [str(child) for child in directories]
    return [child.name for child in directories]


def read_config_directories(path: str | Path) -> dict[str, dict[str, Any]]:
    """Read JSON5 files from immediate child configuration directories."""

    result: dict[str, dict[str, Any]] = {}
    for directory in Path(path).iterdir():
        if not directory.is_dir():
            continue
        for config_path in directory.glob("*.json5"):
            result[str(directory)] = read_json5(config_path)
    return result


def get_config_values(
    path: str | Path,
    file_name: str,
    keys: list[str],
) -> dict[str, dict[str, Any]]:
    """Extract selected values from matching child configuration files."""

    target_name = file_name if file_name.endswith(".json5") else file_name + ".json5"
    result = {}
    for directory in Path(path).iterdir():
        config_path = directory / target_name
        if directory.is_dir() and config_path.is_file():
            payload = read_json5(config_path)
            result[str(directory)] = {key: payload[key] for key in keys}
    return result


def excel_to_csv(path: str | Path) -> list[Path]:
    """Convert the first sheet of every immediate Excel file to UTF-8 CSV."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"{source} does not exist")
    outputs = []
    for excel_path in source.iterdir():
        if excel_path.suffix.lower() not in {".xlsx", ".xls"}:
            continue
        if excel_path.suffix.lower() == ".xlsx":
            sheets = pd.read_excel(excel_path, sheet_name=None)
            frame = sheets[next(iter(sheets))]
        else:
            frame = pd.read_excel(excel_path)
        destination = excel_path.with_suffix(".csv")
        frame.to_csv(destination, index=False, encoding="utf-8")
        outputs.append(destination)
    return outputs


__all__ = [
    "excel_to_csv",
    "get_config_values",
    "list_directories",
    "read_config_directories",
    "read_json5",
    "write_json5",
]
