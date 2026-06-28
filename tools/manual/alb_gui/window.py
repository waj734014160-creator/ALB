"""PySide6 main window for the ALB GUI."""

from __future__ import annotations

import copy
import traceback
from typing import Any, Callable

import matplotlib
import numpy as np

matplotlib.use("QtAgg")
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Arial Unicode MS",
    "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from PySide6.QtCore import Qt, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
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

from .backend import (
    DynamicResult,
    StaticResult,
    clone_config,
    run_dynamic_calculation,
    run_static_calculation,
)
from .config_io import RUNTIME_CONFIG_PATH, load_initial_gui_config, load_paper_gui_config, save_runtime_config


STYLE_SHEET = """
QMainWindow, QWidget {
    background: #0b1117;
    color: #d7e1e8;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QGroupBox {
    border: 1px solid #1e3a44;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px 8px 6px 8px;
    background: #101922;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #72f2d0;
    font-weight: 600;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
    background: #0e1720;
    border: 1px solid #24414a;
    border-radius: 4px;
    padding: 3px;
    color: #e6f2f5;
    selection-background-color: #1e8a88;
}
QPushButton {
    background: #12343d;
    border: 1px solid #2c6f73;
    border-radius: 5px;
    padding: 7px 10px;
    color: #e6f2f5;
}
QPushButton:hover {
    background: #16515c;
}
QPushButton:disabled {
    color: #6e7d83;
    border-color: #1b2a31;
    background: #0d151c;
}
QTabWidget::pane {
    border: 1px solid #1e3a44;
}
QTabBar::tab {
    background: #101922;
    color: #aebdc5;
    padding: 8px 12px;
    border: 1px solid #1e3a44;
}
QTabBar::tab:selected {
    color: #72f2d0;
    background: #13232b;
}
QStatusBar {
    background: #081017;
    color: #94aab3;
}
QProgressBar {
    background: #0e1720;
    border: 1px solid #24414a;
    border-radius: 4px;
    color: #e6f2f5;
    min-height: 20px;
    text-align: center;
}
QProgressBar::chunk {
    background: #24b8a7;
    border-radius: 3px;
}
"""


