import json
import math
from pathlib import Path

import numpy as np
import pytest

from ALB.bearing import HydrostaticBearing, NodimHydrostaticBearing
from ALB.config import HydConfig, ThermalConfig
from ALB.thermal import (
    NodimThermalHydroBearing,
    NodimViscositySkfemNewtonFilm,
    SkfemThermalModelNondim,
    ThermalHydroBearing,
    wrap_pad_collection_with_thermal,
)


REF_JSON = Path("refs/thermal_wrapper_dim_api_reference_v1.json")
REF_NPZ = Path("refs/thermal_wrapper_dim_api_reference_v1.npz")
RTOL = 1e-8
ATOL = 1e-10


def _lambda_and_lr(cfg: HydConfig):
    omega = cfg.w * 2.0 * np.pi / 60.0
    lambda_value = 1.5 * cfg.miu * omega * cfg.l**2 / (cfg.ps * cfg.c**2)
    lr = cfg.l / (2.0 * cfg.r)
    return lambda_value, lr


def _thermal_config(args_nodim=False):
    return ThermalConfig(
        t_in=40.0,
        t_supply=40.0,
        t_ref=40.0,
        beta=0.03,
        k_lub=0.0,
        cp_lub=2000.0,
        heat_partition=0.25,
        relax=0.6,
        max_iter=8,
        tol=5e-2,
        coupling="full",
        pressure_backend="skfem",
        supg=True,
        args_nodim=args_nodim,
        delta_t_scale=20.0,
    )


def _run_reference_case(metadata, nodim_output):
    hyd_config = HydConfig.from_dict(metadata["hyd_config"])
    thermal_config = ThermalConfig.from_dict(metadata["thermal_config"])
    model = ThermalHydroBearing(HydrostaticBearing(hyd_config), thermal_config)
    model.init()
    model.input(
        np.asarray(metadata["input"]["uxy_dim"], dtype=float),
        np.asarray(metadata["input"]["uxyt_dim"], dtype=float),
    )
    return model.output(calc=True, nodim=nodim_output)


def _captured_arrays(out, prefix):
    arrays = {}
    for key in [
        "force",
        "temperature",
        "temperature_film",
        "viscosity_field",
        "pressure_field",
        "pressure_nondim_field",
        "temperature_nondim",
        "temperature_film_nondim",
        "heat_source_nondim",
    ]:
        if key in out:
            arrays[f"{prefix}_{key}"] = np.asarray(out[key], dtype=float)
    return arrays


def _captured_scalars(out, prefix):
    scalars = {}
    for key in [
        "friction",
        "thermal_iterations",
        "thermal_rel_error",
        "thermal_converged",
        "t_eff",
        "t_eff_nondim",
        "q_orifice_total",
        "thermal_newton_iterations",
        "thermal_newton_residual",
        "thermal_newton_line_search_steps",
    ]:
        if key in out:
            value = out[key]
            if isinstance(value, (bool, np.bool_)):
                scalars[f"{prefix}_{key}"] = bool(value)
            elif value is None:
                scalars[f"{prefix}_{key}"] = None
            else:
                scalars[f"{prefix}_{key}"] = float(value)
    scalars[f"{prefix}_thermal_solver_used"] = str(out.get("thermal_solver_used"))
    return scalars


def test_dimensional_thermal_wrapper_matches_reference_baseline():
    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    refs = np.load(REF_NPZ)

    actual_arrays = {}
    actual_scalars = {}
    for nodim_output in (False, True):
        prefix = "nodim" if nodim_output else "dim"
        out = _run_reference_case(metadata, nodim_output)
        actual_arrays.update(_captured_arrays(out, prefix))
        actual_scalars.update(_captured_scalars(out, prefix))

    for key in refs.files:
        assert key in actual_arrays
        np.testing.assert_allclose(
            actual_arrays[key],
            refs[key],
            rtol=RTOL,
            atol=ATOL,
            err_msg=key,
        )

    for key, expected in metadata["scalars"].items():
        actual = actual_scalars[key]
        if isinstance(expected, bool):
            assert actual is expected
        elif isinstance(expected, str):
            assert actual == expected
        elif expected is None:
            assert actual is None
        elif math.isnan(float(expected)):
            assert math.isnan(float(actual))
        else:
            np.testing.assert_allclose(
                np.asarray([actual], dtype=float),
                np.asarray([expected], dtype=float),
                rtol=RTOL,
                atol=ATOL,
                err_msg=key,
            )


def test_dimensional_wrapper_uses_nondim_core_backend():
    cfg = HydConfig(
        miu=0.0195,
        c=80e-6,
        r=0.04,
        l=0.08,
        ps=10e6,
        rho=872.0,
        freq=50.0,
        nx=7,
        nz=5,
        e=0.12,
        angle=20.0,
        max_iter=50,
        error_set=1e-8,
        iter_method="newton",
    )
    model = ThermalHydroBearing(HydrostaticBearing(cfg), _thermal_config(False))

    assert model.config.args_nodim is False
    assert isinstance(model.bearing.main_model, NodimViscositySkfemNewtonFilm)
    assert model.bearing.main_model.args["args_nodim"] is True
    assert isinstance(model.thermal_model, SkfemThermalModelNondim)


def test_thermal_collection_wrapper_dispatches_by_pad_unit_mode():
    cfg = HydConfig(nx=5, nz=3, max_iter=5, error_set=1e-6)
    dim_wrapped = wrap_pad_collection_with_thermal(
        [HydrostaticBearing(cfg)], _thermal_config(False)
    )
    assert isinstance(dim_wrapped[0], ThermalHydroBearing)

    lambda_value, lr = _lambda_and_lr(cfg)
    nodim_pad = NodimHydrostaticBearing(
        lambda_value=lambda_value,
        lr=lr,
        x0=cfg.x0,
        lx=cfg.lx,
        lz=cfg.lz,
        nx=cfg.nx,
        nz=cfg.nz,
        e=cfg.e,
        angle=cfg.angle_rad,
        coe=cfg.coe,
        p_set=cfg.p_set,
        reynold=cfg.reynold,
        max_iter=cfg.max_iter,
        error_set=cfg.error_set,
        damp=cfg.damp,
        miu=cfg.miu,
        c=cfg.c,
        r=cfg.r,
        l=cfg.l,
        ps=cfg.ps,
        rho=cfg.rho,
        w=cfg.w,
    )
    nodim_wrapped = wrap_pad_collection_with_thermal([nodim_pad], _thermal_config(True))
    assert isinstance(nodim_wrapped[0], NodimThermalHydroBearing)

    with pytest.raises(TypeError, match="args_nodim"):
        wrap_pad_collection_with_thermal([HydrostaticBearing(cfg)], _thermal_config(True))
