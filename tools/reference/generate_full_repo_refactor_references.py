"""Generate deterministic ALB_MAIN 0.2.0 full-refactor references.

The artifacts produced by this script freeze the current numerical behavior
before production modules are moved.  Existing v1 artifacts are never read as
generation targets and this script refuses to overwrite any output file.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
import pickle
import platform
import random
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


# Stabilize native-library scheduling before importing numerical packages.
for _thread_variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_thread_variable, "1")

import numpy as np
import pandas as pd
import scipy.sparse as sp
import torch

torch.set_num_threads(1)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    # PyTorch permits configuring inter-op threads only before parallel work.
    pass


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ALB.alb import nodim_alb
from ALB import StepContext
from ALB.core.fem import _assemble_matrixs, _assemble_rights
from ALB.physics.bearing import (
    HydrostaticBearing,
    NodimHydrostaticBearing,
    nodim_four_pads_bearing,
)
from ALB.core.fem.boundary import (
    couple_boundary_matrix,
    set_continuity_boundary,
    set_value_boundary,
)
from ALB.config import (
    GasConfig,
    HydConfig,
    Moog2ndServoConfig,
    NodimALBConfig,
    NodimOrificeConfig,
    NodimPadConfig,
    PIDConfig,
)
from ALB.control.pid import PID
from ALB.dynamics.coupling import RsRotorBearingCouple
from ALB.physics.gas import GasBearing
from ALB.core.numerics.iteration import gauss_seidel_iteration_film
from ALB.harmonic_linear import alb_harmonic_linear
from ALB.core.numerics.dynamic import calc_fe_dx, calc_ke_dx
from ALB.core.numerics.static import calc_fe, calc_fe_vf, calc_ke
from ALB.core.fem.mesh import create_rect, create_serend_2d
from ALB.surrogate.inference import (
    ALBNN,
    ALBNNC4Canonical,
    ALBNN_BASE_INPUT_COLS,
    Net,
    albnn_augment_frame,
    c4_canonicalize_albnn_frame,
)
from ALB.physics.hydraulics import NodimCSOrifice
from ALB.remote import job as remote_job
from ALB.remote.transport import (
    encode_powershell,
    powershell_encoded_command,
    ps_quote,
    remote_path,
)
from ALB.results import DataFrameResult, NpyResult, SaveTreeNode
from ALB.dynamics.rotor import RossRotor
from ALB.control.valve import moog_2nd_servovalve
from ALB.config import ThermalConfig
from ALB.physics.thermal import ThermalHydroBearing
from ALB.surrogate.training.losses import sample_loss_values, weighted_mean
from ALB.surrogate.training.transforms import MidpointMinMaxScaler
from ALB.core import Signal, TimeIterDt


EXPECTED_BASELINE_COMMIT = "a4b2be1abc2efdea0d49e49cf4996ec48fb531c2"
REFERENCE_SCHEMA = "alb.full-repo-refactor-reference.v1"
SEED = 20260720
DEFAULT_OUTPUT_DIR = REPO_ROOT / "refs" / "full_repo_refactor_v1"
DOMAIN_ORDER = (
    "core_fem",
    "film",
    "hydraulics_orifice",
    "bearing",
    "gas",
    "thermal",
    "control_valve",
    "dynamics_coupling",
    "systems_alb_harmonic",
    "surrogate_training",
    "remote_persistence",
)


@dataclass(frozen=True)
class CaseData:
    """Stable metadata and exact numerical arrays for one reference domain."""

    metadata: dict[str, Any]
    arrays: dict[str, np.ndarray]


class _IdentityScaler:
    """Minimal deterministic scaler used to isolate ALBNN inference."""

    def __init__(self, columns: list[str]) -> None:
        self.feature_names_in_ = np.asarray(columns, dtype=object)

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        return frame[list(self.feature_names_in_)].to_numpy(dtype=np.float32)

    def inverse_transform(self, values: Any) -> np.ndarray:
        return np.asarray(values, dtype=float)


class _FirstTwoColumnsNet:
    """Return the first two scaled columns as a deterministic force pair."""

    def eval(self) -> None:
        return None

    def __call__(self, values: torch.Tensor) -> torch.Tensor:
        return values[:, :2]


class _ReferenceRotor:
    """Small rotor port used to freeze rotor-bearing exchange sequencing."""

    def __init__(self, position: np.ndarray) -> None:
        self.signal = Signal(sys=self)
        base = np.asarray(position, dtype=float).reshape(2)
        self.positions = np.vstack(
            (base, base + [1.0e-6, 0.0], base + [0.0, -1.5e-6])
        )
        self.velocities = np.array(
            [[0.0, 0.0], [1.0e-4, -2.0e-4], [-3.0e-4, 4.0e-4]]
        )
        self.output_index = 0
        self.time_history: list[float] = []
        self.force_history: list[np.ndarray] = []
        self.previous_force_history: list[np.ndarray] = []

    def init(self) -> None:
        self.output_index = 0
        self.time_history = []
        self.force_history = []
        self.previous_force_history = []

    def output(self, node_links: Any) -> dict[str, np.ndarray]:
        count = len(np.asarray(node_links).reshape(-1))
        index = min(self.output_index, len(self.positions) - 1)
        return {
            "uxy": np.repeat(self.positions[index][None, :], count, axis=0),
            "uxyt": np.repeat(self.velocities[index][None, :], count, axis=0),
        }

    def input_force2node(
        self,
        t: float,
        force: np.ndarray,
        node_links: Any,
        force0: np.ndarray | None = None,
    ) -> None:
        del node_links
        self.time_history.append(float(t))
        self.force_history.append(np.asarray(force, dtype=float).copy())
        self.previous_force_history.append(np.asarray(force0, dtype=float).copy())

    def advance(self) -> None:
        self.output_index = min(self.output_index + 1, len(self.positions) - 1)

    def finish_signal(self) -> None:
        return None

    def save(self, tofile: bool = False, *args: Any, **kwargs: Any) -> SaveTreeNode:
        del tofile, args, kwargs
        return SaveTreeNode(
            "reference_rotor",
            DataFrameResult({"rotor": pd.DataFrame()}),
        )


class _LinearRotorPlant:
    """Provide a fixed continuous state-space model to the ROSS wrapper."""

    ndof = 1
    number_dof = 1

    def _lti(self, speed: float) -> SimpleNamespace:
        del speed
        return SimpleNamespace(
            A=np.array([[-1.5, 0.25], [-0.5, -0.75]], dtype=float),
            B=np.array([[1.0], [0.2]], dtype=float),
            C=np.eye(2, dtype=float),
            D=np.zeros((2, 1), dtype=float),
        )


def _git_head() -> str:
    """Return the exact source commit used for generation."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _ensure_baseline_source() -> str:
    """Reject generation after production source or package metadata changes."""

    head = _git_head()
    if head != EXPECTED_BASELINE_COMMIT:
        raise RuntimeError(
            f"Reference generation requires {EXPECTED_BASELINE_COMMIT}, got {head}"
        )
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "ALB",
            "pyproject.toml",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise RuntimeError(
            "Production source is dirty; refusing to generate refs:\n"
            + result.stdout
        )
    return head


