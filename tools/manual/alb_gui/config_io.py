"""Configuration loading and persistence for the ALB GUI."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import numpy as np

from ALB.tool import read_json5_with_share


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PAPER_CONFIG_DIR = Path("F:/BaiduSyncdisk/博士论文/PAPER_WORK/task/PAPER/config")
FALLBACK_PAPER_CONFIG_DIR = Path("G:/ALB_PROJECTS/PARAM_SCAN/task/PAPER/config")
RUNTIME_CONFIG_PATH = REPO_ROOT / "outputs" / "alb_gui" / "config.json"

PAPER_CONFIG_FILES = {
    "alb": "alb12.json5",
    "hb": "hb34.json5",
    "track": "et.json5",
    "time": "time_iter.json5",
    "recognition": "tbo.json5",
}


class GuiConfigError(RuntimeError):
    """Raised when GUI configuration cannot be loaded or converted."""


def _required_files() -> Iterable[str]:
    return PAPER_CONFIG_FILES.values()


def _missing_files(config_dir: Path) -> list[str]:
    return [name for name in _required_files() if not (config_dir / name).is_file()]


def resolve_paper_config_dir(
    config_dir: Path | str | None = None,
) -> Tuple[Path, str, list[str]]:
    """Return the best available paper config directory and a source label."""

    candidates: list[tuple[str, Path]]
    if config_dir is not None:
        candidates = [("selected", Path(config_dir))]
    else:
        candidates = [
            ("default", DEFAULT_PAPER_CONFIG_DIR),
            ("fallback", FALLBACK_PAPER_CONFIG_DIR),
        ]

    failures: list[str] = []
    for label, candidate in candidates:
        missing = _missing_files(candidate)
        if candidate.is_dir() and not missing:
            return candidate, label, failures
        failures.append(f"{candidate}: missing {', '.join(missing) if missing else 'directory'}")

    raise GuiConfigError(
        "Could not locate a complete paper config directory. " + "; ".join(failures)
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        if math.isnan(value):
            return None
    return value


def _restore_special_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _restore_special_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore_special_values(item) for item in value]
    if value == "Infinity":
        return math.inf
    if value == "-Infinity":
        return -math.inf
    return value


def _read_paper_files(config_dir: Path) -> Dict[str, dict]:
    return {
        key: read_json5_with_share(str(config_dir / file_name))
        for key, file_name in PAPER_CONFIG_FILES.items()
    }


def _copy_section(data: dict, keys: Iterable[str]) -> dict:
    return {key: copy.deepcopy(data[key]) for key in keys if key in data}


def paper_configs_to_gui_config(configs: Dict[str, dict], config_dir: Path) -> dict:
    """Map paper JSON5 configs into the GUI's grouped runtime schema."""

    alb = configs["alb"]
    hb = configs["hb"]
    track = configs["track"]
    time_cfg = configs["time"]
    rec = configs["recognition"]
    thermal_payload = copy.deepcopy(alb.get("thermal", hb.get("thermal", {})))

    return {
        "version": 1,
        "source_config_dir": str(config_dir),
        "source_files": {
            key: str(config_dir / file_name)
            for key, file_name in PAPER_CONFIG_FILES.items()
        },
        "bearing": {
            **_copy_section(
                alb,
                [
                    "freq",
                    "e",
                    "angle",
                    "lx",
                    "lz",
                    "nx",
                    "nz",
                    "c",
                    "r",
                    "l",
                    "bias",
                    "node_link",
                ],
            )
        },
        "fluid": _copy_section(alb, ["miu", "rho"]),
        "boundary": {
            **_copy_section(
                alb,
                [
                    "ps",
                    "reynold",
                    "coe",
                    "p_set",
                    "error_set",
                    "max_iter",
                    "damp",
                    "vib",
                    "dxt",
                    "dyt",
                    "vf",
                    "iter_method",
                    "path",
                    "save_p",
                    "save_h",
                    "ngauss",
                    "gdamp",
                    "err",
                    "xrange",
                    "zrange",
                    "h_tank",
                ],
            )
        },
        "thermal": {
            "enabled": bool(alb.get("thermal_enabled", False)),
            "settings": thermal_payload,
        },
        "pid": {
            **_copy_section(
                alb,
                [
                    "dt",
                    "kp",
                    "ki",
                    "kd",
                    "gxy",
                    "gxyt",
                    "sensor_angles",
                    "servo",
                    "delay",
                    "tw",
                    "zeta",
                    "tp3",
                    "switch",
                ],
            )
        },
        "dynamic": {
            "a": track.get("a", alb.get("a", 1e-5)),
            "b": track.get("b", alb.get("b", 1e-5)),
            "a0": track.get("a0", alb.get("a0", 0.0)),
            "b0": track.get("b0", alb.get("b0", 0.0)),
            "f0": track.get("f0", 0.0),
            "freq": track.get("freq", alb.get("freq", 50.0)),
            "vf": track.get("vf", alb.get("vf", 1.0)),
            "n": time_cfg.get("n", 1),
            "pt": time_cfg.get("pt", 20),
            "repeat": rec.get("repeat", alb.get("repeat", 0)),
            "tr_start": 0.0,
            "tr_end": 1.0,
        },
        "paper_defaults": {
            "alb": copy.deepcopy(alb),
            "hb": copy.deepcopy(hb),
            "track": copy.deepcopy(track),
            "time": copy.deepcopy(time_cfg),
            "recognition": copy.deepcopy(rec),
        },
    }


