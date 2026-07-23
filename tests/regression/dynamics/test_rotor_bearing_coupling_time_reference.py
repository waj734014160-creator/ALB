"""Exact regression for corrected rotor-bearing target-time semantics."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ALB.core import TimeIterDt
from ALB.dynamics.coupling import RsRotorBearingCouple
from tools.reference.generate_rotor_bearing_coupling_time_reference_v3 import (
    _ReferenceBearing,
    _ReferenceRotor,
)


ROOT = Path(__file__).resolve().parents[3]
REF_JSON = ROOT / "refs/rotor_bearing_coupling_time_reference_v3.json"
REF_NPZ = ROOT / "refs/rotor_bearing_coupling_time_reference_v3.npz"


def test_initial_snapshot_and_three_target_advances_match_v3_exactly():
    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    assert metadata["baseline_commit"] == "7b71d31232c675887929d60ea22427fa8d0dfe61"
    rotor = _ReferenceRotor()
    coupling = RsRotorBearingCouple(rotor, TimeIterDt(0.1, 3))
    coupling.add_bearing(_ReferenceBearing(), node_link=0)
    coupling.init()
    initial = coupling.output()

    with np.load(REF_NPZ, allow_pickle=False) as reference:
        np.testing.assert_array_equal(
            initial.values["rotor_displacement"],
            reference["corrected.initial_state"],
        )
        np.testing.assert_array_equal(
            [initial.metadata["time"]], reference["corrected.initial_time"]
        )

        coupling.solve()
        final = coupling.output()
        actual = {
            "corrected.input_times": np.asarray(rotor.input_times, dtype=float),
            "corrected.states": np.asarray(rotor.states, dtype=float),
            "corrected.final_metadata": np.asarray(
                [final.metadata["step_index"], final.metadata["time"]], dtype=float
            ),
        }
        for name, value in actual.items():
            np.testing.assert_array_equal(value, reference[name], err_msg=name)
        assert coupling.results["bearing0"].empty
