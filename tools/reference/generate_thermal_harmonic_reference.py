"""Freeze pre-migration harmonic equations against the current runtime adapter.

The three historical diagnostic sources are read, hashed, and compiled without
their machine-specific imports, builders, or CLI. Only the old equation classes
are executed. This generator must run before changing the package equations;
its output is an immutable regression reference, not an acceptance oracle that
may be regenerated to match a candidate implementation.
"""

from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import scipy
import scipy.sparse as sp
from scipy.sparse.linalg import splu
from skfem import BilinearForm, LinearForm, asm
from skfem.helpers import grad

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import ALB
from ALB.contracts import BearingInput, UnitSystem
from ALB.physics.thermal.solver import (
    _build_film_grid,
    _reynolds_lhs_miu,
    _reynolds_rhs_miu0,
    _transient_mass_form,
)

INPUT_NAMES = ("ex", "ey", "vx", "vy", "sx", "sy")


def load_original_classes(source_root: Path):
    """Load untouched mathematical definitions, excluding historical tooling."""
    namespace = dict(globals())
    hashes = {}
    selections = {
        "analytic_harmonic_linearization_temp.py": {
            "pressure_miu_block", "pressure_geometry_column",
            "thermal_direct_block", "thermal_source_vector",
            "thermal_qx_coefficient_block", "thermal_qz_coefficient_block",
            "thermal_phi_coefficient_block", "thermal_diff_x_coefficient_block",
            "thermal_diff_z_coefficient_block", "axis_derivative_entries",
            "AnalyticPadSystem",
        },
        "cavitation_moving_boundary_harmonic.py": {"PadComplementaritySystem"},
        "thermal_inertia_cavitation_harmonic.py": {"DynamicPadSystem"},
    }
    namespace["analytic"] = SimpleNamespace(INPUT_NAMES=INPUT_NAMES)
    for filename, names in selections.items():
        path = source_root / filename
        data = path.read_bytes()
        hashes[filename] = hashlib.sha256(data).hexdigest()
        tree = ast.parse(data.decode("utf-8-sig"), filename=str(path))
        tree.body = [node for node in tree.body if getattr(node, "name", None) in names]
        exec(compile(tree, str(path), "exec"), namespace)
    return namespace, hashes


class HistoricalInputAdapter:
    """Translate the old raw input call without changing equation arithmetic."""

    def __init__(self, pad):
        self._pad = pad

    def __getattr__(self, name):
        return getattr(self._pad, name)

    def input(self, *, t, uxy, uxyt, nodim):
        args = self._pad.bearing.main_model.args
        displacement = np.asarray(uxy) * float(args["c"])
        velocity = np.asarray(uxyt) * float(args["c"]) * float(args["w_rad"]) * float(args["vf"])
        self._pad.bearing._prepare_raw(BearingInput(
            displacement, velocity, t, UnitSystem.DIMENSIONAL,
        ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--production-source-coordinates", action="store_true")
    args = parser.parse_args()
    if args.output.with_suffix(".npz").exists() or args.output.with_suffix(".json").exists():
        raise FileExistsError("Reference outputs are immutable; choose a new path")
    namespace, hashes = load_original_classes(args.source_root)
    if args.production_source_coordinates:
        # The historical thermal lookup used local [0, 1] hole coordinates
        # against global film coordinates. Freeze the isolated correction
        # independently, before implementing the package projection path.
        def production_cold_nodes(self):
            coordinates = [item["position_nondim"] for item in self.orifice.flow_info(self.model)["flow_params"]]
            return np.asarray([np.argmin(np.sum((self.mesh.p.T - point)**2, axis=1)) for point in coordinates], dtype=int)
        namespace["AnalyticPadSystem"]._cold_source_nodes = production_cold_nodes
    spec = json.loads(args.config.read_text(encoding="utf-8"))
    config = ALB.BearingConfig(spec["spec"])
    point = np.asarray(spec["operating_point"])
    spool = np.asarray(spec["spool"])
    bearing = ALB.build_bearing(config)
    base = bearing.calculate(displacement=point, velocity=(0.0, 0.0), time=0.0, spool=spool)
    if not base.convergence.converged:
        raise RuntimeError("Production base did not converge")
    arrays = {"production_force": base.force}
    audits = []
    transfer = {frequency: np.zeros((2, 6), dtype=complex) for frequency in spec["frequencies_hz"]}
    for index, pad in enumerate(bearing._runtime._pads):
        film = pad.bearing.main_model
        scales = pad.thermal_model.build_mesh(film, _build_film_grid(film))["scales"]
        temperature = np.asarray(pad.result_snapshot().values["temperature"])
        initial = {"temperature_nondim": scales.temperature_to_nondim(temperature, scales.t_supply)}
        inputs = np.r_[point / scales.c, [0.0, 0.0], spool]
        analytic = namespace["AnalyticPadSystem"](HistoricalInputAdapter(pad), initial, inputs, (1, 1, 0, 0)[index])
        system = namespace["PadComplementaritySystem"](analytic)
        audit = system.refine_base()
        if not audit["converged"] or audit["weakly_active_nodes"]:
            raise RuntimeError(f"Invalid reference base on pad {index}: {audit}")
        dynamic = namespace["DynamicPadSystem"](system, config.spec["time_step"])
        arrays[f"pad_{index}_state"] = system.base_state
        arrays[f"pad_{index}_input"] = system.input_matrix
        arrays[f"pad_{index}_active"] = system.base_pressurized
        arrays[f"pad_{index}_force"] = analytic.force_operator @ system.base_state[:analytic.n] * (scales.ps * scales.r * scales.l / 2)
        for frequency in spec["frequencies_hz"]:
            value, residual = dynamic.strict_transfer(2j * np.pi * frequency)
            transfer[frequency] += value
            arrays[f"pad_{index}_transfer_{frequency:g}"] = value
            audit[f"residual_{frequency:g}"] = residual
        audits.append(audit)
        print(f"pad {index}: merit={audit['final_merit_l2']:.3e}", flush=True)
    force_scale = scales.ps * scales.r * scales.l / 2
    for frequency, value in transfer.items():
        omega = 2 * np.pi * frequency
        impedance = -force_scale / scales.c * (value[:, :2] + 1j * omega / (scales.omega * float(film.args["vf"])) * value[:, 2:4])
        arrays[f"K_{frequency:g}"] = impedance.real
        arrays[f"C_{frequency:g}"] = impedance.imag / omega
        arrays[f"G_{frequency:g}"] = force_scale * value[:, 4:]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output.with_suffix(".npz"), **arrays)
    metadata = {
        "schema": "alb.thermal-harmonic-migration-reference.v1",
        "source_hashes": hashes,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runtime_sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("ALB/physics/thermal/solver.py", "ALB/physics/hydraulics/orifice.py")},
        "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
        "case": spec, "pad_audits": audits,
        "thermal_source_coordinates": "production_flow_info" if args.production_source_coordinates else "historical_local_coordinates",
        "npz_sha256": hashlib.sha256(args.output.with_suffix(".npz").read_bytes()).hexdigest(),
    }
    args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
