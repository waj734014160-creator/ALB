import contextlib
import copy
import io
import json
import math
import warnings
from dataclasses import fields
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ALB.alb import alb2
from ALB.physics.bearing import HydrostaticBearing, NodimHydrostaticBearing
from ALB.config import ALBConfig, CsoArgs, HydConfig, ThermalConfig
from ALB.physics.thermal import NodimThermalHydroBearing, ThermalHydroBearing
from ALB.tool import read_json5_with_share


ROOT = Path(__file__).resolve().parents[2]
REF_DIR = ROOT / "refs"
REF_JSON = REF_DIR / "thermal_segregated_newton_reference_v1.json"
REF_NPZ = REF_DIR / "thermal_segregated_newton_reference_v1.npz"
S0011_CSV = (
    ROOT.parent
    / "SURROGATE_TRAIN"
    / "outputs"
    / "alb_data2"
    / "S0011_alb_data2_exey0to0p9_200000_seed20260607_20260607"
    / "alb_data2_results_n200000_seed20260607.csv"
)
PAPER_CONFIG = Path("F:/BaiduSyncdisk/博士论文/task/PAPER/config/alb12.json5")
S0011_SAMPLE_IDS = [30, 33, 162946]


def _require_s0011_fixture():
    """Skip S0011 integration checks when external paper fixtures are absent."""
    missing = [path for path in (PAPER_CONFIG, S0011_CSV) if not path.exists()]
    if missing:
        pytest.skip(f"S0011 external fixtures are not available: {missing}")


def _dataclass_args(cls, payload):
    names = {item.name for item in fields(cls)}
    return {key: payload[key] for key in names if key in payload}


def _lambda_and_lr(cfg: HydConfig):
    omega = cfg.w * 2.0 * np.pi / 60.0
    lambda_value = 6.0 * cfg.miu * omega * cfg.l**2 / (cfg.ps * cfg.c**2)
    lr = cfg.l / (2.0 * cfg.r)
    return lambda_value, lr


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


def _derive_base_values(base_config):
    thermal = dict(base_config.get("thermal", {}))
    cso = CsoArgs()
    miu = float(base_config["miu"])
    c = float(base_config["c"])
    r = float(base_config["r"])
    l = float(base_config["l"])
    ps = float(base_config["ps"])
    rho = float(base_config["rho"])
    lr = l / (2.0 * r)
    qw = ps * c**3 / (12.0 * miu * lr)
    cq0 = cso.cd * cso.w * math.sqrt(2.0 / rho) * math.sqrt(ps) / qw
    cq1 = rho / (5.0 * (math.pi * c * cso.d) ** 2) * qw**2 / ps
    cq2 = 128.0 * miu * cso.l / (math.pi * cso.d**4) * qw / ps
    lambda_per_hz = 1.5 * miu * (2.0 * math.pi) * l**2 / (ps * c**2)
    beta_nondim = (
        float(thermal.get("beta", 0.03))
        * float(thermal.get("heat_partition", 0.9))
        * ps
        / (rho * float(thermal.get("cp_lub", 2000.0)))
    )
    return {
        "lambda_per_hz": lambda_per_hz,
        "beta_nondim": beta_nondim,
        "lr": lr,
        "cq0": cq0,
        "cq1": cq1,
        "cq2": cq2,
        "force_scale": ps * l * r / 2.0,
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


def _run_s0011_reference():
    _require_s0011_fixture()
    base_config = read_json5_with_share(str(PAPER_CONFIG))
    thermal_config = base_config.setdefault("thermal", {})
    thermal_config["iter_method"] = "direct"
    thermal_config["supg"] = True
    thermal_config["miu_min"] = 1e-4
    thermal_config["max_delta_t"] = 80.0
    thermal_config["miu_update"] = "linear"
    thermal_config.pop("miu_update_max_ratio", None)
    thermal_config.pop("heat_partition_steps", None)
    derived = _derive_base_values(base_config)
    rows = pd.read_csv(S0011_CSV)
    rows = rows[rows["sample_id"].isin(S0011_SAMPLE_IDS)].sort_values("sample_id")
    actual = {}
    for _, row in rows.iterrows():
        cfg = copy.deepcopy(base_config)
        cfg["freq"] = float(row["freq"])
        cfg["alb"] = "ALBSV"
        cfg["servo"] = "static"
        cfg["switch"] = False
        model = alb2(ALBConfig.from_dict(cfg))
        model.init()
        model.input(
            uxy=np.array([float(row["ex"]), float(row["ey"])], dtype=float),
            uxyt=np.array([float(row["vx"]), float(row["vy"])], dtype=float),
            t=0.0,
            sv=np.array([float(row["sx"]), float(row["sy"])], dtype=float),
            nodim=True,
        )
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = model.output(nodim=False)
        force_dim = np.asarray(out["force"], dtype=np.float64)
        force = force_dim / float(derived["force_scale"])
        pads = _pad_summary(model)
        sid = int(row["sample_id"])
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
    _require_s0011_fixture()
    base_config = read_json5_with_share(str(PAPER_CONFIG))
    rows = pd.read_csv(S0011_CSV).set_index("sample_id")
    row = rows.loc[int(sample_id)]
    cfg = copy.deepcopy(base_config)
    cfg["freq"] = float(row["freq"])
    cfg["alb"] = "ALBSV"
    cfg["servo"] = "static"
    cfg["switch"] = False
    thermal = dict(cfg["thermal"])
    thermal.update(thermal_overrides)
    cfg["thermal"] = thermal
    model = alb2(ALBConfig.from_dict(cfg))
    model.init()
    model.input(
        uxy=np.array([float(row["ex"]), float(row["ey"])], dtype=float),
        uxyt=np.array([float(row["vx"]), float(row["vy"])], dtype=float),
        t=0.0,
        sv=np.array([float(row["sx"]), float(row["sy"])], dtype=float),
        nodim=True,
    )
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = model.output(nodim=False)
    return model, out


def test_fixed_point_reference_snapshot_matches_pre_change_results_exactly():
    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    actual = {}
    actual.update(_run_dim_small(metadata))
    actual.update(_run_nondim_small(metadata))
    actual.update(_run_s0011_reference())

    with np.load(REF_NPZ) as reference:
        assert set(actual) == set(reference.files)
        for key in reference.files:
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
