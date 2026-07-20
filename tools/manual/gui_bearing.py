# -*- coding: utf-8 -*-
"""
Hydrostatic Bearing Static & Dynamic Analysis GUI — Phase 1.

Single-pad hydrostatic bearing with pressure field visualization,
load capacity, friction, stiffness and damping coefficient computation.

Requires: PySide6, matplotlib, numpy, ALB
"""

from __future__ import annotations

import traceback
from typing import Dict, Optional

# -- matplotlib backend MUST be set before FigureCanvas import ----------
import matplotlib
import numpy as np

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

# -- PySide6 ------------------------------------------------------------
from PySide6.QtCore import Qt, QThread, Signal  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ALB.physics.bearing import BearingDynamicChar, HydrostaticBearing  # noqa: E402

# -- ALB imports --------------------------------------------------------
from ALB.config import HydConfig  # noqa: E402

# ===========================================================================
# Default Parameters (matching HydConfig defaults)
# ===========================================================================
DEFAULT_PARAMS: Dict[str, object] = {
    # Geometry
    "r": 0.04,  # bearing radius (m)
    "l": 0.08,  # bearing length (m)
    "c": 80e-6,  # nominal clearance (m) — displayed as μm in GUI
    "lx": 80.0,  # pad angular span (degrees)
    "lz": 2.0,  # non-dimensional axial length
    # Operating conditions
    "ps": 7e6,  # supply pressure (Pa) — displayed as MPa in GUI
    "w": 3000,  # rotor speed (rpm)
    "e": 0.0,  # eccentricity ratio
    "angle": 0.0,  # attitude angle (degrees)
    # Fluid properties
    "miu": 0.0195,  # dynamic viscosity (Pa·s)
    "rho": 872.0,  # density (kg/m³)
    # Solver settings
    "nx": 59,  # circumferential grid points
    "nz": 39,  # axial grid points
    "iter_method": "newton",  # newton | gauss | lsq | skfem_newton
    "error_set": 1e-10,  # convergence tolerance
    "max_iter": 30,  # max iterations
}

# ===========================================================================
# Bearing Calculation Backend
# ===========================================================================


class BearingCalculator:
    """Encapsulates HydrostaticBearing construction and computation."""

    def __init__(self, params: Dict[str, object]) -> None:
        self.params = dict(params)
        self._bearing: Optional[HydrostaticBearing] = None
        self._static_done: bool = False
        self._build()

    def _build(self) -> None:
        """Construct HydConfig → HydrostaticBearing from current params."""
        p = self.params
        cfg = HydConfig(
            r=float(p["r"]),
            l=float(p["l"]),
            c=float(p["c"]),
            lx=float(p["lx"]),
            lz=float(p["lz"]),
            ps=float(p["ps"]),
            freq=float(p["w"]) / 60.0,  # rpm → Hz
            miu=float(p["miu"]),
            rho=float(p["rho"]),
            nx=int(p["nx"]),
            nz=int(p["nz"]),
            iter_method=str(p["iter_method"]),
            error_set=float(p["error_set"]),
            max_iter=int(p["max_iter"]),
        )
        self._bearing = HydrostaticBearing(cfg)
        self._static_done = False

    def run_static(self, ex: float, ey: float) -> dict:
        """Run static computation and return results dict."""
        if self._bearing is None:
            self._build()
        bearing = self._bearing
        bearing.init()
        bearing.input(uxy=[ex, ey], uxyt=[0.0, 0.0], nodim=True)
        bearing.output()

        force = bearing.calc_capacity(nodim=False)  # [Fx, Fy] in N
        friction = bearing.calc_friction(nodim=False)  # friction force in N

        # Pressure field (nondimensional)
        pp = bearing.postprocess
        pressure = np.asarray(pp.p, dtype=float)
        X = np.asarray(pp.X, dtype=float)  # axial (z) coordinate
        Y = np.asarray(pp.Y, dtype=float)  # circumferential (x) coordinate

        self._static_done = True
        return {
            "Fx": float(force[0]),
            "Fy": float(force[1]),
            "F_mag": float(np.linalg.norm(force)),
            "friction": float(friction),
            "pressure": pressure,
            "X": X,
            "Y": Y,
        }

    def run_dynamic(self) -> dict:
        """Compute stiffness and damping matrices (requires static first)."""
        if not self._static_done:
            raise RuntimeError("Run static calculation first.")
        bdc = BearingDynamicChar(self._bearing)
        K = np.asarray(bdc.calc_k(nodim=False), dtype=float)
        C = np.asarray(bdc.calc_c(nodim=False), dtype=float)
        return {"K": K, "C": C}