def _reset_random_state() -> None:
    """Reset all randomness used by reference cases."""

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    torch.use_deterministic_algorithms(True)


def _distribution_version(name: str) -> str | None:
    """Return an installed distribution version when available."""

    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _array_manifest(arrays: dict[str, np.ndarray]) -> dict[str, dict[str, Any]]:
    """Describe every exact array stored in one NPZ artifact."""

    return {
        name: {
            "shape": list(np.asarray(value).shape),
            "dtype": str(np.asarray(value).dtype),
            "sha256": hashlib.sha256(
                np.ascontiguousarray(value).view(np.uint8)
            ).hexdigest(),
        }
        for name, value in arrays.items()
    }


def _record_residuals(model: Any) -> list[float]:
    """Attach a non-invasive recorder to one legacy calc_error method."""

    history: list[float] = []
    original = model.calc_error

    def recorded(*args: Any, **kwargs: Any) -> Any:
        value = original(*args, **kwargs)
        array = np.asarray(value)
        if array.size == 1 and not isinstance(value, (bool, np.bool_)):
            history.append(float(array.reshape(-1)[0]))
        return value

    model.calc_error = recorded
    return history


def _core_fem_case() -> CaseData:
    """Freeze mesh order, assembly order, boundaries, and matrix kernels."""

    points, elements = create_rect(
        np.array([-0.25, 0.75]), np.array([0.0, 2.0]), np.array([2, 2])
    )
    serend_points, serend_elements = create_serend_2d(
        np.array([0.0, 1.0]), np.array([-1.0, 1.0]), np.array([2, 1])
    )
    element_matrices = np.array(
        [
            [[2.0, -1.0, 0.5], [-1.0, 3.0, -0.25], [0.5, -0.25, 1.5]],
            [[1.5, 0.25, -0.5], [0.25, 2.5, -1.0], [-0.5, -1.0, 2.0]],
        ],
        dtype=float,
    )
    mappings = np.array([[0, 1, 2], [1, 2, 3]], dtype=np.int64)
    element_rights = np.array([[1.0, 2.0, 3.0], [-1.0, 0.5, 2.5]])
    assembled_matrix = _assemble_matrixs(element_matrices, mappings, 4).toarray()
    assembled_right = _assemble_rights(element_rights, mappings, 4)
    continuity_k, continuity_f = set_continuity_boundary([0, 2], [1, 3], 4)
    value_k, value_f = set_value_boundary(4, [0, 3], p_set=0.75)
    coupled_matrix, coupled_right = couple_boundary_matrix(
        sp.csc_matrix(assembled_matrix),
        assembled_right,
        [sp.csr_matrix(continuity_k), sp.csr_matrix(value_k)],
        [continuity_f, value_f],
    )
    h = np.array([0.85, 0.95, 1.1, 1.05], dtype=float)
    gauss_solution, gauss_iterations, gauss_error = gauss_seidel_iteration_film(
        np.array([[4.0, -1.0], [-1.0, 3.0]]),
        np.array([1.0, 2.0]),
        np.zeros(2),
        np.zeros(2),
        error_set=1.0e-12,
        n=50,
        damp=0.8,
        reynold=True,
    )
    arrays = {
        "rect_points": points,
        "rect_elements": elements,
        "serend_points": serend_points,
        "serend_elements": serend_elements,
        "assembled_matrix": assembled_matrix,
        "assembled_right": assembled_right,
        "continuity_matrix": continuity_k,
        "continuity_right": continuity_f,
        "value_matrix": value_k,
        "value_right": value_f,
        "coupled_matrix": coupled_matrix.toarray(),
        "coupled_right": coupled_right,
        "static_ke": calc_ke(h, 0.75, 0.4, 0.3),
        "static_fe": calc_fe(h, 0.4, 1.25),
        "static_fe_vf": calc_fe_vf(0.2, 0.3, 0.4, 1.25, 0.7, -0.1, 0.2),
        "dynamic_ke_dx": calc_ke_dx(0.2, 0.75, 0.3, 0.4, h),
        "dynamic_fe_dx": calc_fe_dx(0.2, 0.3, 0.4, 1.25),
        "gauss_solution": gauss_solution,
        "gauss_summary": np.array([gauss_iterations, gauss_error], dtype=float),
    }
    return CaseData(
        metadata={
            "purpose": "FEM node/element ordering, assembly, boundaries, and kernels",
            "fixed_inputs": {
                "rect_size": [2, 2],
                "assembly_freedoms": 4,
                "gauss_max_iterations": 50,
            },
        },
        arrays=arrays,
    )


