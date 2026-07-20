import unittest

import numpy as np

from ALB.alb import ALB, NodimALB, nodim_alb
from ALB.physics.bearing import (
    HydrostaticBearing,
    NodimHydrostaticBearing,
    four_pads_bearings,
    nodim_four_pads_bearings,
)
from ALB.config import (
    ALBConfig,
    FPBConfig,
    HydConfig,
    NodimALBConfig,
    NodimOrificeConfig,
    NodimPadConfig,
    PIDConfig,
)
from ALB.control.pid import PID
from ALB.physics.hydraulics import CSOrifice, NodimCSOrifice
from ALB.control.valve import static_sv
from ALB.config import ThermalConfig
from ALB.physics.thermal import NodimThermalHydroBearing, ThermalHydroBearing


def _unit_scale_hyd_config(config_class=HydConfig, **kwargs):
    args = dict(
        miu=1.0,
        c=1.0,
        r=1.0,
        l=2.0,
        ps=1.0,
        rho=1.0,
        freq=1.0 / (2.0 * np.pi),
        x0=-45.0,
        lx=120.0,
        lz=2.0,
        nx=7,
        nz=5,
        e=0.08,
        angle=25.0,
        coe=False,
        max_iter=10,
        error_set=1e-9,
        damp=0.8,
    )
    args.update(kwargs)
    return config_class(**args)


def _thermal_config(args_nodim):
    return ThermalConfig(
        t_in=1.0,
        t_supply=1.0,
        t_ref=1.0,
        beta=0.03,
        k_lub=0.0,
        cp_lub=1.0,
        heat_partition=0.25,
        relax=0.6,
        max_iter=20,
        tol=1e-2,
        coupling="full",
        pressure_backend="skfem",
        args_nodim=args_nodim,
        delta_t_scale=1.0,
    )


def _lambda_and_lr(config):
    lambda_value = (
        1.5
        * config.miu
        * config.w
        * 2.0
        * np.pi
        / 60.0
        * config.l**2
        / config.ps
        / config.c**2
    )
    lr = config.l / (2.0 * config.r)
    return lambda_value, lr


