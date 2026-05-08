import numpy as np
import pytest

from ALB.bearing import HydrostaticBearing, NodimHydrostaticBearing
from ALB.config import HydConfig
from ALB.nondim import ThermalNondimScales
from ALB.thermal import (
    NodimThermalHydroBearing,
    SkfemThermalModelNondim,
    ThermalConfig,
    ThermalHydroBearing,
)


def _lambda_and_lr(cfg: HydConfig):
    omega = cfg.w * 2.0 * np.pi / 60.0
    lambda_value = 6.0 * cfg.miu * omega * cfg.l**2 / (cfg.ps * cfg.c**2)
    lr = cfg.l / (2.0 * cfg.r)
    return lambda_value, lr


def _build_pad(cfg: HydConfig, args_nodim: bool):
    if not args_nodim:
        return HydrostaticBearing(cfg)
    lambda_value, lr = _lambda_and_lr(cfg)
    return NodimHydrostaticBearing(
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


def make_small_thermal_bearing(**thermal_kwargs):
    cfg = HydConfig(
        nx=11,
        nz=7,
        e=0.25,
        angle=30.0,
        max_iter=120,
        error_set=1e-8,
        iter_method="newton",
    )
    args_nodim = bool(thermal_kwargs.pop("args_nodim", True))
    pad = _build_pad(cfg, args_nodim)
    tcfg = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        relax=0.6,
        max_iter=8,
        tol=5e-2,
        coupling="full",
        pressure_backend="skfem",
        supg=True,
        args_nodim=args_nodim,
        **thermal_kwargs,
    )
    wrapper_cls = NodimThermalHydroBearing if args_nodim else ThermalHydroBearing
    model = wrapper_cls(pad, tcfg)
    model.init()
    model.input(np.array([0.25 * cfg.c, 0.0]), np.array([0.0, 0.0]))
    return cfg, pad, tcfg, model


def test_thermal_nondim_scales_round_trip_temperature_and_viscosity():
    cfg, pad, tcfg, _ = make_small_thermal_bearing(delta_t_scale=20.0)
    scales = ThermalNondimScales.from_model_config(pad.main_model, tcfg, miu0=cfg.miu)

    temperature = np.array([40.0, 45.0, 60.0])
    temperature_bar = scales.temperature_to_nondim(temperature, tcfg.t_in)
    np.testing.assert_allclose(
        scales.temperature_from_nondim(temperature_bar, tcfg.t_in), temperature
    )

    viscosity = np.array([0.02, 0.03, 0.04])
    viscosity_bar = scales.viscosity_to_nondim(viscosity)
    np.testing.assert_allclose(scales.viscosity_from_nondim(viscosity_bar), viscosity)


def test_nondim_beta_matches_dimensional_viscosity_update():
    cfg, pad, tcfg, model = make_small_thermal_bearing(
        delta_t_scale=20.0,
        t_ref=45.0,
        t_supply=40.0,
    )
    scales = ThermalNondimScales.from_model_config(pad.main_model, tcfg, miu0=cfg.miu)

    temperature_nondim = np.array([0.0, 0.5, 1.2], dtype=float)
    temperature_dim = scales.temperature_from_nondim(
        temperature_nondim, scales.t_supply
    )

    miu_dim = model._viscosity_from_temperature(temperature_dim)
    miu_nondim = model._viscosity_from_temperature_nondim(temperature_nondim, scales)

    np.testing.assert_allclose(scales.beta_nondim, tcfg.beta * scales.delta_t)
    np.testing.assert_allclose(miu_nondim, miu_dim, rtol=1e-12, atol=1e-12)


def test_thermal_config_accepts_nondim_beta_and_reference_temperature():
    tcfg = ThermalConfig.from_dict(
        {
            "args_nodim": True,
            "delta_t_scale": 25.0,
            "t_in": 40.0,
            "t_supply": 42.0,
            "beta_nondim": 0.75,
            "t_ref_nondim": 0.4,
        }
    )

    np.testing.assert_allclose(tcfg.beta, 0.75 / 25.0)
    np.testing.assert_allclose(tcfg.t_ref, 42.0 + 0.4 * 25.0)


def test_nondim_beta_requires_explicit_temperature_scale():
    with pytest.raises(ValueError, match="delta_t_scale > 0"):
        ThermalConfig.from_dict({"args_nodim": True, "beta_nondim": 0.75})


def test_nondim_solver_is_selected_and_returns_nondim_fields():
    _, _, _, model = make_small_thermal_bearing(delta_t_scale=30.0)

    assert isinstance(model.thermal_model, SkfemThermalModelNondim)
    out = model.output(calc=True, nodim=True)

    assert "temperature_nondim" in out
    assert "temperature_film_nondim" in out
    assert "temperature_nondim_field" in out
    assert "pressure_nondim_field" in out
    assert "viscosity_ratio_field" in out
    assert "thermal_config_readonly" in out
    assert "heat_source_nondim" in out
    assert "qx_nondim" in out
    assert np.all(np.isfinite(out["temperature_nondim"]))
    assert np.all(np.isfinite(out["temperature_film_nondim"]))
    assert np.all(np.isfinite(out["temperature_nondim_field"]))
    assert np.all(np.isfinite(out["heat_source_nondim"]))
    np.testing.assert_allclose(
        out["viscosity_ratio_field"],
        out["viscosity_field_grid"] / out["thermal_config_readonly"]["miu0"],
    )
    assert out["t_eff"] > model.config.t_in


def test_nondim_solver_zero_heat_partition_stays_at_supply_temperature():
    _, _, _, model = make_small_thermal_bearing(heat_partition=0.0)

    out = model.output(calc=True, nodim=True)

    np.testing.assert_allclose(out["temperature"], model.config.t_in, atol=1e-8)
    np.testing.assert_allclose(out["temperature_nondim"], 0.0, atol=1e-8)
    np.testing.assert_allclose(out["heat_source_nondim"], 0.0, atol=1e-12)


def test_args_nodim_rejects_dimensional_output_by_default():
    """NodimThermalHydroBearing returns nondimensional output by default.

    The legacy ``ThermalHydroBearing(args_nodim=True)`` validation has been
    superseded by the class hierarchy: dim/nondim policy is encoded by the
    wrapper class itself, mirroring :class:`FilmModel` vs
    :class:`NodimFilmModel`.
    """
    _, _, _, model = make_small_thermal_bearing(args_nodim=True)

    out_default = model.output(calc=True)
    assert "temperature_nondim" in out_default

    out_explicit = model.output(calc=True, nodim=True)
    assert "temperature_nondim" in out_explicit
