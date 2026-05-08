import copy
import json
from pathlib import Path

import numpy as np

from ALB.base import TimeIterDt
from ALB.bearing import MultiPad
from ALB.orbit import test_bearing_orbit
from ALB.thermal import ThermalHydroBearing
from run import thermal_kc_compare as kc

OUT = Path("outputs/thermal_kc_compare/pressure_mean_diagnosis.json")


def apply_mean_miu_ratio_to_nodes(self, miu_field):
    model = self.bearing.main_model
    miu_mean = float(np.mean(np.asarray(miu_field, dtype=float)))
    ratio = miu_mean / self._miu0
    for node in model.nodes.values():
        node.miu_ratio = ratio


ThermalHydroBearing._apply_miu_ratio_to_nodes = apply_mean_miu_ratio_to_nodes


def identify_mean_pressure(coupling):
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


def to_list(result):
    return {
        "k": result["k"].tolist(),
        "c": result["c"].tolist(),
        "forward_samples": result["forward_samples"],
        "inverse_samples": result["inverse_samples"],
    }


summary = json.loads(
    Path("outputs/thermal_kc_compare/summary.json").read_text(encoding="utf-8")
)
baseline = summary["cases"]["bare_hydro"]
full = summary["cases"]["thermal_steady"]
baseline_k = np.asarray(baseline["stiffness"], dtype=float)
baseline_c = np.asarray(baseline["damping"], dtype=float)
full_k = np.asarray(full["stiffness"], dtype=float)
full_c = np.asarray(full["damping"], dtype=float)

mean_pressure_full_heat = identify_mean_pressure("full")
mean_pressure_mean_heat = identify_mean_pressure("half")

result = {
    "baseline_from_existing_summary": baseline,
    "thermal_steady_full_from_existing_summary": full,
    "mean_pressure_full_heat": to_list(mean_pressure_full_heat),
    "mean_pressure_mean_heat": to_list(mean_pressure_mean_heat),
    "mean_pressure_full_heat_minus_full_pressure_full_heat": {
        "delta_k": (mean_pressure_full_heat["k"] - full_k).tolist(),
        "delta_c": (mean_pressure_full_heat["c"] - full_c).tolist(),
        "max_abs_delta_k": float(np.max(np.abs(mean_pressure_full_heat["k"] - full_k))),
        "max_abs_delta_c": float(np.max(np.abs(mean_pressure_full_heat["c"] - full_c))),
    },
    "mean_pressure_full_heat_minus_baseline": {
        "delta_k": (mean_pressure_full_heat["k"] - baseline_k).tolist(),
        "delta_c": (mean_pressure_full_heat["c"] - baseline_c).tolist(),
        "max_abs_delta_k": float(
            np.max(np.abs(mean_pressure_full_heat["k"] - baseline_k))
        ),
        "max_abs_delta_c": float(
            np.max(np.abs(mean_pressure_full_heat["c"] - baseline_c))
        ),
    },
    "mean_pressure_mean_heat_minus_baseline": {
        "delta_k": (mean_pressure_mean_heat["k"] - baseline_k).tolist(),
        "delta_c": (mean_pressure_mean_heat["c"] - baseline_c).tolist(),
        "max_abs_delta_k": float(
            np.max(np.abs(mean_pressure_mean_heat["k"] - baseline_k))
        ),
        "max_abs_delta_c": float(
            np.max(np.abs(mean_pressure_mean_heat["c"] - baseline_c))
        ),
    },
}
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
