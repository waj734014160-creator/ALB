import json
from pathlib import Path

import numpy as np

from ALB.config import FPBConfig
from ALB.thermal import ThermalConfig
from run.compare_orifice_methods import (
    HYD_MAX_ITER,
    _uxy_from_e_right_down,
    build_alb,
    solve_thermal,
)

OUT = Path("outputs/thermal_kc_compare/flux_boundary_diagnosis.json")


def flux_stats_for(e_ratio, pad_name="down"):
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
    tcfg = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        relax=0.5,
        max_iter=50,
        tol=1e-4,
        coupling="full",
        args_nodim=False,
        t_supply=40.0,
        k_lub=0.13,
        supg=True,
    )
    uxy = _uxy_from_e_right_down(e_ratio, pad_cfg.c)
    uxyt = np.array([0.0, 0.0])
    alb, csos = build_alb(pad_cfg)
    res = solve_thermal(alb, csos, tcfg, uxy, uxyt)
    pad_names = ["up", "down", "right", "left"]
    # Rebuild identical thermal wrapped pad object from result path is not retained by solve_thermal,
    # so rerun only the target pad with object access.
    from ALB.thermal import ThermalHydroBearing

    alb2, csos2 = build_alb(pad_cfg)
    thermal_pads = [ThermalHydroBearing(pad, tcfg) for pad in alb2.pads]
    alb2.init()
    for cso in csos2:
        cso.input(xv=0.3)
    tpad = thermal_pads[pad_names.index(pad_name)]
    tpad.init()
    tpad.input(uxy=uxy, uxyt=uxyt)
    out = tpad.output(calc=True, nodim=True)

    model = tpad.bearing.main_model
    mesh_data = tpad.thermal_model.build_mesh(model, tpad._thermal_grid)
    tpad.thermal_model.update_pressure_gradients(model, mesh_data)
    miu = np.asarray(out["viscosity_field"], dtype=float)
    miu_nodal = tpad.thermal_model._prepare_viscosity_nodal(
        tpad._map_miu_to_thermal(miu, mesh_data["grid"], mesh_data["mesh"], mesh_data),
        mesh_data["mesh"],
    )
    qx, qz, phi = tpad.thermal_model._calc_flux_and_source(mesh_data, miu_nodal)
    h = np.asarray(mesh_data["h_nodal"], dtype=float)
    dp_dx = np.asarray(mesh_data["dp_dx_nodal"], dtype=float)
    dp_dz = np.asarray(mesh_data["dp_dz_nodal"], dtype=float)
    temp = np.asarray(out["temperature_film"], dtype=float)

    mesh = mesh_data["mesh"]
    tx = mesh.p[0]
    tz = mesh.p[1]
    x_min, x_max = float(tx.min()), float(tx.max())
    z_min, z_max = float(tz.min()), float(tz.max())
    tol_x = (x_max - x_min) * 1e-8
    tol_z = (z_max - z_min) * 1e-8
    left = np.where(np.abs(tx - x_min) < tol_x)[0]
    right = np.where(np.abs(tx - x_max) < tol_x)[0]
    zlo = np.where(np.abs(tz - z_min) < tol_z)[0]
    zhi = np.where(np.abs(tz - z_max) < tol_z)[0]

    def stat(arr):
        arr = np.asarray(arr, dtype=float)
        return {
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
            "neg_fraction": float(np.mean(arr < 0.0)),
            "pos_fraction": float(np.mean(arr > 0.0)),
        }

    hot_idx = int(np.argmax(temp))
    # film index -> thermal index for hot film node
    thermal_hot_idx = int(mesh_data["film_to_thermal_idx"][hot_idx])

    return {
        "e": float(e_ratio),
        "pad": pad_name,
        "t_eff": float(out["t_eff"]),
        "tmax": float(temp.max()),
        "thermal_iterations": int(out["thermal_iterations"]),
        "h": stat(h),
        "miu": stat(miu_nodal),
        "dp_dx": stat(dp_dx),
        "dp_dz": stat(dp_dz),
        "qx": stat(qx),
        "qz": stat(qz),
        "phi": stat(phi),
        "left_boundary_qx": stat(qx[left]),
        "right_boundary_qx": stat(qx[right]),
        "zmin_boundary_qz": stat(qz[zlo]),
        "zmax_boundary_qz": stat(qz[zhi]),
        "hot_film_node": {
            "film_index": hot_idx,
            "thermal_index": thermal_hot_idx,
            "temperature": float(temp[hot_idx]),
            "x": float(mesh.p[0, thermal_hot_idx]),
            "z": float(mesh.p[1, thermal_hot_idx]),
            "h": float(h[thermal_hot_idx]),
            "miu": float(miu_nodal[thermal_hot_idx]),
            "dp_dx": float(dp_dx[thermal_hot_idx]),
            "dp_dz": float(dp_dz[thermal_hot_idx]),
            "qx": float(qx[thermal_hot_idx]),
            "qz": float(qz[thermal_hot_idx]),
            "phi": float(phi[thermal_hot_idx]),
        },
    }


result = {
    "down_e_0p5": flux_stats_for(0.5, "down"),
    "down_e_0p6": flux_stats_for(0.6, "down"),
    "down_e_0p7": flux_stats_for(0.7, "down"),
    "right_e_0p7": flux_stats_for(0.7, "right"),
}
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
