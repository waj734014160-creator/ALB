import contextlib
import copy
import io
import json
import warnings
from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from ALB.systems.alb import alb2
from ALB.physics.bearing import HydrostaticBearing, NodimHydrostaticBearing
from ALB.config import ALBConfig, HydConfig, ThermalConfig
from ALB.physics.thermal import (
    FilmNondimScales,
    NodimThermalHydroBearing,
    ThermalHydroBearing,
)


ROOT = Path(__file__).resolve().parents[3]
REF_DIR = ROOT / "refs"
REF_JSON = REF_DIR / "thermal_segregated_newton_reference_v2.json"
REF_NPZ = REF_DIR / "thermal_segregated_newton_reference_v2.npz"


def _dataclass_args(cls, payload):
    names = {item.name for item in fields(cls)}
    return {key: payload[key] for key in names if key in payload}


def _lambda_and_lr(cfg: HydConfig):
    scales = FilmNondimScales.from_dimensional(
        w=cfg.w,
        miu=cfg.miu,
        c=cfg.c,
        r=cfg.r,
        l=cfg.l,
        ps=cfg.ps,
        rho=cfg.rho,
        vf=cfg.vf,
    )
    return scales.lambda_value, scales.lr


def _build_nondim_pad(cfg: HydConfig):
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


def _make_small_thermal_model(args_nodim, **thermal_overrides):
    cfg = HydConfig(
        nx=11,
        nz=7,
        e=0.25,
        angle=30.0,
        max_iter=120,
        error_set=1e-8,
        iter_method="newton",
    )
    pad = _build_nondim_pad(cfg) if args_nodim else HydrostaticBearing(cfg)
    thermal_args = {
        "t_in": 40.0,
        "beta": 0.03,
        "relax": 0.6,
        "max_iter": 6,
        "tol": 5e-2,
        "coupling": "full",
        "pressure_backend": "skfem",
        "args_nodim": bool(args_nodim),
    }
    if args_nodim:
        thermal_args["delta_t_scale"] = 30.0
    thermal_args.update(thermal_overrides)
    tcfg = ThermalConfig(**thermal_args)
    wrapper_cls = NodimThermalHydroBearing if args_nodim else ThermalHydroBearing
    model = wrapper_cls(pad, tcfg)
    model.init()
    model.input(np.array([0.25 * cfg.c, 0.0]), np.array([0.0, 0.0]))
    return cfg, tcfg, model


def _run_dim_small(metadata):
    case = metadata["cases"]["dim_small_fixed_point"]
    cfg = HydConfig.from_dict(case["hyd_config"])
    tcfg = ThermalConfig.from_dict(case["thermal_config"])
    model = ThermalHydroBearing(HydrostaticBearing(cfg), tcfg)
    model.init()
    model.input(
        np.asarray(case["input"]["uxy"], dtype=float),
        np.asarray(case["input"]["uxyt"], dtype=float),
    )
    out = model.output(calc=True, nodim=True)
    return {
        "dim_small_fixed_point.force": np.asarray(out["force"], dtype=np.float64),
        "dim_small_fixed_point.friction": np.asarray(
            [out["friction"]], dtype=np.float64
        ),
        "dim_small_fixed_point.pressure_field": np.asarray(
            out["pressure_field"], dtype=np.float64
        ),
        "dim_small_fixed_point.temperature_field": np.asarray(
            out["temperature_field"], dtype=np.float64
        ),
        "dim_small_fixed_point.temperature_film": np.asarray(
            out["temperature_film"], dtype=np.float64
        ),
        "dim_small_fixed_point.viscosity_field": np.asarray(
            out["viscosity_field"], dtype=np.float64
        ),
        "dim_small_fixed_point.thermal_iterations": np.asarray(
            [out["thermal_iterations"]], dtype=np.int64
        ),
        "dim_small_fixed_point.thermal_converged": np.asarray(
            [bool(out["thermal_converged"])], dtype=np.bool_
        ),
    }


