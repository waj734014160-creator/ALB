"""Configuration sweep generation and continuation selection."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ALB.infrastructure.config_io import list_directories, read_json5, write_json5

from .execution import iter_parameter_combinations
from .naming import build_parameter_name


class ConfigurationSweep:
    """Generate named task directories from selected JSON5 parameter products."""

    def __init__(self, config_dir: str | Path) -> None:
        self.config_dir = Path(config_dir)
        self.configs = {
            path.stem: read_json5(path) for path in self.config_dir.glob("*.json5")
        }
        self._variations: dict[str, dict[str, Any]] = {}
        self.saved_directories: list[Path] = []

    def vary(self, file_stem: str, **named_values: Any) -> None:
        """Declare varying values for one configuration file."""

        self._variations[file_stem] = named_values

    def save(
        self,
        *,
        write_files: bool = True,
        save_path: str | Path | None = None,
    ) -> list[Path]:
        """Materialize every configuration combination without overwriting files."""

        root = self.config_dir if save_path is None else Path(save_path)
        per_file = {
            file_stem: list(iter_parameter_combinations(**values))
            for file_stem, values in self._variations.items()
        }
        for combination in iter_parameter_combinations(**per_file):
            configs = copy.deepcopy(self.configs)
            tokens = []
            for file_stem, values in combination.items():
                tokens.append(f"{file_stem}_{build_parameter_name(values)}")
                configs[file_stem].update(values)
            destination = root / "_".join(tokens)
            destination.mkdir(parents=True, exist_ok=True)
            if write_files:
                for file_stem, payload in configs.items():
                    write_json5(destination / f"{file_stem}.json5", payload)
            self.saved_directories.append(destination)
        return list(self.saved_directories)


def pending_task_directories(
    config_dir: str | Path,
    result_dir: str = "result",
) -> list[str]:
    """Return task directories that do not yet contain ``result_dir``."""

    pending = []
    for directory in list_directories(config_dir):
        if not (Path(directory) / result_dir).exists():
            pending.append(directory)
    return pending


__all__ = ["ConfigurationSweep", "pending_task_directories"]
