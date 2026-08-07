"""Freeze all ALB runtime families before the native lifecycle migration."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config import (
    ALBConfig,
    FPBConfig,
    NodimALBConfig,
    OrificeConfig,
    StaticServoConfig,
    TankConfig,
)
from ALB.contracts import (
    BearingInput,
    DirectSpoolBearingInput,
    ValveOutput,
)
from ALB.systems.alb.harmonic import _build_harmonic_runtime
from ALB.systems.alb.assembly_runtime import assemble_active_runtime
from ALB.surrogate.runtime import SurrogateBearingRuntime
from tools.reference.generate_albsv_direct_spool_reference_v1 import (
    CONFIG as NODIM_CONFIG,
    config_from_payload,
)


DEFAULT_JSON = ROOT / "refs" / "alb_runtime_families_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "alb_runtime_families_reference_v1.npz"
DT = 6.667e-4


def _dimensional_config(kind: str) -> ALBConfig:
    """Return one compact dimensional ALB configuration."""

    return ALBConfig(
        pad_config=FPBConfig(
            nx=15,
            nz=7,
            lx=80.0,
            lz=2.0,
            coe=False,
            max_iter=80,
            error_set=1.0e-6,
        ),
        servo_config=StaticServoConfig(dt=DT),
        orifice_config=OrificeConfig(),
        tank_config=TankConfig(),
        controller_config=None,
        dt=DT,
        node_link=2,
        control_mode="external_spool" if kind == "ALBSV" else "uncontrolled",
    )


def _nondimensional_config(kind: str, *, thermal: bool) -> NodimALBConfig:
    """Return one compact nondimensional ALB configuration."""

    payload = copy.deepcopy(NODIM_CONFIG)
    payload.update({"nx": 15, "nz": 7, "max_iter": 80, "dt": DT})
    config = config_from_payload(payload, thermal=thermal)
    config.node_link = 2
    config.control_mode = (
        "external_spool" if kind == "ALBSV" else "uncontrolled"
    )
    return config


def _run_family_case(
    *,
    unit: str,
    kind: str,
    thermal: bool = False,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Run one raw implementation twice and capture component results."""

    if unit == "dimensional":
        model = assemble_active_runtime(_dimensional_config(kind))
        displacement = np.asarray([1.0e-6, -2.0e-6], dtype=float)
        velocity = np.asarray([1.0e-3, -2.0e-3], dtype=float)
        nodim_kwargs: dict[str, Any] = {}
    else:
        config = _nondimensional_config(kind, thermal=thermal)
        model = assemble_active_runtime(config)
        displacement = np.asarray([0.1, -0.2], dtype=float)
        velocity = np.asarray([0.03, -0.04], dtype=float)
        nodim_kwargs = {"nodim": True}
    force_rows = []
    friction_rows = []
    spool_rows = []
    history_rows = []
    for index in range(2):
        bearing_input = BearingInput(
            displacement * (1.0 - 0.1 * index),
            velocity * (1.0 - 0.2 * index),
            DT * index,
            unit,
        )
        if kind == "ALBSV":
            spool = np.asarray(
                [0.2 - 0.05 * index, -0.3 + 0.1 * index],
                dtype=float,
            )
            model.input(
                DirectSpoolBearingInput(
                    bearing_input,
                    ValveOutput(spool, DT * index, "nondimensional"),
                )
            )
        else:
            model.input(bearing_input)
        model.evaluate()
        output = model.output()
        force_rows.append(np.asarray(output.force, dtype=float))
        friction_rows.append(
            float(model.result_snapshot().values["friction"])
        )
        spool_rows.append(
            np.asarray([valve.xv for valve in model._servovalves], dtype=float)
        )
        history_rows.append(
            [
                bearing_input.time,
                bearing_input.displacement[0],
                bearing_input.displacement[1],
                bearing_input.velocity[0],
                bearing_input.velocity[1],
                output.force[0],
                output.force[1],
            ]
        )

    arrays = {
        "force": np.asarray(force_rows, dtype=float),
        "friction": np.asarray(friction_rows, dtype=float),
        "spool": np.asarray(spool_rows, dtype=float),
        "history": np.asarray(history_rows, dtype=float),
        "pressure": np.vstack(
            [
                np.asarray(
                    getattr(pad, "bearing", pad).main_model.latest_result,
                    dtype=float,
                )
                for pad in model._pads
            ]
        ),
    }
    metadata = {
        "class_name": type(model).__name__,
        "unit_system": model.unit_system,
        "kind": kind,
        "thermal": thermal,
        "history_columns": ["t", "ux", "uy", "uxt", "uyt", "fx", "fy"],
        "save_tree": f"{unit}_{kind.lower()}",
    }
    if thermal:
        arrays.update(
            {
                "thermal_t_eff": np.asarray(
                    [
                        pad._last_thermal["t_eff"]
                        for pad in model._pads
                    ],
                    dtype=float,
                ),
                "thermal_viscosity": np.vstack(
                    [
                        np.asarray(
                            pad._last_thermal["viscosity_field"],
                            dtype=float,
                        )
                        for pad in model._pads
                    ]
                ),
                "thermal_iterations": np.asarray(
                    [
                        pad._last_thermal["iterations"]
                        for pad in model._pads
                    ],
                    dtype=np.int64,
                ),
                "thermal_newton_residual": np.asarray(
                    [
                        pad._last_thermal["newton_residual"]
                        for pad in model._pads
                    ],
                    dtype=float,
                ),
                "thermal_relax_history": np.vstack(
                    [
                        np.asarray(
                            pad._last_thermal["relax_history"],
                            dtype=float,
                        )
                            for pad in model._pads
                    ]
                ),
            }
        )
        metadata["thermal_converged"] = [
            bool(pad._last_thermal["converged"]) for pad in model._pads
        ]
    return arrays, metadata


