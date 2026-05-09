import numpy as np

from ALB.bearing import HydrostaticBearing
from ALB.config import HydConfig
from ALB.thermal import ThermalConfig, ThermalHydroBearing


def test_pressure_solver_records_adaptive_damp_history_when_enabled():
    cfg = HydConfig(
        nx=9,
        nz=5,
        e=0.25,
        angle=20.0,
        max_iter=12,
        error_set=1e-8,
        damp=0.5,
        iter_method="newton",
        adaptive_damp={"enabled": True, "min_value": 0.05},
    )
    bearing = HydrostaticBearing(cfg)
    bearing.solve()

    pressure = np.asarray(bearing.main_model.latest_result, dtype=float)
    assert np.isfinite(pressure).all()
    assert bearing.main_model._adaptive_damp.enabled
    assert isinstance(bearing.main_model.adaptive_damp_history, list)
    assert all(
        0.05 <= item["value_after"] <= cfg.damp
        for item in bearing.main_model.adaptive_damp_history
    )


def test_thermal_solver_records_adaptive_relax_history_when_enabled():
    cfg = HydConfig(
        nx=9,
        nz=5,
        e=0.25,
        angle=20.0,
        max_iter=40,
        error_set=1e-8,
        damp=0.5,
        iter_method="newton",
        adaptive_damp={"enabled": True, "min_value": 0.05},
    )
    pad = HydrostaticBearing(cfg)
    tcfg = ThermalConfig(
        t_in=40.0,
        beta=0.02,
        relax=0.4,
        max_iter=4,
        tol=5e-2,
        coupling="half",
        pressure_backend="skfem",
        args_nodim=False,
        adaptive_damp={"enabled": True, "min_value": 0.05},
    )
    model = ThermalHydroBearing(pad, tcfg)
    model.init()
    model.input(np.array([0.2 * cfg.c, 0.0]), np.array([0.0, 0.0]))

    out = model.output(calc=True, nodim=True)

    assert np.isfinite(out["force"]).all()
    assert out["thermal_adaptive_damp_enabled"] is True
    assert isinstance(out["thermal_relax_history"], list)
    assert all(
        0.05 <= item["value_after"] <= tcfg.relax
        for item in out["thermal_relax_history"]
    )