def _run_nondim_small(metadata):
    case = metadata["cases"]["nondim_small_fixed_point"]
    cfg = HydConfig.from_dict(case["hyd_config"])
    tcfg = ThermalConfig.from_dict(case["thermal_config"])
    model = NodimThermalHydroBearing(_build_nondim_pad(cfg), tcfg)
    model.init()
    model.input(
        np.asarray(case["input"]["uxy"], dtype=float),
        np.asarray(case["input"]["uxyt"], dtype=float),
    )
    out = model.output(calc=True, nodim=True)
    return {
        "nondim_small_fixed_point.force": np.asarray(
            out["force"], dtype=np.float64
        ),
        "nondim_small_fixed_point.temperature_nondim": np.asarray(
            out["temperature_nondim"], dtype=np.float64
        ),
        "nondim_small_fixed_point.temperature_field": np.asarray(
            out["temperature_field"], dtype=np.float64
        ),
        "nondim_small_fixed_point.viscosity_field_grid": np.asarray(
            out["viscosity_field_grid"], dtype=np.float64
        ),
        "nondim_small_fixed_point.beta_nondim": np.asarray(
            [out["beta_nondim"]], dtype=np.float64
        ),
        "nondim_small_fixed_point.thermal_iterations": np.asarray(
            [out["thermal_iterations"]], dtype=np.int64
        ),
        "nondim_small_fixed_point.thermal_converged": np.asarray(
            [bool(out["thermal_converged"])], dtype=np.bool_
        ),
    }


def _pad_summary(model):
    result = []
    for pad in getattr(model, "pads", []):
        state = getattr(pad, "thermal_state", {})
        temp = np.asarray(pad.post_process.temperature_field, dtype=float)
        visc = np.asarray(pad.post_process.viscosity_field, dtype=float)
        result.append(
            {
                "iterations": int(state.get("iterations", 0)),
                "converged": bool(state.get("converged", False)),
                "temperature_summary": [
                    float(np.nanmin(temp)),
                    float(np.nanmean(temp)),
                    float(np.nanmax(temp)),
                ],
                "viscosity_summary": [
                    float(np.nanmin(visc)),
                    float(np.nanmean(visc)),
                    float(np.nanmax(visc)),
                ],
            }
        )
    return result


def _run_s0011_reference(metadata):
    case = metadata["cases"]["s0011_diagnostic_fixed_point"]
    base_config = case["fixed_point_config"]
    force_scale = float(case["derived"]["force_scale"])
    actual = {}
    for record in case["records"]:
        sample = record["input"]
        cfg = copy.deepcopy(base_config)
        cfg["freq"] = float(sample["freq"])
        cfg["alb"] = "ALBSV"
        cfg["servo"] = "static"
        cfg["switch"] = False
        model = alb2(ALBConfig.from_dict(cfg))
        model.init()
        model.input(
            uxy=np.array([float(sample["ex"]), float(sample["ey"])], dtype=float),
            uxyt=np.array([float(sample["vx"]), float(sample["vy"])], dtype=float),
            t=0.0,
            sv=np.array([float(sample["sx"]), float(sample["sy"])], dtype=float),
            nodim=True,
        )
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = model.output(nodim=False)
        force_dim = np.asarray(out["force"], dtype=np.float64)
        force = force_dim / force_scale
        pads = _pad_summary(model)
        sid = int(record["sample_id"])
        prefix = f"s0011_diagnostic_fixed_point.sample_{sid}"
        actual[f"{prefix}.force"] = force
        actual[f"{prefix}.force_dim"] = force_dim
        actual[f"{prefix}.thermal_iterations_by_pad"] = np.asarray(
            [item["iterations"] for item in pads], dtype=np.int64
        )
        actual[f"{prefix}.thermal_converged_by_pad"] = np.asarray(
            [item["converged"] for item in pads], dtype=np.bool_
        )
        actual[f"{prefix}.temperature_summary"] = np.asarray(
            [item["temperature_summary"] for item in pads], dtype=np.float64
        )
        actual[f"{prefix}.viscosity_summary"] = np.asarray(
            [item["viscosity_summary"] for item in pads], dtype=np.float64
        )
    return actual