def _film_case() -> CaseData:
    """Freeze one dimensional Reynolds film solve and residual sequence."""

    config = HydConfig(
        nx=7,
        nz=5,
        e=0.2,
        angle=25.0,
        l=0.08,
        ps=3.0e6,
        freq=50.0,
        coe=False,
        reynold=True,
        max_iter=20,
        error_set=1.0e-9,
        iter_method="newton",
        damp=0.7,
    )
    bearing = HydrostaticBearing(config)
    residuals = _record_residuals(bearing.main_model)
    bearing.init()
    uxy = np.array([0.12, -0.07])
    uxyt = np.array([0.015, -0.01])
    bearing.input(uxy, uxyt, nodim=True)
    output = bearing.output(nodim=True)
    arrays = {
        "input_uxy": uxy,
        "input_uxyt": uxyt,
        "pressure": np.asarray(bearing.main_model.latest_result, dtype=float),
        "pressure_field": np.asarray(bearing.postprocess.p, dtype=float),
        "thickness": np.array(
            [node.h for node in bearing.main_model.nodes.values()], dtype=float
        ),
        "force_nondim": np.asarray(output["force"], dtype=float),
        "force_dimensional": np.asarray(
            bearing.calc_capacity(calc=False, nodim=False), dtype=float
        ),
        "friction_nondim": np.asarray([output["friction"]], dtype=float),
        "residual_history": np.asarray(residuals, dtype=float),
    }
    return CaseData(
        metadata={
            "purpose": "Reynolds film field, force, and residual order",
            "config": {
                "nx": config.nx,
                "nz": config.nz,
                "max_iter": config.max_iter,
                "error_set": config.error_set,
                "damp": config.damp,
                "iter_method": config.iter_method,
            },
            "final_iter": int(bearing.final_iter),
            "converged": bool(bearing.calc_is_finished()),
        },
        arrays=arrays,
    )


def _hydraulics_orifice_case() -> CaseData:
    """Freeze restrictor flow coupled to a nondimensional Reynolds pad."""

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
        max_iter=8,
        error_set=1.0e-9,
        damp=0.8,
    )
    orifice = NodimCSOrifice(
        position=np.array([[0.35, 0.35], [0.65, 0.65]]),
        cq0=0.2,
        cq1=1.0,
        cq2=0.1,
    )
    orifice.xv = 0.45
    bearing.add_simple_model(orifice)
    residuals = _record_residuals(bearing.main_model)
    bearing.init()
    uxy = np.array([0.05, -0.02])
    uxyt = np.array([0.01, 0.0])
    bearing.input(uxy, uxyt, nodim=True)
    output = bearing.output(nodim=True)
    flow_info = orifice.flow_info(bearing.main_model)
    arrays = {
        "input_uxy": uxy,
        "input_uxyt": uxyt,
        "pressure": np.asarray(bearing.main_model.latest_result, dtype=float),
        "force": np.asarray(output["force"], dtype=float),
        "qn": np.asarray(orifice.qn, dtype=float),
        "flow": np.asarray(flow_info["flow"], dtype=float),
        "flow_nondim": np.asarray(
            [item["q_nondim"] for item in flow_info["flow_params"]], dtype=float
        ),
        "flow_volumetric": np.asarray(
            [item["q_vol"] for item in flow_info["flow_params"]], dtype=float
        ),
        "residual_history": np.asarray(residuals, dtype=float),
    }
    return CaseData(
        metadata={
            "purpose": "Orifice pressure-flow coupling and pad response",
            "orifice_count": len(flow_info["flow_params"]),
            "final_iter": int(bearing.final_iter),
            "converged": bool(bearing.calc_is_finished()),
        },
        arrays=arrays,
    )


def _bearing_case() -> CaseData:
    """Freeze four-pad aggregation, pad order, and local residual histories."""

    bearing = nodim_four_pads_bearing(
        lambda_value=1.2,
        lr=1.0,
        lx=90.0,
        lz=2.0,
        nx=5,
        nz=3,
        bias=0.0,
        coe=False,
        max_iter=8,
        error_set=1.0e-9,
        damp=0.8,
    )
    residuals = [_record_residuals(pad.main_model) for pad in bearing.bearings]
    bearing.init()
    uxy = np.array([0.04, -0.03])
    uxyt = np.array([0.01, -0.02])
    bearing.input(uxy, uxyt, t=0.125, nodim=True)
    output = bearing.output(nodim=True)
    residual_offsets = np.cumsum([0, *[len(values) for values in residuals]])
    arrays = {
        "input_uxy": uxy,
        "input_uxyt": uxyt,
        "aggregate_force": np.asarray(output["force"], dtype=float),
        "aggregate_friction": np.asarray([output["friction"]], dtype=float),
        "pad_force": np.vstack(
            [pad.calc_capacity(calc=False, nodim=True) for pad in bearing.bearings]
        ),
        "pad_pressure": np.stack(
            [pad.main_model.latest_result for pad in bearing.bearings]
        ),
        "pad_residual_history": np.concatenate(
            [np.asarray(values, dtype=float) for values in residuals]
        ),
        "pad_residual_offsets": residual_offsets,
        "result_rows": bearing.results.to_numpy(dtype=float),
    }
    return CaseData(
        metadata={
            "purpose": "Four-pad ordering and aggregate bearing behavior",
            "pad_order": ["up", "down", "right", "left"],
            "pad_final_iterations": [
                int(pad.final_iter) for pad in bearing.bearings
            ],
            "converged": bool(bearing.calc_is_finished()),
        },
        arrays=arrays,
    )


