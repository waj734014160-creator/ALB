"""UTF-8-first JSON5 and tabular configuration IO."""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

import json5
import pandas as pd

from ALB.config import TimeGridConfig


def read_json5(path: str | Path) -> dict[str, Any]:
    """Read a JSON5 object as UTF-8, with an explicit legacy GBK fallback."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        warnings.warn(
            f"legacy GBK/CP936 fallback used for {source}; convert it to UTF-8 before editing",
            UnicodeWarning,
            stacklevel=2,
        )
        text = source.read_text(encoding="gbk")
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


def read_shared_config(path: str | Path, recover: bool = False) -> dict[str, Any]:
    """Resolve one shared config and its adjacent canonical time-grid config."""

    source = Path(path)
    shared = read_json5(source)
    time_path = source.with_name("time_iter.json5")
    if time_path.exists():
        time_payload = read_json5(time_path)
        share_keys = time_payload.pop("share_name", [])
        if not isinstance(share_keys, list):
            share_keys = [share_keys]
        for key in share_keys:
            if key not in shared:
                raise KeyError(
                    f"Parameter '{key}' requested by 'time_iter.json5' not found in share data."
                )
            time_payload[key] = shared[key]
    else:
        time_payload = shared

    resolved = TimeGridConfig.from_dict(time_payload).resolve()
    shared.update(
        {
            "mode": resolved.mode,
            "freq": resolved.freq,
            "dt": resolved.dt,
            "steps": resolved.steps,
            "cycles": resolved.cycles,
            "points_per_cycle": resolved.points_per_cycle,
            "pt": resolved.points_per_cycle,
        }
    )
    if resolved.mode == "cycle_points":
        shared["n"] = int(resolved.cycles)
    else:
        shared.pop("n", None)
    if recover:
        warnings.warn(
            "recover=True is deprecated; derived values are returned in memory only",
            DeprecationWarning,
            stacklevel=2,
        )
    return shared


def read_json5_with_shared(
    path: str | Path,
    shared: dict[str, Any] | None = None,
    *,
    shared_file_name: str = "share.json5",
    shared_key: str = "share_name",
) -> dict[str, Any]:
    """Read one JSON5 object and merge only explicitly requested shared values."""

    source = Path(path)
    payload = read_json5(source)
    shared_values = shared
    if shared_values is None:
        shared_path = source.with_name(shared_file_name)
        if shared_path.exists():
            raw_shared = read_json5(shared_path)
            has_legacy_time = all(key in raw_shared for key in ("freq", "n", "pt"))
            time_path = source.with_name("time_iter.json5")
            shared_values = (
                read_shared_config(shared_path)
                if time_path.exists() or has_legacy_time
                else raw_shared
            )
    if shared_values is not None and shared_key in payload:
        requested = payload[shared_key]
        if not isinstance(requested, list):
            requested = [requested]
        for key in requested:
            if key not in shared_values:
                raise KeyError(
                    f"Parameter '{key}' requested by '{source.name}' not found in share data."
                )
            payload[key] = shared_values[key]
    payload.pop(shared_key, None)
    return payload


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
    "read_json5_with_shared",
    "read_shared_config",
    "write_json5",
]
