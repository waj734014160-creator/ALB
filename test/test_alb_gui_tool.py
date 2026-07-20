# -- coding: utf-8 --
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tools.manual.alb_gui.backend import (
    DynamicResult,
    StaticResult,
    build_alb_config,
    run_dynamic_calculation,
    run_static_calculation,
)
from tools.manual.alb_gui.config_io import (
    DEFAULT_PAPER_CONFIG_DIR,
    PAPER_CONFIG_DIR_NAME,
    build_flat_alb_config,
    load_paper_gui_config,
    load_runtime_config,
    make_small_test_config,
    resolve_gui_time_grid,
    save_runtime_config,
)
from tools.manual.alb_gui.fields import (
    merge_pad_field,
    pressure_map_from_pads,
    temperature_map_from_pads,
)


def _paper_config_available():
    return DEFAULT_PAPER_CONFIG_DIR.is_dir()


def _qt_app():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return None
    return QApplication.instance() or QApplication([])


class _FakeModel:
    def __init__(self, start_deg, end_deg):
        self.args = {
            "x_lim": np.deg2rad([start_deg, end_deg]),
            "z_lim": np.array([0.0, 1.0]),
        }


class _FakePost:
    def __init__(self, p):
        self.p = np.asarray(p, dtype=float)


class _FakePad:
    def __init__(self, start_deg, end_deg, value):
        self.main_model = _FakeModel(start_deg, end_deg)
        self.postprocess = _FakePost(np.full((4, 3), value, dtype=float))


