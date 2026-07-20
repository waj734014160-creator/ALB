import copy
import json
from pathlib import Path

import numpy as np

from ALB.core import TimeIterDt
from ALB.physics.bearing import MultiPad
from ALB.dynamics.orbit import test_bearing_orbit
from run import thermal_kc_compare as kc

OUT = Path("outputs/thermal_kc_compare/coupling_diagnosis.json")


def identify_custom_steady(coupling):
    case_cfg = copy.deepcopy(kc.CASE_CONFIGS["thermal_steady"]["thermal_data"])
    case_cfg["coupling"] = coupling
    pad_cfg = kc.create_pad_config()
    dt = 1.0 / (kc.ORBIT_FREQ_HZ * kc.PTS_PER_CYCLE)
    pads = kc.build_fixed_opening_pads(pad_cfg)
    thermal_config = kc.build_thermal_config(True, case_cfg, dt=dt)
    bearing = MultiPad(*kc.wrap_pad_collection_with_thermal(pads, thermal_config))
    bearing.init()
    time_iter = TimeIterDt(dt=dt, num=kc.PTS_PER_CYCLE * kc.N_CYCLES)
    track = kc.create_identification_track()
    result = test_bearing_orbit(time_iter, bearing, track)
    return {
        "k": np.asarray(result["hkc"]["k"], dtype=float),
        "c": np.asarray(result["hkc"]["c"], dtype=float),
        "forward_samples": int(len(result["bft"].bearing_forces)),
        "inverse_samples": int(len(result["ibft"].bearing_forces)),
    }


def single_point_heat_stats(coupling):
    case_cfg = copy.deepcopy(kc.CASE_CONFIGS["thermal_steady"]["thermal_data"])
    case_cfg["coupling"] = coupling
    pad_cfg = kc.create_pad_config()
    dt = 1.0 / (kc.ORBIT_FREQ_HZ * kc.PTS_PER_CYCLE)
    pads = kc.build_fixed_opening_pads(pad_cfg)
    thermal_config = kc.build_thermal_config(True, case_cfg, dt=dt)
    bearing = MultiPad(*kc.wrap_pad_collection_with_thermal(pads, thermal_config))
    bearing.init()

    track = kc.create_identification_track()
    u, v, a = track.generate_track([0.0])
    bearing.input(uxy=u[0], uxyt=v[0], uxytt=a[0], t=0.0, nodim=False)
    out = bearing.output()

    pad = bearing.bearings[0]
    model = pad.bearing.main_model
    mesh_data = pad.thermal_model.build_mesh(model, pad._thermal_grid)
    pad.thermal_model.update_pressure_gradients(model, mesh_data)
    miu_field = np.asarray(out["viscosity_field"], dtype=float)
    miu_mean = float(np.mean(miu_field))
    miu_for_thermal = pad._get_thermal_viscosity(miu_field, miu_mean, mesh_data)
    miu_nodal = pad.thermal_model._prepare_viscosity_nodal(
        miu_for_thermal, mesh_data["mesh"]
    )
    qx, qz, phi = pad.thermal_model._calc_flux_and_source(mesh_data, miu_nodal)

    h = mesh_data["h_nodal"]
    surface_speed = mesh_data["surface_speed"]
    dp_dx = mesh_data["dp_dx_nodal"]
    dp_dz = mesh_data["dp_dz_nodal"]
    phi_couette = miu_nodal * surface_speed**2 / h
    phi_poiseuille = h**3 / (12.0 * miu_nodal) * (dp_dx**2 + dp_dz**2)

    temp = np.asarray(out["temperature_film"], dtype=float)
    return {
        "force": np.asarray(out["force"], dtype=float).tolist(),
        "t_eff": float(out["t_eff"]),
        "temp_min": float(temp.min()),
        "temp_max": float(temp.max()),
        "temp_mean": float(temp.mean()),
        "miu_min": float(miu_field.min()),
        "miu_max": float(miu_field.max()),
        "miu_mean": miu_mean,
        "miu_thermal_min": float(np.min(miu_nodal)),
        "miu_thermal_max": float(np.max(miu_nodal)),
        "miu_thermal_mean": float(np.mean(miu_nodal)),
        "phi_couette_min": float(np.min(phi_couette)),
        "phi_couette_max": float(np.max(phi_couette)),
        "phi_couette_mean": float(np.mean(phi_couette)),
        "phi_poiseuille_min": float(np.min(phi_poiseuille)),
        "phi_poiseuille_max": float(np.max(phi_poiseuille)),
        "phi_poiseuille_mean": float(np.mean(phi_poiseuille)),
        "phi_total_min": float(np.min(phi)),
        "phi_total_max": float(np.max(phi)),
        "phi_total_mean": float(np.mean(phi)),
        "qx_min": float(np.min(qx)),
        "qx_max": float(np.max(qx)),
        "qx_mean": float(np.mean(qx)),
        "qz_min": float(np.min(qz)),
        "qz_max": float(np.max(qz)),
        "qz_mean": float(np.mean(qz)),
    }


def matrix_to_list(result):
    return {
        "k": result["k"].tolist(),
        "c": result["c"].tolist(),
        "forward_samples": result["forward_samples"],
        "inverse_samples": result["inverse_samples"],
    }


summary_path = Path("outputs/thermal_kc_compare/summary.json")
existing = (
    json.loads(summary_path.read_text(encoding="utf-8"))
    if summary_path.exists()
    else {}
)
baseline = existing.get("cases", {}).get("bare_hydro", {})
full = existing.get("cases", {}).get("thermal_steady", {})

half = identify_custom_steady("half")
heat_full = single_point_heat_stats("full")
heat_half = single_point_heat_stats("half")

full_k = np.asarray(full.get("stiffness", []), dtype=float)
full_c = np.asarray(full.get("damping", []), dtype=float)
baseline_k = np.asarray(baseline.get("stiffness", []), dtype=float)
baseline_c = np.asarray(baseline.get("damping", []), dtype=float)

result = {
    "baseline_from_existing_summary": baseline,
    "thermal_steady_full_from_existing_summary": full,
    "thermal_steady_half_identified": matrix_to_list(half),
    "half_minus_full": {
        "delta_k": (half["k"] - full_k).tolist() if full_k.size else None,
        "delta_c": (half["c"] - full_c).tolist() if full_c.size else None,
        "max_abs_delta_k": float(np.max(np.abs(half["k"] - full_k)))
        if full_k.size
        else None,
        "max_abs_delta_c": float(np.max(np.abs(half["c"] - full_c)))
        if full_c.size
        else None,
    },
    "half_minus_baseline": {
        "delta_k": (half["k"] - baseline_k).tolist() if baseline_k.size else None,
        "delta_c": (half["c"] - baseline_c).tolist() if baseline_c.size else None,
        "max_abs_delta_k": float(np.max(np.abs(half["k"] - baseline_k)))
        if baseline_k.size
        else None,
        "max_abs_delta_c": float(np.max(np.abs(half["c"] - baseline_c)))
        if baseline_c.size
        else None,
    },
    "single_point_heat_source_full": heat_full,
    "single_point_heat_source_half": heat_half,
    "single_point_half_minus_full": {
        key: heat_half[key] - heat_full[key]
        for key in heat_full
        if isinstance(heat_full[key], float)
    },
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