def _gas_case() -> CaseData:
    """Freeze gas-film pressure, force, and iteration behavior."""

    config = GasConfig(
        e=0.25,
        angle=30.0,
        nx=12,
        nz=8,
        max_iter=15,
        error_set=1.0e-8,
        damp=0.7,
        coe=True,
        reynold=True,
    )
    bearing = GasBearing(config)
    residuals = _record_residuals(bearing.main_model)
    bearing.solve()
    arrays = {
        "pressure": np.asarray(bearing.main_model.latest_result, dtype=float),
        "pressure_field": np.asarray(bearing.postprocess.p, dtype=float),
        "force": np.asarray(bearing.calc_capacity(nodim=True), dtype=float),
        "residual_history": np.asarray(residuals, dtype=float),
    }
    return CaseData(
        metadata={
            "purpose": "Gas bearing pressure and load behavior",
            "config": {"nx": config.nx, "nz": config.nz, "damp": config.damp},
            "final_iter": int(bearing.final_iter),
            "converged": bool(bearing.calc_is_finished()),
        },
        arrays=arrays,
    )


def _thermal_case() -> CaseData:
    """Freeze coupled pressure-temperature-viscosity state and convergence."""

    hyd_config = HydConfig(
        nx=7,
        nz=5,
        e=0.2,
        angle=30.0,
        l=0.08,
        max_iter=40,
        error_set=1.0e-8,
        iter_method="newton",
    )
    thermal_config = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        k_lub=0.0,
        relax=0.6,
        max_iter=12,
        tol=0.03,
        coupling="full",
        pressure_backend="skfem",
        supg=True,
        args_nodim=False,
        delta_t_scale=30.0,
    )
    pad = HydrostaticBearing(hyd_config)
    pressure_residuals = _record_residuals(pad.main_model)
    bearing = ThermalHydroBearing(pad, thermal_config)
    bearing.init()
    uxy = np.array([1.6e-5, -0.8e-5])
    uxyt = np.array([0.0, 0.0])
    bearing.input(uxy, uxyt)
    output = bearing.output(calc=True, nodim=True)
    thermal_state = bearing.thermal_state

    transient_hyd_config = HydConfig(
        nx=5,
        nz=3,
        e=0.15,
        angle=15.0,
        l=0.08,
        max_iter=30,
        error_set=1.0e-8,
        iter_method="newton",
        damp=0.6,
    )
    transient_config = ThermalConfig(
        t_in=40.0,
        beta=0.03,
        k_lub=0.0,
        relax=0.5,
        max_iter=8,
        tol=0.03,
        coupling="full",
        pressure_backend="skfem",
        args_nodim=False,
        transient_enabled=True,
        dt=0.005,
    )
    transient = ThermalHydroBearing(
        HydrostaticBearing(transient_hyd_config), transient_config
    )
    transient.init()
    transient_positions = np.array(
        [[1.2e-5, 0.0], [1.0e-5, 0.4e-5], [0.6e-5, 0.8e-5]]
    )
    transient_velocities = np.array(
        [[0.0, 0.0], [-4.0e-4, 8.0e-4], [-8.0e-4, 8.0e-4]]
    )
    transient_temperatures = []
    transient_forces = []
    transient_effective_temperatures = []
    transient_committed_states = []
    for index, (position, velocity) in enumerate(
        zip(transient_positions, transient_velocities)
    ):
        transient.input(
            position,
            velocity,
            t=index * transient_config.dt,
            nodim=False,
        )
        transient_output = transient.output(calc=True, nodim=False)
        transient_temperatures.append(transient_output["temperature"])
        transient_forces.append(transient_output["force"])
        transient_effective_temperatures.append(transient_output["t_eff"])
        transient_committed_states.append(transient._temperature_prev.copy())
    arrays = {
        "input_uxy": uxy,
        "input_uxyt": uxyt,
        "force": np.asarray(output["force"], dtype=float),
        "pressure_field": np.asarray(output["pressure_field"], dtype=float),
        "temperature_field": np.asarray(output["temperature_field"], dtype=float),
        "temperature_film": np.asarray(output["temperature_film"], dtype=float),
        "viscosity_field": np.asarray(output["viscosity_field"], dtype=float),
        "viscosity_field_grid": np.asarray(
            output["viscosity_field_grid"], dtype=float
        ),
        "thermal_relax_history": np.asarray(
            output["thermal_relax_history"], dtype=float
        ),
        "pressure_residual_history": np.asarray(pressure_residuals, dtype=float),
        "thermal_scalars": np.asarray(
            [
                output["t_eff"],
                output["viscosity"],
                output["friction"],
                output["q_orifice_total"],
                output["thermal_newton_residual"],
            ],
            dtype=float,
        ),
        "transient_positions": transient_positions,
        "transient_velocities": transient_velocities,
        "transient_temperature": np.stack(transient_temperatures),
        "transient_force": np.vstack(transient_forces),
        "transient_t_eff": np.asarray(
            transient_effective_temperatures, dtype=float
        ),
        "transient_committed_temperature": np.stack(
            transient_committed_states
        ),
    }
    return CaseData(
        metadata={
            "purpose": "Thermal coupling fields, memory, and local convergence",
            "hyd_config": {"nx": hyd_config.nx, "nz": hyd_config.nz},
            "thermal_config": {
                "max_iter": thermal_config.max_iter,
                "tol": thermal_config.tol,
                "coupling": thermal_config.coupling,
            },
            "thermal_iterations": int(output["thermal_iterations"]),
            "thermal_converged": bool(output["thermal_converged"]),
            "thermal_solver_used": str(output["thermal_solver_used"]),
            "thermal_state_keys": sorted(thermal_state),
            "transient_steps": len(transient_temperatures),
            "transient_commits_per_step": 1,
        },
        arrays=arrays,
    )


