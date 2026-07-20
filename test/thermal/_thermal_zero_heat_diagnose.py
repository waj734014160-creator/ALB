import copy
import json
from pathlib import Path

import numpy as np

from ALB.core import TimeIterDt
from ALB.physics.bearing import MultiPad
from ALB.dynamics.orbit import test_bearing_orbit
from run import thermal_kc_compare as kc

OUT = Path("outputs/thermal_kc_compare/zero_heat_diagnosis.json")

case_cfg = copy.deepcopy(kc.CASE_CONFIGS["thermal_steady"]["thermal_data"])
case_cfg["heat_partition"] = 0.0
case_cfg["coupling"] = "full"

pad_cfg = kc.create_pad_config()
dt = 1.0 / (kc.ORBIT_FREQ_HZ * kc.PTS_PER_CYCLE)
pads = kc.build_fixed_opening_pads(pad_cfg)
thermal_config = kc.build_thermal_config(True, case_cfg, dt=dt)
bearing = MultiPad(*kc.wrap_pad_collection_with_thermal(pads, thermal_config))
bearing.init()
time_iter = TimeIterDt(dt=dt, num=kc.PTS_PER_CYCLE * kc.N_CYCLES)
track = kc.create_identification_track()
result = test_bearing_orbit(time_iter, bearing, track)
zero_k = np.asarray(result["hkc"]["k"], dtype=float)
zero_c = np.asarray(result["hkc"]["c"], dtype=float)

summary = json.loads(
    Path("outputs/thermal_kc_compare/summary.json").read_text(encoding="utf-8")
)
baseline = summary["cases"]["bare_hydro"]
baseline_k = np.asarray(baseline["stiffness"], dtype=float)
baseline_c = np.asarray(baseline["damping"], dtype=float)

# Single point thermal state check.
bearing2 = MultiPad(
    *kc.wrap_pad_collection_with_thermal(
        kc.build_fixed_opening_pads(pad_cfg), thermal_config
    )
)
bearing2.init()
u, v, a = track.generate_track([0.0])
bearing2.input(uxy=u[0], uxyt=v[0], uxytt=a[0], t=0.0, nodim=False)
out = bearing2.output()

res = {
    "zero_heat": {
        "k": zero_k.tolist(),
        "c": zero_c.tolist(),
        "forward_samples": int(len(result["bft"].bearing_forces)),
        "inverse_samples": int(len(result["ibft"].bearing_forces)),
    },
    "zero_heat_minus_baseline": {
        "delta_k": (zero_k - baseline_k).tolist(),
        "delta_c": (zero_c - baseline_c).tolist(),
        "max_abs_delta_k": float(np.max(np.abs(zero_k - baseline_k))),
        "max_abs_delta_c": float(np.max(np.abs(zero_c - baseline_c))),
    },
    "single_point": {
        "t_eff": float(out["t_eff"]),
        "temperature_min": float(np.min(out["temperature_film"])),
        "temperature_max": float(np.max(out["temperature_film"])),
        "viscosity_min": float(np.min(out["viscosity_field"])),
        "viscosity_max": float(np.max(out["viscosity_field"])),
        "viscosity_mean": float(np.mean(out["viscosity_field"])),
    },
}
OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps(res, indent=2))