def _run_s0011_case(sample_id, thermal_overrides):
    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    case = metadata["cases"]["s0011_diagnostic_fixed_point"]
    base_config = case["resolved_source_config"]
    record = next(
        item for item in case["records"] if int(item["sample_id"]) == int(sample_id)
    )
    sample = record["input"]
    cfg = copy.deepcopy(base_config)
    cfg["freq"] = float(sample["freq"])
    cfg["alb"] = "ALBSV"
    cfg["servo"] = "static"
    cfg["switch"] = False
    thermal = dict(cfg["thermal"])
    thermal.update(thermal_overrides)
    cfg["thermal"] = thermal
    model = alb2(ALBConfig.from_dict(cfg))
    model.init()
    model.input(
        uxy=np.array([float(sample["ex"]), float(sample["ey"])], dtype=float),
        uxyt=np.array([float(sample["vx"]), float(sample["vy"])], dtype=float),
        t=0.0,
        sv=np.array([float(sample["sx"]), float(sample["sy"])], dtype=float),
        nodim=True,
    )
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = model.output(nodim=False)
    return model, out


def test_fixed_point_reference_snapshot_matches_pre_change_results_exactly():
    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    assert metadata["reference_name"] == "thermal_segregated_newton_reference_v2"
    actual = {}
    actual.update(_run_dim_small(metadata))
    actual.update(_run_nondim_small(metadata))

    with np.load(REF_NPZ) as reference:
        expected_keys = {
            key for key in reference.files if not key.startswith("s0011_")
        }
        assert set(actual) == expected_keys
        for key in expected_keys:
            np.testing.assert_array_equal(actual[key], reference[key], err_msg=key)


def test_s0011_current_replay_reference_v2_matches_exactly():
    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    s0011_case = metadata["cases"]["s0011_diagnostic_fixed_point"]
    assert not s0011_case["config_provenance"]["historical_share_available"]
    actual = _run_s0011_reference(metadata)

    with np.load(REF_NPZ) as reference:
        expected_keys = {
            key for key in reference.files if key.startswith("s0011_")
        }
        assert set(actual) == expected_keys
        for key in expected_keys:
            np.testing.assert_array_equal(actual[key], reference[key], err_msg=key)


def test_thermal_config_accepts_and_validates_iter_method_options():
    default_config = ThermalConfig()
    assert default_config.iter_method == "direct"
    assert default_config.k_lub == pytest.approx(0.0)
    assert default_config.supg is True
    assert default_config.thermal_newton_line_search is False
    assert default_config.miu_update == "linear"
    assert default_config.miu_update_max_ratio is None
    assert default_config.heat_partition_steps is None
    for method in ("direct", "newton", "direct_then_newton"):
        assert ThermalConfig.from_dict({"iter_method": method}).iter_method == method
    log_config = ThermalConfig.from_dict(
        {
            "miu_update": "log",
            "miu_update_max_ratio": 1.2,
            "heat_partition": 0.9,
            "heat_partition_steps": [0.3, 0.6],
        }
    )
    assert log_config.miu_update == "log"
    assert log_config.miu_update_max_ratio == pytest.approx(1.2)
    assert log_config.heat_partition_steps == pytest.approx((0.3, 0.6, 0.9))

    with pytest.raises(ValueError, match="iter_method"):
        ThermalConfig(iter_method="bad_solver")
    with pytest.raises(ValueError, match="miu_update"):
        ThermalConfig(miu_update="bad_update")
    with pytest.raises(ValueError, match="miu_update_max_ratio"):
        ThermalConfig(miu_update_max_ratio=1.0)
    with pytest.raises(ValueError, match="heat_partition_steps"):
        ThermalConfig(heat_partition_steps=[0.2, 1.0])
    with pytest.raises(ValueError, match="Unknown ThermalConfig"):
        ThermalConfig.from_dict({"thermal_nonlinear_solver": "segregated_newton"})
    with pytest.raises(ValueError, match="thermal_newton_max_iter"):
        ThermalConfig(thermal_newton_max_iter=0)
    with pytest.raises(ValueError, match="thermal_newton_tol"):
        ThermalConfig(thermal_newton_tol=0.0)
    with pytest.raises(ValueError, match="thermal_newton_damp"):
        ThermalConfig(thermal_newton_damp=0.0)
    with pytest.raises(ValueError, match="thermal_newton_min_damp"):
        ThermalConfig(thermal_newton_damp=0.5, thermal_newton_min_damp=0.6)