def _run_harmonic_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Capture the strict harmonic numerical capabilities and history."""

    model = _build_harmonic_runtime(node_link=2)
    force_rows = []
    spool_rows = []
    history_rows = []
    for index in range(2):
        phase = model.phase_step * (index + 1)
        displacement = 2.0e-6 * np.asarray(
            [np.cos(phase), np.sin(phase)],
            dtype=float,
        )
        velocity = (
            2.0e-6
            * model.coefficients.whirl_omega_rad_s
            * np.asarray([-np.sin(phase), np.cos(phase)], dtype=float)
        )
        model.input(
            BearingInput(
                model.uxy0 + displacement,
                velocity,
                index * model.dt,
                "dimensional",
            )
        )
        model.evaluate()
        output = model.output()
        force_rows.append(output.force)
        spool_rows.append(model.result_snapshot().values["spool"])
        history_rows.append(
            [
                model.t,
                model.uxy[0],
                model.uxy[1],
                model.uxyt[0],
                model.uxyt[1],
                model.spool_command[0],
                model.spool_command[1],
                model.spool[0],
                model.spool[1],
                model.spool_quadrature[0],
                model.spool_quadrature[1],
                model._force_stiffness[0],
                model._force_stiffness[1],
                model._force_damping[0],
                model._force_damping[1],
                model._force_spool[0],
                model._force_spool[1],
                model.force[0],
                model.force[1],
                model.controller_saturated,
                model.servovalve_saturated,
            ]
        )
    arrays = {
        "force": np.asarray(force_rows, dtype=float),
        "spool": np.asarray(spool_rows, dtype=float),
        "history": np.asarray(history_rows, dtype=float),
        "K": np.asarray(model.K),
        "C": np.asarray(model.C),
        "G_xv_real": np.asarray(model.G_xv.real),
        "G_xv_imag": np.asarray(model.G_xv.imag),
    }
    metadata = {
        "class_name": type(model).__name__,
        "unit_system": model.unit_system,
        "runtime_schema": "alb.harmonic-bearing-result.v1",
    }
    return arrays, metadata


class _DeterministicNet:
    """Small ALBNN shell dependency with a fixed affine force law."""

    def __init__(self) -> None:
        self.latched = np.zeros(6, dtype=float)

    def input(self, uxy, uxyt, spool, *, nodim: bool) -> None:
        del nodim
        self.latched = np.concatenate(
            (
                np.asarray(uxy, dtype=float),
                np.asarray(uxyt, dtype=float),
                np.asarray(spool, dtype=float),
            )
        )

    def output(self, *, nodim: bool) -> np.ndarray:
        scale = 1.0 if nodim else 10.0
        matrix = np.asarray(
            [
                [1.0, 2.0, 0.5, -0.25, 3.0, -2.0],
                [-1.5, 0.75, 0.1, 0.2, -1.0, 4.0],
            ]
        )
        return scale * (matrix @ self.latched)


def _run_albnn_shell_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Capture the native surrogate runtime around deterministic inference."""

    model = SurrogateBearingRuntime(
        _DeterministicNet(),
        unit_system="nondimensional",
        node_link=None,
        external_spool=True,
    )
    force_rows = []
    history_rows = []
    for index in range(2):
        bearing_input = BearingInput(
            np.asarray([0.1, -0.2]) * (index + 1),
            np.asarray([0.03, -0.04]) * (index + 1),
            index * DT,
            "nondimensional",
        )
        spool = np.asarray(
            [0.1 + 0.05 * index, -0.2 + 0.02 * index],
            dtype=float,
        )
        model.input(
            DirectSpoolBearingInput(
                bearing_input,
                ValveOutput(
                    spool,
                    bearing_input.time,
                    "nondimensional",
                ),
            )
        )
        model.evaluate()
        force = model.output().force
        force_rows.append(force)
        history_rows.append(
            np.concatenate(
                (
                    [bearing_input.time],
                    bearing_input.displacement,
                    bearing_input.velocity,
                    force,
                )
            )
        )
    arrays = {
        "force": np.asarray(force_rows, dtype=float),
        "history": np.asarray(history_rows, dtype=float),
    }
    metadata = {
        "class_name": type(model).__name__,
        "runtime_schema": "alb.surrogate-bearing-result.v0.4",
        "history_columns": ["t", "ux", "uy", "uxt", "uyt", "fx", "fy"],
    }
    return arrays, metadata


