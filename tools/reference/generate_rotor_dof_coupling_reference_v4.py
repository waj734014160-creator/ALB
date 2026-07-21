"""Freeze full 4/6-DOF rotor-bearing coupling and mapping contracts.

The reference uses real ROSS four- and six-DOF rotors, a nonzero
state-dependent bearing, and linearly interpolated force0/force1 loads.  It
also verifies that each physical step produces exactly one rotor history row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import ross as rs


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.core import Signal, TimeIterDt
from ALB.dynamics.coupling import RsRotorBearingCouple
from ALB.dynamics.rotor import RossRotor


DEFAULT_JSON = ROOT / "refs/rotor_dof_coupling_reference_v4.json"
DEFAULT_NPZ = ROOT / "refs/rotor_dof_coupling_reference_v4.npz"
DT = 1.0e-4
STEP_COUNT = 3
SPEED_RAD_S = 30.0


class _StateDependentBearing:
    """Nonzero bearing whose force changes with displacement and velocity."""

    unit_system = "dimensional"

    def __init__(self, node_link: int) -> None:
        self.node_link = node_link
        self.signal = Signal(sys=self)
        self._stiffness = np.asarray([[2.0e5, 1.0e4], [-2.0e4, 1.5e5]])
        self._damping = np.asarray([[80.0, 5.0], [3.0, 60.0]])
        self._bias = np.asarray([2.5, -1.25])
        self.init()

    def init(self) -> None:
        """Reset latched states and complete input/output histories."""
        self.uxy = np.zeros(2, dtype=float)
        self.uxyt = np.zeros(2, dtype=float)
        self.time = 0.0
        self.input_history: list[np.ndarray] = []
        self.force_history: list[np.ndarray] = []

    def input(self, uxy, uxyt, t) -> None:
        """Latch one rotor state used by the deterministic force law."""
        self.uxy = np.asarray(uxy, dtype=float).reshape(2)
        self.uxyt = np.asarray(uxyt, dtype=float).reshape(2)
        self.time = float(t)
        self.input_history.append(
            np.concatenate(([self.time], self.uxy, self.uxyt))
        )

    def output(self) -> dict[str, np.ndarray]:
        """Evaluate and record a nonzero force at the latched state."""
        harmonic = np.asarray(
            [0.4 * np.sin(200.0 * self.time), 0.3 * np.cos(150.0 * self.time)]
        )
        force = self._bias + harmonic - self._stiffness @ self.uxy
        force -= self._damping @ self.uxyt
        self.force_history.append(force.copy())
        return {"force": force}

    def finish_signal(self) -> None:
        """Accept the coupling completion signal without extra mutation."""

    def save(self, *args, **kwargs):
        """Reject persistence because reference generation is in-memory only."""
        del args, kwargs
        raise AssertionError("save is outside coupling reference generation")


class _RecordingRossRotor(RossRotor):
    """Real ROSS wrapper that records nodal and mapped interpolation loads."""

    def init(self, x0=None):
        super().init(x0=x0)
        self.nodal_force0: list[np.ndarray] = []
        self.nodal_force1: list[np.ndarray] = []
        self.global_force0: list[np.ndarray] = []
        self.global_force1: list[np.ndarray] = []

    def input_force2node(self, t, force, node, x0=None, **kwargs):
        force0 = kwargs.get("force0")
        super().input_force2node(t, force, node, x0=x0, **kwargs)
        self.nodal_force1.append(np.asarray(force, dtype=float).copy())
        self.nodal_force0.append(np.asarray(force0, dtype=float).copy())
        self.global_force1.append(np.asarray(self._force1, dtype=float).copy())
        self.global_force0.append(np.asarray(self._force0, dtype=float).copy())


def _build_ross_rotor(dof_per_node: int) -> _RecordingRossRotor:
    """Build a small supported ROSS rotor for one DOF layout."""
    if dof_per_node == 4:
        shaft = rs.ShaftElement(
            L=0.2,
            idl=0.0,
            odl=0.03,
            material=rs.steel,
            n=0,
            shear_effects=True,
            rotary_inertia=True,
            gyroscopic=True,
        )
        bearings = [
            rs.BearingElement(n=node, kxx=2.0e6, kyy=2.2e6, cxx=120.0, cyy=130.0)
            for node in (0, 1)
        ]
    elif dof_per_node == 6:
        shaft = rs.ShaftElement6DoF(
            L=0.2,
            idl=0.0,
            odl=0.03,
            material=rs.steel,
            n=0,
            shear_effects=True,
            rotary_inertia=True,
            gyroscopic=True,
        )
        bearings = [
            rs.BearingElement6DoF(
                n=node,
                kxx=2.0e6,
                kyy=2.2e6,
                kzz=1.8e6,
                cxx=120.0,
                cyy=130.0,
                czz=110.0,
            )
            for node in (0, 1)
        ]
    else:
        raise ValueError("reference supports only 4 or 6 DOFs per node")
    rotor = rs.Rotor(shaft_elements=[shaft], bearing_elements=bearings)
    return _RecordingRossRotor(rotor, SPEED_RAD_S, DT)


def _local_dof_map(rotor: rs.Rotor) -> dict[str, int]:
    """Derive local node-zero indices from the ROSS element mapping."""
    mapping = rotor.shaft_elements[0].dof_mapping()
    return {
        name: int(mapping[f"{name}_0"])
        for name in ("x", "y", "alpha", "beta")
    }


def _mapping_matrix(
    total_dof: int,
    dof_per_node: int,
    local_map: dict[str, int],
    locations: list[tuple[int, str]],
) -> np.ndarray:
    """Return an implementation-independent mapping oracle."""
    result = np.zeros((total_dof, len(locations)), dtype=float)
    for column, (node, direction) in enumerate(locations):
        result[dof_per_node * node + local_map[direction], column] = 1.0
    return result


def _run_case(dof_per_node: int) -> dict[str, np.ndarray]:
    """Run one real coupling case and construct independent target arrays."""
    rotor = _build_ross_rotor(dof_per_node)
    bearing = _StateDependentBearing(node_link=1)
    coupling = RsRotorBearingCouple(
        rotor,
        TimeIterDt(DT, STEP_COUNT),
        bearing,
    )
    coupling.solve()

    prefix = f"dof{dof_per_node}"
    corrected_xouts = np.asarray(rotor._xouts, dtype=float)
    corrected_youts = np.asarray(rotor._youts, dtype=float)
    if corrected_xouts.shape[0] != STEP_COUNT:
        raise AssertionError("coupling must record one xout per physical step")
    if corrected_youts.shape[0] != STEP_COUNT:
        raise AssertionError("coupling must record one yout per physical step")

    local_map = _local_dof_map(rotor._rotor)
    node = 1
    xy_columns = [
        dof_per_node * node + local_map["x"],
        dof_per_node * node + local_map["y"],
    ]
    locations = [(1, "x"), (1, "y"), (1, "alpha"), (1, "beta")]
    mapping = _mapping_matrix(
        rotor._rotor.ndof,
        dof_per_node,
        local_map,
        locations,
    )

    lqg_act_locations = [(1, "x"), (1, "y")]
    lqg_sensor_locations = [(0, "x"), (0, "y")]
    lqg_t_act = _mapping_matrix(
        rotor._rotor.ndof,
        dof_per_node,
        local_map,
        lqg_act_locations,
    )
    lqg_h_sensor = _mapping_matrix(
        2 * rotor._rotor.ndof,
        dof_per_node,
        local_map,
        lqg_sensor_locations,
    ).T
    lqg_h_actuator = _mapping_matrix(
        2 * rotor._rotor.ndof,
        dof_per_node,
        local_map,
        lqg_act_locations,
    ).T
    lqg_h_velocity = np.roll(lqg_h_actuator, rotor._rotor.ndof, axis=1)

    return {
        f"{prefix}.times": np.asarray(rotor._t, dtype=float),
        f"{prefix}.corrected_xouts": corrected_xouts,
        f"{prefix}.corrected_youts": corrected_youts,
        f"{prefix}.final_state": np.asarray(rotor.current_state(), dtype=float),
        f"{prefix}.bearing_inputs": np.asarray(bearing.input_history, dtype=float),
        f"{prefix}.bearing_forces": np.asarray(bearing.force_history, dtype=float),
        f"{prefix}.nodal_force0": np.asarray(rotor.nodal_force0, dtype=float),
        f"{prefix}.nodal_force1": np.asarray(rotor.nodal_force1, dtype=float),
        f"{prefix}.global_force0": np.asarray(rotor.global_force0, dtype=float),
        f"{prefix}.global_force1": np.asarray(rotor.global_force1, dtype=float),
        f"{prefix}.coupling_table": coupling.results["bearing0"].to_numpy(dtype=float),
        f"{prefix}.result_uxy_expected": corrected_youts[:, xy_columns],
        f"{prefix}.result_uxy_observed_pre_fix": np.asarray(
            rotor.result_uxy(node), dtype=float
        ),
        f"{prefix}.mapping_expected": mapping,
        f"{prefix}.mapping_locations": np.asarray(
            [[node, local_map[direction]] for node, direction in locations],
            dtype=np.int64,
        ),
        f"{prefix}.lqg_T_act": lqg_t_act,
        f"{prefix}.lqg_H_sensor": lqg_h_sensor,
        f"{prefix}.lqg_H_actuator": lqg_h_actuator,
        f"{prefix}.lqg_H_velocity": lqg_h_velocity,
        f"{prefix}.layout": np.asarray(
            [
                dof_per_node,
                local_map["x"],
                local_map["y"],
                local_map["alpha"],
                local_map["beta"],
            ],
            dtype=np.int64,
        ),
    }


def collect_reference_arrays() -> dict[str, np.ndarray]:
    """Return deterministic arrays for both supported ROSS layouts."""
    return {**_run_case(4), **_run_case(6)}


def _sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def main() -> None:
    """Write the immutable v4 JSON/NPZ pair without overwriting files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError("Refusing to overwrite rotor/coupling reference v4")
    arrays = collect_reference_arrays()
    metadata = {
        "reference_name": "rotor_dof_coupling_reference_v4",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "python": sys.executable,
        "python_version": sys.version,
        "ross_version": rs.__version__,
        "platform": platform.platform(),
        "dt": DT,
        "step_count": STEP_COUNT,
        "speed_rad_s": SPEED_RAD_S,
        "observed_defects": [
            "six-DOF result_uxy and LQG mappings use four-DOF offsets",
        ],
        "target_contract": (
            "ROSS-provided local DOF layout and one exact rotor history row per "
            "committed coupling step"
        ),
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _sha256(value),
            }
            for name, value in sorted(arrays.items())
        },
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.npz, **arrays)
    args.json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.json)
    print(args.npz)
    print(f"arrays={len(arrays)}")


if __name__ == "__main__":
    main()