def test_newton_dimensional_small_case_converges_with_diagnostics():
    _, tcfg, model = _make_small_thermal_model(
        False,
        iter_method="newton",
        thermal_newton_max_iter=12,
        thermal_newton_tol=1e-5,
    )

    out = model.output(calc=True, nodim=True)

    assert out["thermal_converged"]
    assert out["thermal_solver_used"] == "newton"
    assert out["thermal_newton_iterations"] > 0
    assert np.isfinite(out["thermal_newton_residual"])
    assert out["thermal_newton_residual"] < tcfg.thermal_newton_tol
    assert out["thermal_newton_line_search_steps"] >= 0
    assert np.all(np.isfinite(out["temperature"]))


def test_newton_nondim_small_case_converges_with_nondim_outputs():
    _, _, model = _make_small_thermal_model(
        True,
        iter_method="newton",
        thermal_newton_max_iter=12,
        thermal_newton_tol=1e-5,
    )

    out = model.output(calc=True, nodim=True)

    assert out["thermal_converged"]
    assert out["thermal_solver_used"] == "newton"
    assert out["thermal_newton_iterations"] > 0
    assert np.isfinite(out["thermal_newton_residual"])
    assert "temperature_nondim" in out
    assert "beta_nondim" in out
    assert np.all(np.isfinite(out["temperature_nondim"]))


def test_direct_log_update_continuation_small_case_converges():
    _, _, model = _make_small_thermal_model(
        False,
        iter_method="direct",
        miu_min=0.0,
        miu_update="log",
        miu_update_max_ratio=1.2,
        heat_partition_steps=[0.3, 0.6, 0.9],
        max_iter=12,
        tol=5e-2,
    )

    out = model.output(calc=True, nodim=True)

    assert out["thermal_converged"]
    assert out["thermal_solver_used"] == "direct"
    assert out["thermal_continuation_steps"] == pytest.approx([0.3, 0.6, 0.9])
    assert np.all(np.asarray(out["viscosity_field"]) > 0.0)


def test_direct_then_newton_reports_s0011_sample_30_without_false_convergence():
    model, out = _run_s0011_case(
        30,
        {
            "iter_method": "direct_then_newton",
            "thermal_newton_max_iter": 20,
            "thermal_newton_tol": 1e-6,
            "thermal_newton_damp": 1.0,
            "thermal_newton_line_search": True,
        },
    )

    states = [pad.thermal_state for pad in model.pads]
    assert np.all(np.isfinite(out["force"]))
    assert not all(bool(state["converged"]) for state in states)
    assert any(state["solver_used"] == "direct_then_newton" for state in states)
    assert any(int(state["newton_iterations"]) > 0 for state in states)
    assert all("newton_residual" in state for state in states)
    assert all(
        np.isfinite(state["newton_residual"])
        for state in states
        if int(state["newton_iterations"]) > 0
    )


def test_direct_then_newton_does_not_false_converge_s0011_sample_162946():
    model, out = _run_s0011_case(
        162946,
        {
            "max_iter": 2,
            "iter_method": "direct_then_newton",
            "thermal_newton_max_iter": 4,
            "thermal_newton_tol": 1e-6,
            "thermal_newton_damp": 1.0,
            "thermal_newton_line_search": True,
        },
    )

    states = [pad.thermal_state for pad in model.pads]
    assert np.all(np.isfinite(out["force"]))
    assert not all(bool(state["converged"]) for state in states)
    assert any(state["solver_used"] == "direct_then_newton" for state in states)
    assert all("newton_residual" in state for state in states)
    assert all(np.isfinite(state["newton_residual"]) for state in states)
