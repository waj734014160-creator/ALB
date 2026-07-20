import copy
import unittest
from pathlib import Path

import matplotlib
from matplotlib.collections import QuadMesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from ALB.systems.alb import ALB, ALBBuilder
from ALB.core import TimeIterDt
from ALB.physics.bearing import HydrostaticBearing, four_pads_bearings
from ALB.config import (
    ALBConfig,
    CsoArgs,
    FPBConfig,
    HydConfig,
    OrificeConfig,
    PIDConfig,
    ServoConfig,
    TankConfig,
    ThermalConfig,
)
from ALB.control.pid import PID
from ALB.dynamics.orbit import EllipseTrack
from ALB.dynamics.orbit import test_bearing_orbit as run_bearing_orbit
from ALB.physics.hydraulics import CSOrifice
from ALB.control.valve import moog_servovalve
from ALB.physics.thermal import (
    ThermalHydroBearing,
    ThermalPostProcess,
    ViscosityFilmNode,
)


def _make_bearing_and_thermal(coupling="full", pressure_backend="skfem"):
    cfg = HydConfig(
        nx=19,
        nz=11,
        e=0.3,
        angle=30.0,
        max_iter=200,
        error_set=1e-10,
        iter_method="newton",
    )
    pad = HydrostaticBearing(cfg)
    tcfg = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        relax=0.5,
        max_iter=20,
        tol=1e-2,
        coupling=coupling,
        pressure_backend=pressure_backend,
        args_nodim=False,
    )
    model = ThermalHydroBearing(pad, tcfg)
    model.init()
    model.input(np.array([0.3 * cfg.c, 0.0]), np.array([0.0, 0.0]))
    return cfg, pad, tcfg, model


