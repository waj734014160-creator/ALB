# coding: utf-8
"""Numerical equivalence checks for dimensional ALBSV and nodim_alb."""

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ALB.systems.alb import alb2, nodim_alb
from ALB.config import ALBConfig, CsoArgs, NodimALBConfig, ThermalConfig
from ALB.contracts import (
    BearingInput,
    DirectSpoolBearingInput,
    ValveOutput,
)
from ALB.physics.thermal import FilmNondimScales

BASE = dict(
    alb="ALBSV",
    servo="static",
    switch=False,
    dt=6.667e-4,
    lx=80.0,
    lz=2.0,
    nx=15,
    nz=9,
    coe=False,
    max_iter=120,
    error_set=1e-9,
    damp=0.7,
    miu=0.0195,
    c=80e-6,
    r=0.04,
    l=0.08,
    ps=3e6,
    rho=872,
    freq=50.0,
    vf=1.0,
    position=np.array([[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]]),
    xrange=[0.49, 0.51],
    zrange=[0.2, 0.8],
    h_tank=2.0,
)

THERMAL = dict(
    t_in=40.0,
    t_supply=40.0,
    t_ref=40.0,
    beta=0.03,
    k_lub=0.0,
    cp_lub=2000.0,
    heat_partition=0.25,
    relax=0.6,
    tol=1e-8,
    max_iter=60,
    coupling="full",
    pressure_backend="skfem",
    supg=True,
    delta_t_scale=1.0,
    transient_enabled=False,
    max_delta_t=80.0,
    miu_min=1e-4,
    miu_max=1.0,
)


def _scales():
    return FilmNondimScales.from_dimensional(
        w=BASE["freq"] * 60.0,
        miu=BASE["miu"],
        c=BASE["c"],
        r=BASE["r"],
        l=BASE["l"],
        ps=BASE["ps"],
        rho=BASE["rho"],
        vf=BASE["vf"],
    )


def _force_scale():
    return BASE["ps"] * BASE["l"] * BASE["r"] / 2.0


def _nodim_config(cq0=1.0, cq1=1.0, cq2=0.0, thermal_config=None):
    scales = _scales()
    config = dict(
        alb="ALBSV",
        servo="static",
        switch=False,
        dt=BASE["dt"],
        lambda_value=scales.lambda_value,
        lr=scales.lr,
        lx=BASE["lx"],
        lz=BASE["lz"],
        nx=BASE["nx"],
        nz=BASE["nz"],
        coe=BASE["coe"],
        max_iter=BASE["max_iter"],
        error_set=BASE["error_set"],
        damp=BASE["damp"],
        position=BASE["position"],
        cq0=float(cq0),
        cq1=float(cq1),
        cq2=float(cq2),
        ps=1.0,
        p0=0.0,
        scale_miu=BASE["miu"],
        scale_c=BASE["c"],
        scale_r=BASE["r"],
        scale_l=BASE["l"],
        scale_ps=BASE["ps"],
        scale_rho=BASE["rho"],
        scale_w=BASE["freq"] * 60.0,
        xrange=BASE["xrange"],
        zrange=BASE["zrange"],
        h_tank=BASE["h_tank"],
    )
    if thermal_config is not None:
        config["thermal_config"] = thermal_config
    return NodimALBConfig.from_dict(config)


def _run_dimensional(case):
    ex, ey, vx, vy, sx, sy = case
    scales = _scales()
    model = alb2(ALBConfig.from_dict(BASE))
    model.init()
    model.input(
        DirectSpoolBearingInput(
            BearingInput(
                [ex * BASE["c"], ey * BASE["c"]],
                [
                    vx * BASE["c"] * scales.w_rad,
                    vy * BASE["c"] * scales.w_rad,
                ],
                0.0,
                "dimensional",
            ),
            ValveOutput([sx, sy], 0.0, "nondimensional"),
        )
    )
    model.evaluate()
    force = model.output().force / _force_scale()
    return model, force


def _run_nodim(case, cq0=1.0, cq1=1.0, cq2=0.0):
    ex, ey, vx, vy, sx, sy = case
    model = nodim_alb(_nodim_config(cq0=cq0, cq1=cq1, cq2=cq2))
    model.init()
    model.input(
        DirectSpoolBearingInput(
            BearingInput([ex, ey], [vx, vy], 0.0, "nondimensional"),
            ValveOutput([sx, sy], 0.0, "nondimensional"),
        )
    )
    model.evaluate()
    return model, model.output().force


def _orifice_coefficients(dim_model=None, orifice=None):
    if orifice is None:
        orifice = dim_model.servovalves[0].simple_models[0]
    return orifice.cq0, float(orifice.cq1), orifice.cq2