def collect_reference() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Collect every runtime-family array and metadata contract."""

    cases: dict[str, tuple[dict[str, np.ndarray], dict[str, Any]]] = {}
    for unit in ("dimensional", "nondimensional"):
        for kind in ("ALB", "ALBSV"):
            name = f"{unit}.{kind.lower()}"
            cases[name] = _run_family_case(unit=unit, kind=kind)
    cases["nondimensional.albsv_thermal"] = _run_family_case(
        unit="nondimensional",
        kind="ALBSV",
        thermal=True,
    )
    cases["harmonic"] = _run_harmonic_case()
    cases["albnn_shell"] = _run_albnn_shell_case()

    arrays: dict[str, np.ndarray] = {}
    metadata: dict[str, Any] = {}
    for case_name, (case_arrays, case_metadata) in cases.items():
        arrays.update(
            {
                f"{case_name}.{array_name}": np.asarray(value)
                for array_name, value in case_arrays.items()
            }
        )
        metadata[case_name] = case_metadata
    return arrays, metadata


def _sha256_array(value: np.ndarray) -> str:
    """Return a stable byte digest for one array."""

    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def generate(output_json: Path, output_npz: Path) -> None:
    """Generate the versioned reference without overwriting existing files."""

    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite reference: {output}")
    np.random.seed(20260723)
    arrays, contracts = collect_reference()
    metadata = {
        "schema": "alb.runtime-families-reference.v1",
        "baseline_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).strip(),
        "random_seed": 20260723,
        "environment": {
            "python": sys.version,
            "numpy": importlib.metadata.version("numpy"),
            "scipy": importlib.metadata.version("scipy"),
            "scikit-fem": importlib.metadata.version("scikit-fem"),
        },
        "contracts": contracts,
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _sha256_array(value),
            }
            for name, value in sorted(arrays.items())
        },
    }
    output_json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    np.savez(output_npz, **arrays)
    print(f"Wrote {output_json}")
    print(f"Wrote {output_npz}")


def main() -> None:
    """Parse output paths and generate the reference."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    generate(args.output_json, args.output_npz)


if __name__ == "__main__":
    main()