def load_paper_gui_config(config_dir: Path | str | None = None) -> Tuple[dict, str]:
    """Load and convert paper configs into a GUI runtime config."""

    resolved_dir, source_label, failures = resolve_paper_config_dir(config_dir)
    configs = _read_paper_files(resolved_dir)
    gui_config = paper_configs_to_gui_config(configs, resolved_dir)
    if source_label == "fallback":
        message = f"Loaded fallback paper config: {resolved_dir}"
    elif source_label == "selected":
        message = f"Loaded selected paper config: {resolved_dir}"
    else:
        message = f"Loaded paper config: {resolved_dir}"
    if failures:
        message += f" (fallback after: {'; '.join(failures)})"
    return _restore_special_values(gui_config), message


def load_runtime_config(path: Path | str = RUNTIME_CONFIG_PATH) -> dict:
    """Load the persisted GUI runtime config."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return _restore_special_values(data)


def save_runtime_config(
    config: dict, path: Path | str = RUNTIME_CONFIG_PATH
) -> Path:
    """Persist the GUI runtime config as strict UTF-8 JSON."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(_json_safe(config), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return target


def load_initial_gui_config(
    *,
    runtime_path: Path | str = RUNTIME_CONFIG_PATH,
    prefer_runtime: bool = True,
) -> Tuple[dict, str]:
    """Load the GUI startup config, preferring the last runtime state."""

    runtime = Path(runtime_path)
    if prefer_runtime and runtime.is_file():
        try:
            return load_runtime_config(runtime), f"Loaded GUI runtime config: {runtime}"
        except Exception as exc:  # pragma: no cover - defensive UI path
            paper_config, message = load_paper_gui_config()
            return paper_config, f"{message}; ignored invalid runtime config: {exc}"
    return load_paper_gui_config()


def build_flat_alb_config(config: dict, *, dynamic: bool = False) -> dict:
    """Convert grouped GUI config into flat ALBConfig input."""

    flat: dict[str, Any] = {}
    for section in ("bearing", "fluid", "boundary", "pid"):
        flat.update(copy.deepcopy(config.get(section, {})))

    thermal = copy.deepcopy(config.get("thermal", {}))
    flat["thermal_enabled"] = bool(thermal.get("enabled", False))
    flat["thermal"] = copy.deepcopy(thermal.get("settings", {}))
    if dynamic and flat["thermal_enabled"]:
        dyn = config.get("dynamic", {})
        freq = float(dyn.get("freq", flat.get("freq", 50.0)))
        pt = int(dyn.get("pt", 20))
        if pt > 0 and freq > 0:
            flat["thermal"]["dt"] = 1.0 / (freq * pt)
        flat["thermal"]["transient_enabled"] = True

    dyn_freq = config.get("dynamic", {}).get("freq")
    if dynamic and dyn_freq is not None:
        flat["freq"] = dyn_freq

    if "source_config_dir" in config:
        flat["_source_config_dir"] = config["source_config_dir"]
    flat.pop("node_link", None)
    if config.get("bearing", {}).get("node_link") is not None:
        flat["node_link"] = config["bearing"]["node_link"]
    return _restore_special_values(flat)


def make_small_test_config(*, thermal: bool = False) -> dict:
    """Return a compact ALB GUI config for smoke tests."""

    cfg, _ = load_paper_gui_config()
    cfg = copy.deepcopy(cfg)
    cfg["bearing"].update(
        {
            "freq": 50.0,
            "e": 0.05,
            "angle": 20.0,
            "nx": 7,
            "nz": 5,
            "bias": 45.0,
        }
    )
    cfg["boundary"].update(
        {
            "error_set": 1e-5,
            "max_iter": 20,
            "damp": 0.6,
            "iter_method": "newton",
        }
    )
    cfg["thermal"]["enabled"] = thermal
    cfg["thermal"]["settings"].update(
        {
            "max_iter": 4,
            "tol": 1e-2,
            "heat_partition": 0.2,
            "heat_partition_steps": None,
            "miu_update": "linear",
            "miu_update_max_ratio": None,
            "max_delta_t": 20.0,
        }
    )
    cfg["pid"].update({"kp": 0.0, "ki": 0.0, "kd": 0.0, "servo": "static"})
    cfg["dynamic"].update(
        {
            "a": 2e-6,
            "b": 2e-6,
            "a0": 0.0,
            "b0": 0.0,
            "n": 1,
            "pt": 8,
            "repeat": 1,
            "tr_start": 0.0,
            "tr_end": 1.0,
        }
    )
    return cfg