def _expected_cso_coefficients():
    cso = CsoArgs()
    scales = _scales()
    qw = BASE["ps"] * BASE["c"] ** 3 / (12.0 * BASE["miu"] * scales.lr)
    cq0 = cso.cd * cso.w * np.sqrt(2.0 / BASE["rho"]) * np.sqrt(BASE["ps"]) / qw
    cq1 = BASE["rho"] / 5.0 / (np.pi * BASE["c"] * cso.d) ** 2
    cq1 = cq1 * qw**2 / BASE["ps"]
    cq2 = 128.0 * BASE["miu"] * cso.l / np.pi / cso.d**4
    cq2 = cq2 * qw / BASE["ps"]
    return cq0, cq1, cq2


def _all_orifices(model):
    return [
        model.servovalves[0].simple_models[0],
        model.servovalves[0].simple_models[1],
        model.servovalves[1].simple_models[0],
        model.servovalves[1].simple_models[1],
    ]


def _run_dimensional_thermal(case):
    ex, ey, vx, vy, sx, sy = case
    scales = _scales()
    config = ALBConfig.from_dict(
        {**BASE, "thermal_enabled": True, "thermal": {**THERMAL, "args_nodim": False}}
    )
    model = alb2(config)
    model.init()
    model.input(
        DirectSpoolBearingInput(
            BearingInput(
                [ex * BASE["c"], ey * BASE["c"]],
                [
                    vx * BASE["c"] * scales.w_rad,
                    vy * BASE["c"] * scales.w_rad,
                ],
                0.0,
                "dimensional",
            ),
            ValveOutput([sx, sy], 0.0, "nondimensional"),
        )
    )
    model.evaluate()
    force = model.output().force / _force_scale()
    return model, force


def _run_nodim_thermal(
    case, branch_orifice_coefficients=None, cq0=1.0, cq1=1.0, cq2=0.0
):
    ex, ey, vx, vy, sx, sy = case
    thermal_config = ThermalConfig.from_dict({**THERMAL, "args_nodim": True})
    model = nodim_alb(
        _nodim_config(
            cq0=cq0,
            cq1=cq1,
            cq2=cq2,
            thermal_config=thermal_config,
        )
    )
    if branch_orifice_coefficients is not None:
        for orifice, coefficients in zip(
            _all_orifices(model), branch_orifice_coefficients
        ):
            branch_cq0, branch_cq1, branch_cq2 = coefficients
            orifice.cq0 = float(branch_cq0)
            orifice.cq1 = float(branch_cq1)
            orifice.cq2 = float(branch_cq2)
    model.init()
    model.input(
        DirectSpoolBearingInput(
            BearingInput([ex, ey], [vx, vy], 0.0, "nondimensional"),
            ValveOutput([sx, sy], 0.0, "nondimensional"),
        )
    )
    model.evaluate()
    return model, model.output().force


def _max_thermal_field_delta(dim_model, nd_model):
    max_temperature = 0.0
    max_viscosity = 0.0
    for dim_pad, nd_pad in zip(dim_model.pads, nd_model.pads):
        max_temperature = max(
            max_temperature,
            float(
                np.max(
                    np.abs(
                        nd_pad.post_process.temperature_field
                        - dim_pad.post_process.temperature_field
                    )
                )
            ),
        )
        max_viscosity = max(
            max_viscosity,
            float(
                np.max(
                    np.abs(
                        nd_pad.post_process.viscosity_field
                        - dim_pad.post_process.viscosity_field
                    )
                )
            ),
        )
    return max_temperature, max_viscosity


def compare_no_orifice_flow():
    cases = [
        (-0.2, 0.15, 0.0, 0.0, 0.0, 0.0),
        (0.35, -0.1, 0.08, -0.04, 0.0, 0.0),
        (-0.55, 0.25, -0.12, 0.09, 0.0, 0.0),
    ]
    for case in cases:
        dim_model, dim_force = _run_dimensional(case)
        nd_model, nd_force = _run_nodim(case)
        rel = np.linalg.norm(nd_force - dim_force) / max(
            np.linalg.norm(dim_force), 1e-12
        )
        print("no-flow", case, "rel", rel, "dim", dim_force, "nodim", nd_force)
        print("dim finished:", dim_model.calc_is_finished())
        print("nd finished:", nd_model.calc_is_finished())
        print("rel:", rel)
        assert dim_model.calc_is_finished()
        assert nd_model.calc_is_finished()
        assert rel < 1e-10


def compare_with_orifice_flow():
    cases = [
        (0.0, 0.0, 0.0, 0.0, 0.3, -0.2),
        (0.45, -0.25, 0.10, -0.08, 0.6, -0.4),
        (-0.55, 0.20, -0.12, 0.09, -0.7, 0.5),
        (0.65, 0.35, 0.2, -0.15, 0.8, 0.7),
    ]
    for case in cases:
        dim_model, dim_force = _run_dimensional(case)
        cq0, cq1, cq2 = _orifice_coefficients(dim_model)
        nd_model, nd_force = _run_nodim(case, cq0=cq0, cq1=cq1, cq2=cq2)
        rel = np.linalg.norm(nd_force - dim_force) / max(
            np.linalg.norm(dim_force), 1e-12
        )
        print("flow", case, "rel", rel, "dim", dim_force, "nodim", nd_force)
        print("dim finished:", dim_model.calc_is_finished())
        print("nd finished:", nd_model.calc_is_finished())
        print("rel:", rel)
        assert dim_model.calc_is_finished()
        assert nd_model.calc_is_finished()
        assert rel < 3e-3