class TestThermalHydroBearing(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _set_artifact_dir(self, tmp_path):
        self.artifact_dir = tmp_path

    def _run_and_check(self, coupling):
        cfg, pad, tcfg, model = _make_bearing_and_thermal(coupling)

        for node in pad.main_model.nodes.values():
            self.assertIsInstance(node, ViscosityFilmNode)

        out = model.output(calc=True, nodim=True)

        self.assertIn("force", out)
        self.assertIn("t_eff", out)
        self.assertIn("viscosity", out)
        self.assertIn("thermal_converged", out)
        self.assertIn("temperature_film", out)
        self.assertIn("viscosity_field", out)

        self.assertEqual(model._thermal_grid.n_film_nodes, len(pad.main_model.nodes))
        mesh_data = model.thermal_model.build_mesh(pad.main_model, model._thermal_grid)
        self.assertIs(mesh_data["grid"], model._thermal_grid)

        # Thermal iteration must converge within max_iter
        self.assertTrue(
            out["thermal_converged"],
            f"Thermal iteration did not converge within {tcfg.max_iter} iterations "
            f"(stopped at iter {out['thermal_iterations']})",
        )
        self.assertLess(
            out["thermal_iterations"],
            tcfg.max_iter,
            f"Thermal iteration reached max_iter={tcfg.max_iter}, "
            f"convergence may be insufficient",
        )

        # Pressure solver must converge (final_iter < max_iter)
        self.assertLess(
            pad.final_iter,
            cfg.max_iter,
            f"Pressure solver reached max_iter={cfg.max_iter} "
            f"(final_iter={pad.final_iter}), FB cavitation may not have converged",
        )

        self.assertTrue(np.isfinite(out["t_eff"]))
        self.assertGreater(out["t_eff"], tcfg.t_in)

        vf = out["viscosity_field"]
        self.assertGreater(float(np.std(vf)), 0.0)

        miu_ratios = np.array([n.miu_ratio for n in pad.main_model.nodes.values()])
        self.assertGreater(float(np.std(miu_ratios)), 0.0)
        self.assertAlmostEqual(pad.main_model.args["miu0"], model._miu0)
        self.assertAlmostEqual(pad.main_model.args["miu"], model._miu0)

        # Pressure must be non-negative everywhere (FB cavitation constraint).
        # Allow small numerical residual from FB complementarity iterations.
        pressure = np.array([n.p for n in pad.main_model.nodes.values()])
        self.assertGreater(float(np.max(pressure)), 0.0)
        p_min = float(np.min(pressure))
        fb_tol = -5e-6
        self.assertGreaterEqual(
            p_min,
            fb_tol,
            f"Negative pressure detected: p_min={p_min:.6e}. "
            f"FB cavitation did not fully enforce p>=0. "
            f"Consider increasing HydConfig.max_iter (current={cfg.max_iter}).",
        )
        if p_min < 0:
            print(
                f"  [WARN] Small numerical negative pressure: p_min={p_min:.2e} "
                f"(within FB tolerance {fb_tol:.0e})"
            )

        return cfg, pad, tcfg, model, out

    def test_full_coupling(self):
        """Full-field coupling: per-node viscosity in both Reynolds and thermal."""
        self._run_and_check("full")

    def test_half_coupling(self):
        """Half-field coupling: per-node viscosity in Reynolds, mean in thermal."""
        self._run_and_check("half")

    def test_full_vs_half_differ(self):
        """Full and half coupling should give different temperature results."""
        _, _, _, _, out_full = self._run_and_check("full")
        _, _, _, _, out_half = self._run_and_check("half")

        t_full = out_full["t_eff"]
        t_half = out_half["t_eff"]
        # They should differ (same bearing params but different coupling)
        self.assertNotAlmostEqual(
            t_full,
            t_half,
            places=4,
            msg="Full and half coupling should produce "
            "different effective temperatures",
        )

    def test_legacy_pressure_backend_rejected(self):
        """The legacy h_eff pressure branch is kept only as internal reference."""
        with self.assertRaisesRegex(ValueError, "only supports 'skfem'"):
            _make_bearing_and_thermal(coupling="full", pressure_backend="legacy")

    def test_thermal_grid_refreshes_after_input_geometry_change(self):
        cfg = HydConfig(
            nx=11,
            nz=7,
            e=0.1,
            angle=0.0,
            max_iter=80,
            error_set=1e-8,
            iter_method="newton",
        )
        pad = HydrostaticBearing(cfg)
        tcfg = ThermalConfig(
            t_in=40.0,
            beta=0.03,
            relax=0.5,
            max_iter=1,
            tol=1e-2,
            coupling="full",
            pressure_backend="skfem",
            args_nodim=False,
            heat_partition=0.0,
            supg=False,
        )
        model = ThermalHydroBearing(pad, tcfg)
        model.init()

        model.input(np.array([0.1 * cfg.c, 0.0]), np.array([0.0, 0.0]))
        model.output(calc=True, nodim=True)
        current_h_1 = np.array([n.h for n in pad.main_model.nodes.values()]) * cfg.c
        grid_h_1 = model._thermal_grid.h_grid[
            model._thermal_grid.ix, model._thermal_grid.iz
        ]
        np.testing.assert_allclose(grid_h_1, current_h_1, rtol=0.0, atol=1e-12)

        model.input(np.array([0.6 * cfg.c, 0.0]), np.array([0.0, 0.0]))
        model.output(calc=True, nodim=True)
        current_h_2 = np.array([n.h for n in pad.main_model.nodes.values()]) * cfg.c
        grid_h_2 = model._thermal_grid.h_grid[
            model._thermal_grid.ix, model._thermal_grid.iz
        ]
        np.testing.assert_allclose(grid_h_2, current_h_2, rtol=0.0, atol=1e-12)
        self.assertGreater(float(np.max(np.abs(grid_h_2 - grid_h_1))), 1e-8)

    def test_comparison_plot(self):
        """Generate comparison plots for full vs half coupling."""
        _, pad_f, _, _, out_f = self._run_and_check("full")
        _, pad_h, _, _, out_h = self._run_and_check("half")

        plot_dir = self.artifact_dir / "thermal_plots"
        plot_dir.mkdir(parents=True, exist_ok=True)

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))

        for col, (label, pad, out) in enumerate(
            [
                ("Full Coupling", pad_f, out_f),
                ("Half Coupling", pad_h, out_h),
            ]
        ):
            nodes = list(pad.main_model.nodes.values())
            px = np.array([n.coords[0] for n in nodes])
            pz = np.array([n.coords[1] for n in nodes])
            pp = np.array([n.p for n in nodes]) * pad.main_model.args["ps"]

            ax = axes[0, col]
            c1 = ax.tricontourf(px, pz, pp, levels=20, cmap="viridis")
            fig.colorbar(c1, ax=ax, label="Pa")
            ax.set_title(f"Pressure ({label})")
            ax.set_xlabel("x (rad)")
            ax.set_ylabel("z")

            ax = axes[1, col]
            tx = np.asarray(out["temperature_x"])
            tz = np.asarray(out["temperature_z"])
            temp = np.asarray(out["temperature"])
            c2 = ax.tricontourf(tx, tz, temp, levels=20, cmap="inferno")
            fig.colorbar(c2, ax=ax, label="°C")
            ax.set_title(f"Temperature ({label})")
            ax.set_xlabel("x (m)")
            ax.set_ylabel("z (m)")

        # Difference column
        nodes_f = list(pad_f.main_model.nodes.values())
        px = np.array([n.coords[0] for n in nodes_f])
        pz = np.array([n.coords[1] for n in nodes_f])
        vf_f = out_f["viscosity_field"]
        vf_h = out_h["viscosity_field"]

        ax = axes[0, 2]
        c3 = ax.tricontourf(px, pz, vf_f, levels=20, cmap="coolwarm")
        fig.colorbar(c3, ax=ax, label="Pa·s")
        ax.set_title("Viscosity Field (Full)")
        ax.set_xlabel("x (rad)")
        ax.set_ylabel("z")

        ax = axes[1, 2]
        c4 = ax.tricontourf(px, pz, vf_h, levels=20, cmap="coolwarm")
        fig.colorbar(c4, ax=ax, label="Pa·s")
        ax.set_title("Viscosity Field (Half)")
        ax.set_xlabel("x (rad)")
        ax.set_ylabel("z")

        fig.suptitle(
            f"Full: T_eff={out_f['t_eff']:.2f}°C, miu={out_f['viscosity']:.5f}  |  "
            f"Half: T_eff={out_h['t_eff']:.2f}°C, miu={out_h['viscosity']:.5f}",
            fontsize=11,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(plot_dir / "full_vs_half_coupling.png", dpi=160)
        plt.close(fig)

    def test_transient_temperature_converges_cycle_to_cycle(self):
        cfg = HydConfig(
            nx=11,
            nz=7,
            e=0.2,
            angle=20.0,
            max_iter=80,
            error_set=1e-8,
            iter_method="newton",
            damp=0.6,
        )
        pad = HydrostaticBearing(cfg)
        dt = 1.0 / (20.0 * 6)
        tcfg = ThermalConfig(
            t_in=40.0,
            beta=0.03,
            relax=0.5,
            max_iter=8,
            tol=2e-2,
            coupling="full",
            args_nodim=False,
            transient_enabled=True,
            dt=dt,
        )
        model = ThermalHydroBearing(pad, tcfg)
        model.init()

        ti = TimeIterDt(dt=dt, num=24)
        et = EllipseTrack(
            a=0.08 * cfg.c, b=0.04 * cfg.c, freq=20.0, a0=0.15 * cfg.c, b0=0.0
        )
        u, v, a = et.generate_track(ti)

        t_eff_trace = []
        for t, ui, vi, ai in zip(ti.t_list, u, v, a):
            model.input(uxy=ui, uxyt=vi, uxytt=ai, t=t, nodim=False)
            out = model.output(calc=True, nodim=False)
            t_eff_trace.append(float(out["t_eff"]))

        t_eff_trace = np.asarray(t_eff_trace, dtype=float)
        cycle_1 = t_eff_trace[6:12]
        cycle_2 = t_eff_trace[12:18]
        cycle_3 = t_eff_trace[18:24]

        err_12 = float(np.max(np.abs(cycle_2 - cycle_1)))
        err_23 = float(np.max(np.abs(cycle_3 - cycle_2)))

        self.assertLess(err_23, err_12)
        self.assertLess(err_23, 0.5)

    def test_transient_thermal_bearing_supports_kc_identification(self):
        cfg = HydConfig(
            nx=11,
            nz=7,
            e=0.15,
            angle=10.0,
            max_iter=80,
            error_set=1e-8,
            iter_method="newton",
            damp=0.6,
        )
        pad = HydrostaticBearing(cfg)
        dt = 1.0 / (20.0 * 8)
        tcfg = ThermalConfig(
            t_in=40.0,
            beta=0.03,
            relax=0.5,
            max_iter=6,
            tol=2e-2,
            coupling="full",
            args_nodim=False,
            transient_enabled=True,
            dt=dt,
        )
        model = ThermalHydroBearing(pad, tcfg)
        ti = TimeIterDt(dt=dt, num=24)
        et = EllipseTrack(
            a=0.06 * cfg.c, b=0.03 * cfg.c, freq=20.0, a0=0.12 * cfg.c, b0=0.0
        )

        result = run_bearing_orbit(ti, model, et, repeat=1)

        self.assertIn("hkc", result)
        self.assertTrue(
            np.all(np.isfinite(np.asarray(result["hkc"]["k"], dtype=float)))
        )
        self.assertTrue(
            np.all(np.isfinite(np.asarray(result["hkc"]["c"], dtype=float)))
        )

    def test_orifice_cooling_correction(self):
        """With orifices, T_eff should be lower than without (extra cooling flow)."""
        # --- Without orifices ---
        _, _, _, _, out_no_orifice = self._run_and_check("full")

        # --- With orifices ---
        cfg = HydConfig(
            nx=19,
            nz=11,
            e=0.3,
            angle=30.0,
            ps=3e6,
            max_iter=200,
            error_set=1e-8,
            iter_method="newton",
            damp=0.6,
        )
        pad = HydrostaticBearing(cfg)
        # Add 4 orifices at symmetric positions
        positions = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)]
        pad.add_orifices(positions, r=1e-3, cd=0.3)

        tcfg = ThermalConfig(
            t_in=40.0,
            beta=0.03,
            relax=0.5,
            max_iter=20,
            tol=1e-2,
            coupling="full",
            args_nodim=False,
            t_supply=25.0,
        )
        model = ThermalHydroBearing(pad, tcfg)
        model.init()
        model.input(np.array([0.3 * cfg.c, 0.0]), np.array([0.0, 0.0]))
        out_orifice = model.output(calc=True, nodim=True)

        self.assertIn("q_orifice_total", out_orifice)
        q_total = out_orifice["q_orifice_total"]
        self.assertGreater(q_total, 0.0, "Orifice total flow should be positive")
        public_nondim = []
        public_vol = []
        for simple_model in pad.simple_models:
            self.assertTrue(hasattr(simple_model, "flow_info"))
            info = simple_model.flow_info(pad.main_model)
            for item, legacy in zip(info["flow_params"], info["flow"]):
                self.assertIn("position_nondim", item)
                self.assertIn("position_dim", item)
                self.assertIn("q_nondim", item)
                self.assertIn("q_vol", item)
                self.assertIn("qw", item)
                np.testing.assert_allclose(
                    item["q_vol"], item["q_nondim"] * item["qw"]
                )
                np.testing.assert_allclose(legacy[:2], item["position_dim"])
                np.testing.assert_allclose(legacy[2], item["q_vol"])
                public_nondim.append((*item["position_nondim"], item["q_nondim"]))
                public_vol.append(item["q_vol"])
        np.testing.assert_allclose(model._collect_orifice_info(), public_nondim)
        np.testing.assert_allclose(q_total, sum(abs(value) for value in public_vol))
        np.testing.assert_allclose(
            out_orifice["q_orifice_total_nondim"],
            sum(abs(item[2]) for item in public_nondim),
        )
        self.assertEqual(q_total, out_orifice["q_orifice_total_vol"])

        # With extra cooling flow, T_eff should typically be lower
        t_no = out_no_orifice["t_eff"]
        t_with = out_orifice["t_eff"]
        print(f"\n[No Orifice]  T_eff={t_no:.2f}°C")
        print(f"[With Orifice] T_eff={t_with:.2f}°C  Q_orifice={q_total:.2e} m³/s")
        self.assertLess(
            t_with,
            t_no,
            f"Orifice cooling should reduce T_eff: "
            f"no_orifice={t_no:.3f}, with_orifice={t_with:.3f}",
        )

    def test_thermal_postprocess_supports_quad_fields_save_and_lines(self):
        _, pad, _, model, out = self._run_and_check("full")

        self.assertIsInstance(model.post_process, ThermalPostProcess)
        post = model.post_process

        pressure_field = post.pressure_field
        temperature_field = post.temperature_field
        viscosity_field = post.viscosity_field

        self.assertEqual(post.postprocess_result["mesh_type"], "quadrilateral")
        self.assertEqual(pressure_field.shape, temperature_field.shape)
        self.assertEqual(pressure_field.shape, viscosity_field.shape)
        self.assertEqual(
            pressure_field.shape,
            (pad.main_model.args["nx"] + 1, pad.main_model.args["nz"] + 1),
        )
        self.assertTrue(np.allclose(pressure_field, out["pressure_field"]))
        self.assertTrue(np.allclose(temperature_field, out["temperature_field"]))

        fig, ax = post.plot_temperature_field(show=False)
        self.assertTrue(any(isinstance(item, QuadMesh) for item in ax.collections))
        plt.close(fig)

        fig, ax = post.plot_line("viscosity", axis="x", show=False)
        self.assertEqual(len(ax.lines), 1)
        plt.close(fig)

        save_dir = post.save(self.artifact_dir / "thermal_postprocess")
        self.assertTrue((save_dir / "pressure_field.csv").exists())
        self.assertTrue((save_dir / "temperature_field.csv").exists())
        self.assertTrue((save_dir / "viscosity_field.csv").exists())
        self.assertTrue((save_dir / "thermal_fields.npz").exists())
        self.assertTrue((save_dir / "summary.json").exists())

    def test_orifice_plots(self):
        """Generate pressure / temperature / viscosity contour plots with orifices."""
        # --- Without orifices ---
        _, pad_no, _, _, out_no = self._run_and_check("full")

        # --- With orifices ---
        cfg = HydConfig(
            nx=19,
            nz=11,
            e=0.3,
            angle=30.0,
            ps=3e6,
            max_iter=200,
            error_set=1e-8,
            iter_method="newton",
            damp=0.6,
        )
        pad_ori = HydrostaticBearing(cfg)
        positions = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)]
        pad_ori.add_orifices(positions, r=1e-3, cd=0.3)

        tcfg = ThermalConfig(
            t_in=40.0,
            beta=0.03,
            relax=0.5,
            max_iter=20,
            tol=1e-2,
            coupling="full",
            args_nodim=False,
            t_supply=25.0,
        )
        model = ThermalHydroBearing(pad_ori, tcfg)
        model.init()
        model.input(np.array([0.3 * cfg.c, 0.0]), np.array([0.0, 0.0]))
        out_ori = model.output(calc=True, nodim=True)

        plot_dir = self.artifact_dir / "thermal_plots"
        plot_dir.mkdir(parents=True, exist_ok=True)

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))

        # Helper to extract film-node arrays
        def _film_arrays(pad, out):
            nodes = list(pad.main_model.nodes.values())
            px = np.array([n.coords[0] for n in nodes])
            pz = np.array([n.coords[1] for n in nodes])
            pp = np.array([n.p for n in nodes]) * pad.main_model.args["ps"]
            vf = np.asarray(out["viscosity_field"])
            return px, pz, pp, vf

        # Row labels
        row_labels = ["No Orifice", "With Orifice"]

        for row, (label, pad, out) in enumerate(
            [
                ("No Orifice", pad_no, out_no),
                ("With Orifice", pad_ori, out_ori),
            ]
        ):
            px, pz, pp, vf = _film_arrays(pad, out)

            # Pressure
            ax = axes[row, 0]
            c1 = ax.tricontourf(px, pz, pp, levels=20, cmap="viridis")
            fig.colorbar(c1, ax=ax, label="Pa")
            ax.set_title(f"Pressure ({label})")
            ax.set_xlabel("x (rad)")
            ax.set_ylabel("z")

            # Temperature
            ax = axes[row, 1]
            tx = np.asarray(out["temperature_x"])
            tz = np.asarray(out["temperature_z"])
            temp = np.asarray(out["temperature"])
            c2 = ax.tricontourf(tx, tz, temp, levels=20, cmap="inferno")
            fig.colorbar(c2, ax=ax, label="°C")
            ax.set_title(f"Temperature ({label})")
            ax.set_xlabel("x (m)")
            ax.set_ylabel("z (m)")

            # Viscosity
            ax = axes[row, 2]
            c3 = ax.tricontourf(px, pz, vf, levels=20, cmap="coolwarm")
            fig.colorbar(c3, ax=ax, label="Pa·s")
            ax.set_title(f"Viscosity ({label})")
            ax.set_xlabel("x (rad)")
            ax.set_ylabel("z")

        fig.suptitle(
            f"No Orifice: T_eff={out_no['t_eff']:.2f}°C, miu={out_no['viscosity']:.5f}  |  "
            f"With Orifice: T_eff={out_ori['t_eff']:.2f}°C, miu={out_ori['viscosity']:.5f}, "
            f"Q_ori={out_ori['q_orifice_total']:.2e} m³/s",
            fontsize=11,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(plot_dir / "orifice_thermal_comparison.png", dpi=160)
        plt.close(fig)

        print(
            f"\n[No Orifice]   T_eff={out_no['t_eff']:.2f}°C  "
            f"miu={out_no['viscosity']:.6f}"
        )
        print(
            f"[With Orifice] T_eff={out_ori['t_eff']:.2f}°C  "
            f"miu={out_ori['viscosity']:.6f}  "
            f"Q_ori={out_ori['q_orifice_total']:.2e}"
        )
        print(f"  Plot saved to {plot_dir / 'orifice_thermal_comparison.png'}")

    def test_csorifice_thermal(self):
        """CSOrifice with thermal coupling: single pad with servo-controlled orifices."""
        cfg = HydConfig(
            nx=19,
            nz=11,
            e=0.3,
            angle=30.0,
            ps=3e6,
            max_iter=200,
            error_set=1e-8,
            iter_method="newton",
            damp=0.6,
        )
        pad = HydrostaticBearing(cfg)

        # Add CSOrifice with 3 positions
        positions = np.array([[0.5, 0.25 + 0.25 * i] for i in range(3)])
        cso_args = CsoArgs()
        cso = CSOrifice(position=positions, ps=3e6, cso_args=cso_args)
        cso.xv = 0.5  # Set servo valve opening
        pad.add_simple_model(cso)

        tcfg = ThermalConfig(
            t_in=40.0,
            beta=0.03,
            relax=0.5,
            max_iter=20,
            tol=1e-2,
            coupling="full",
            args_nodim=False,
            t_supply=25.0,
        )
        model = ThermalHydroBearing(pad, tcfg)
        model.init()
        model.input(np.array([0.3 * cfg.c, 0.0]), np.array([0.0, 0.0]))
        out = model.output(calc=True, nodim=True)

        # Basic output checks
        self.assertIn("force", out)
        self.assertIn("t_eff", out)
        self.assertIn("viscosity", out)
        self.assertIn("q_orifice_total", out)
        self.assertTrue(out["thermal_converged"])
        self.assertTrue(np.isfinite(out["t_eff"]))

        # CSOrifice should generate flow
        q_total = out["q_orifice_total"]
        self.assertGreater(q_total, 0.0, "CSOrifice total flow should be positive")

        # Temperature should be lower than no-orifice case
        _, _, _, _, out_no = self._run_and_check("full")
        self.assertLess(
            out["t_eff"],
            out_no["t_eff"],
            "CSOrifice cooling should reduce T_eff",
        )

        print(
            f"\n[CSOrifice] T_eff={out['t_eff']:.2f}°C  "
            f"miu={out['viscosity']:.6f}  Q_ori={q_total:.2e}"
        )


class TestALBThermal(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _set_artifact_dir(self, tmp_path):
        self.artifact_dir = tmp_path

    """Test ThermalHydroBearing wrapped around a full ALB system's pads."""

    def test_alb_with_csorifice_thermal(self):
        """Build ALB with CSOrifice, wrap each pad in ThermalHydroBearing,
        verify input/output pipeline works end-to-end."""

        # --- Build four-pad bearing with CSOrifice ---
        pad_cfg = FPBConfig(
            nx=15,
            nz=9,
            e=0.0,
            lx=80,
            ps=3e6,
            freq=50,
            max_iter=200,
            error_set=1e-8,
            iter_method="newton",
            damp=0.6,
            coe=False,
        )
        pads_dict = four_pads_bearings(pad_cfg)

        # Create CSOrifice pairs (soa = supply, sob = tank)
        positions = np.array([[0.5, 0.25 + 0.25 * i] for i in range(3)])
        cso_args = CsoArgs()

        soa_y = CSOrifice(position=positions, ps=3e6, cso_args=cso_args)
        sob_y = CSOrifice(position=positions, ps=0, p0=3e6, cso_args=cso_args)
        soa_x = copy.deepcopy(soa_y)
        sob_x = copy.deepcopy(sob_y)

        # Wire orifices to pads
        pads_dict["up"].add_simple_model(soa_y)
        pads_dict["down"].add_simple_model(sob_y)
        pads_dict["right"].add_simple_model(soa_x)
        pads_dict["left"].add_simple_model(sob_x)

        # Create servovalves and wire orifices
        sv_x = moog_servovalve(6.667e-4, 0.0)
        sv_y = moog_servovalve(6.667e-4, 0.0)
        sv_x.add_simple_model([soa_x, sob_x])
        sv_y.add_simple_model([soa_y, sob_y])

        # Create controller
        pid_cfg = PIDConfig(kp=0.0, ki=0.0, kd=0.0)
        controller = PID(pid_cfg)

        # Build ALB
        alb_cfg = ALBConfig(
            pad_config=pad_cfg,
            servo_config=ServoConfig(),
            orifice_config=OrificeConfig(ps=3e6),
            c=pad_cfg.c,
            w=pad_cfg.w,
        )
        pads_list = list(pads_dict.values())
        alb = ALB(pads_list, [sv_x, sv_y], controller=controller, alb_config=alb_cfg)

        # --- Wrap each pad with ThermalHydroBearing ---
        tcfg = ThermalConfig(
            t_in=40.0,
            beta=0.03,
            relax=0.5,
            max_iter=20,
            tol=1e-2,
            coupling="full",
            args_nodim=False,
            t_supply=25.0,
        )
        thermal_pads = []
        for pad in alb.pads:
            tpad = ThermalHydroBearing(pad, tcfg)
            thermal_pads.append(tpad)

        # --- Init and compute ---
        alb.init()
        c = pad_cfg.c
        uxy = np.array([0.2 * c, 0.1 * c])  # dimensional displacement
        uxyt = np.array([0.0, 0.0])
        t = 0.0

        # Test ALB input/output
        alb.input(uxy=uxy, uxyt=uxyt, t=t)

        # Set xv for CSOrifices (simulate servo output)
        xv_val = 0.3
        for cso in [soa_y, sob_y, soa_x, sob_x]:
            cso.input(xv=xv_val)

        # Standard ALB output (without thermal wrapper)
        out_alb = alb.output(nodim=True)
        self.assertIn("force", out_alb)
        force = out_alb["force"]
        self.assertEqual(len(force), 2)
        self.assertTrue(np.all(np.isfinite(force)))

        # --- Now test individual thermal pad outputs ---
        # Re-init and set positions
        alb.init()
        alb.input(uxy=uxy, uxyt=uxyt, t=t)
        for cso in [soa_y, sob_y, soa_x, sob_x]:
            cso.input(xv=xv_val)

        # Run thermal on one pad (up)
        thermal_up = thermal_pads[0]
        thermal_up.init()
        pad_up = alb.pads[0]
        thermal_up.input(uxy=uxy, uxyt=uxyt)
        out_thermal = thermal_up.output(calc=True, nodim=True)

        self.assertIn("force", out_thermal)
        self.assertIn("t_eff", out_thermal)
        self.assertIn("viscosity", out_thermal)
        self.assertIn("q_orifice_total", out_thermal)
        self.assertTrue(np.isfinite(out_thermal["t_eff"]))

        print(
            f"\n[ALB up-pad thermal]  T_eff={out_thermal['t_eff']:.2f}°C  "
            f"miu={out_thermal['viscosity']:.6f}  "
            f"Q_ori={out_thermal['q_orifice_total']:.2e}  "
            f"force={out_thermal['force']}"
        )

    def test_alb_builder_output(self):
        """ALBBuilder creates ALB with CSOrifice; verify output is valid."""
        alb_cfg = ALBConfig(
            pad_config=FPBConfig(
                nx=15,
                nz=9,
                lx=80,
                ps=3e6,
                freq=50,
                max_iter=200,
                error_set=1e-8,
                iter_method="newton",
                damp=0.6,
                coe=False,
            ),
            servo_config=ServoConfig(),
            orifice_config=OrificeConfig(ps=3e6),
            controller_config=PIDConfig(kp=0.0, ki=0.0, kd=0.0),
            servo="static",
            c=80e-6,
        )
        alb = ALBBuilder(alb_cfg).build()
        alb.init()

        c = alb_cfg.c
        alb.input(uxy=np.array([0.1 * c, 0.05 * c]), uxyt=np.array([0.0, 0.0]), t=0.0)
        out = alb.output(nodim=True)

        self.assertIn("force", out)
        force = out["force"]
        self.assertEqual(len(force), 2)
        self.assertTrue(np.all(np.isfinite(force)))

        print(f"\n[ALBBuilder]  force={force}")

    def test_alb_thermal_plots(self):
        """Build ALB with CSOrifice + ThermalHydroBearing on all 4 pads,
        generate 4×3 pressure/temperature/viscosity contour plots."""

        n_orifice = 3  # <-- change this to modify orifice count
        pad_cfg = FPBConfig(
            nx=60,
            nz=40,
            e=0.0,
            lx=80,
            ps=3e6,
            freq=50,
            max_iter=200,
            error_set=1e-8,
            iter_method="newton",
            damp=0.6,
            coe=False,
        )
        pads_dict = four_pads_bearings(pad_cfg)

        # Even distribution: z_i = (i+1) / (n+1) for i in 0..n-1
        positions = np.array(
            [[0.5, (i + 1) / (n_orifice + 1)] for i in range(n_orifice)]
        )

        # Add pressure-equalization grooves (均压槽) at each orifice position
        dx_tank, dz_tank = 0.02, 0.06  # groove half-width in relative coords
        xrange_list = [[0.5 - dx_tank, 0.5 + dx_tank]] * n_orifice
        zrange_list = [
            [positions[i, 1] - dz_tank, positions[i, 1] + dz_tank]
            for i in range(n_orifice)
        ]
        for pad in pads_dict.values():
            pad.set_thickness(
                method="add_tank",
                xrange=xrange_list,
                zrange=zrange_list,
                h_tank=2,
            )

        cso_args = CsoArgs()
        soa_y = CSOrifice(position=positions, ps=3e6, cso_args=cso_args)
        sob_y = CSOrifice(position=positions, ps=0, p0=3e6, cso_args=cso_args)
        soa_x = copy.deepcopy(soa_y)
        sob_x = copy.deepcopy(sob_y)

        pads_dict["up"].add_simple_model(soa_y)
        pads_dict["down"].add_simple_model(sob_y)
        pads_dict["right"].add_simple_model(soa_x)
        pads_dict["left"].add_simple_model(sob_x)

        sv_x = moog_servovalve(6.667e-4, 0.0)
        sv_y = moog_servovalve(6.667e-4, 0.0)
        sv_x.add_simple_model([soa_x, sob_x])
        sv_y.add_simple_model([soa_y, sob_y])

        controller = PID(PIDConfig(kp=0.0, ki=0.0, kd=0.0))
        alb_cfg = ALBConfig(
            pad_config=pad_cfg,
            servo_config=ServoConfig(),
            orifice_config=OrificeConfig(ps=3e6),
            c=pad_cfg.c,
            w=pad_cfg.w,
        )
        pads_list = list(pads_dict.values())
        alb = ALB(pads_list, [sv_x, sv_y], controller=controller, alb_config=alb_cfg)

        tcfg = ThermalConfig(
            t_in=40.0,
            beta=0.03,
            relax=0.5,
            max_iter=20,
            tol=1e-2,
            coupling="full",
            args_nodim=False,
            t_supply=40.0,
        )

        # Wrap all pads with thermal
        thermal_pads = [ThermalHydroBearing(pad, tcfg) for pad in alb.pads]

        # Init and set displacement
        alb.init()
        c = pad_cfg.c
        uxy = np.array([0.2 * c, 0.1 * c])
        uxyt = np.array([0.0, 0.0])

        for cso in [soa_y, sob_y, soa_x, sob_x]:
            cso.input(xv=0.3)

        # Solve thermal for each pad
        pad_names = ["up", "down", "right", "left"]
        pad_results = {}
        for name, tpad in zip(pad_names, thermal_pads):
            tpad.init()
            tpad.input(uxy=uxy, uxyt=uxyt)
            out = tpad.output(calc=True, nodim=True)
            pad_results[name] = out

        # --- Plot 4×3 grid ---
        plot_dir = self.artifact_dir / "thermal_plots"
        plot_dir.mkdir(parents=True, exist_ok=True)

        nx = pad_cfg.nx
        nz = pad_cfg.nz

        # Collect CSOrifice references per pad for marking positions
        cso_per_pad = [soa_y, sob_y, soa_x, sob_x]

        fig, axes = plt.subplots(4, 3, figsize=(18, 22))

        for row, name in enumerate(pad_names):
            pad = alb.pads[row]
            out = pad_results[name]
            model = pad.main_model
            # Structured grid: nodes ordered x-major (for i in x for j in z)
            # shape = (nx+1, nz+1)
            nodes_sorted = [model.nodes[i] for i in range(len(model.nodes))]
            pp = np.array([n.p for n in nodes_sorted]) * model.args["ps"]
            vf = np.asarray(out["viscosity_field"])
            # Reshape to 2D grid
            X = np.array([n.coords[0] for n in nodes_sorted]).reshape(nx + 1, nz + 1)
            Z = np.array([n.coords[1] for n in nodes_sorted]).reshape(nx + 1, nz + 1)
            P = pp.reshape(nx + 1, nz + 1)
            V = vf.reshape(nx + 1, nz + 1)

            tx = np.asarray(out["temperature_x"])
            tz = np.asarray(out["temperature_z"])
            temp = np.asarray(out["temperature"])

            # Orifice node coordinates in film space (for markers)
            cso = cso_per_pad[row]
            if cso.node is not None:
                ori_x = [n.coords[0] for n in cso.node]
                ori_z = [n.coords[1] for n in cso.node]
            else:
                ori_x, ori_z = [], []

            # Pressure (structured grid – pcolormesh guarantees full fill)
            ax = axes[row, 0]
            c1 = ax.pcolormesh(X, Z, P, cmap="viridis", shading="gouraud")
            fig.colorbar(c1, ax=ax, label="Pa")
            if ori_x:
                ax.plot(ori_x, ori_z, "r^", ms=8, mew=1.5, label="orifice")
                ax.legend(loc="upper right", fontsize=7)
            ax.set_title(f"Pressure ({name})")
            ax.set_xlabel("x (rad)")
            ax.set_ylabel("z")
            ax.set_aspect("auto")

            # Temperature (triangular thermal mesh)
            ax = axes[row, 1]
            c2 = ax.tricontourf(tx, tz, temp, levels=20, cmap="inferno")
            fig.colorbar(c2, ax=ax, label="°C")
            ax.set_title(f"Temperature ({name})")
            ax.set_xlabel("x (m)")
            ax.set_ylabel("z (m)")
            ax.set_xlim(tx.min(), tx.max())
            ax.set_ylim(tz.min(), tz.max())
            ax.set_aspect("auto")

            # Viscosity (structured grid)
            ax = axes[row, 2]
            c3 = ax.pcolormesh(X, Z, V, cmap="coolwarm", shading="gouraud")
            fig.colorbar(c3, ax=ax, label="Pa·s")
            ax.set_title(f"Viscosity ({name})")
            ax.set_xlabel("x (rad)")
            ax.set_ylabel("z")
            ax.set_aspect("auto")

        suptitle_lines = "  |  ".join(
            f"{n}: T={pad_results[n]['t_eff']:.1f}°C, miu={pad_results[n]['viscosity']:.5f}"
            for n in pad_names
        )
        fig.suptitle(
            f"ALB Thermal (CSOrifice, n_orifice={n_orifice})\n{suptitle_lines}",
            fontsize=11,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        save_path = plot_dir / "alb_thermal_4pads.png"
        fig.savefig(save_path, dpi=160)
        plt.close(fig)

        for name in pad_names:
            out = pad_results[name]
            print(
                f"[{name:>5s}]  T_eff={out['t_eff']:.2f}°C  "
                f"miu={out['viscosity']:.6f}  "
                f"Q_ori={out['q_orifice_total']:.2e}"
            )
        print(f"  Plot saved to {save_path}")


if __name__ == "__main__":
    unittest.main()