@unittest.skipUnless(_paper_config_available(), "paper config directory is unavailable")
class TestAlbGuiConfig(unittest.TestCase):
    def test_paper_defaults_map_required_fields(self):
        config, message = load_paper_gui_config()

        self.assertIn("PAPER", message.upper())
        self.assertEqual(config["source_config_dir"], str(DEFAULT_PAPER_CONFIG_DIR))
        self.assertEqual(DEFAULT_PAPER_CONFIG_DIR.name, PAPER_CONFIG_DIR_NAME)
        self.assertTrue((DEFAULT_PAPER_CONFIG_DIR / "share.json5").is_file())
        self.assertEqual(config["bearing"]["freq"], 50)
        self.assertEqual(config["bearing"]["bias"], 45)
        self.assertIn("miu", config["fluid"])
        self.assertTrue(config["thermal"]["enabled"])
        self.assertIn("settings", config["thermal"])
        self.assertEqual(config["dynamic"]["n"], 8)
        self.assertEqual(config["dynamic"]["pt"], 500)
        self.assertEqual(config["dynamic"]["mode"], "cycle_points")
        self.assertEqual(config["dynamic"]["cycles"], 8)
        self.assertEqual(config["dynamic"]["points_per_cycle"], 500)
        self.assertEqual(config["dynamic"]["steps"], 4000)
        self.assertNotIn("dt", config["pid"])

        flat = build_flat_alb_config(config)
        derived_dt = 1.0 / (config["bearing"]["freq"] * config["dynamic"]["pt"])
        self.assertEqual(flat["freq"], config["bearing"]["freq"])
        self.assertAlmostEqual(flat["dt"], derived_dt)
        self.assertEqual(flat["thermal_enabled"], config["thermal"]["enabled"])
        self.assertEqual(flat["thermal"]["t_in"], config["thermal"]["settings"]["t_in"])

        dynamic_flat = build_flat_alb_config(config, dynamic=True)
        self.assertAlmostEqual(dynamic_flat["dt"], derived_dt)
        self.assertAlmostEqual(dynamic_flat["thermal"]["dt"], derived_dt)

    def test_runtime_config_round_trip_preserves_special_values(self):
        config, _ = load_paper_gui_config()
        config["thermal"]["settings"]["max_delta_t"] = np.inf
        config.setdefault("pid", {})["dt"] = 123.0

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            save_runtime_config(config, path)
            loaded = load_runtime_config(path)

        self.assertEqual(loaded["bearing"]["c"], config["bearing"]["c"])
        self.assertTrue(np.isinf(loaded["thermal"]["settings"]["max_delta_t"]))
        self.assertEqual(loaded["dynamic"]["repeat"], config["dynamic"]["repeat"])
        self.assertNotIn("dt", loaded["pid"])

    def test_legacy_runtime_time_schema_is_migrated_in_memory(self):
        config, _ = load_paper_gui_config()
        config["version"] = 1
        for key in ("mode", "cycles", "points_per_cycle", "dt", "steps"):
            config["dynamic"].pop(key, None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(
                json.dumps(config, ensure_ascii=False),
                encoding="utf-8",
            )
            loaded = load_runtime_config(path)

        self.assertEqual(loaded["version"], 2)
        self.assertEqual(loaded["dynamic"]["mode"], "cycle_points")
        self.assertEqual(loaded["dynamic"]["cycles"], 8)
        self.assertEqual(loaded["dynamic"]["points_per_cycle"], 500)
        self.assertEqual(loaded["dynamic"]["dt"], 4e-5)
        self.assertEqual(loaded["dynamic"]["steps"], 4000)

    def test_fixed_dt_gui_config_preserves_dt_with_partial_revolution(self):
        config, _ = load_paper_gui_config()
        config["dynamic"].update(
            {
                "mode": "fixed_dt",
                "dt": 4e-5,
                "steps": 401,
            }
        )

        resolved = resolve_gui_time_grid(config)
        flat = build_flat_alb_config(config, dynamic=True)

        self.assertEqual(resolved.mode, "fixed_dt")
        self.assertEqual(resolved.steps, 401)
        self.assertNotEqual(resolved.steps % resolved.points_per_cycle, 0)
        self.assertEqual(flat["dt"], 4e-5)

    def test_bearing_frequency_is_the_single_gui_time_grid_authority(self):
        config, _ = load_paper_gui_config()
        config["bearing"]["freq"] = 40.0
        config["dynamic"]["freq"] = 50.0

        resolved = resolve_gui_time_grid(config)
        flat = build_flat_alb_config(config, dynamic=True)

        self.assertEqual(resolved.freq, 40.0)
        self.assertEqual(resolved.dt, 1.0 / (40.0 * 500.0))
        self.assertEqual(flat["freq"], 40.0)
        self.assertEqual(flat["dt"], resolved.dt)

    def test_static_flat_config_forces_fixed_journal_control(self):
        config, _ = load_paper_gui_config()
        config["pid"].update({"ki": 1.5, "kd": 2.5, "servo": "moog"})

        static_flat = build_flat_alb_config(config, dynamic=False)
        dynamic_flat = build_flat_alb_config(config, dynamic=True)

        self.assertEqual(static_flat["ki"], 0.0)
        self.assertEqual(static_flat["kd"], 0.0)
        self.assertEqual(static_flat["servo"], "static")
        self.assertEqual(dynamic_flat["ki"], 1.5)
        self.assertEqual(dynamic_flat["kd"], 2.5)
        self.assertEqual(dynamic_flat["servo"], "moog")
        self.assertEqual(config["pid"]["ki"], 1.5)
        self.assertEqual(config["pid"]["kd"], 2.5)
        self.assertEqual(config["pid"]["servo"], "moog")


class TestAlbGuiFieldMerge(unittest.TestCase):
    def test_pressure_gaps_are_zero_filled(self):
        pads = [_FakePad(0, 60, 3.0), _FakePad(180, 240, 7.0)]

        field = merge_pad_field(pads, field="pressure", n_theta=13, fill_value=0.0)

        self.assertEqual(field.values.shape, (13, 3))
        self.assertGreater(float(np.max(field.values)), 0.0)
        self.assertEqual(float(field.values[3, 0]), 0.0)

    def test_temperature_gaps_are_masked(self):
        class _ThermalPost:
            postprocess_result = {"ready": True}

            def __init__(self, value):
                self.temperature_field = np.full((4, 3), value, dtype=float)

        class _ThermalPad(_FakePad):
            def __init__(self, start_deg, end_deg, value):
                super().__init__(start_deg, end_deg, value)
                self.post_process = _ThermalPost(value)

        pads = [_ThermalPad(0, 60, 20.0), _ThermalPad(180, 240, 30.0)]

        field = merge_pad_field(
            pads,
            field="temperature",
            n_theta=13,
            fill_value=np.nan,
            mask_gaps=True,
        )

        self.assertTrue(field.masked)
        self.assertTrue(np.ma.is_masked(field.values[3, 0]))


@unittest.skipUnless(_paper_config_available(), "paper config directory is unavailable")
class TestAlbGuiBackend(unittest.TestCase):
    def test_static_smoke_nonthermal(self):
        config = make_small_test_config(thermal=False)

        result = run_static_calculation(config)

        self.assertIsInstance(result, StaticResult)
        self.assertEqual(result.force.shape, (2,))
        self.assertTrue(np.isfinite(result.force).all())
        self.assertEqual(result.pressure.values.ndim, 2)
        self.assertIsNone(result.temperature)
        self.assertEqual(len(result.pad_status), 4)

    def test_static_gui_backend_matches_script_style_result(self):
        from ALB.alb import alb2_static

        config = make_small_test_config(thermal=False)
        gui_result = run_static_calculation(config)

        script_model = alb2_static(build_alb_config(config, dynamic=False))
        script_model.init()
        bearing = config["bearing"]
        angle = np.deg2rad(float(bearing["angle"]))
        uxy = np.array(
            [
                float(bearing["e"]) * np.cos(angle),
                float(bearing["e"]) * np.sin(angle),
            ],
            dtype=float,
        )
        script_model.input(uxy=uxy, uxyt=np.zeros(2), t=0.0, nodim=True)
        script_output = script_model.output(nodim=False)
        script_pads = list(script_model.pads)
        script_pressure = pressure_map_from_pads(script_pads)
        script_temperature = temperature_map_from_pads(script_pads)

        np.testing.assert_allclose(gui_result.force, script_output["force"])
        np.testing.assert_allclose(gui_result.friction, script_output["friction"])
        np.testing.assert_allclose(
            gui_result.pressure.values, script_pressure.values
        )
        self.assertIsNone(gui_result.temperature)
        self.assertIsNone(script_temperature)

    def test_parallel_orbit_matches_serial_orbit_nonthermal(self):
        from ALB.alb import alb2
        from ALB.dynamics.orbit import (
            EllipseTrack,
            orbitime,
            test_bearing_orbit,
            test_bearing_orbit_parallel,
        )

        config = make_small_test_config(thermal=False)
        alb_config = build_alb_config(config, dynamic=True)
        dyn = config["dynamic"]
        time_iter = orbitime(config["bearing"]["freq"], dyn["n"], dyn["pt"])
        serial_track = EllipseTrack(
            a=dyn["a"],
            b=dyn["b"],
            freq=config["bearing"]["freq"],
            a0=dyn["a0"],
            b0=dyn["b0"],
            f0=dyn["f0"],
            vf=config["boundary"]["vf"],
        )
        parallel_track = EllipseTrack(
            a=dyn["a"],
            b=dyn["b"],
            freq=config["bearing"]["freq"],
            a0=dyn["a0"],
            b0=dyn["b0"],
            f0=dyn["f0"],
            vf=config["boundary"]["vf"],
        )
        serial_model = alb2(alb_config)
        parallel_model = alb2(alb_config)
        serial_model.init()
        parallel_model.init()
        progress = []

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            serial = test_bearing_orbit(
                time_iter,
                serial_model,
                serial_track,
                repeat=dyn["repeat"],
                pt=dyn["pt"],
                tr=[dyn["tr_start"], dyn["tr_end"]],
            )
            parallel = test_bearing_orbit_parallel(
                time_iter,
                parallel_model,
                parallel_track,
                repeat=dyn["repeat"],
                pt=dyn["pt"],
                tr=[dyn["tr_start"], dyn["tr_end"]],
                progress_callback=lambda value, message: progress.append(
                    (value, message)
                ),
            )

        np.testing.assert_allclose(
            parallel["hkc"]["k"], serial["hkc"]["k"], rtol=1e-10, atol=1e-8
        )
        np.testing.assert_allclose(
            parallel["hkc"]["c"], serial["hkc"]["c"], rtol=1e-10, atol=1e-8
        )
        values = [value for value, _message in progress]
        self.assertEqual(values[0], 0)
        self.assertEqual(values[-1], 100)
        self.assertEqual(values, sorted(values))
        self.assertTrue(
            any("Parallel vortex force calculation" in message for _, message in progress)
        )

    def test_dynamic_gui_backend_matches_script_style_result(self):
        from ALB.alb import alb2
        from ALB.dynamics.orbit import EllipseTrack, orbitime, test_bearing_orbit

        config = make_small_test_config(thermal=False)
        gui_result = run_dynamic_calculation(config)
        dyn = config["dynamic"]
        freq = float(dyn.get("freq", config["bearing"]["freq"]))
        time_iter = orbitime(freq, int(dyn["n"]), int(dyn["pt"]))
        track = EllipseTrack(
            a=float(dyn["a"]),
            b=float(dyn["b"]),
            freq=freq,
            a0=float(dyn["a0"]),
            b0=float(dyn["b0"]),
            f0=float(dyn["f0"]),
            vf=float(dyn.get("vf", config["boundary"]["vf"])),
        )
        script_model = alb2(build_alb_config(config, dynamic=True))
        script_model.init()

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            script_result = test_bearing_orbit(
                time_iter,
                script_model,
                track,
                repeat=int(dyn["repeat"]),
                pt=int(dyn["pt"]),
                tr=[float(dyn["tr_start"]), float(dyn["tr_end"])],
            )

        script_bft = script_result["bft"].bearing_forces
        np.testing.assert_allclose(gui_result.stiffness, script_result["hkc"]["k"])
        np.testing.assert_allclose(gui_result.damping, script_result["hkc"]["c"])
        np.testing.assert_allclose(
            gui_result.trajectory, script_bft[["ux", "uy"]].to_numpy(dtype=float)
        )
        np.testing.assert_allclose(
            gui_result.force_track, script_bft[["fx", "fy"]].to_numpy(dtype=float)
        )
        np.testing.assert_allclose(
            gui_result.time, script_bft["t"].to_numpy(dtype=float)
        )

    def test_dynamic_smoke_nonthermal(self):
        config = make_small_test_config(thermal=False)
        progress = []

        result = run_dynamic_calculation(
            config, progress_callback=lambda value, message: progress.append((value, message))
        )

        self.assertIsInstance(result, DynamicResult)
        self.assertEqual(result.stiffness.shape, (2, 2))
        self.assertEqual(result.damping.shape, (2, 2))
        self.assertTrue(np.isfinite(result.stiffness).all())
        self.assertTrue(np.isfinite(result.damping).all())
        self.assertEqual(result.trajectory.shape[1], 2)
        self.assertEqual(result.force_track.shape[1], 2)
        self.assertEqual(progress[0][0], 0)
        self.assertEqual(progress[-1][0], 100)
        self.assertTrue(any("正反涡动并行计算" in message for _, message in progress))


@unittest.skipUnless(_paper_config_available(), "paper config directory is unavailable")
class TestAlbGuiWindow(unittest.TestCase):
    def test_window_constructs_offscreen_and_saves(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.window import AlbGuiWindow

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = Path(tmpdir) / "config.json"
            window = AlbGuiWindow(
                config=make_small_test_config(thermal=False),
                runtime_path=runtime_path,
                prefer_runtime=False,
            )
            window._save_current_config()
            self.assertTrue(runtime_path.is_file())
            window.close()
            app.processEvents()

    def test_parameter_panel_round_trip_and_change_signal(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.window import ParameterPanel

        config = make_small_test_config(thermal=False)
        panel = ParameterPanel(config)
        emissions = []
        panel.changed.connect(lambda: emissions.append("changed"))
        self.assertNotIn(("pid", "dt"), panel._widgets)

        freq_widget = panel._widgets[("bearing", "freq")]
        freq_widget.setValue(77.0)
        app.processEvents()

        updated = panel.config()
        self.assertEqual(updated["bearing"]["freq"], 77.0)
        self.assertEqual(updated["dynamic"]["freq"], 77.0)
        self.assertNotIn("dt", updated["pid"])
        self.assertTrue(emissions)

        emissions.clear()
        panel.set_config(config)
        app.processEvents()
        self.assertEqual(emissions, [])
        panel.close()

    def test_parameter_panel_displays_clearance_and_track_in_micrometers(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.window import ParameterPanel

        config = make_small_test_config(thermal=False)
        config["bearing"]["c"] = 80e-6
        config["dynamic"].update(
            {"a": 2e-6, "b": 3e-6, "a0": -4e-6, "b0": 5e-6}
        )
        panel = ParameterPanel(config)

        c_widget = panel._widgets[("bearing", "c")]
        a_widget = panel._widgets[("dynamic", "a")]
        b_widget = panel._widgets[("dynamic", "b")]
        a0_widget = panel._widgets[("dynamic", "a0")]
        b0_widget = panel._widgets[("dynamic", "b0")]

        self.assertEqual(c_widget.suffix(), " um")
        self.assertEqual(a_widget.suffix(), " um")
        self.assertAlmostEqual(c_widget.value(), 80.0)
        self.assertAlmostEqual(a_widget.value(), 2.0)
        self.assertAlmostEqual(b_widget.value(), 3.0)
        self.assertAlmostEqual(a0_widget.value(), -4.0)
        self.assertAlmostEqual(b0_widget.value(), 5.0)

        c_widget.setValue(125.0)
        a_widget.setValue(6.5)
        b_widget.setValue(7.5)
        a0_widget.setValue(-8.5)
        b0_widget.setValue(9.5)
        updated = panel.config()

        self.assertAlmostEqual(updated["bearing"]["c"], 125e-6)
        self.assertAlmostEqual(updated["dynamic"]["a"], 6.5e-6)
        self.assertAlmostEqual(updated["dynamic"]["b"], 7.5e-6)
        self.assertAlmostEqual(updated["dynamic"]["a0"], -8.5e-6)
        self.assertAlmostEqual(updated["dynamic"]["b0"], 9.5e-6)
        panel.close()
        app.processEvents()

    def test_parameter_panel_wheel_does_not_change_input_values(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from PySide6.QtWidgets import QAbstractSpinBox

        from tools.manual.alb_gui.window import ParameterPanel

        class _WheelEvent:
            def __init__(self):
                self.ignored = False

            def ignore(self):
                self.ignored = True

        config = make_small_test_config(thermal=False)
        panel = ParameterPanel(config)
        double_widget = panel._widgets[("bearing", "freq")]
        int_widget = panel._widgets[("dynamic", "pt")]
        combo_widget = panel._widgets[("boundary", "iter_method")]

        double_value = double_widget.value()
        int_value = int_widget.value()
        combo_index = combo_widget.currentIndex()

        for widget in (double_widget, int_widget, combo_widget):
            event = _WheelEvent()
            widget.wheelEvent(event)
            self.assertTrue(event.ignored)

        self.assertEqual(double_widget.value(), double_value)
        self.assertEqual(int_widget.value(), int_value)
        self.assertEqual(combo_widget.currentIndex(), combo_index)
        self.assertEqual(double_widget.buttonSymbols(), QAbstractSpinBox.NoButtons)
        self.assertEqual(int_widget.buttonSymbols(), QAbstractSpinBox.NoButtons)
        panel.close()
        app.processEvents()

    def test_parameter_panel_updates_nested_thermal_settings(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.window import ParameterPanel

        config = make_small_test_config(thermal=True)
        panel = ParameterPanel(config)

        panel._widgets[("thermal", "enabled")].setChecked(False)
        panel._widgets[("thermal.settings", "t_in")].setValue(33.0)
        app.processEvents()

        updated = panel.config()
        self.assertFalse(updated["thermal"]["enabled"])
        self.assertEqual(updated["thermal"]["settings"]["t_in"], 33.0)
        panel.close()

    def test_window_busy_state_toggles_command_buttons(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.window import AlbGuiWindow

        window = AlbGuiWindow(config=make_small_test_config(thermal=False))

        window._set_busy(True)
        self.assertFalse(window._static_button.isEnabled())
        self.assertFalse(window._dynamic_button.isEnabled())
        self.assertFalse(window._reload_button.isEnabled())

        window._set_busy(False)
        self.assertTrue(window._static_button.isEnabled())
        self.assertTrue(window._dynamic_button.isEnabled())
        self.assertTrue(window._reload_button.isEnabled())
        window.close()
        app.processEvents()

    def test_window_static_result_updates_text_and_plots(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.fields import FieldMap
        from tools.manual.alb_gui.window import AlbGuiWindow

        theta = np.linspace(0.0, 360.0, 5)
        z = np.linspace(0.0, 1.0, 3)
        pressure = FieldMap(theta, z, np.ones((5, 3)), masked=False)
        temperature = FieldMap(
            theta,
            z,
            np.ma.array(
                np.full((5, 3), 25.0),
                mask=np.array(
                    [
                        [False, False, False],
                        [False, False, False],
                        [True, True, True],
                        [False, False, False],
                        [False, False, False],
                    ]
                ),
            ),
            masked=True,
        )
        result = StaticResult(
            force=np.array([1.0, -2.0]),
            friction=0.5,
            pressure=pressure,
            temperature=temperature,
            pad_status=[{"finished": True} for _ in range(4)],
        )
        window = AlbGuiWindow(config=make_small_test_config(thermal=False))

        window._on_static_done(result)

        text = window._static_text.toPlainText()
        self.assertIn("Fx = 1.000000e+00 N", text)
        self.assertIn("Friction = 5.000000e-01", text)
        self.assertGreaterEqual(len(window._fig_pressure.axes), 2)
        self.assertGreaterEqual(len(window._fig_temperature.axes), 2)
        temp_mesh = window._fig_temperature.axes[0].collections[0]
        self.assertTrue(np.ma.is_masked(temp_mesh.get_array()[2]))
        self.assertEqual(window._status.currentMessage(), "静特性计算完成")
        window.close()
        app.processEvents()

    def test_window_static_result_without_temperature_shows_placeholder(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.fields import FieldMap
        from tools.manual.alb_gui.window import AlbGuiWindow

        pressure = FieldMap(
            np.linspace(0.0, 360.0, 5),
            np.linspace(0.0, 1.0, 3),
            np.ones((5, 3)),
            masked=False,
        )
        result = StaticResult(
            force=np.array([1.0, 2.0]),
            friction=0.5,
            pressure=pressure,
            temperature=None,
            pad_status=[],
        )
        window = AlbGuiWindow(config=make_small_test_config(thermal=False))

        window._on_static_done(result)

        labels = [
            item.get_text()
            for ax in window._fig_temperature.axes
            for item in ax.texts
        ]
        self.assertIn("未开启热效应", labels)
        window.close()
        app.processEvents()

    def test_window_dynamic_result_updates_text_and_plots(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.window import AlbGuiWindow

        result = DynamicResult(
            stiffness=np.array([[1.0, 2.0], [3.0, 4.0]]),
            damping=np.array([[5.0, 6.0], [7.0, 8.0]]),
            trajectory=np.array([[0.0, 0.0], [1.0, 0.5], [0.0, 1.0]]),
            force_track=np.array([[0.0, 0.0], [10.0, 5.0], [0.0, 10.0]]),
            time=np.array([0.0, 0.1, 0.2]),
        )
        window = AlbGuiWindow(config=make_small_test_config(thermal=False))

        window._on_dynamic_done(result)

        text = window._dynamic_text.toPlainText()
        self.assertIn("Stiffness K (N/m)", text)
        self.assertIn("Damping C (N*s/m)", text)
        self.assertEqual(len(window._fig_trajectory.axes[0].lines), 3)
        self.assertEqual(len(window._fig_force.axes[0].lines), 3)
        self.assertEqual(window._status.currentMessage(), "动特性计算完成")
        self.assertEqual(window._dynamic_progress.value(), 100)
        self.assertIn("动特性计算完成", window._dynamic_progress.text())
        window.close()
        app.processEvents()

    def test_window_dynamic_progress_updates_progress_bar(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.window import AlbGuiWindow

        window = AlbGuiWindow(config=make_small_test_config(thermal=False))

        window._on_dynamic_progress(42, "正向涡动轨迹 4/10")

        self.assertEqual(window._dynamic_progress.value(), 42)
        self.assertIn("正向涡动轨迹", window._dynamic_progress.text())
        self.assertEqual(window._status.currentMessage(), "正向涡动轨迹 4/10")
        window.close()
        app.processEvents()

    def test_window_error_handler_reenables_buttons(self):
        app = _qt_app()
        if app is None:
            self.skipTest("PySide6 is not installed")

        from tools.manual.alb_gui.window import AlbGuiWindow

        window = AlbGuiWindow(config=make_small_test_config(thermal=False))
        window._set_busy(True)
        exc = RuntimeError("boom")
        exc._worker_traceback = "traceback text"

        with mock.patch("tools.manual.alb_gui.window.QMessageBox.critical") as critical:
            handled = window._handle_error("计算失败", exc)

        self.assertTrue(handled)
        self.assertTrue(window._static_button.isEnabled())
        self.assertTrue(window._dynamic_button.isEnabled())
        critical.assert_called_once()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