class TestNodimInterfaces(unittest.TestCase):
    def test_csorifice_inherits_nodim_csorifice(self):
        self.assertTrue(issubclass(CSOrifice, NodimCSOrifice))

    def test_nodim_bearing_with_nodim_csorifice_solves(self):
        bearing = NodimHydrostaticBearing(
            lambda_value=1.2,
            lr=1.0,
            x0=0.0,
            lx=90.0,
            lz=2.0,
            nx=5,
            nz=3,
            e=0.05,
            angle=0.0,
            coe=False,
            max_iter=3,
            error_set=1e-5,
        )
        orifice = NodimCSOrifice(
            position=np.array([[0.5, 0.5]]),
            cq0=0.2,
            cq1=1.0,
            cq2=0.1,
        )
        orifice.xv = 0.5
        bearing.add_simple_model(orifice)

        bearing.init()
        bearing.input(np.array([0.05, 0.0]), np.array([0.0, 0.0]), nodim=True)
        out = bearing.output(nodim=True)

        self.assertIn("force", out)
        self.assertTrue(np.all(np.isfinite(out["force"])))
        self.assertTrue(np.isfinite(out["friction"]))
        self.assertIsNotNone(orifice.qn)
        info = orifice.flow_info(bearing.main_model)
        self.assertEqual(len(info["flow_params"]), 1)
        item = info["flow_params"][0]
        self.assertTrue(
            {
                "position_nondim",
                "position_dim",
                "q_nondim",
                "q_vol",
                "qw",
            }.issubset(item)
        )
        np.testing.assert_allclose(item["q_vol"], item["q_nondim"] * item["qw"])
        np.testing.assert_allclose(
            info["flow"][0], (*item["position_dim"], item["q_vol"])
        )

    def test_nodim_alb_factory_smoke(self):
        cfg = NodimALBConfig(
            pad_config=NodimPadConfig(
                lambda_value=1.2,
                lr=1.0,
                lx=90.0,
                lz=2.0,
                nx=5,
                nz=3,
                coe=False,
                max_iter=3,
                error_set=1e-5,
            ),
            orifice_config=NodimOrificeConfig(
                position=np.array([[0.5, 0.5]]),
                cq0=0.2,
                cq1=1.0,
                cq2=0.1,
            ),
            controller_config=PIDConfig(),
            servo="static",
        )
        alb = nodim_alb(cfg)

        self.assertIsInstance(alb, NodimALB)
        self.assertAlmostEqual(alb.pads[0].main_model.args["lambda"], 1.2)
        alb.init()
        alb.input(np.array([0.05, 0.0]), np.array([0.0, 0.0]), t=0.0, nodim=True)
        out = alb.output(nodim=True)

        self.assertIn("force", out)
        self.assertTrue(np.all(np.isfinite(out["force"])))
        self.assertTrue(np.isfinite(out["friction"]))

    def test_nodim_alb_config_from_dict_builds_config_only(self):
        cfg = NodimALBConfig.from_dict(
            dict(
                lambda_value=1.2,
                lr=1.0,
                lx=90.0,
                lz=2.0,
                nx=5,
                nz=3,
                position=np.array([[0.5, 0.5]]),
                cq0=0.2,
                cq1=1.0,
                cq2=0.1,
                coe=False,
                max_iter=3,
                error_set=1e-5,
                servo="static",
            )
        )

        alb = nodim_alb(cfg)

        self.assertIsInstance(alb, NodimALB)
        self.assertEqual(cfg.pad_config.nx, 5)
        self.assertEqual(cfg.orifice_config.position.shape, (1, 2))

    def test_nodim_alb_rejects_dimensional_scale_inputs(self):
        cfg = NodimALBConfig()
        cfg.servo = "static"

        with self.assertRaisesRegex(ValueError, "dimensional pad parameters: c"):
            nodim_alb(
                lambda_value=1.2,
                lr=1.0,
                lx=90.0,
                lz=2.0,
                position=np.array([[0.5, 0.5]]),
                cq0=0.2,
                cq1=1.0,
                cq2=0.1,
                alb_config=cfg,
                c=80e-6,
            )

        dimensional_cfg = ALBConfig(c=80e-6, w=3000.0)
        with self.assertRaisesRegex(ValueError, "ALBConfig.c/w"):
            nodim_alb(
                lambda_value=1.2,
                lr=1.0,
                lx=90.0,
                lz=2.0,
                position=np.array([[0.5, 0.5]]),
                cq0=0.2,
                cq1=1.0,
                cq2=0.1,
                alb_config=dimensional_cfg,
            )

    def test_nodim_pressure_matches_dimensional_pressure_with_degree_angles(self):
        hyd_config = _unit_scale_hyd_config(
            miu=0.0195,
            c=80e-6,
            r=0.04,
            l=0.08,
            ps=10e6,
            rho=872.0,
            freq=50.0,
            max_iter=8,
        )
        lambda_value, lr = _lambda_and_lr(hyd_config)

        dimensional = HydrostaticBearing(hyd_config)
        nodim = NodimHydrostaticBearing(
            lambda_value=lambda_value,
            lr=lr,
            x0=hyd_config.x0,
            lx=hyd_config.lx,
            lz=hyd_config.lz,
            nx=hyd_config.nx,
            nz=hyd_config.nz,
            e=hyd_config.e,
            angle=hyd_config.angle_rad,
            coe=hyd_config.coe,
            p_set=hyd_config.p_set,
            reynold=hyd_config.reynold,
            max_iter=hyd_config.max_iter,
            error_set=hyd_config.error_set,
            damp=hyd_config.damp,
        )

        uxy = np.array([0.04, -0.03])
        uxyt = np.array([0.0, 0.0])

        dimensional.init()
        dimensional.input(uxy, uxyt, nodim=True)
        dimensional.output(nodim=True)

        nodim.init()
        nodim.input(uxy, uxyt, nodim=True)
        nodim.output(nodim=True)

        np.testing.assert_allclose(
            nodim.main_model.args["x_lim"],
            dimensional.main_model.args["x_lim"],
            rtol=0.0,
            atol=1e-14,
        )
        np.testing.assert_allclose(
            nodim.postprocess.p,
            dimensional.postprocess.p,
            rtol=1e-8,
            atol=1e-10,
        )

    def test_nodim_thermal_bearing_force_matches_dimensional_force(self):
        hyd_config = _unit_scale_hyd_config()
        lambda_value, lr = _lambda_and_lr(hyd_config)

        dimensional = ThermalHydroBearing(
            HydrostaticBearing(hyd_config), _thermal_config(args_nodim=False)
        )
        nodim = NodimThermalHydroBearing(
            NodimHydrostaticBearing(
                lambda_value=lambda_value,
                lr=lr,
                x0=hyd_config.x0,
                lx=hyd_config.lx,
                lz=hyd_config.lz,
                nx=hyd_config.nx,
                nz=hyd_config.nz,
                e=hyd_config.e,
                angle=hyd_config.angle_rad,
                coe=hyd_config.coe,
                p_set=hyd_config.p_set,
                reynold=hyd_config.reynold,
                max_iter=hyd_config.max_iter,
                error_set=hyd_config.error_set,
                damp=hyd_config.damp,
            ),
            _thermal_config(args_nodim=True),
        )

        uxy = np.array([0.04, -0.03])
        uxyt = np.array([0.0, 0.0])

        dimensional.init()
        dimensional.input(uxy, uxyt, nodim=True)
        dim_out = dimensional.output(calc=True, nodim=True)

        nodim.init()
        nodim.input(uxy, uxyt, nodim=True)
        nodim_out = nodim.output(calc=True, nodim=True)

        self.assertTrue(dim_out["thermal_converged"])
        self.assertTrue(nodim_out["thermal_converged"])
        np.testing.assert_allclose(
            nodim_out["force"], dim_out["force"], rtol=1e-7, atol=1e-9
        )
        np.testing.assert_allclose(
            nodim_out["friction"], dim_out["friction"], rtol=1e-7, atol=1e-9
        )

    def test_nodim_thermal_alb_force_matches_dimensional_alb_force(self):
        pad_config = _unit_scale_hyd_config(FPBConfig, lx=90.0, nx=5, nz=3)
        lambda_value, lr = _lambda_and_lr(pad_config)

        dim_pads = [
            ThermalHydroBearing(pad, _thermal_config(args_nodim=False))
            for pad in four_pads_bearings(pad_config).values()
        ]
        nodim_pads = [
            NodimThermalHydroBearing(pad, _thermal_config(args_nodim=True))
            for pad in nodim_four_pads_bearings(
                lambda_value=lambda_value,
                lr=lr,
                lx=pad_config.lx,
                lz=pad_config.lz,
                nx=pad_config.nx,
                nz=pad_config.nz,
                bias=pad_config.bias,
                e=pad_config.e,
                angle=pad_config.angle_rad,
                coe=pad_config.coe,
                p_set=pad_config.p_set,
                reynold=pad_config.reynold,
                max_iter=pad_config.max_iter,
                error_set=pad_config.error_set,
                damp=pad_config.damp,
            ).values()
        ]

        alb_config = ALBConfig(
            pad_config=pad_config,
            controller_config=PIDConfig(kp=0.0, ki=0.0, kd=0.0),
            servo="static",
            switch=False,
        )
        nodim_alb_config = NodimALBConfig(
            controller_config=PIDConfig(kp=0.0, ki=0.0, kd=0.0),
            servo="static",
            switch=False,
        )
        dim_alb = ALB(
            dim_pads,
            [static_sv(alb_config.dt), static_sv(alb_config.dt)],
            controller=PID(alb_config.controller_config),
            alb_config=alb_config,
        )
        nodim_alb_model = NodimALB(
            nodim_pads,
            [static_sv(nodim_alb_config.dt), static_sv(nodim_alb_config.dt)],
            controller=PID(nodim_alb_config.controller_config),
            alb_config=nodim_alb_config,
        )

        uxy = np.array([0.03, -0.02])
        uxyt = np.array([0.0, 0.0])

        dim_alb.init()
        dim_alb.input(uxy, uxyt, t=0.0, nodim=True)
        dim_out = dim_alb.output(nodim=True)

        nodim_alb_model.init()
        nodim_alb_model.input(uxy, uxyt, t=0.0, nodim=True)
        nodim_out = nodim_alb_model.output(nodim=True)

        np.testing.assert_allclose(
            nodim_out["force"], dim_out["force"], rtol=1e-7, atol=1e-9
        )
        np.testing.assert_allclose(
            nodim_out["friction"], dim_out["friction"], rtol=1e-7, atol=1e-9
        )


if __name__ == "__main__":
    unittest.main()
