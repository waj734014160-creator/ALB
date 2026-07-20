# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


repo_root = Path(SPECPATH).resolve().parents[3]
entry_script = repo_root / "tools" / "manual" / "alb_gui_app.py"
conda_bin = Path(sys.prefix) / "Library" / "bin"

datas = collect_data_files("matplotlib")
binaries = []
for dll_name in (
    "pyside6.cp310-win_amd64.dll",
    "shiboken6.cp310-win_amd64.dll",
    "jpeg8.dll",
    "tiff.dll",
    "libwebp.dll",
    "libwebpmux.dll",
    "libwebpdemux.dll",
    "lcms2.dll",
    "openjp2.dll",
    "freetype.dll",
    "libpng16.dll",
    "zlib.dll",
    "zstd.dll",
    "yaml.dll",
    "libmmd.dll",
    "libifcoremd.dll",
    "libblas.dll",
    "liblapack.dll",
    "Qt6Svg.dll",
    "double-conversion.dll",
    "graphite2.dll",
    "harfbuzz.dll",
    "harfbuzz-subset.dll",
    "harfbuzz-icu.dll",
    "icudt75.dll",
    "icuin75.dll",
    "icuuc75.dll",
    "pcre2-16.dll",
    "pcre2-8.dll",
    "Qt6Network.dll",
    "Qt6OpenGL.dll",
    "Qt6OpenGLWidgets.dll",
):
    dll_path = conda_bin / dll_name
    if dll_path.is_file():
        binaries.append((str(dll_path), "."))
hiddenimports = [
    "matplotlib.backends.backend_qtagg",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "json5",
    "control",
    "slycot",
    "skfem",
    "skfem.assembly",
    "skfem.helpers",
    "scipy.optimize",
    "scipy.sparse",
    "scipy.sparse.linalg",
    "tqdm",
    "ALB.alb",
    "ALB.base",
    "ALB.physics.bearing",
    "ALB.boundary",
    "ALB.config",
    "ALB.control.controllers",
    "ALB.damping",
    "ALB.physics.film",
    "ALB.gauss",
    "ALB.control.state_space",
    "ALB.matrix.dynmaic",
    "ALB.matrix.static",
    "ALB.mesh",
    "ALB.physics.thermal.scales",
    "ALB.dynamics.orbit",
    "ALB.physics.hydraulics.orifice",
    "ALB.results",
    "ALB.control.valve",
    "ALB.physics.thermal",
    "ALB.tool",
]
hiddenimports += collect_submodules("tools.manual.alb_gui")


a = Analysis(
    [str(entry_script)],
    pathex=[str(repo_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(repo_root / "tools" / "manual" / "alb_gui" / "pyinstaller" / "pyi_rth_alb_gui_dll_path.py")
    ],
    excludes=[
        "tkinter",
        "pytest",
        "IPython",
        "jupyter",
        "notebook",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "ALB.surrogate.inference",
        "ALB.surrogate.training",
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "jax",
        "sklearn",
        "plotly",
        "ross",
        "pyvista",
        "vtk",
        "IPython",
        "jupyterlab",
        "h5py",
        "netCDF4",
        "cftime",
        "zmq",
        "openpyxl",
        "lxml",
        "fsspec",
        "tables",
        "xarray",
        "pyarrow",
        "fastparquet",
        "sqlalchemy",
        "PIL.ImageQt",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ALB_GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ALB_GUI",
)
