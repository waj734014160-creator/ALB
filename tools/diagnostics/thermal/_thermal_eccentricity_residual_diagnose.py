import json
from pathlib import Path

import numpy as np

from ALB.config import FPBConfig
from ALB.config import ThermalConfig
from run.compare_orifice_methods import (
    HYD_MAX_ITER,
    _uxy_from_e_right_down,
    build_alb,
    solve_thermal,
)

OUT = Path(
    "outputs/thermal_kc_compare/eccentricity_temperature_residual_diagnosis.json"
)


def run_sweep(tol=1e-2, max_iter=20, coupling="full", k_lub=0.13, supg=True):
    pad_cfg = FPBConfig(
        nx=60,
        nz=40,
        e=0.0,
        lx=80,
        ps=3e6,
        freq=50,
        max_iter=HYD_MAX_ITER,
        error_set=1e-8,
        iter_method="newton",
        damp=0.6,
        coe=False,
    )
    uxyt = np.array([0.0, 0.0])
    e_list = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], dtype=float)
    tcfg = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        relax=0.5,
        max_iter=max_iter,
        tol=tol,
        coupling=coupling,
        args_nodim=False,
        t_supply=40.0,
        k_lub=k_lub,
        supg=supg,
    )
    pad_names = ["up", "down", "right", "left"]
    rows = []
    for e_ratio in e_list:
        uxy = _uxy_from_e_right_down(e_ratio, pad_cfg.c)
        alb, csos = build_alb(pad_cfg)
        res = solve_thermal(alb, csos, tcfg, uxy, uxyt)
        for name in pad_names:
            out = res[name]
            temp = np.asarray(out["temperature_film"], dtype=float)
            miu = np.asarray(out["viscosity_field"], dtype=float)
            miu_target = 0.0195 * np.exp(-tcfg.beta * (temp - 40.0))
            miu_target = np.clip(miu_target, tcfg.miu_min, tcfg.miu_max)
            rel = np.abs(miu_target - miu) / np.maximum(np.abs(miu), 1e-12)
            rows.append(
                {
                    "e": float(e_ratio),
                    "pad": name,
                    "t_eff": float(out["t_eff"]),
                    "t_film_mean": float(temp.mean()),
                    "t_film_max": float(temp.max()),
                    "temperature_max": float(np.max(out["temperature"])),
                    "miu_mean": float(miu.mean()),
                    "miu_target_mean": float(miu_target.mean()),
                    "miu_rel_residual_max": float(rel.max()),
                    "miu_rel_residual_mean": float(rel.mean()),
                    "thermal_iterations": int(out["thermal_iterations"]),
                    "thermal_converged": bool(out["thermal_converged"]),
                }
            )
    return rows


def slopes(rows, key):
    result = {}
    for pad in ["up", "down", "right", "left"]:
        subset = [r for r in rows if r["pad"] == pad]
        e = np.asarray([r["e"] for r in subset], dtype=float)
        y = np.asarray([r[key] for r in subset], dtype=float)
        result[pad] = {
            "delta_0p1_to_0p7": float(y[-1] - y[0]),
            "max_step_slope_per_e": float(np.max(np.abs(np.diff(y) / np.diff(e)))),
            "values": y.tolist(),
        }
    return result


rows_default = run_sweep(tol=1e-2, max_iter=20)
rows_strict = run_sweep(tol=1e-4, max_iter=50)

result = {
    "default_tol_1e-2": {
        "rows": rows_default,
        "t_eff_slopes": slopes(rows_default, "t_eff"),
        "t_max_slopes": slopes(rows_default, "t_film_max"),
        "residual_slopes": slopes(rows_default, "miu_rel_residual_max"),
    },
    "strict_tol_1e-4": {
        "rows": rows_strict,
        "t_eff_slopes": slopes(rows_strict, "t_eff"),
        "t_max_slopes": slopes(rows_strict, "t_film_max"),
        "residual_slopes": slopes(rows_strict, "miu_rel_residual_max"),
    },
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(
    json.dumps(
        {
            "default_t_eff_slopes": result["default_tol_1e-2"]["t_eff_slopes"],
            "strict_t_eff_slopes": result["strict_tol_1e-4"]["t_eff_slopes"],
            "default_residual_slopes": result["default_tol_1e-2"]["residual_slopes"],
            "strict_residual_slopes": result["strict_tol_1e-4"]["residual_slopes"],
        },
        indent=2,
    )
)