class ComputeWorker(QThread):
    """Run a GUI calculation in a worker thread."""

    progress = Signal(int, str)
    finished = Signal(object)

    def __init__(self, func: Callable[..., object], config: dict) -> None:
        super().__init__()
        self._func = func
        self._config = config

    def run(self) -> None:
        try:
            self.finished.emit(
                self._func(self._config, progress_callback=self.progress.emit)
            )
        except Exception as exc:
            exc._worker_traceback = traceback.format_exc()
            self.finished.emit(exc)


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Double spin box that keeps mouse wheel events for the scroll area."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """Integer spin box that keeps mouse wheel events for the scroll area."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class NoWheelComboBox(QComboBox):
    """Combo box that does not change selection on mouse wheel."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class ParameterPanel(QWidget):
    """Grouped parameter controls for ALB GUI input."""

    changed = Signal()
    _DISPLAY_SCALES = {
        ("bearing", "c"): 1e6,
        ("dynamic", "a"): 1e6,
        ("dynamic", "b"): 1e6,
        ("dynamic", "a0"): 1e6,
        ("dynamic", "b0"): 1e6,
    }

    def __init__(self, config: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._widgets: dict[tuple[str, str], QWidget] = {}
        self._config = copy.deepcopy(config)
        self._loading = False
        self._setup_ui()
        self.set_config(config)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._add_bearing_group(layout)
        self._add_fluid_group(layout)
        self._add_boundary_group(layout)
        self._add_thermal_group(layout)
        self._add_pid_group(layout)
        self._add_dynamic_group(layout)
        layout.addStretch(1)

    def _add_group(self, layout: QVBoxLayout, title: str) -> QFormLayout:
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addWidget(group)
        return form

    def _add_double(
        self,
        form: QFormLayout,
        section: str,
        key: str,
        label: str,
        *,
        minimum: float = -1e12,
        maximum: float = 1e12,
        decimals: int = 6,
        step: float = 1.0,
        suffix: str = "",
    ) -> None:
        widget = NoWheelDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setSingleStep(step)
        widget.setSuffix(suffix)
        widget.valueChanged.connect(self._emit_changed)
        form.addRow(label, widget)
        self._widgets[(section, key)] = widget

    def _add_int(
        self,
        form: QFormLayout,
        section: str,
        key: str,
        label: str,
        *,
        minimum: int = 0,
        maximum: int = 100000,
    ) -> None:
        widget = NoWheelSpinBox()
        widget.setRange(minimum, maximum)
        widget.valueChanged.connect(self._emit_changed)
        form.addRow(label, widget)
        self._widgets[(section, key)] = widget

    def _add_check(
        self, form: QFormLayout, section: str, key: str, label: str
    ) -> None:
        widget = QCheckBox()
        widget.stateChanged.connect(self._emit_changed)
        form.addRow(label, widget)
        self._widgets[(section, key)] = widget

    def _add_combo(
        self,
        form: QFormLayout,
        section: str,
        key: str,
        label: str,
        values: list[str],
    ) -> None:
        widget = NoWheelComboBox()
        widget.addItems(values)
        widget.currentTextChanged.connect(self._emit_changed)
        form.addRow(label, widget)
        self._widgets[(section, key)] = widget

    def _add_bearing_group(self, layout: QVBoxLayout) -> None:
        form = self._add_group(layout, "瓦块结构参数")
        self._add_double(form, "bearing", "freq", "转频", minimum=1e-6, maximum=5000, decimals=4, suffix=" Hz")
        self._add_double(form, "bearing", "e", "偏心率", minimum=0, maximum=0.99, decimals=5, step=0.01)
        self._add_double(form, "bearing", "angle", "偏位角", minimum=-360, maximum=360, decimals=3, suffix=" deg")
        self._add_double(form, "bearing", "r", "半径 r", minimum=1e-6, maximum=10, decimals=6, suffix=" m")
        self._add_double(form, "bearing", "l", "长度 l", minimum=1e-6, maximum=10, decimals=6, suffix=" m")
        self._add_double(form, "bearing", "c", "间隙 c", minimum=0.001, maximum=10000, decimals=6, suffix=" um")
        self._add_double(form, "bearing", "lx", "周向长度", minimum=1, maximum=360, decimals=3, suffix=" deg")
        self._add_double(form, "bearing", "lz", "轴向长度", minimum=0.01, maximum=100, decimals=4)
        self._add_int(form, "bearing", "nx", "周向网格 nx", minimum=2, maximum=1000)
        self._add_int(form, "bearing", "nz", "轴向网格 nz", minimum=2, maximum=1000)
        self._add_double(form, "bearing", "bias", "瓦块偏置", minimum=-360, maximum=360, decimals=3, suffix=" deg")

    def _add_fluid_group(self, layout: QVBoxLayout) -> None:
        form = self._add_group(layout, "滑油物性参数")
        self._add_double(form, "fluid", "miu", "动力黏度 miu", minimum=0, maximum=10, decimals=6, suffix=" Pa.s")
        self._add_double(form, "fluid", "rho", "密度 rho", minimum=1, maximum=5000, decimals=3, suffix=" kg/m3")

    def _add_boundary_group(self, layout: QVBoxLayout) -> None:
        form = self._add_group(layout, "边界条件设置")
        self._add_double(form, "boundary", "ps", "供油压力", minimum=1, maximum=1e9, decimals=1, suffix=" Pa")
        self._add_double(form, "boundary", "p_set", "环境压力", minimum=-1e9, maximum=1e9, decimals=4, suffix=" Pa")
        self._add_check(form, "boundary", "reynold", "Reynolds 边界")
        self._add_check(form, "boundary", "coe", "连续边界")
        self._add_double(form, "boundary", "error_set", "压力收敛阈值", minimum=1e-14, maximum=1, decimals=12)
        self._add_int(form, "boundary", "max_iter", "最大迭代", minimum=1, maximum=10000)
        self._add_double(form, "boundary", "damp", "压力松弛", minimum=1e-6, maximum=10, decimals=6)
        self._add_double(form, "boundary", "vf", "涡动频率比", minimum=-100, maximum=100, decimals=6)
        self._add_combo(form, "boundary", "iter_method", "迭代方法", ["newton", "gauss", "lsq", "skfem_newton"])

    def _add_thermal_group(self, layout: QVBoxLayout) -> None:
        form = self._add_group(layout, "热效应")
        self._add_check(form, "thermal", "enabled", "开启热效应")
        settings = "thermal.settings"
        self._add_double(form, settings, "t_in", "入口温度", minimum=-100, maximum=300, decimals=4, suffix=" degC")
        self._add_double(form, settings, "beta", "黏温系数 beta", minimum=0, maximum=10, decimals=6)
        self._add_double(form, settings, "k_lub", "导热系数", minimum=0, maximum=100, decimals=6)
        self._add_double(form, settings, "cp_lub", "比热 cp", minimum=1, maximum=10000, decimals=3)
        self._add_double(form, settings, "heat_partition", "热分配", minimum=0, maximum=1, decimals=4)
        self._add_double(form, settings, "relax", "热松弛", minimum=0, maximum=1, decimals=4)
        self._add_double(form, settings, "tol", "热收敛阈值", minimum=1e-12, maximum=1, decimals=12)
        self._add_int(form, settings, "max_iter", "热迭代上限", minimum=1, maximum=10000)
        self._add_combo(form, settings, "coupling", "耦合模式", ["full", "half"])

    def _add_pid_group(self, layout: QVBoxLayout) -> None:
        form = self._add_group(layout, "PID 控制参数")
        self._add_double(form, "pid", "kp", "Kp", minimum=0, maximum=1000, decimals=6)
        self._add_double(form, "pid", "ki", "Ki", minimum=0, maximum=1000, decimals=6)
        self._add_double(form, "pid", "kd", "Kd", minimum=0, maximum=1000, decimals=6)
        self._add_combo(form, "pid", "servo", "伺服阀", ["moog", "static"])
        self._add_double(form, "pid", "delay", "延迟", minimum=0, maximum=10, decimals=9, suffix=" s")
        self._add_double(form, "pid", "tw", "tw", minimum=0, maximum=10, decimals=12)
        self._add_double(form, "pid", "zeta", "zeta", minimum=0, maximum=10, decimals=9)
        self._add_double(form, "pid", "tp3", "tp3", minimum=0, maximum=10, decimals=9)

    def _add_dynamic_group(self, layout: QVBoxLayout) -> None:
        form = self._add_group(layout, "动特性轨迹")
        self._add_double(form, "dynamic", "a", "x 幅值", minimum=0, maximum=1000000, decimals=6, suffix=" um")
        self._add_double(form, "dynamic", "b", "y 幅值", minimum=0, maximum=1000000, decimals=6, suffix=" um")
        self._add_double(form, "dynamic", "a0", "x 原点", minimum=-1000000, maximum=1000000, decimals=6, suffix=" um")
        self._add_double(form, "dynamic", "b0", "y 原点", minimum=-1000000, maximum=1000000, decimals=6, suffix=" um")
        self._add_double(form, "dynamic", "f0", "轨迹相位", minimum=-360, maximum=360, decimals=6)
        self._add_int(form, "dynamic", "n", "轨迹圈数", minimum=1, maximum=10000)
        self._add_int(form, "dynamic", "pt", "每圈点数", minimum=4, maximum=100000)
        self._add_int(form, "dynamic", "repeat", "FFT repeat", minimum=0, maximum=10000)
        self._add_double(form, "dynamic", "tr_start", "识别起点", minimum=0, maximum=1, decimals=4)
        self._add_double(form, "dynamic", "tr_end", "识别终点", minimum=0, maximum=1, decimals=4)

    def _emit_changed(self) -> None:
        if not self._loading:
            self.changed.emit()

    def _lookup(self, section: str, key: str) -> Any:
        if section == "thermal.settings":
            return self._config.get("thermal", {}).get("settings", {}).get(key)
        return self._config.get(section, {}).get(key)

    def _assign(self, config: dict, section: str, key: str, value: Any) -> None:
        if section == "thermal.settings":
            config.setdefault("thermal", {}).setdefault("settings", {})[key] = value
            return
        config.setdefault(section, {})[key] = value

    def _to_widget_value(self, section: str, key: str, value: Any) -> float:
        """Convert stored SI values to the unit displayed by the widget."""

        return float(value) * self._DISPLAY_SCALES.get((section, key), 1.0)

    def _from_widget_value(self, section: str, key: str, value: float) -> float:
        """Convert displayed widget values back to stored SI values."""

        return float(value) / self._DISPLAY_SCALES.get((section, key), 1.0)

    def set_config(self, config: dict) -> None:
        self._loading = True
        self._config = copy.deepcopy(config)
        try:
            for (section, key), widget in self._widgets.items():
                value = self._lookup(section, key)
                if value is None:
                    continue
                if isinstance(widget, QDoubleSpinBox):
                    if np.isfinite(float(value)):
                        widget.setValue(self._to_widget_value(section, key, value))
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QComboBox):
                    text = str(value)
                    index = widget.findText(text)
                    if index >= 0:
                        widget.setCurrentIndex(index)
        finally:
            self._loading = False

    def config(self) -> dict:
        data = copy.deepcopy(self._config)
        for (section, key), widget in self._widgets.items():
            if isinstance(widget, QDoubleSpinBox):
                value: Any = self._from_widget_value(section, key, widget.value())
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            else:
                continue
            self._assign(data, section, key, value)
        dyn = data.setdefault("dynamic", {})
        dyn["freq"] = data.get("bearing", {}).get("freq", dyn.get("freq", 50.0))
        dyn["vf"] = data.get("boundary", {}).get("vf", dyn.get("vf", 1.0))
        data.setdefault("pid", {}).pop("dt", None)
        return data


class AlbGuiWindow(QMainWindow):
    """Main window for the ALB GUI."""

    def __init__(
        self,
        *,
        config: dict | None = None,
        runtime_path=RUNTIME_CONFIG_PATH,
        prefer_runtime: bool = True,
    ) -> None:
        super().__init__()
        self.setWindowTitle("ALB GUI")
        self.resize(1420, 860)
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(STYLE_SHEET)

        self._runtime_path = runtime_path
        if config is None:
            self._config, self._source_message = load_initial_gui_config(
                runtime_path=runtime_path,
                prefer_runtime=prefer_runtime,
            )
        else:
            self._config = copy.deepcopy(config)
            self._source_message = "Loaded provided GUI config"
        self._worker: ComputeWorker | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(500)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_current_config)

        self._setup_actions()
        self._setup_ui()
        self._status.showMessage(self._source_message)

    def _setup_actions(self) -> None:
        reload_action = QAction("重新载入 paper/config 默认值", self)
        reload_action.triggered.connect(self._reload_paper_defaults)
        self.addAction(reload_action)

    def _setup_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        self._panel = ParameterPanel(self._config)
        self._panel.changed.connect(self._schedule_save)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._panel)
        scroll.setMinimumWidth(390)
        splitter.addWidget(scroll)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        toolbar = QHBoxLayout()
        self._reload_button = QPushButton("重新载入 paper/config 默认值")
        self._reload_button.setToolTip("丢弃当前 GUI 参数并重新读取论文配置目录")
        self._reload_button.clicked.connect(self._reload_paper_defaults)
        toolbar.addWidget(self._reload_button)
        toolbar.addStretch(1)
        right_layout.addLayout(toolbar)

        self._tabs = QTabWidget()
        self._setup_static_tab()
        self._setup_dynamic_tab()
        right_layout.addWidget(self._tabs, 1)
        splitter.addWidget(right)
        splitter.setSizes([430, 980])
        self.setCentralWidget(splitter)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

    def _setup_static_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        btns = QHBoxLayout()
        self._static_button = QPushButton("运行静特性计算")
        self._static_button.clicked.connect(self._run_static)
        btns.addWidget(self._static_button)
        btns.addStretch(1)
        layout.addLayout(btns)

        self._static_text = QTextEdit()
        self._static_text.setReadOnly(True)
        self._static_text.setMaximumHeight(150)
        layout.addWidget(self._static_text)

        plot_tabs = QTabWidget()
        self._fig_pressure = Figure(figsize=(6, 4), dpi=100)
        self._canvas_pressure = FigureCanvasQTAgg(self._fig_pressure)
        plot_tabs.addTab(self._canvas_pressure, "压力场")
        self._fig_temperature = Figure(figsize=(6, 4), dpi=100)
        self._canvas_temperature = FigureCanvasQTAgg(self._fig_temperature)
        plot_tabs.addTab(self._canvas_temperature, "温度场")
        layout.addWidget(plot_tabs, 1)
        self._tabs.addTab(page, "静特性计算")

    def _setup_dynamic_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        btns = QHBoxLayout()
        self._dynamic_button = QPushButton("运行动特性计算")
        self._dynamic_button.clicked.connect(self._run_dynamic)
        btns.addWidget(self._dynamic_button)
        self._dynamic_progress = QProgressBar()
        self._dynamic_progress.setRange(0, 100)
        self._dynamic_progress.setValue(0)
        self._dynamic_progress.setFormat("待运行")
        btns.addWidget(self._dynamic_progress, 1)
        btns.addStretch(1)
        layout.addLayout(btns)

        self._dynamic_text = QTextEdit()
        self._dynamic_text.setReadOnly(True)
        self._dynamic_text.setMaximumHeight(170)
        layout.addWidget(self._dynamic_text)

        plot_tabs = QTabWidget()
        self._fig_trajectory = Figure(figsize=(6, 4), dpi=100)
        self._canvas_trajectory = FigureCanvasQTAgg(self._fig_trajectory)
        plot_tabs.addTab(self._canvas_trajectory, "轨迹")
        self._fig_force = Figure(figsize=(6, 4), dpi=100)
        self._canvas_force = FigureCanvasQTAgg(self._fig_force)
        plot_tabs.addTab(self._canvas_force, "力轨迹")
        layout.addWidget(plot_tabs, 1)
        self._tabs.addTab(page, "动特性计算")

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _save_current_config(self) -> None:
        self._config = self._panel.config()
        path = save_runtime_config(self._config, self._runtime_path)
        self._status.showMessage(f"参数已自动保存: {path}")

    def _reload_paper_defaults(self) -> None:
        try:
            self._config, message = load_paper_gui_config()
            self._panel.set_config(self._config)
            self._save_current_config()
            self._status.showMessage(message)
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", str(exc))

    def _set_busy(self, busy: bool) -> None:
        self._static_button.setDisabled(busy)
        self._dynamic_button.setDisabled(busy)
        self._reload_button.setDisabled(busy)

    def _run_static(self) -> None:
        self._save_current_config()
        self._set_busy(True)
        self._status.showMessage("正在计算静特性...")
        self._worker = ComputeWorker(run_static_calculation, clone_config(self._config))
        self._worker.finished.connect(self._on_static_done)
        self._worker.start()

    def _run_dynamic(self) -> None:
        self._save_current_config()
        self._set_busy(True)
        self._on_dynamic_progress(0, "初始化动特性模型")
        self._status.showMessage("正在计算动特性...")
        self._worker = ComputeWorker(run_dynamic_calculation, clone_config(self._config))
        self._worker.progress.connect(self._on_dynamic_progress)
        self._worker.finished.connect(self._on_dynamic_done)
        self._worker.start()

    def _on_dynamic_progress(self, value: int, message: str) -> None:
        self._dynamic_progress.setValue(max(0, min(100, int(value))))
        self._dynamic_progress.setFormat(f"{self._dynamic_progress.value()}%  {message}")
        self._status.showMessage(message)

    def _handle_error(self, title: str, result: object) -> bool:
        if not isinstance(result, Exception):
            return False
        tb = getattr(result, "_worker_traceback", "")
        QMessageBox.critical(self, title, f"{result}\n\n{tb}")
        self._status.showMessage(f"{title}: {result}")
        if title.startswith("动特性"):
            self._on_dynamic_progress(0, "计算失败")
        self._set_busy(False)
        return True

    def _on_static_done(self, result: object) -> None:
        if self._handle_error("静特性计算失败", result):
            return
        assert isinstance(result, StaticResult)
        self._set_busy(False)
        force = result.force
        lines = [
            "=== 静特性计算 ===",
            f"Fx = {force[0]:.6e} N",
            f"Fy = {force[1]:.6e} N",
            f"|F| = {np.linalg.norm(force):.6e} N",
            f"Friction = {result.friction:.6e}",
            "",
            "Pad status:",
        ]
        for idx, status in enumerate(result.pad_status):
            lines.append(f"  pad{idx}: {status}")
        self._static_text.setText("\n".join(lines))
        self._plot_field(self._fig_pressure, self._canvas_pressure, result.pressure, "合并压力场", "p [Pa]", "viridis")
        if result.temperature is not None:
            self._plot_field(self._fig_temperature, self._canvas_temperature, result.temperature, "合并温度场", "T [degC]", "inferno")
        else:
            self._fig_temperature.clear()
            ax = self._fig_temperature.add_subplot(111)
            ax.text(0.5, 0.5, "未开启热效应", ha="center", va="center", color="#d7e1e8")
            ax.set_axis_off()
            self._canvas_temperature.draw()
        self._status.showMessage("静特性计算完成")

    def _on_dynamic_done(self, result: object) -> None:
        if self._handle_error("动特性计算失败", result):
            return
        assert isinstance(result, DynamicResult)
        self._set_busy(False)
        self._on_dynamic_progress(100, "动特性计算完成")
        k = result.stiffness
        c = result.damping
        self._dynamic_text.setText(
            "=== 动特性计算 ===\n"
            f"Stiffness K (N/m):\n"
            f"[[{k[0, 0]:.6e}, {k[0, 1]:.6e}],\n"
            f" [{k[1, 0]:.6e}, {k[1, 1]:.6e}]]\n\n"
            f"Damping C (N*s/m):\n"
            f"[[{c[0, 0]:.6e}, {c[0, 1]:.6e}],\n"
            f" [{c[1, 0]:.6e}, {c[1, 1]:.6e}]]"
        )
        self._plot_xy(self._fig_trajectory, self._canvas_trajectory, result.trajectory, "转子中心轨迹", "ux [m]", "uy [m]")
        self._plot_xy(self._fig_force, self._canvas_force, result.force_track, "油膜力轨迹", "Fx [N]", "Fy [N]")
        self._status.showMessage("动特性计算完成")

    def _plot_field(
        self,
        fig: Figure,
        canvas: FigureCanvasQTAgg,
        field,
        title: str,
        colorbar_label: str,
        cmap: str,
    ) -> None:
        fig.clear()
        ax = fig.add_subplot(111)
        values = np.ma.asarray(field.values).T
        mesh = ax.pcolormesh(field.theta_deg, field.z, values, shading="auto", cmap=cmap)
        fig.colorbar(mesh, ax=ax, label=colorbar_label)
        ax.set_xlabel("Circumferential angle [deg]")
        ax.set_ylabel("Axial coordinate")
        ax.set_title(title)
        fig.tight_layout()
        canvas.draw()

    def _plot_xy(
        self,
        fig: Figure,
        canvas: FigureCanvasQTAgg,
        values: np.ndarray,
        title: str,
        xlabel: str,
        ylabel: str,
    ) -> None:
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(values[:, 0], values[:, 1], color="#72f2d0", linewidth=1.4)
        ax.axhline(0.0, color="#41535b", linewidth=0.8)
        ax.axvline(0.0, color="#41535b", linewidth=0.8)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.set_aspect("equal", adjustable="datalim")
        fig.tight_layout()
        canvas.draw()


def main() -> int:
    """Run the desktop application."""

    import sys

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AlbGuiWindow()
    window.show()
    return int(app.exec())
