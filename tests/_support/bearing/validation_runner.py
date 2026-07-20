# -- coding: utf-8 --

import numpy as np

from ALB.physics.bearing import HydrostaticBearing, MultiPad
from ALB.config import HydConfig

from .validation_reference_data import BASE_HYD_CONFIG


def _build_hyd_config(e, angle, x0):
    kwargs = dict(BASE_HYD_CONFIG)
    kwargs.update({"e": e, "angle": angle, "x0": x0, "lx": 160})
    return HydConfig(**kwargs)


def run_validation_case(e, angle):
    hyd_config0 = _build_hyd_config(e=e, angle=angle, x0=-80)
    hyd_config1 = _build_hyd_config(e=e, angle=angle, x0=100)

    bearing1 = HydrostaticBearing(hyd_config0)
    bearing2 = HydrostaticBearing(hyd_config1)
    mp = MultiPad(bearing1, bearing2)

    mp.solve()
    force = mp.calc_capacity(nodim=False)
    load = float(np.linalg.norm(force))
    friction = float(mp.calc_friction(nodim=True))

    args1 = bearing2.margs
    k = mp.calc_k(nodim=False)
    c = mp.calc_c(nodim=False)
    ka = k * args1["c"] / load
    ca = c * args1["c"] / load * args1["w_rad"]
    s = (
        args1["miu"]
        * args1["w"]
        / 60
        * args1["l"]
        * args1["r"]
        * 2
        / load
        * (args1["r"] / args1["c"]) ** 2
    )

    return {
        "e": float(e),
        "angle": float(angle),
        "force": np.asarray(force, dtype=float),
        "load": float(load),
        "friction": float(friction),
        "S": float(s),
        "k_matrix": np.asarray(ka, dtype=float),
        "c_matrix": np.asarray(ca, dtype=float),
        "kxx": float(ka[0, 0]),
        "kxy": float(ka[0, 1]),
        "kyx": float(ka[1, 0]),
        "kyy": float(ka[1, 1]),
        "cxx": float(ca[0, 0]),
        "cxy": float(ca[0, 1]),
        "cyx": float(ca[1, 0]),
        "cyy": float(ca[1, 1]),
    }


def is_case_correct(result, reference, thresholds=None):
    # Thresholds are intentionally tolerant to numerical solver variation.
    limits = {
        "kxx_abs": 0.35,
        "cxy_abs": 0.40,
        "cyx_abs": 0.40,
        "p_rel": 0.35,
    }
    if thresholds:
        limits.update(thresholds)

    checks = {
        "kxx": abs(result["kxx"] - reference["kxx"]) <= limits["kxx_abs"],
        "cxy": abs(result["cxy"] - reference["cxy"]) <= limits["cxy_abs"],
        "cyx": abs(result["cyx"] - reference["cyx"]) <= limits["cyx_abs"],
        "p": abs(result["friction"] - reference["p"]) / max(abs(reference["p"]), 1e-12)
        <= limits["p_rel"],
    }
    return all(checks.values()), checks
