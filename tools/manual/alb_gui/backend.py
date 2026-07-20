"""Calculation backend for the ALB GUI."""

from __future__ import annotations

import contextlib
import copy
import io
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from ALB.alb import alb2, alb2_static
from ALB.config import ALBConfig
from ALB.dynamics.orbit import EllipseTrack, orbitime, test_bearing_orbit_parallel

from .config_io import build_flat_alb_config, resolve_gui_time_grid
from .fields import FieldMap, pressure_map_from_pads, temperature_map_from_pads

ProgressCallback = Callable[[int, str], None]


@dataclass
class StaticResult:
    """Static ALB calculation output for the GUI."""

    force: np.ndarray
    friction: float
    pressure: FieldMap
    temperature: FieldMap | None
    pad_status: list[dict[str, Any]]


@dataclass
class DynamicResult:
    """Dynamic ALB calculation output for the GUI."""

    stiffness: np.ndarray
    damping: np.ndarray
    trajectory: np.ndarray
    force_track: np.ndarray
    time: np.ndarray


def _eccentricity_vector(config: dict) -> np.ndarray:
    bearing = config.get("bearing", {})
    e = float(bearing.get("e", 0.0))
    angle = np.deg2rad(float(bearing.get("angle", 0.0)))
    return np.array([e * np.cos(angle), e * np.sin(angle)], dtype=float)


def _summarize_pad(pad) -> dict[str, Any]:
    base = getattr(pad, "bearing", pad)
    state = {
        "finished": bool(pad.calc_is_finished()),
        "final_iter": int(getattr(base, "final_iter", -1)),
        "max_iter": int(getattr(base, "max_iter", -1)),
    }
    if hasattr(pad, "thermal_state"):
        thermal_state = getattr(pad, "thermal_state", {}) or {}
        state.update(
            {
                "thermal_converged": bool(thermal_state.get("converged", False)),
                "thermal_iterations": int(thermal_state.get("iterations", 0)),
            }
        )
        if hasattr(pad, "post_process"):
            temp = np.asarray(pad.post_process.temperature_field, dtype=float)
            state.update(
                {
                    "temperature_min": float(np.nanmin(temp)),
                    "temperature_mean": float(np.nanmean(temp)),
                    "temperature_max": float(np.nanmax(temp)),
                }
            )
    return state


def build_alb_config(config: dict, *, dynamic: bool = False) -> ALBConfig:
    """Build an ALBConfig from grouped GUI input."""

    return ALBConfig.from_dict(build_flat_alb_config(config, dynamic=dynamic))


def run_static_calculation(
    config: dict, progress_callback: ProgressCallback | None = None
) -> StaticResult:
    """Run a static ALB force and field calculation."""

    alb_config = build_alb_config(config, dynamic=False)
    model = alb2_static(alb_config)
    model.init()
    uxy = _eccentricity_vector(config)
    model.input(uxy=uxy, uxyt=np.zeros(2), t=0.0, nodim=True)
    out = model.output(nodim=False)
    force = np.asarray(out["force"], dtype=float)
    friction = float(out.get("friction", np.nan))
    pads = list(model.pads)
    return StaticResult(
        force=force,
        friction=friction,
        pressure=pressure_map_from_pads(pads),
        temperature=temperature_map_from_pads(pads),
        pad_status=[_summarize_pad(pad) for pad in pads],
    )


def _emit_progress(
    progress_callback: ProgressCallback | None, value: int, message: str
) -> None:
    """Emit bounded integer progress if a callback is available."""

    if progress_callback is not None:
        progress_callback(max(0, min(100, int(value))), message)


def _translate_orbit_progress(message: str) -> str:
    """Translate package-level orbit progress messages for the GUI."""

    replacements = {
        "Initializing parallel orbit calculation": "初始化并行动特性模型",
        "Generating forward and reverse tracks": "生成正向/反向轨迹",
        "Parallel vortex force calculation": "正反涡动并行计算",
        "Identifying stiffness and damping matrices": "识别刚度/阻尼矩阵",
        "Dynamic orbit calculation complete": "动特性计算完成",
    }
    for source, target in replacements.items():
        if message.startswith(source):
            return message.replace(source, target, 1)
    return message


def run_dynamic_calculation(
    config: dict, progress_callback: ProgressCallback | None = None
) -> DynamicResult:
    """Run dynamic orbit identification and return dimensional K/C matrices."""

    _emit_progress(progress_callback, 0, "初始化动特性模型")
    alb_config = build_alb_config(config, dynamic=True)
    model = alb2(alb_config)
    model.init()
    dyn = config.get("dynamic", {})
    resolved_time = resolve_gui_time_grid(config)
    freq = resolved_time.freq
    points_per_cycle = resolved_time.points_per_cycle
    time_iter = orbitime(**resolved_time.to_time_config())
    track = EllipseTrack(
        a=float(dyn.get("a", 1e-5)),
        b=float(dyn.get("b", 1e-5)),
        freq=freq,
        a0=float(dyn.get("a0", 0.0)),
        b0=float(dyn.get("b0", 0.0)),
        f0=float(dyn.get("f0", 0.0)),
        vf=float(dyn.get("vf", config.get("boundary", {}).get("vf", 1.0))),
    )
    kwargs = {
        "repeat": int(dyn.get("repeat", 0)),
        "pt": points_per_cycle,
        "tr": [float(dyn.get("tr_start", 0.0)), float(dyn.get("tr_end", 1.0))],
    }

    def gui_progress(value: int, message: str) -> None:
        _emit_progress(progress_callback, value, _translate_orbit_progress(message))

    with contextlib.redirect_stdout(io.StringIO()):
        result = test_bearing_orbit_parallel(
            time_iter,
            model,
            track,
            progress_callback=gui_progress,
            max_workers=2,
            **kwargs,
        )
    hkc = result["hkc"]
    bft = result["bft"].bearing_forces
    return DynamicResult(
        stiffness=np.asarray(hkc["k"], dtype=float),
        damping=np.asarray(hkc["c"], dtype=float),
        trajectory=bft[["ux", "uy"]].to_numpy(dtype=float),
        force_track=bft[["fx", "fy"]].to_numpy(dtype=float),
        time=bft["t"].to_numpy(dtype=float),
    )


def clone_config(config: dict) -> dict:
    """Return a deep copy suitable for worker threads."""

    return copy.deepcopy(config)
