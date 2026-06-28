"""Ensure frozen ALB GUI DLL directories are available before Qt imports."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepend_path(path: Path) -> None:
    """Add a directory to both Windows DLL search and PATH."""

    if not path.is_dir():
        return
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(path))
    current = os.environ.get("PATH", "")
    value = str(path)
    if value.lower() not in {item.lower() for item in current.split(os.pathsep)}:
        os.environ["PATH"] = value + os.pathsep + current


base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
for candidate in (
    base,
    base / "PySide6",
    base / "PySide6" / "plugins",
    base / "PySide6" / "plugins" / "platforms",
):
    _prepend_path(candidate)