def _control_valve_case() -> CaseData:
    """Freeze PID state updates and servo-valve LTI command sequencing."""

    pid = PID(
        PIDConfig(
            kp=0.5,
            ki=0.1,
            kd=0.02,
            freq=50.0,
            dt=1.0e-3,
        )
    )
    pid.init()
    times = np.array([0.0, 1.0e-3, 2.0e-3, 3.0e-3])
    errors = np.array(
        [[0.1, -0.2], [0.15, -0.1], [-0.05, 0.05], [0.0, 0.0]]
    )
    pid_outputs = []
    for time_s, error in zip(times, errors):
        pid.input(time_s, error)
        pid_outputs.append(pid.output())

    servo_config = Moog2ndServoConfig(dt=1.0e-3)
    servo = moog_2nd_servovalve(
        servo_config.dt,
        servo_config.delay,
        servo_config.tw,
        servo_config.zeta,
    )
    servo.init()
    commands = np.array([0.0, 0.4, -0.25, 0.1])
    servo_outputs = []
    for time_s, command in zip(times, commands):
        servo.input(time_s, [command])
        servo_outputs.append(np.asarray(servo.output(), dtype=float).reshape(-1))
    lti = servo.main_model
    arrays = {
        "time": times,
        "pid_errors": errors,
        "pid_outputs": np.vstack(pid_outputs),
        "pid_kp_terms": np.vstack(pid.results["kp_calc"]),
        "pid_ki_terms": np.vstack(pid.results["ki_calc"]),
        "pid_kd_terms": np.vstack(pid.results["kd_calc"]),
        "servo_commands": commands,
        "servo_outputs": np.vstack(servo_outputs),
        "servo_state_history": np.asarray(lti.xout, dtype=float),
        "servo_output_history": np.asarray(lti.yout, dtype=float),
        "servo_A": np.asarray(lti.A, dtype=float),
        "servo_B": np.asarray(lti.B, dtype=float),
        "servo_C": np.asarray(lti.C, dtype=float),
        "servo_D": np.asarray(lti.D, dtype=float),
    }
    return CaseData(
        metadata={
            "purpose": "Controller and servo-valve state transition order",
            "pid_result_columns": list(pid.results.columns),
            "servo_class": type(servo).__name__,
        },
        arrays=arrays,
    )


def _dynamics_coupling_case() -> CaseData:
    """Freeze hidden RossRotor advancement and rotor-bearing force exchange."""

    rotor = RossRotor(_LinearRotorPlant(), speed=2.0 * np.pi * 50.0, dt=1.0e-3)
    rotor_forces = np.array([[0.0], [1.0], [0.5], [-0.25]])
    rotor_states = []
    for index, force in enumerate(rotor_forces):
        rotor.input_force(index * rotor._dt, force)
        rotor.advance()
        rotor_states.append(rotor.output())

    bearing = alb_harmonic_linear(node_link=12)
    reference_rotor = _ReferenceRotor(bearing.uxy0)
    coupling = RsRotorBearingCouple(
        reference_rotor,
        TimeIterDt(bearing.dt, num=3),
        bearing,
    )
    coupling.init()
    for index in range(3):
        coupling.advance(
            StepContext(index, index * bearing.dt, bearing.dt, "dimensional")
        )
    arrays = {
        "rotor_forces": rotor_forces,
        "rotor_states": np.vstack(rotor_states),
        "rotor_state_history": np.asarray(rotor._xouts, dtype=float),
        "rotor_output_history": np.asarray(rotor._youts, dtype=float),
        "rotor_Ad": np.asarray(rotor._a, dtype=float),
        "rotor_Bd0": np.asarray(rotor._Bd0, dtype=float),
        "rotor_Bd1": np.asarray(rotor._Bd1, dtype=float),
        "coupling_times": np.asarray(reference_rotor.time_history, dtype=float),
        "coupling_forces": np.stack(reference_rotor.force_history),
        "coupling_previous_forces": np.stack(
            reference_rotor.previous_force_history
        ),
        "coupling_bearing_results": coupling.results["bearing0"].to_numpy(
            dtype=float
        ),
    }
    return CaseData(
        metadata={
            "purpose": "Rotor advance timing and coupling exchange order",
            "legacy_output_advances_state": False,
            "coupling_result_keys": sorted(coupling.results),
            "save_tree": coupling.save(tofile=False).get_dir(),
        },
        arrays=arrays,
    )


