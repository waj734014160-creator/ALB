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
    Moog2ndServoConfig,
    NodimALBConfig,
    OrificeConfig,
    TankConfig,
)
from ALB.systems.alb import alb_harmonic_linear
from ALB.systems.alb.factories import alb2, nodim_alb
from ALB.systems.alb.linear import FakeOf
import ALB.systems.alb.surrogate_runtime as surrogate_runtime
from tools.reference.generate_albsv_direct_spool_reference_v1 import (
    CONFIG as NODIM_CONFIG,
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
        servo_config=Moog2ndServoConfig(dt=DT),
        orifice_config=OrificeConfig(),
        tank_config=TankConfig(),
        controller_config=None,
        dt=DT,
        node_link=2,
        alb=kind,
        servo="static",
        switch=False,
    )


def _nondimensional_config(kind: str, *, thermal: bool) -> NodimALBConfig:
    """Return one compact nondimensional ALB configuration."""

    payload = copy.deepcopy(NODIM_CONFIG)
    payload.update(
        {
            "alb": kind,
            "servo": "static",
            "switch": False,
            "nx": 15,
            "nz": 7,
            "max_iter": 80,
            "dt": DT,
            "node_link": 2,
        }
    )
    if not thermal:
        payload["thermal_enabled"] = False
        payload.pop("thermal", None)
    return NodimALBConfig.from_dict(payload)


def _run_family_case(
    *,
    unit: str,
    kind: str,
    thermal: bool = False,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Run one raw implementation twice and capture component results."""

    if unit == "dimensional":
        model = alb2(_dimensional_config(kind))
        displacement = np.asarray([1.0e-6, -2.0e-6], dtype=float)
        velocity = np.asarray([1.0e-3, -2.0e-3], dtype=float)
        nodim_kwargs: dict[str, Any] = {}
    else:
        config = _nondimensional_config(kind, thermal=thermal)
        model = nodim_alb(config, thermal_config=config.thermal_config)
        displacement = np.asarray([0.1, -0.2], dtype=float)
        velocity = np.asarray([0.03, -0.04], dtype=float)
        nodim_kwargs = {"nodim": True}
    model.init()

    force_rows = []
    friction_rows = []
    spool_rows = []
    for index in range(2):
        input_kwargs = dict(nodim_kwargs)
        if kind == "ALBSV":
            input_kwargs["sv"] = np.asarray(
                [0.2 - 0.05 * index, -0.3 + 0.1 * index],
                dtype=float,
            )
        model.input(
            displacement * (1.0 - 0.1 * index),
            velocity * (1.0 - 0.2 * index),
            DT * index,
            **input_kwargs,
        )
        output = model.output(**nodim_kwargs)
        force_rows.append(np.asarray(output["force"], dtype=float))
        friction_rows.append(float(output["friction"]))
        spool_rows.append(
            np.asarray([valve.xv for valve in model.servovalves], dtype=float)
        )

    arrays = {
        "force": np.asarray(force_rows, dtype=float),
        "friction": np.asarray(friction_rows, dtype=float),
        "spool": np.asarray(spool_rows, dtype=float),
        "history": model.results.to_numpy(dtype=float),
        "pressure": np.vstack(
            [
                np.asarray(
                    getattr(pad, "bearing", pad).main_model.latest_result,
                    dtype=float,
                )
                for pad in model.pads
            ]
        ),
    }
    metadata = {
        "class_name": type(model).__name__,
        "unit_system": model.unit_system,
        "kind": kind,
        "thermal": thermal,
        "history_columns": list(model.results.columns),
        "save_tree": model.save(
            tofile=False,
            path=f"{unit}_{kind.lower()}",
            name="alb",
        ).get_dir(),
    }
    if thermal:
        arrays.update(
            {
                "thermal_t_eff": np.asarray(
                    [
                        pad._last_thermal["t_eff"]
                        for pad in model.pads
                    ],
                    dtype=float,
                ),
                "thermal_viscosity": np.vstack(
                    [
                        np.asarray(
                            pad._last_thermal["viscosity_field"],
                            dtype=float,
                        )
                        for pad in model.pads
                    ]
                ),
                "thermal_iterations": np.asarray(
                    [
                        pad._last_thermal["iterations"]
                        for pad in model.pads
                    ],
                    dtype=np.int64,
                ),
                "thermal_newton_residual": np.asarray(
                    [
                        pad._last_thermal["newton_residual"]
                        for pad in model.pads
                    ],
                    dtype=float,
                ),
                "thermal_relax_history": np.vstack(
                    [
                        np.asarray(
                            pad._last_thermal["relax_history"],
                            dtype=float,
                        )
                        for pad in model.pads
                    ]
                ),
            }
        )
        metadata["thermal_converged"] = [
            bool(pad._last_thermal["converged"]) for pad in model.pads
        ]
    return arrays, metadata


def _run_harmonic_case() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Capture the strict harmonic numerical capabilities and history."""

    model = alb_harmonic_linear(node_link=2)
    model.init()
    force_rows = []
    spool_rows = []
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
        model.input(model.uxy0 + displacement, velocity, index * model.dt)
        output = model.output()
        force_rows.append(output["force"])
        spool_rows.append(output["spool"])
    arrays = {
        "force": np.asarray(force_rows, dtype=float),
        "spool": np.asarray(spool_rows, dtype=float),
        "history": model.results.to_numpy(dtype=float),
        "K": np.asarray(model.K),
        "C": np.asarray(model.C),
        "G_xv_real": np.asarray(model.G_xv.real),
        "G_xv_imag": np.asarray(model.G_xv.imag),
    }
    metadata = {
        "class_name": type(model).__name__,
        "unit_system": model.unit_system,
        "history_columns": list(model.results.columns),
        "save_tree": model.save(
            tofile=False,
            path="harmonic",
            name="alb",
        ).get_dir(),
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
    """Capture the legacy ALBNN bearing shell around deterministic inference."""

    # The pre-migration module omitted this import. Injecting the exact class
    # records the intended shell behavior while preserving the defect in metadata.
    surrogate_runtime.FakeOf = FakeOf
    model = surrogate_runtime.ALBNNAgent(_DeterministicNet())
    model.init()
    force_rows = []
    for index in range(2):
        model.of[0].xv = 0.1 + 0.05 * index
        model.of[1].xv = -0.2 + 0.02 * index
        model.input(
            index * DT,
            np.asarray([0.1, -0.2]) * (index + 1),
            np.asarray([0.03, -0.04]) * (index + 1),
            nodim=True,
        )
        force_rows.append(model.output(nodim=True)["force"])
    arrays = {
        "force": np.asarray(force_rows, dtype=float),
        "history": model._results.to_numpy(dtype=float),
    }
    metadata = {
        "class_name": type(model).__name__,
        "agent": model.agent,
        "history_columns": list(model._results.columns),
        "compatibility_setup": "injected_missing_FakeOf_symbol",
        "save_tree": model.save(
            tofile=False,
            path="albnn",
            name="albnn",
        ).get_dir(),
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