def compare_thermal_no_orifice_flow():
    cases = [
        (-0.2, 0.15, 0.0, 0.0, 0.0, 0.0),
        (0.35, -0.1, 0.08, -0.04, 0.0, 0.0),
    ]
    for case in cases:
        dim_model, dim_force = _run_dimensional_thermal(case)
        nd_model, nd_force = _run_nodim_thermal(case)
        rel = np.linalg.norm(nd_force - dim_force) / max(
            np.linalg.norm(dim_force), 1e-12
        )
        max_temperature, max_viscosity = _max_thermal_field_delta(dim_model, nd_model)
        print(
            "thermal no-flow",
            case,
            "rel",
            rel,
            "max_temperature",
            max_temperature,
            "max_viscosity",
            max_viscosity,
        )
        print("dim finished:", dim_model.calc_is_finished())
        print("nd finished:", nd_model.calc_is_finished())
        print("rel:", rel)
        assert dim_model.calc_is_finished()
        assert nd_model.calc_is_finished()
        assert rel < 1e-10
        assert max_temperature < 1e-8
        assert max_viscosity < 1e-10


def compare_thermal_with_orifice_flow_branch_specific():
    cases = [
        (0.0, 0.0, 0.0, 0.0, 0.3, -0.2),
        (0.45, -0.25, 0.10, -0.08, 0.6, -0.4),
    ]
    for case in cases:
        dim_model, dim_force = _run_dimensional_thermal(case)
        branch_coefficients = [
            _orifice_coefficients(orifice=orifice)
            for orifice in _all_orifices(dim_model)
        ]
        nd_model, nd_force = _run_nodim_thermal(
            case,
            branch_orifice_coefficients=branch_coefficients,
        )
        rel = np.linalg.norm(nd_force - dim_force) / max(
            np.linalg.norm(dim_force), 1e-12
        )
        max_temperature, max_viscosity = _max_thermal_field_delta(dim_model, nd_model)
        print(
            "thermal flow branch-cq",
            case,
            "rel",
            rel,
            "max_temperature",
            max_temperature,
            "max_viscosity",
            max_viscosity,
        )
        print("dim finished:", dim_model.calc_is_finished())
        print("nd finished:", nd_model.calc_is_finished())
        print("rel:", rel)
        assert dim_model.calc_is_finished()
        assert nd_model.calc_is_finished()
        assert rel < 1e-10
        assert max_temperature < 1e-8
        assert max_viscosity < 1e-10


def test_no_orifice_flow():
    compare_no_orifice_flow()


def test_with_orifice_flow():
    compare_with_orifice_flow()


def test_dimensional_csorifice_stores_nondim_coefficients():
    case = (0.0, 0.0, 0.0, 0.0, 0.3, -0.2)
    model, _ = _run_dimensional(case)
    orifice = model.servovalves[0].simple_models[0]
    cq0, cq1, cq2 = _orifice_coefficients(model)
    expected_cq0, expected_cq1, expected_cq2 = _expected_cso_coefficients()
    assert isinstance(orifice.cq1, float)
    assert orifice.cq1_h2.shape == (len(orifice.position),)
    np.testing.assert_allclose(cq0, expected_cq0, rtol=1e-14, atol=1e-14)
    np.testing.assert_allclose(cq1, expected_cq1, rtol=1e-14, atol=1e-14)
    np.testing.assert_allclose(cq2, expected_cq2, rtol=1e-14, atol=1e-14)
    info = orifice.flow_info(orifice.model)
    assert len(info["flow_params"]) == len(info["flow"])
    for item, legacy in zip(info["flow_params"], info["flow"]):
        assert {
            "position_nondim",
            "position_dim",
            "q_nondim",
            "q_vol",
            "qw",
        }.issubset(item)
        np.testing.assert_allclose(item["q_vol"], item["q_nondim"] * item["qw"])
        np.testing.assert_allclose(legacy, (*item["position_dim"], item["q_vol"]))


def test_thermal_no_orifice_flow():
    compare_thermal_no_orifice_flow()


def test_thermal_with_orifice_flow_branch_specific():
    compare_thermal_with_orifice_flow_branch_specific()


if __name__ == "__main__":
    test_no_orifice_flow()
    test_with_orifice_flow()
    test_thermal_no_orifice_flow()
    test_thermal_with_orifice_flow_branch_specific()