def _systems_alb_harmonic_case() -> CaseData:
    """Freeze nonlinear ALB assembly and harmonic K/C/G_xv capability."""

    harmonic = alb_harmonic_linear(node_link=12)
    harmonic.init()
    harmonic_outputs = []
    harmonic_positions = []
    harmonic_velocities = []
    harmonic_last_output: dict[str, Any] = {}
    for step in range(6):
        phase = harmonic.phase_step * (step + 1)
        displacement = 2.0e-6 * np.array([np.cos(phase), np.sin(phase)])
        velocity = 2.0e-6 * harmonic.coefficients.whirl_omega_rad_s * np.array(
            [-np.sin(phase), np.cos(phase)]
        )
        position = harmonic.uxy0 + displacement
        harmonic.input(position, velocity, step * harmonic.dt)
        harmonic_last_output = dict(harmonic.output())
        harmonic_outputs.append(harmonic_last_output["force"])
        harmonic_positions.append(position)
        harmonic_velocities.append(velocity)

    config = NodimALBConfig(
        pad_config=NodimPadConfig(
            lambda_value=1.2,
            lr=1.0,
            lx=90.0,
            lz=2.0,
            nx=5,
            nz=3,
            coe=False,
            max_iter=12,
            error_set=1.0e-8,
        ),
        orifice_config=NodimOrificeConfig(
            position=np.array([[0.5, 0.5]]),
            cq0=0.2,
            cq1=1.0,
            cq2=0.1,
        ),
        controller_config=PIDConfig(kp=0.0, ki=0.0, kd=0.0),
        servo="static",
        switch=False,
    )
    system = nodim_alb(config)
    system.init()
    alb_inputs = np.array([[0.03, -0.02], [0.02, -0.01]])
    alb_velocities = np.array([[0.0, 0.0], [0.01, -0.005]])
    alb_outputs = []
    for index, (uxy, uxyt) in enumerate(zip(alb_inputs, alb_velocities)):
        system.input(uxy, uxyt, t=index * config.dt, nodim=True)
        alb_outputs.append(system.output(nodim=True)["force"])
    arrays = {
        "harmonic_positions": np.vstack(harmonic_positions),
        "harmonic_velocities": np.vstack(harmonic_velocities),
        "harmonic_forces": np.vstack(harmonic_outputs),
        "harmonic_K": np.asarray(harmonic.K),
        "harmonic_C": np.asarray(harmonic.C),
        "harmonic_G_xv_real": np.asarray(harmonic.G_xv.real),
        "harmonic_G_xv_imag": np.asarray(harmonic.G_xv.imag),
        "alb_inputs": alb_inputs,
        "alb_velocities": alb_velocities,
        "alb_forces": np.vstack(alb_outputs),
        "alb_pad_pressures": np.stack(
            [pad.main_model.latest_result for pad in system.pads]
        ),
    }
    return CaseData(
        metadata={
            "purpose": "ALB builder behavior and formal harmonic coefficients",
            "harmonic_output_keys": sorted(harmonic_last_output),
            "alb_class": type(system).__name__,
            "pad_count": len(system.pads),
            "pad_final_iterations": [int(pad.final_iter) for pad in system.pads],
            "converged": bool(system.calc_is_finished()),
        },
        arrays=arrays,
    )


def _surrogate_training_case() -> CaseData:
    """Freeze feature order, inference, network initialization, and losses."""

    frame = pd.DataFrame(
        {
            column: values
            for column, values in zip(
                ALBNN_BASE_INPUT_COLS,
                np.array(
                    [
                        [0.2, 0.3, 0.1, 0.4, 0.5, 0.6, 1.5, 0.03, 0.7, 5.0, 0.02, 0.003],
                        [-0.2, 0.3, -0.4, 0.1, -0.6, 0.5, 1.5, 0.03, 0.7, 5.0, 0.02, 0.003],
                        [-0.2, -0.3, 0.4, -0.1, 0.6, -0.5, 1.5, 0.03, 0.7, 5.0, 0.02, 0.003],
                        [0.2, -0.3, -0.1, -0.4, -0.5, -0.6, 1.5, 0.03, 0.7, 5.0, 0.02, 0.003],
                    ],
                    dtype=float,
                ).T,
            )
        }
    )
    augmented = albnn_augment_frame(frame, feature_set="sqrt28")
    canonical, canonical_steps = c4_canonicalize_albnn_frame(frame)
    base_model = ALBNN(
        _FirstTwoColumnsNet(),
        _IdentityScaler(ALBNN_BASE_INPUT_COLS),
        _IdentityScaler(["fx", "fy"]),
        input_cols=ALBNN_BASE_INPUT_COLS,
        use_augment=False,
    )
    wrapped = ALBNNC4Canonical(base_model)
    canonical_forces = wrapped.predict_nondim(frame)

    torch.manual_seed(SEED)
    network = Net([12, 8, 2], activation="gelu")
    network.eval()
    network_input = torch.as_tensor(
        frame.to_numpy(dtype=np.float32), dtype=torch.float32
    )
    with torch.no_grad():
        network_output = network(network_input).cpu().numpy()
    flat_parameters = np.concatenate(
        [parameter.detach().cpu().numpy().reshape(-1) for parameter in network.parameters()]
    )

    scaler_input = pd.DataFrame(
        {"constant": [3.0, 3.0, 3.0], "varying": [1.0, 2.0, 5.0]}
    )
    scaler = MidpointMinMaxScaler(feature_range=(-1.0, 1.0)).fit(scaler_input)
    scaled = scaler.transform(scaler_input)
    pred = torch.tensor([[0.1, -0.2], [0.3, 0.4]], dtype=torch.float32)
    target = torch.tensor([[0.0, -0.1], [0.25, 0.5]], dtype=torch.float32)
    weights = torch.tensor([1.0, 2.0], dtype=torch.float32)
    losses = sample_loss_values(pred, target, loss_type="huber", huber_delta=0.2)
    optimizer = torch.optim.SGD(network.parameters(), lr=1.0e-3)
    training_target = torch.tensor(
        [[0.1, -0.1], [0.2, 0.0], [-0.1, 0.15], [0.05, -0.2]],
        dtype=torch.float32,
    )
    training_losses = []
    training_parameters = []
    for _ in range(2):
        optimizer.zero_grad(set_to_none=True)
        prediction = network(network_input)
        loss = torch.mean((prediction - training_target) ** 2)
        loss.backward()
        optimizer.step()
        training_losses.append(float(loss.detach().cpu().item()))
        training_parameters.append(
            np.concatenate(
                [
                    parameter.detach().cpu().numpy().reshape(-1)
                    for parameter in network.parameters()
                ]
            )
        )
    arrays = {
        "base_frame": frame.to_numpy(dtype=float),
        "augmented_frame": augmented.to_numpy(dtype=float),
        "canonical_frame": canonical.to_numpy(dtype=float),
        "canonical_steps": np.asarray(canonical_steps, dtype=np.int64),
        "canonical_forces": np.asarray(canonical_forces, dtype=float),
        "network_input": network_input.cpu().numpy(),
        "network_parameters": flat_parameters,
        "network_output": network_output,
        "scaler_input": scaler_input.to_numpy(dtype=float),
        "scaler_output": np.asarray(scaled, dtype=float),
        "sample_losses": losses.detach().cpu().numpy(),
        "weighted_loss": np.asarray(
            [weighted_mean(losses, weights).detach().cpu().item()], dtype=float
        ),
        "training_target": training_target.cpu().numpy(),
        "training_losses": np.asarray(training_losses, dtype=float),
        "training_parameters": np.vstack(training_parameters),
    }
    return CaseData(
        metadata={
            "purpose": "ALBNN feature, inference, scaler, and loss behavior",
            "base_columns": list(frame.columns),
            "augmented_columns": list(augmented.columns),
            "network_architecture": [12, 8, 2],
            "seed": SEED,
        },
        arrays=arrays,
    )


