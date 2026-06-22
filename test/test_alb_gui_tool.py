# -- coding: utf-8 --
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
    run_dynamic_calculation,
    run_static_calculation,
)
from tools.manual.alb_gui.config_io import (
    DEFAULT_PAPER_CONFIG_DIR,
    build_flat_alb_config,
    load_paper_gui_config,
    load_runtime_config,
    make_small_test_config,
    save_runtime_config,
)
from tools.manual.alb_gui.fields import merge_pad_field


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
        self.assertEqual(config["bearing"]["freq"], 50)
        self.assertEqual(config["bearing"]["bias"], 45)
        self.assertIn("miu", config["fluid"])
        self.assertTrue(config["thermal"]["enabled"])
        self.assertIn("settings", config["thermal"])
        self.assertEqual(config["dynamic"]["n"], 8)
        self.assertEqual(config["dynamic"]["pt"], 500)

        flat = build_flat_alb_config(config)
        self.assertEqual(flat["freq"], config["bearing"]["freq"])
        self.assertEqual(flat["thermal_enabled"], config["thermal"]["enabled"])
        self.assertEqual(flat["thermal"]["t_in"], config["thermal"]["settings"]["t_in"])

    def test_runtime_config_round_trip_preserves_special_values(self):
        config, _ = load_paper_gui_config()
        config["thermal"]["settings"]["max_delta_t"] = np.inf

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            save_runtime_config(config, path)
            loaded = load_runtime_config(path)

        self.assertEqual(loaded["bearing"]["c"], config["bearing"]["c"])
        self.assertTrue(np.isinf(loaded["thermal"]["settings"]["max_delta_t"]))
        self.assertEqual(loaded["dynamic"]["repeat"], config["dynamic"]["repeat"])


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

    def test_dynamic_smoke_nonthermal(self):
        config = make_small_test_config(thermal=False)

        result = run_dynamic_calculation(config)

        self.assertIsInstance(result, DynamicResult)
        self.assertEqual(result.stiffness.shape, (2, 2))
        self.assertEqual(result.damping.shape, (2, 2))
        self.assertTrue(np.isfinite(result.stiffness).all())
        self.assertTrue(np.isfinite(result.damping).all())
        self.assertEqual(result.trajectory.shape[1], 2)
        self.assertEqual(result.force_track.shape[1], 2)


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

        freq_widget = panel._widgets[("bearing", "freq")]
        freq_widget.setValue(77.0)
        app.processEvents()

        updated = panel.config()
        self.assertEqual(updated["bearing"]["freq"], 77.0)
        self.assertEqual(updated["dynamic"]["freq"], 77.0)
        self.assertTrue(emissions)

        emissions.clear()
        panel.set_config(config)
        app.processEvents()
        self.assertEqual(emissions, [])
        panel.close()

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
