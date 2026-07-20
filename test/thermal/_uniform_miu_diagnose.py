import copy
import json
from pathlib import Path

import numpy as np

from ALB.core import TimeIterDt
from ALB.physics.bearing import MultiPad
from ALB.orbit import test_bearing_orbit
from run import thermal_kc_compare as kc

OUT = Path("outputs/thermal_kc_compare/uniform_miu_diagnosis.json")

summary = json.loads(
    Path("outputs/thermal_kc_compare/summary.json").read_text(encoding="utf-8")
)
baseline = summary["cases"]["bare_hydro"]
thermal = summary["cases"]["thermal_steady"]
baseline_k = np.asarray(baseline["stiffness"], dtype=float)
baseline_c = np.asarray(baseline["damping"], dtype=float)
thermal_k = np.asarray(thermal["stiffness"], dtype=float)
thermal_c = np.asarray(thermal["damping"], dtype=float)

# Values observed from thermal steady trajectory diagnostics.
miu_values = {
    "thermal_single_point_mean": 0.01898652310761633,
    "thermal_track_mean": 0.018993595865438494,
    "thermal_min": 0.018477040115720007,
}


def identify_bare_with_miu(miu):
    pad_cfg = kc.create_pad_config()
    pad_cfg.miu = float(miu)
    dt = 1.0 / (kc.ORBIT_FREQ_HZ * kc.PTS_PER_CYCLE)
    pads = kc.build_fixed_opening_pads(pad_cfg)
    bearing = MultiPad(*pads)
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


results = {}
for label, miu in miu_values.items():
    identified = identify_bare_with_miu(miu)
    results[label] = {
        "miu": miu,
        "k": identified["k"].tolist(),
        "c": identified["c"].tolist(),
        "minus_baseline": {
            "delta_k": (identified["k"] - baseline_k).tolist(),
            "delta_c": (identified["c"] - baseline_c).tolist(),
            "max_abs_delta_k": float(np.max(np.abs(identified["k"] - baseline_k))),
            "max_abs_delta_c": float(np.max(np.abs(identified["c"] - baseline_c))),
        },
        "minus_thermal_steady": {
            "delta_k": (identified["k"] - thermal_k).tolist(),
            "delta_c": (identified["c"] - thermal_c).tolist(),
            "max_abs_delta_k": float(np.max(np.abs(identified["k"] - thermal_k))),
            "max_abs_delta_c": float(np.max(np.abs(identified["c"] - thermal_c))),
        },
    }

OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