def _remote_persistence_case() -> CaseData:
    """Freeze remote command construction and legacy result-tree payloads."""

    config = {
        remote_job.INTERNAL_CONFIG_DIR: "C:/baseline",
        "run_id": "A0001_full_refactor_reference_20260720",
        "owner": "ALB_MAIN",
        "profile": {
            "host": "10.0.0.1",
            "user": "host\\user",
            "key": "C:/keys/reference",
            "work": "F:/work",
            "root": "F:/work/outputs",
            "remote_python": "F:/env/python.exe",
        },
        "job": {
            "task_name": "ALB_Reference",
            "runner": "${work}/run_reference.ps1",
            "command": ["${remote_python}", "-u", "run/reference.py", "--dry"],
            "env": {"PYTHONUNBUFFERED": "1"},
            "stdout": "${root}/reference.stdout.log",
            "stderr": "${root}/reference.stderr.log",
            "runner_log": "${root}/reference.runner.log",
            "execution_time_limit": "PT1H",
        },
    }
    spec = remote_job.build_job_spec(config)
    runner = remote_job.build_runner_content(spec)
    frame = pd.DataFrame({"time": [0.0, 0.1], "force": [1.0, -2.0]})
    array = np.array([[1.0, 2.0], [3.0, 4.0]])
    child_a = SaveTreeNode("frames", DataFrameResult({"history": frame}))
    child_b = SaveTreeNode("arrays", NpyResult({"state": array}))
    tree = SaveTreeNode("bundle", DataFrameResult({}), [child_a, child_b])
    serialized = pickle.dumps(tree, protocol=pickle.HIGHEST_PROTOCOL)
    arrays = {
        "persistence_frame": frame.to_numpy(dtype=float),
        "persistence_array": array,
        "persistence_pickle": np.frombuffer(serialized, dtype=np.uint8).copy(),
    }
    return CaseData(
        metadata={
            "purpose": "Remote command and persistence payload compatibility",
            "remote": {
                "task_name": spec.task_name,
                "command": spec.command,
                "runner": spec.runner,
                "runner_content": runner,
                "ps_quote": ps_quote("alpha'beta"),
                "remote_path": remote_path("F:/work", "run", "reference.py"),
                "encoded_script": encode_powershell("$x = 'reference'"),
                "encoded_command": powershell_encoded_command(
                    "$x = 'reference'"
                ),
            },
            "save_tree": tree.get_dir(),
            "pickle_protocol": pickle.HIGHEST_PROTOCOL,
        },
        arrays=arrays,
    )


CASE_BUILDERS: dict[str, Callable[[], CaseData]] = {
    "core_fem": _core_fem_case,
    "film": _film_case,
    "hydraulics_orifice": _hydraulics_orifice_case,
    "bearing": _bearing_case,
    "gas": _gas_case,
    "thermal": _thermal_case,
    "control_valve": _control_valve_case,
    "dynamics_coupling": _dynamics_coupling_case,
    "systems_alb_harmonic": _systems_alb_harmonic_case,
    "surrogate_training": _surrogate_training_case,
    "remote_persistence": _remote_persistence_case,
}


def collect_cases() -> dict[str, CaseData]:
    """Recompute every domain case in the fixed, documented order."""

    cases = {}
    for name in DOMAIN_ORDER:
        _reset_random_state()
        cases[name] = CASE_BUILDERS[name]()
    return cases


