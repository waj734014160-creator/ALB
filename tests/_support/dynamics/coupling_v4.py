"""Exact replay helper for the corrected 4/6-DOF coupling reference."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np

from ALB.control import ALBLQGController
from ALB.core import TimeIterDt
from ALB.dynamics import RotorDofLayout, RsRotorBearingCouple
from ALB.dynamics.rotor import location_mapping_matrix
from tools.reference.generate_rotor_dof_coupling_reference_v4 import (
    DT,
    SPEED_RAD_S,
    STEP_COUNT,
    _StateDependentBearing,
    _build_ross_rotor,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "refs" / "rotor_dof_coupling_reference_v4.npz"
REFERENCE_METADATA = ROOT / "refs" / "rotor_dof_coupling_reference_v4.json"


@lru_cache(maxsize=1)
def replay_corrected_coupling_reference() -> dict[str, np.ndarray]:
    """Replay both ROSS layouts once and return their corrected arrays."""
    actual: dict[str, np.ndarray] = {}
    for dof_per_node in (4, 6):
        prefix = f"dof{dof_per_node}"
        rotor = _build_ross_rotor(dof_per_node)
        bearing = _StateDependentBearing(node_link=1)
        coupling = RsRotorBearingCouple(rotor, TimeIterDt(DT, STEP_COUNT))
        coupling.add_bearing(bearing, node_link=1)
        coupling.solve()

        layout = rotor.dof_layout
        locations = [(1, "x"), (1, "y"), (1, "alpha"), (1, "beta")]
        controller = ALBLQGController(
            rotor,
            dt=DT,
            freq=SPEED_RAD_S / (2.0 * np.pi),
            eso_enable=False,
        )
        controller.add_bearing(
            valve=None,
            K=np.zeros((2, 2)),
            C=np.zeros((2, 2)),
            dxv=np.zeros(2),
            act_node=1,
            sensor_node=0,
        )
        controller.add_unbalance_node(1)
        open_loop = controller.assemble_open_loop()

        actual.update(
            {
                f"{prefix}.times": np.asarray(rotor._t, dtype=float),
                f"{prefix}.corrected_xouts": np.asarray(
                    rotor._xouts, dtype=float
                ),
                f"{prefix}.corrected_youts": np.asarray(
                    rotor._youts, dtype=float
                ),
                f"{prefix}.final_state": np.asarray(
                    rotor.current_state(), dtype=float
                ),
                f"{prefix}.bearing_inputs": np.asarray(
                    bearing.input_history, dtype=float
                ),
                f"{prefix}.bearing_forces": np.asarray(
                    bearing.force_history, dtype=float
                ),
                f"{prefix}.nodal_force0": np.asarray(
                    rotor.nodal_force0, dtype=float
                ),
                f"{prefix}.nodal_force1": np.asarray(
                    rotor.nodal_force1, dtype=float
                ),
                f"{prefix}.global_force0": np.asarray(
                    rotor.global_force0, dtype=float
                ),
                f"{prefix}.global_force1": np.asarray(
                    rotor.global_force1, dtype=float
                ),
                f"{prefix}.result_uxy_expected": rotor.result_uxy(1),
                f"{prefix}.mapping_expected": location_mapping_matrix(
                    rotor._rotor.ndof,
                    locations,
                    layout=layout,
                ),
                f"{prefix}.layout": np.asarray(
                    [
                        layout.dof_per_node,
                        layout.x,
                        layout.y,
                        layout.alpha,
                        layout.beta,
                    ],
                    dtype=np.int64,
                ),
                f"{prefix}.lqg_T_act": location_mapping_matrix(
                    rotor._rotor.ndof,
                    [(1, "x"), (1, "y")],
                    layout=layout,
                ),
                f"{prefix}.lqg_H_sensor": location_mapping_matrix(
                    2 * rotor._rotor.ndof,
                    [(0, "x"), (0, "y")],
                    layout=layout,
                ).T,
                f"{prefix}.lqg_H_actuator": location_mapping_matrix(
                    2 * rotor._rotor.ndof,
                    [(1, "x"), (1, "y")],
                    layout=layout,
                ).T,
            }
        )
        actual[f"{prefix}.lqg_H_velocity"] = np.roll(
            actual[f"{prefix}.lqg_H_actuator"],
            rotor._rotor.ndof,
            axis=1,
        )
        lti = rotor._rotor._lti(SPEED_RAD_S)
        expected_b = np.hstack(
            [
                lti.B @ actual[f"{prefix}.lqg_T_act"],
                lti.B @ actual[f"{prefix}.lqg_T_act"],
            ]
        )
        expected_c = np.vstack(
            [
                actual[f"{prefix}.lqg_H_actuator"],
                actual[f"{prefix}.lqg_H_velocity"],
                actual[f"{prefix}.lqg_H_sensor"],
            ]
        )
        np.testing.assert_array_equal(open_loop.B, expected_b)
        np.testing.assert_array_equal(open_loop.C, expected_c)
        np.testing.assert_array_equal(
            open_loop.D,
            np.zeros((expected_c.shape[0], expected_b.shape[1])),
        )
        assert isinstance(layout, RotorDofLayout)
        assert len(rotor._t) == len(rotor._xouts) == len(rotor._youts) == STEP_COUNT
    return actual


def assert_corrected_coupling_reference_exact() -> None:
    """Require the current coupling implementation to equal the v4 targets."""
    actual = replay_corrected_coupling_reference()
    metadata = json.loads(REFERENCE_METADATA.read_text(encoding="utf-8"))
    assert metadata["reference_name"] == "rotor_dof_coupling_reference_v4"
    with np.load(REFERENCE) as reference:
        assert set(reference.files) == set(metadata["arrays"])
        for key in reference.files:
            stored = reference[key]
            assert list(stored.shape) == metadata["arrays"][key]["shape"]
            assert str(stored.dtype) == metadata["arrays"][key]["dtype"]
            assert (
                hashlib.sha256(np.ascontiguousarray(stored).tobytes()).hexdigest()
                == metadata["arrays"][key]["sha256"]
            )
        corrected_keys = {
            key
            for key in reference.files
            if not key.endswith(".result_uxy_observed_pre_fix")
            and not key.endswith(".mapping_locations")
            and not key.endswith(".coupling_table")
        }
        assert set(actual) == corrected_keys
        for key in sorted(corrected_keys):
            np.testing.assert_array_equal(actual[key], reference[key], err_msg=key)

        np.testing.assert_array_equal(
            reference["dof4.result_uxy_observed_pre_fix"],
            reference["dof4.result_uxy_expected"],
        )
        assert not np.array_equal(
            reference["dof6.result_uxy_observed_pre_fix"],
            reference["dof6.result_uxy_expected"],
        )