# ===========================================================================
# Parameter Panel (4 progressive sections)
# ===========================================================================


class ParamPanel(QWidget):
    """Left-side panel with 4 grouped sections of input controls."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._widgets: Dict[str, object] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # -- Geometry Group -------------------------------------------------
        geo_group = QGroupBox("1. Geometry")
        geo_form = QFormLayout(geo_group)
        self._add_spin(geo_form, "r", 0.01, 1.0, 3, " m", DEFAULT_PARAMS["r"])
        self._add_spin(geo_form, "l", 0.01, 1.0, 3, " m", DEFAULT_PARAMS["l"])
        self._add_spin(geo_form, "c", 1.0, 500.0, 1, " \u03bcm", 80.0)
        self._add_spin(geo_form, "lx", 10.0, 360.0, 1, " \u00b0", DEFAULT_PARAMS["lx"])
        self._add_spin(geo_form, "lz", 0.5, 5.0, 1, "", DEFAULT_PARAMS["lz"])
        layout.addWidget(geo_group)

        # -- Operating Group ------------------------------------------------
        oper_group = QGroupBox("2. Operating Conditions")
        oper_form = QFormLayout(oper_group)
        self._add_spin(oper_form, "ps", 1.0, 30.0, 1, " MPa", 7.0)
        self._add_spin(oper_form, "w", 1.0, 20000.0, 0, " rpm", DEFAULT_PARAMS["w"])
        self._add_spin(oper_form, "e", 0.0, 0.99, 2, "", DEFAULT_PARAMS["e"])
        self._add_spin(
            oper_form, "angle", 0.0, 360.0, 1, " \u00b0", DEFAULT_PARAMS["angle"]
        )
        layout.addWidget(oper_group)

        # -- Fluid Group ----------------------------------------------------
        fluid_group = QGroupBox("3. Fluid Properties")
        fluid_form = QFormLayout(fluid_group)
        self._add_spin(
            fluid_form, "miu", 0.001, 1.0, 4, " Pa\u00b7s", DEFAULT_PARAMS["miu"]
        )
        self._add_spin(
            fluid_form, "rho", 500.0, 2000.0, 1, " kg/m\u00b3", DEFAULT_PARAMS["rho"]
        )
        layout.addWidget(fluid_group)

        # -- Solver Group ---------------------------------------------------
        solver_group = QGroupBox("4. Solver Settings")
        solver_form = QFormLayout(solver_group)

        nx_spin = QSpinBox()
        nx_spin.setRange(10, 200)
        nx_spin.setValue(DEFAULT_PARAMS["nx"])
        solver_form.addRow("nx", nx_spin)
        self._widgets["nx"] = nx_spin

        nz_spin = QSpinBox()
        nz_spin.setRange(10, 200)
        nz_spin.setValue(DEFAULT_PARAMS["nz"])
        solver_form.addRow("nz", nz_spin)
        self._widgets["nz"] = nz_spin

        iter_combo = QComboBox()
        iter_combo.addItems(["newton", "gauss", "lsq", "skfem_newton"])
        iter_combo.setCurrentText(str(DEFAULT_PARAMS["iter_method"]))
        solver_form.addRow("iter_method", iter_combo)
        self._widgets["iter_method"] = iter_combo

        err_combo = QComboBox()
        err_combo.addItems(["1e-8", "1e-10", "1e-12"])
        err_combo.setCurrentText("1e-10")
        solver_form.addRow("error_set", err_combo)
        self._widgets["error_set"] = err_combo

        max_iter = QSpinBox()
        max_iter.setRange(1, 200)
        max_iter.setValue(DEFAULT_PARAMS["max_iter"])
        solver_form.addRow("max_iter", max_iter)
        self._widgets["max_iter"] = max_iter

        layout.addWidget(solver_group)
        layout.addStretch()

    # ------------------------------------------------------------------
    def _add_spin(
        self,
        form: QFormLayout,
        key: str,
        vmin: float,
        vmax: float,
        decimals: int,
        suffix: str,
        default: object,
    ) -> None:
        spin = QDoubleSpinBox()
        spin.setRange(vmin, vmax)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        spin.setValue(float(default))
        form.addRow(key, spin)
        self._widgets[key] = spin

    # ------------------------------------------------------------------
    def get_params(self) -> Dict[str, object]:
        """Collect current parameter values from all widgets."""
        params: Dict[str, object] = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QDoubleSpinBox):
                params[key] = widget.value()
            elif isinstance(widget, QSpinBox):
                params[key] = widget.value()
            elif isinstance(widget, QComboBox):
                text = widget.currentText()
                # error_set stored as float
                if key == "error_set":
                    params[key] = float(text)
                else:
                    params[key] = text
        # Unit conversions: GUI displays μm/MPa, store as m/Pa
        params["c"] = float(params["c"]) * 1e-6  # μm → m
        params["ps"] = float(params["ps"]) * 1e6  # MPa → Pa
        return params

    # ------------------------------------------------------------------
    def reset_to_defaults(self) -> None:
        """Restore all widgets to DEFAULT_PARAMS values."""
        for key, widget in self._widgets.items():
            default = DEFAULT_PARAMS.get(key)
            if default is None:
                continue
            if isinstance(widget, QDoubleSpinBox):
                # Display values: c in μm, ps in MPa
                if key == "c":
                    widget.setValue(float(default) * 1e6)
                elif key == "ps":
                    widget.setValue(float(default) * 1e-6)
                else:
                    widget.setValue(float(default))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(default))
            elif isinstance(widget, QComboBox):
                if key == "error_set":
                    widget.setCurrentText(str(default))
                else:
                    widget.setCurrentText(str(default))


# ===========================================================================
# Computation Worker (QThread)
# ===========================================================================


class ComputeWorker(QThread):
    """Run bearing computation in a background thread to avoid UI freeze."""

    finished = Signal(object)  # emits result dict or Exception
    mode: str = ""
    ex: float = 0.0
    ey: float = 0.0
    calculator: Optional[BearingCalculator] = None

    def run(self) -> None:
        try:
            if self.mode == "static":
                result = self.calculator.run_static(self.ex, self.ey)
                self.finished.emit(result)
            elif self.mode == "dynamic":
                result = self.calculator.run_dynamic()
                self.finished.emit(result)
        except Exception as exc:
            exc._worker_tb = (
                traceback.format_exc()
            )  # capture traceback in worker thread
            self.finished.emit(exc)


# ===========================================================================
# Main Window
# ===========================================================================


class BearingGui(QMainWindow):
    """Main application window for bearing analysis."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Hydrostatic Bearing Analysis")
        self.resize(1200, 700)
        self.setMinimumSize(1000, 600)

        self._calculator: Optional[BearingCalculator] = None
        self._static_result: Optional[dict] = None

        self._setup_menu()
        self._setup_central()
        self._setup_statusbar()

        self.statusBar().showMessage("Ready")

    # -- Menu ---------------------------------------------------------------
    def _setup_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        help_menu = menu_bar.addMenu("&Help")
        about_action = help_menu.addAction("&About")
        about_action.triggered.connect(self._show_about)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About",
            "Hydrostatic Bearing Analysis GUI — Phase 1\n\n"
            "Single-pad hydrostatic bearing static & dynamic characteristics.\n"
            "Built with PySide6 + matplotlib + ALB.",
        )

    # -- Central Widget -----------------------------------------------------
    def _setup_central(self) -> None:
        splitter = QSplitter(Qt.Horizontal)

        # --- Left: parameter panel + results + buttons --------------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._param_panel = ParamPanel()
        scroll.setWidget(self._param_panel)
        left_layout.addWidget(scroll, 1)

        # Results text area
        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setMaximumHeight(180)
        self._result_text.setPlaceholderText(
            "Results will appear here after calculation..."
        )
        left_layout.addWidget(self._result_text)

        # Buttons
        btn_layout = QHBoxLayout()

        self._btn_static = QPushButton("Calculate Static")
        self._btn_static.clicked.connect(self._on_static)
        btn_layout.addWidget(self._btn_static)

        self._btn_dynamic = QPushButton("Calculate Dynamic")
        self._btn_dynamic.clicked.connect(self._on_dynamic)
        self._btn_dynamic.setEnabled(False)
        btn_layout.addWidget(self._btn_dynamic)

        btn_reset = QPushButton("Reset to Defaults")
        btn_reset.clicked.connect(self._on_reset)
        btn_layout.addWidget(btn_reset)

        left_layout.addLayout(btn_layout)
        splitter.addWidget(left)

        # --- Right: matplotlib tabs ---------------------------------------
        self._tab_widget = QTabWidget()

        self._fig_pressure = Figure(figsize=(5, 4), dpi=100)
        self._canvas_pressure = FigureCanvasQTAgg(self._fig_pressure)
        self._tab_widget.addTab(self._canvas_pressure, "Pressure Field")

        self._fig_force = Figure(figsize=(5, 4), dpi=100)
        self._canvas_force = FigureCanvasQTAgg(self._fig_force)
        self._tab_widget.addTab(self._canvas_force, "Load Capacity")

        splitter.addWidget(self._tab_widget)
        splitter.setSizes([450, 750])

        self.setCentralWidget(splitter)

    # -- Status Bar ---------------------------------------------------------
    def _setup_statusbar(self) -> None:
        self._status = QStatusBar()
        self.setStatusBar(self._status)

    # -- Button Handlers ----------------------------------------------------
    def _on_static(self) -> None:
        """Trigger static computation in a worker thread."""
        params = self._param_panel.get_params()
        self._calculator = BearingCalculator(params)

        e_val = float(params["e"])
        angle_deg = float(params["angle"])
        angle_rad = np.deg2rad(angle_deg)
        ex = e_val * np.cos(angle_rad)
        ey = e_val * np.sin(angle_rad)

        self._disable_buttons()
        self._status.showMessage("Computing static characteristics...")

        self._worker = ComputeWorker()
        self._worker.mode = "static"
        self._worker.ex = ex
        self._worker.ey = ey
        self._worker.calculator = self._calculator
        self._worker.finished.connect(self._on_static_done)
        self._worker.start()

    def _on_static_done(self, result: object) -> None:
        """Handle static computation result."""
        self._enable_buttons()
        if isinstance(result, Exception):
            self._status.showMessage("Computation failed")
            tb = getattr(result, "_worker_tb", "")
            QMessageBox.critical(
                self,
                "Error",
                f"Static computation failed:\n{result}\n\n{tb}",
            )
            return

        if not isinstance(result, dict):
            self._status.showMessage("Computation failed")
            QMessageBox.critical(
                self, "Error", f"Unexpected result type: {type(result).__name__}"
            )
            return

        self._static_result = result
        self._btn_dynamic.setEnabled(True)
        self._status.showMessage("Static computation done")

        # Update text results
        self._result_text.setText(
            f"=== Static Characteristics ===\n"
            f"Fx       = {result['Fx']:12.2f} N\n"
            f"Fy       = {result['Fy']:12.2f} N\n"
            f"|F|      = {result['F_mag']:12.2f} N\n"
            f"Friction = {result['friction']:12.4f} N\n"
        )

        # Update plots
        self._plot_pressure(result)
        self._plot_force(result)

    # ------------------------------------------------------------------
    def _on_dynamic(self) -> None:
        """Trigger dynamic computation in a worker thread."""
        if self._calculator is None:
            QMessageBox.warning(self, "Warning", "Run static calculation first.")
            return

        self._disable_buttons()
        self._status.showMessage("Computing dynamic characteristics...")

        self._worker = ComputeWorker()
        self._worker.mode = "dynamic"
        self._worker.calculator = self._calculator
        self._worker.finished.connect(self._on_dynamic_done)
        self._worker.start()

    def _on_dynamic_done(self, result: object) -> None:
        """Handle dynamic computation result."""
        self._enable_buttons()
        if isinstance(result, Exception):
            self._status.showMessage("Dynamic computation failed")
            tb = getattr(result, "_worker_tb", "")
            QMessageBox.critical(
                self,
                "Error",
                f"Dynamic computation failed:\n{result}\n\n{tb}",
            )
            return

        if not isinstance(result, dict):
            self._status.showMessage("Computation failed")
            QMessageBox.critical(
                self, "Error", f"Unexpected result type: {type(result).__name__}"
            )
            return

        K = result["K"]
        C = result["C"]
        self._status.showMessage("Dynamic computation done")

        # Append dynamic results to text
        prev = self._result_text.toPlainText()
        self._result_text.setText(
            prev + f"\n=== Dynamic Characteristics ===\n"
            f"Stiffness K (N/m):\n"
            f"  [[{K[0, 0]:10.2e}, {K[0, 1]:10.2e}],\n"
            f"   [{K[1, 0]:10.2e}, {K[1, 1]:10.2e}]]\n"
            f"Damping C (N·s/m):\n"
            f"  [[{C[0, 0]:10.2e}, {C[0, 1]:10.2e}],\n"
            f"   [{C[1, 0]:10.2e}, {C[1, 1]:10.2e}]]\n"
        )

    # ------------------------------------------------------------------
    def _on_reset(self) -> None:
        """Reset parameters to defaults."""
        self._param_panel.reset_to_defaults()
        self._calculator = None
        self._static_result = None
        self._btn_dynamic.setEnabled(False)
        self._result_text.clear()
        self._clear_plots()
        self._status.showMessage("Parameters reset to defaults")

    # -- Button State -------------------------------------------------------
    def _disable_buttons(self) -> None:
        self._btn_static.setEnabled(False)
        self._btn_dynamic.setEnabled(False)

    def _enable_buttons(self) -> None:
        self._btn_static.setEnabled(True)
        if self._static_result is not None:
            self._btn_dynamic.setEnabled(True)

    # -- Plotting -----------------------------------------------------------
    def _plot_pressure(self, result: dict) -> None:
        """Draw pressure field as pcolormesh."""
        self._fig_pressure.clear()
        ax = self._fig_pressure.add_subplot(111)

        X = result["X"]
        Y = result["Y"]
        p = result["pressure"]

        c = ax.pcolormesh(X, Y, p, shading="auto", cmap="jet")
        self._fig_pressure.colorbar(c, ax=ax, label="p / p_s")
        ax.set_xlabel("Axial coordinate (z)")
        ax.set_ylabel("Circumferential coordinate (x)")
        ax.set_title("Pressure Field (nondimensional)")
        ax.set_aspect("auto")
        self._fig_pressure.tight_layout()
        self._canvas_pressure.draw()

    def _plot_force(self, result: dict) -> None:
        """Draw horizontal bar chart of Fx, Fy."""
        self._fig_force.clear()
        ax = self._fig_force.add_subplot(111)

        labels = ["Fx", "Fy"]
        values = [result["Fx"], result["Fy"]]
        colors = ["steelblue", "indianred"]

        ax.barh(labels, values, color=colors, height=0.5)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Force (N)")
        ax.set_title("Load Capacity")
        self._fig_force.tight_layout()
        self._canvas_force.draw()

    def _clear_plots(self) -> None:
        """Clear all plot canvases."""
        self._fig_pressure.clear()
        self._canvas_pressure.draw()
        self._fig_force.clear()
        self._canvas_force.draw()


# ===========================================================================
# Entry Point
# ===========================================================================

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = BearingGui()
    window.show()
    sys.exit(app.exec())