def _installed_distributions() -> list[str]:
    """Capture package names and versions without leaking local source paths."""

    versions = {
        f"{distribution.metadata['Name']}=={distribution.version}"
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }
    return sorted(versions, key=str.lower)


def _environment_payload(baseline_commit: str) -> dict[str, Any]:
    """Build the environment, dependency, seed, and thread manifest."""

    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        np.__config__.show()
    dependencies = {
        name: _distribution_version(name)
        for name in (
            "numpy",
            "scipy",
            "pandas",
            "torch",
            "scikit-learn",
            "scikit-fem",
            "numba",
            "control",
            "ross-rotordynamics",
            "json5",
            "matplotlib",
            "pytest",
        )
    }
    return {
        "schema": "alb.full-repo-refactor-environment.v1",
        "baseline_commit": baseline_commit,
        "seed": SEED,
        "python_hash_seed_required": "0",
        "python": sys.version,
        "python_executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "dependencies": dependencies,
        "installed_distributions": _installed_distributions(),
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "numpy_configuration": stream.getvalue(),
    }


def _benchmark(
    name: str,
    builder: Callable[[], CaseData],
    repeats: int,
    work_units: int,
) -> dict[str, Any]:
    """Measure a warmed case repeatedly and return its median runtime."""

    _reset_random_state()
    builder()
    samples = []
    for _ in range(repeats):
        _reset_random_state()
        start = time.perf_counter()
        for _ in range(work_units):
            builder()
        samples.append((time.perf_counter() - start) / work_units)
    median = statistics.median(samples)
    mad = statistics.median(abs(value - median) for value in samples)
    return {
        "case": name,
        "work_units_per_sample": work_units,
        "samples_seconds": samples,
        "median_seconds": median,
        "mad_seconds": mad,
        "p25_seconds": float(np.percentile(samples, 25)),
        "p75_seconds": float(np.percentile(samples, 75)),
        "noise_ratio": mad / median if median > 0.0 else 0.0,
        "noise_threshold_ratio": 0.05,
        "baseline_stable": bool(median > 0.0 and mad / median <= 0.05),
        "allowed_ratio": 1.15,
    }


def _performance_payload(baseline_commit: str) -> dict[str, Any]:
    """Capture same-machine medians for the five required performance paths."""

    specifications = (
        ("film", _film_case, 7, 30),
        ("thermal", _thermal_case, 7, 5),
        ("alb", _systems_alb_harmonic_case, 7, 20),
        ("albnn", _surrogate_training_case, 11, 200),
        ("coupling", _dynamics_coupling_case, 9, 20),
    )
    return {
        "schema": "alb.full-repo-refactor-performance.v1",
        "baseline_commit": baseline_commit,
        "policy": (
            "Pause a domain when its same-machine median exceeds the baseline "
            "by more than 15 percent."
        ),
        "benchmarks": [
            _benchmark(name, builder, repeats, work_units)
            for name, builder, repeats, work_units in specifications
        ],
    }


def generate_performance_only(output_dir: Path) -> Path:
    """Generate only the immutable performance file after case validation."""

    baseline_commit = _ensure_baseline_source()
    output_dir.mkdir(parents=True, exist_ok=True)
    performance_path = output_dir / "performance_baseline.json"
    if performance_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing reference: {performance_path}"
        )
    performance_path.write_text(
        json.dumps(
            _performance_payload(baseline_commit),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return performance_path


def generate(output_dir: Path, *, include_performance: bool = True) -> list[Path]:
    """Write all references once and return the created file paths."""

    baseline_commit = _ensure_baseline_source()
    output_dir.mkdir(parents=True, exist_ok=True)
    planned = [output_dir / "environment.json"]
    for name in DOMAIN_ORDER:
        planned.extend([output_dir / f"{name}.json", output_dir / f"{name}.npz"])
    if include_performance:
        planned.append(output_dir / "performance_baseline.json")
    existing = [path for path in planned if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing references:\n"
            + "\n".join(str(path) for path in existing)
        )

    cases = collect_cases()
    created = []
    for name in DOMAIN_ORDER:
        case = cases[name]
        arrays = {
            key: np.asarray(value)
            for key, value in case.arrays.items()
        }
        metadata = {
            "schema": REFERENCE_SCHEMA,
            "domain": name,
            "baseline_commit": baseline_commit,
            "seed": SEED,
            **case.metadata,
            "arrays": _array_manifest(arrays),
        }
        json_path = output_dir / f"{name}.json"
        npz_path = output_dir / f"{name}.npz"
        json_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        np.savez(npz_path, **arrays)
        created.extend([json_path, npz_path])

    environment_path = output_dir / "environment.json"
    environment_path.write_text(
        json.dumps(
            _environment_payload(baseline_commit),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(environment_path)
    if include_performance:
        performance_path = output_dir / "performance_baseline.json"
        performance_path.write_text(
            json.dumps(
                _performance_payload(baseline_commit),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        created.append(performance_path)
    return created


def main() -> int:
    """Run the one-time reference generation command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-performance", action="store_true")
    parser.add_argument("--performance-only", action="store_true")
    args = parser.parse_args()
    if args.no_performance and args.performance_only:
        parser.error("--no-performance and --performance-only are mutually exclusive")
    if args.performance_only:
        print(generate_performance_only(args.output_dir.resolve()))
        return 0
    created = generate(
        args.output_dir.resolve(),
        include_performance=not args.no_performance,
    )
    for path in created:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
